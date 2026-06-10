import os
import requests
import pymongo
from datetime import datetime, timezone
from collections import Counter
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

MONGO_URI = os.environ.get("MONGO_URI")
DIGIKEY_CLIENT_ID = os.environ.get("DIGIKEY_CLIENT_ID")
DIGIKEY_CLIENT_SECRET = os.environ.get("DIGIKEY_CLIENT_SECRET")
MONGO_DB = "datasheet_hpe" 

# Initialize OpenAI client for generating embeddings
openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

def _get_db():
    """Returns Mongo database handle or None if not configured."""
    if not MONGO_URI:
        print("❌ MONGO_URI missing from .env file!")
        return None
    client = pymongo.MongoClient(MONGO_URI)
    return client[MONGO_DB]

# ========================================================================
# ENGINE A: MATH / MARKET DATABASE LOGIC (Existing)
# ========================================================================

def get_cached_pdf_extraction(pdf_sha256: str):
    """Returns previously extracted record for an identical PDF hash, if available."""
    db = _get_db()
    if db is None:
        return None
    col = db["pdf_extractions"]
    return col.find_one({"pdf_hash": pdf_sha256}, {"_id": 0})

def save_pdf_extraction(
    pdf_sha256: str,
    filename: str,
    detected_type: str,
    extracted_specs: dict,
):
    """Upserts final extracted specs by PDF hash so re-uploads become instant cache hits."""
    db = _get_db()
    if db is None:
        return
    col = db["pdf_extractions"]
    col.update_one(
        {"pdf_hash": pdf_sha256},
        {
            "$set": {
                "pdf_hash": pdf_sha256,
                "filename": filename,
                "detected_type": detected_type,
                "specs": extracted_specs,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "source": "upload_pipeline",
            }
        },
        upsert=True,
    )

