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
import numpy as np

# ========================================================================
# ENGINE B: RAG VECTOR DATABASE LOGIC (FAISS - Local)
# ========================================================================

# We will save the FAISS index and the text metadata in your project folder
FAISS_INDEX_PATH = "local_faiss.index"
FAISS_META_PATH = "local_faiss_meta.json"

def store_rag_chunks(chunks: list):
    """
    Phase 2: Generates OpenAI embeddings and stores them in local FAISS.
    Uses a companion JSON file to store the actual text.
    """
    try:
        import faiss
    except ImportError:
        print("❌ ERROR: FAISS not installed. Run: pip install faiss-cpu numpy")
        return

    if not chunks:
        return

    filename = chunks[0]["filename"]
    print(f"\n📊 Generating embeddings and syncing to FAISS for {filename}...")

    # We use IndexFlatIP (Inner Product) which equals Cosine Similarity 
    # when the vectors are normalized (which OpenAI vectors are).
    dimension = 1536
    index = faiss.IndexFlatIP(dimension)
    metadata = {}
    embeddings_list = []

    for i, chunk in enumerate(chunks):
        try:
            # Generate OpenAI embedding
            response = openai_client.embeddings.create(
                input=chunk["text"],
                model="text-embedding-3-small"
            )
            embeddings_list.append(response.data[0].embedding)
            
            # Store the text and metadata in our dictionary
            metadata[str(i)] = {
                "chunk_id": chunk["chunk_id"],
                "filename": chunk["filename"],
                "page": chunk["page"],
                "type": chunk["type"],
                "text": chunk["text"]
            }
        except Exception as e:
            print(f"⚠️ Error generating embedding for chunk {chunk['chunk_id']}: {e}")

    if embeddings_list:
        # Convert list of embeddings to a float32 NumPy matrix (required by FAISS)
        embedding_matrix = np.array(embeddings_list).astype('float32')
        
        # Add to FAISS index
        index.add(embedding_matrix)
        
        # Save FAISS index to disk
        faiss.write_index(index, FAISS_INDEX_PATH)
        
        # Save Metadata to disk
        with open(FAISS_META_PATH, "w") as f:
            json.dump(metadata, f)
            
        print(f"✅ Successfully stored {len(embeddings_list)} vectorized chunks in FAISS.")


def retrieve_rag_context(query: str, filename: str, top_k: int = 15):
    """
    Phase 3: Performs a blazing fast local FAISS search.
    Maps the resulting vector IDs back to the JSON text chunks.
    """
    try:
        import faiss
    except ImportError:
        return []

    print(f"\n🔎 Executing Local FAISS Search for: '{query}'")

    if not os.path.exists(FAISS_INDEX_PATH) or not os.path.exists(FAISS_META_PATH):
        print("❌ FAISS index not found. Please upload a document first.")
        return []

    try:
        # 1. Load FAISS index and Metadata
        index = faiss.read_index(FAISS_INDEX_PATH)
        with open(FAISS_META_PATH, "r") as f:
            metadata = json.load(f)

        # 2. Embed the user's question
        response = openai_client.embeddings.create(
            input=query,
            model="text-embedding-3-small"
        )
        
        # Convert query to FAISS-compatible numpy array
        query_vector = np.array([response.data[0].embedding]).astype('float32')

        # 3. Search FAISS (returns distances and the integer IDs of the closest vectors)
        distances, indices = index.search(query_vector, top_k)

        formatted_results = []
        
        # 4. Map the integer IDs back to our text chunks
        for idx in indices[0]:
            idx_str = str(idx)
            if idx_str in metadata:
                chunk = metadata[idx_str]
                # Filter to make sure we only return text from the requested PDF
                if chunk["filename"] == filename:
                    formatted_results.append(chunk)
        
        print(f"🎯 Diagnostic Result: Found {len(formatted_results)} highly relevant chunks.")
        return formatted_results

    except Exception as e:
        print(f"❌ FAISS Vector Search failed: {e}")
        return []