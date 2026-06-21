import os
import requests
import pymongo
import hashlib
from datetime import datetime, timezone
from collections import Counter
from dotenv import load_dotenv
import uuid

# Load environment variables from local .env file
load_dotenv()

MONGO_URI = os.environ.get("MONGO_URI")
DIGIKEY_CLIENT_ID = os.environ.get("DIGIKEY_CLIENT_ID")
DIGIKEY_CLIENT_SECRET = os.environ.get("DIGIKEY_CLIENT_SECRET")
MONGO_DB = "datasheet_hpe" 

LLM_SERVER_URL = os.environ.get("LLM_SERVER_URL", "http://127.0.0.1:8086")

def _get_db():
    if not MONGO_URI:
        print("❌ MONGO_URI missing from .env file!")
        return None
    client = pymongo.MongoClient(MONGO_URI)
    return client[MONGO_DB]

# ========================================================================
# ENGINE 0: USER MANAGEMENT
# ========================================================================

def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def register_user(username, password):
    db = _get_db()
    if db is None: return False, "Database not connected"
    col = db["users"]
    if col.find_one({"username": username}):
        return False, "Username already exists"
    col.insert_one({"username": username, "password": _hash_password(password)})
    return True, "Registered successfully"

def login_user(username, password):
    db = _get_db()
    if db is None: return None, "Database not connected"
    col = db["users"]
    user = col.find_one({"username": username, "password": _hash_password(password)})
    if user:
        return str(user["_id"]), "Login successful"
    return None, "Invalid username or password"