def get_digikey_token_lazy():
    """Fetches a fresh token from the DigiKey OAuth endpoint."""
    resp = requests.post(
        "https://api.digikey.com/v1/oauth2/token",
        data={
            "client_id": DIGIKEY_CLIENT_ID,
            "client_secret": DIGIKEY_CLIENT_SECRET,
            "grant_type": "client_credentials",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    resp.raise_for_status()
    return resp.json()["access_token"]

def get_or_build_component_data(component_type):
    """
    100% Dynamic Schema Discovery.
    Queries DigiKey using the exact component type, calculates the 30% threshold,
    and returns ALL features the market deems standard without hardcoded filtering.
    """
    db = _get_db()
    if db is None:
        return None, None
    schema_col = db["feature_schemas"]
    
    # 1. CACHE CHECK
    cached_data = schema_col.find_one({"component_type": component_type})
    
    if cached_data and cached_data.get("features") and cached_data.get("competitors"):
        print(f"🧠 CACHE HIT! Loaded dynamic schema and competitors for '{component_type}'.")
        return cached_data["features"], cached_data["competitors"]
        
    # 2. CACHE MISS -> DIGIKEY API FALLBACK
    print(f"⚠️ CACHE MISS! '{component_type}' not found. Fetching from DigiKey...")
    
    try:
        token = get_digikey_token_lazy()

        resp = requests.post(
            "https://api.digikey.com/products/v4/search/keyword",
            headers={
                "X-DIGIKEY-Client-Id": DIGIKEY_CLIENT_ID,
                "Authorization": f"Bearer {token}",
                "X-DIGIKEY-Locale-Site": "US",
                "X-DIGIKEY-Locale-Language": "en",
                "X-DIGIKEY-Locale-Currency": "USD",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json={
                "Keywords": component_type, 
                "Limit": 20, 
                "Offset": 0,
                "FilterOptionsRequest": {"StatusFilter": [{"Id": 0}]}
            }
        )
        resp.raise_for_status()
        products = resp.json().get("Products", [])

        if not products:
            print(f"❌ DigiKey returned 0 products for '{component_type}'.")
            return None, None

        # 3. STATISTICAL SCHEMA LOGIC (30% Threshold)
        param_counter = Counter()
        competitors = []

        for p in products:
            name = str(p.get("ManufacturerProductNumber", "Unknown"))
            params_raw = p.get("Parameters", [])
            
            param_dict = {}
            for param in params_raw:
                k = param.get("ParameterText", "").strip()
                v = param.get("ValueText", "").strip()
                if k and v:
                    param_counter[k] += 1
                    param_dict[k] = v
            
            competitors.append({"part_number": name, "specs": param_dict})

        # Keep ALL features that appear in at least 30% of the market products
        min_count = max(1, len(products) * 0.3)
        dynamic_features = [name for name, cnt in param_counter.items() if cnt >= min_count]

        # 4. STORE IN MONGODB
        schema_col.update_one(
            {"component_type": component_type},
            {"$set": {
                "component_type": component_type,
                "features": dynamic_features, 
                "competitors": competitors, 
                "sampled_products": len(products),
                "stored_at": datetime.now(timezone.utc).isoformat(),
                "source": "digikey_api"
            }},
            upsert=True
        )
        
        print(f"💾 SAVED! Extracted {len(dynamic_features)} dynamic specs and {len(competitors)} competitors.")
        return dynamic_features, competitors

    except Exception as e:
        print(f"❌ DigiKey fetch failed: {e}")
        return None, None

import os
import json

# ========================================================================
# ENGINE B: RAG VECTOR DATABASE LOGIC (MongoDB Atlas Vector Search)
# ========================================================================

def has_rag_chunks(pdf_sha256: str) -> bool:
    """Checks if the chunks for this PDF are already stored in MongoDB."""
    db = _get_db()
    if db is None:
        return False
    col = db["pdf_chunks"]
    return col.find_one({"pdf_hash": pdf_sha256}) is not None

def store_rag_chunks(chunks: list, pdf_sha256: str):
    """
    Phase 2: Generates OpenAI embeddings and stores them in MongoDB Atlas.
    """
    db = _get_db()
    if db is None:
        print("❌ ERROR: MongoDB not configured.")
        return

    if not chunks:
        return

    col = db["pdf_chunks"]
    filename = chunks[0]["filename"]
    
    if has_rag_chunks(pdf_sha256):
        print(f"  ✅ Already ingested RAG chunks for {filename} — skipping")
        return

    print(f"\n📊 Generating embeddings and syncing to MongoDB for {filename}...")

    # We batch texts for OpenAI API
    texts = [c["text"] for c in chunks]
    all_embeddings = []
    
    batch_size = 256
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        try:
            resp = openai_client.embeddings.create(model="text-embedding-3-small", input=batch)
            all_embeddings.extend([r.embedding for r in resp.data])
        except Exception as e:
            print(f"⚠️ Error generating embeddings: {e}")
            return
            
    if len(all_embeddings) != len(chunks):
        print("❌ ERROR: Mismatch between chunks and embeddings.")
        return

    docs = []
    for chunk, emb in zip(chunks, all_embeddings):
        docs.append({
            "pdf_hash": pdf_sha256,
            "chunk_id": chunk["chunk_id"],
            "filename": chunk["filename"],
            "page": chunk["page"],
            "chunk_type": chunk.get("type", "text"),
            "text": chunk["text"],
            "embedding": emb,
            "ingested_at": datetime.now(timezone.utc).isoformat()
        })

    if docs:
        col.insert_many(docs)
        print(f"✅ Successfully stored {len(docs)} vectorized chunks in MongoDB.")


def retrieve_rag_context(query: str, filename: str, pdf_sha256: str = None, top_k: int = 15):
    """
    Phase 3: Performs a blazing fast Atlas Vector Search.
    """
    db = _get_db()
    if db is None:
        return []

    print(f"\n🔎 Executing MongoDB Vector Search for: '{query}'")
    col = db["pdf_chunks"]

    try:
        # 1. Embed the user's question
        response = openai_client.embeddings.create(
            input=query,
            model="text-embedding-3-small"
        )
        q_emb = response.data[0].embedding
        
        # 2. Resolve pdf_hash if missing natively through standard Mongo query
        if not pdf_sha256 and filename:
            doc = col.find_one({'filename': filename}, {'pdf_hash': 1})
            if doc:
                pdf_sha256 = doc.get('pdf_hash')

        # 3. Filter match using ONLY pdf_hash (to respect vector index requirements)
        match_filter = {}
        if pdf_sha256:
            match_filter = {'pdf_hash': pdf_sha256}

        # 4. Aggregation pipeline for Vector Search
        pipeline = [
            {
                '$vectorSearch': {
                    'index': 'vector_index',
                    'path': 'embedding',
                    'queryVector': q_emb,
                    'numCandidates': top_k * 10,
                    'limit': top_k,
                    'filter': match_filter
                }
            },
            {
                '$project': {
                    '_id': 0,
                    'text': 1,
                    'page': 1,
                    'type': '$chunk_type',
                    'chunk_id': 1,
                    'filename': 1,
                    'score': {'$meta': 'vectorSearchScore'}
                }
            }
        ]

        results = list(col.aggregate(pipeline))
        print(f"🎯 Diagnostic Result: Found {len(results)} highly relevant chunks.")
        return results

    except Exception as e:
        print(f"❌ MongoDB Vector Search failed: {e}")
        return []