def add_user_pdf(user_id, pdf_hash, filename):
    db = _get_db()
    if db is None: return
    col = db["user_pdfs"]
    col.update_one(
        {"user_id": user_id, "pdf_hash": pdf_hash},
        {"$set": {"user_id": user_id, "pdf_hash": pdf_hash, "filename": filename, "uploaded_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True
    )

def get_user_pdfs(user_id):
    db = _get_db()
    if db is None: return []
    col = db["user_pdfs"]
    # Return list of PDFs belonging to the user
    return list(col.find({"user_id": user_id}, {"_id": 0}).sort("uploaded_at", -1))

def get_user_pdf_hashes(user_id):
    db = _get_db()
    if db is None: return []
    return [doc["pdf_hash"] for doc in list(db["user_pdfs"].find({"user_id": user_id}, {"pdf_hash": 1}))]


# ========================================================================
# ENGINE 0.5: CHAT SESSION MANAGEMENT
# ========================================================================

def create_chat_session(user_id: str, session_name: str = "New Workspace"):
    """Creates a fresh, isolated chat session for the user."""
    db = _get_db()
    if db is None: return None
    
    session_id = f"session_{uuid.uuid4().hex[:16]}"
    session_doc = {
        "session_id": session_id,
        "user_id": user_id,
        "session_name": session_name,
        "attached_pdfs": [], 
        "messages": [],       
        "is_pinned": False, 
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    db["chat_sessions"].insert_one(session_doc)
    return session_id

def get_user_sessions(user_id: str):
    """Retrieves all chat sessions, sorting pinned ones to the top."""
    db = _get_db()
    if db is None: return []
    col = db["chat_sessions"]
    return list(col.find({"user_id": user_id}, {"_id": 0}).sort([("is_pinned", -1), ("updated_at", -1)]))

def attach_pdf_to_session(session_id: str, pdf_hash: str):
    """Links an uploaded datasheet to a specific workspace."""
    db = _get_db()
    if db is None: return False
    
    result = db["chat_sessions"].update_one(
        {"session_id": session_id},
        {
            "$addToSet": {"attached_pdfs": pdf_hash}, # $addToSet prevents duplicates
            "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}
        }
    )
    return result.modified_count > 0

def get_session_data(session_id: str):
    """Pulls the current state of a workspace (attached PDFs and memory)."""
    db = _get_db()
    if db is None: return None
    return db["chat_sessions"].find_one({"session_id": session_id}, {"_id": 0})

def save_session_messages(session_id: str, new_messages: list):
    """Appends new user/assistant messages to the database memory."""
    db = _get_db()
    if db is None: return
    
    db["chat_sessions"].update_one(
        {"session_id": session_id},
        {
            "$push": {"messages": {"$each": new_messages}},
            "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}
        }
    )

def delete_chat_session(session_id: str):
    """Permanently deletes a workspace."""
    db = _get_db()
    if db is None: return False
    result = db["chat_sessions"].delete_one({"session_id": session_id})
    return result.deleted_count > 0

def rename_chat_session(session_id: str, new_name: str):
    """Renames a workspace and updates its timestamp."""
    db = _get_db()
    if db is None: return False
    
    from datetime import datetime, timezone # Ensure this is imported if not already
    result = db["chat_sessions"].update_one(
        {"session_id": session_id},
        {"$set": {
            "session_name": new_name,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    return result.modified_count > 0

def toggle_pin_session(session_id: str):
    """Toggles the pin status of a workspace."""
    db = _get_db()
    if db is None: return False
    session = db["chat_sessions"].find_one({"session_id": session_id})
    if not session: return False
    
    new_status = not session.get("is_pinned", False)
    result = db["chat_sessions"].update_one(
        {"session_id": session_id},
        {"$set": {"is_pinned": new_status}}
    )
    return result.modified_count > 0

# ========================================================================
# ENGINE A: MATH / MARKET DATABASE LOGIC 
# ========================================================================

def get_cached_pdf_extraction(pdf_sha256: str):
    db = _get_db()
    if db is None: return None
    col = db["pdf_extractions"]
    return col.find_one({"pdf_hash": pdf_sha256}, {"_id": 0})

def save_pdf_extraction(pdf_sha256: str, filename: str, detected_type: str, extracted_specs: dict):
    db = _get_db()
    if db is None: return
    col = db["pdf_extractions"]
    col.update_one(
        {"pdf_hash": pdf_sha256},
        {"$set": {
            "pdf_hash": pdf_sha256,
            "filename": filename,
            "detected_type": detected_type,
            "specs": extracted_specs,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "source": "upload_pipeline",
        }},
        upsert=True,
    )

def get_digikey_token_lazy():
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
    db = _get_db()
    if db is None: return None, None
    schema_col = db["feature_schemas"]
    
    cached_data = schema_col.find_one({"component_type": component_type})
    if cached_data and cached_data.get("features") and cached_data.get("competitors"):
        print(f"🧠 CACHE HIT! Loaded dynamic schema and competitors for '{component_type}'.")
        return cached_data["features"], cached_data["competitors"]
        
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

        if not products: return None, None

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

        min_count = max(1, len(products) * 0.3)
        dynamic_features = [name for name, cnt in param_counter.items() if cnt >= min_count]

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
        return dynamic_features, competitors

    except Exception as e:
        print(f"❌ DigiKey fetch failed: {e}")
        return None, None

# ========================================================================
# ENGINE B: RAG VECTOR DATABASE LOGIC
# ========================================================================

def has_rag_chunks(pdf_sha256: str) -> bool:
    db = _get_db()
    if db is None: return False
    col = db["pdf_chunks"]
    return col.find_one({"pdf_hash": pdf_sha256}) is not None

def store_rag_chunks(chunks: list, pdf_sha256: str):
    db = _get_db()
    if db is None: return
    if not chunks: return

    col = db["pdf_chunks"]
    filename = chunks[0]["filename"]
    
    if has_rag_chunks(pdf_sha256):
        return

    texts = [c["text"] for c in chunks]
    all_embeddings = []
    
    batch_size = 256
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        try:
            res = requests.post(
                f"{LLM_SERVER_URL}/api/llm/embeddings",
                json={"input_data": batch, "model": "text-embedding-3-small"}
            )
            res.raise_for_status()
            all_embeddings.extend(res.json()["embeddings"])
        except Exception as e:
            print(f"❌ Failed to get embeddings: {e}")
            return
            
    if len(all_embeddings) != len(chunks): return

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

def retrieve_rag_context(query: str, filename: str = None, pdf_sha256 = None, top_k: int = 15):
    db = _get_db()
    if db is None: return []

    col = db["pdf_chunks"]

    try:
        res = requests.post(
            f"{LLM_SERVER_URL}/api/llm/embeddings",
            json={"input_data": query, "model": "text-embedding-3-small"}
        )
        res.raise_for_status()
        q_emb = res.json()["embeddings"]
        
        if not pdf_sha256 and filename:
            doc = col.find_one({'filename': filename}, {'pdf_hash': 1})
            if doc:
                pdf_sha256 = doc.get('pdf_hash')

        # TWO-STAGE APPROACH: $vectorSearch (broad) → $match (filter by hash)
        # This avoids the need for pdf_hash to be declared as 'filterable' in the
        # Atlas vector index definition, which is the root cause of global search
        # only returning chunks from a subset of documents.
        
        # If filtering, fetch a much larger pool so all documents have representation
        fetch_limit = top_k
        if pdf_sha256:
            if isinstance(pdf_sha256, list):
                # Global search: fetch more to ensure all user documents are represented
                fetch_limit = top_k * len(pdf_sha256) * 3
            else:
                fetch_limit = top_k * 5

        pipeline = [
            {
                '$vectorSearch': {
                    'index': 'vector_index',
                    'path': 'embedding',
                    'queryVector': q_emb,
                    'numCandidates': fetch_limit * 10,
                    'limit': fetch_limit
                }
            },
            {
                '$project': {
                    '_id': 0, 'text': 1, 'page': 1, 'type': '$chunk_type', 
                    'chunk_id': 1, 'filename': 1, 'pdf_hash': 1,
                    'score': {'$meta': 'vectorSearchScore'}
                }
            }
        ]

        # Stage 2: Filter by pdf_hash AFTER vector search
        if isinstance(pdf_sha256, list):
            pipeline.append({'$match': {'pdf_hash': {'$in': pdf_sha256}}})
        elif pdf_sha256:
            pipeline.append({'$match': {'pdf_hash': pdf_sha256}})

        # Stage 3: Limit to the desired top_k after filtering
        pipeline.append({'$limit': top_k})

        results = list(col.aggregate(pipeline))
        
        # Diagnostic: log which documents contributed chunks
        if pdf_sha256 and isinstance(pdf_sha256, list):
            doc_counts = {}
            for r in results:
                fn = r.get('filename', 'unknown')
                doc_counts[fn] = doc_counts.get(fn, 0) + 1
            print(f"📊 [GLOBAL SEARCH] Chunk distribution across documents: {doc_counts}")

        return results

    except Exception as e:
        print(f"❌ MongoDB Vector Search failed: {e}")
        return []