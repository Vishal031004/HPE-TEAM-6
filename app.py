import os
import requests
from fastapi import FastAPI, UploadFile, File, Query, BackgroundTasks, Form
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
from typing import List
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

from core.pdf_processor import detect_component_type, pdf_hash, process_pdf_for_rag
from core.database import (
    get_or_build_component_data, get_cached_pdf_extraction, save_pdf_extraction,
    register_user, login_user, add_user_pdf, get_user_pdfs, get_user_pdf_hashes,
    store_rag_chunks, retrieve_rag_context, has_rag_chunks,
    get_digikey_token_lazy, DIGIKEY_CLIENT_ID,
    create_chat_session, get_user_sessions, attach_pdf_to_session, get_session_data, save_session_messages, delete_chat_session, toggle_pin_session, rename_chat_session
)
from core.extractor import parse_datasheet_staged, rerank_chunks_cross_encoder, answer_rag_question, reformulate_query, route_user_intent
from core.similarity import rank_components

app = FastAPI()

class AuthRequest(BaseModel):
    username: str
    password: str

class RankRequest(BaseModel):
    detected_type: str
    extracted_specs: dict
    weights: dict

class ChatRequest(BaseModel):
    question: str
    filename: str = ""
    user_id: str = None
    session_id: str = None  
    is_global: bool = False
    chat_history: list = []

class PricingRequest(BaseModel):
    part_numbers: List[str]

class SessionCreateRequest(BaseModel):
    user_id: str
    session_name: str

class AttachPdfRequest(BaseModel):
    session_id: str
    pdf_hash: str

class SaveMessagesRequest(BaseModel):
    session_id: str
    new_messages: list

class RenameRequest(BaseModel):
    new_name: str

def _run_rag_ingestion(file_path: str, filename: str, pdf_sha: str):
    try:
        if not has_rag_chunks(pdf_sha):
            rag_chunks = process_pdf_for_rag(file_path, filename)
            if rag_chunks:
                store_rag_chunks(rag_chunks, pdf_sha)
    except Exception as e:
        print(f"--- [BACKGROUND] RAG ingestion failed: {e} ---")

@app.get("/")
async def serve_frontend():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read(), status_code=200)

@app.post("/api/register")
async def register(request: AuthRequest):
    success, msg = register_user(request.username, request.password)
    return {"message": msg} if success else {"error": msg}

@app.post("/api/login")
async def login(request: AuthRequest):
    user_id, msg = login_user(request.username, request.password)
    return {"user_id": user_id, "message": msg} if user_id else {"error": msg}

@app.get("/api/user/{user_id}/pdfs")
async def get_user_uploaded_pdfs(user_id: str):
    return {"pdfs": get_user_pdfs(user_id)}

@app.get("/api/extraction/{pdf_hash}")
async def get_extraction(pdf_hash: str):
    """Fetches previously extracted data so users don't have to re-extract when clicking from dashboard."""
    record = get_cached_pdf_extraction(pdf_hash)
    if record:
        return {
            "detected_type": record.get("detected_type", "Unknown"),
            "specs": record.get("specs", {}),
            "filename": record.get("filename")
        }
    return {"error": "Extraction not found. Document may need re-processing."}

@app.post("/api/upload")
async def upload_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user_id: str = Form(None),
    session_id: str = Form(None) # Added support for the new sessions!
):
    """LAZY UPLOAD: Only saves the file, generates the hash, and triggers background RAG."""
    os.makedirs("datasheets", exist_ok=True)
    file_path = os.path.join("datasheets", file.filename)
    
    with open(file_path, "wb") as f:
        f.write(await file.read())
        
    pdf_sha = pdf_hash(file_path)

    # 1. Attach to user library
    if user_id:
        add_user_pdf(user_id, pdf_sha, file.filename)
        
    # 2. Attach to specific active workspace/session
    if session_id:
        attach_pdf_to_session(session_id, pdf_sha)

    # 3. Spin up Vectorization in the background (Non-blocking!)
    background_tasks.add_task(_run_rag_ingestion, file_path, file.filename, pdf_sha)
    
    # 4. Return immediately. No math engine!
    return {
        "pdf_hash": pdf_sha, 
        "filename": file.filename,
        "message": "PDF uploaded successfully and is being vectorized for chat."
    }

@app.post("/api/rank")
async def rank_alternatives(request: RankRequest):
    _, market_competitors = get_or_build_component_data(request.detected_type)
    top_5 = rank_components(request.extracted_specs, market_competitors, request.weights)
    return {"results": top_5}

@app.post("/api/chat")
async def chat_with_datasheet(request: ChatRequest):
    
    # 1. Intent Routing
    intent = route_user_intent(request.question, request.chat_history)
    print(f"\n🧠 [AGENT ROUTER] Detected Intent: {intent.upper()}")

    # ==========================================
    # PATH A: THE MARKET ANALYSIS ENGINE
    # ==========================================
    if intent == "find_alternatives":
        if not request.filename:
            return {"answer": "Please specify which component you want me to find alternatives for."}
            
        file_path = os.path.join("datasheets", request.filename)
        if not os.path.exists(file_path):
            return {"answer": "I cannot access the file to run the market analysis."}

        # We need the hash to check the database cache
        pdf_sha = pdf_hash(file_path)
        
        # 🚨 RESTORED CACHING LOGIC
        cached_record = get_cached_pdf_extraction(pdf_sha)
        
        if cached_record and cached_record.get("specs"):
            print(f"🧠 CACHE HIT! Loading previously extracted specs for {request.filename}")
            detected_type = cached_record.get("detected_type", "Unknown")
            user_extracted_specs = cached_record.get("specs")
        else:
            print(f"⚠️ CACHE MISS! Running heavy LLM extraction for {request.filename}...")
            
            detected_type = detect_component_type(file_path)
            if detected_type == "Unknown":
                return {"answer": "I could not detect the specific component category needed to query the market."}
                
            target_specs, market_competitors = get_or_build_component_data(detected_type)
            
            user_extracted_specs = parse_datasheet_staged(
                filepath=file_path, component_type=detected_type, required_features=target_specs,
                market_competitors=market_competitors, component_name=request.filename, chunk_size=15
            )
            
            # Save to database so we never have to extract this specific PDF again
            save_pdf_extraction(pdf_sha, request.filename, detected_type, user_extracted_specs)

        return {
            "type": "interactive_ranking",
            "detected_type": detected_type,
            "extracted_specs": user_extracted_specs,
            "answer": f"I extracted the specs for **{request.filename}**. Adjust your parametric weights below, and click 'Run Math Engine' to fetch live market alternatives."
        }
    
    # ==========================================
    # PATH B: STANDARD ADVANCED RAG
    # ==========================================
    search_query = request.question
    if request.chat_history:
        search_query = reformulate_query(request.question, request.chat_history)

    target_hashes = None

    if request.is_global and request.session_id:
        session_data = get_session_data(request.session_id)
        if session_data and session_data.get("attached_pdfs"):
            target_hashes = session_data["attached_pdfs"]
    elif request.filename:
        file_path = os.path.join("datasheets", request.filename)
        if os.path.exists(file_path):
            target_hashes = pdf_hash(file_path)

    raw_chunks = retrieve_rag_context(search_query, request.filename, pdf_sha256=target_hashes, top_k=35)
    
    if not raw_chunks:
        return {"answer": "I couldn't find any relevant text in the database to answer that question."}
    
    ranked_chunks = rerank_chunks_cross_encoder(search_query, raw_chunks, top_k=5)
    answer = answer_rag_question(request.question, ranked_chunks, request.chat_history, is_global=request.is_global)
    
    return {"answer": answer}

@app.post("/api/sessions")
async def create_session(request: SessionCreateRequest):
    session_id = create_chat_session(request.user_id, request.session_name)
    if session_id:
        return {"session_id": session_id}
    return {"error": "Failed to create session"}

@app.get("/api/user/{user_id}/sessions")
async def get_sessions(user_id: str):
    return {"sessions": get_user_sessions(user_id)}

@app.post("/api/sessions/attach")
async def attach_pdf(request: AttachPdfRequest):
    success = attach_pdf_to_session(request.session_id, request.pdf_hash)
    if success:
        return {"message": "PDF successfully attached to workspace"}
    return {"error": "Failed to attach PDF. Session may not exist."}

# ========================================================================
# 🚨 CRITICAL FIX: The specific POST route is now BEFORE the dynamic GET route!
# ========================================================================
@app.post("/api/sessions/save_messages")
async def save_messages(request: SaveMessagesRequest):
    save_session_messages(request.session_id, request.new_messages)
    return {"status": "success"}

@app.get("/api/sessions/{session_id}")
async def fetch_session(session_id: str):
    data = get_session_data(session_id)
    if not data:
        return {"error": "Session not found"}
        
    # Cross-reference hashes with the user's PDF library to get actual filenames
    user_pdfs = get_user_pdfs(data.get("user_id", ""))
    hash_to_name = {p["pdf_hash"]: p["filename"] for p in user_pdfs} if user_pdfs else {}
    
    enriched_pdfs = []
    for pdf_hash in data.get("attached_pdfs", []):
        filename = hash_to_name.get(pdf_hash, "Datasheet.pdf")
        enriched_pdfs.append({"hash": pdf_hash, "filename": filename})
        
    data["attached_pdfs"] = enriched_pdfs
    return data

@app.get("/api/datasheets/{filename}")
async def get_datasheet(filename: str):
    file_path = os.path.join("datasheets", filename)
    if os.path.exists(file_path):
        return FileResponse(file_path)
    return {"error": "File not found"}

@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str):
    success = delete_chat_session(session_id)
    if success:
        return {"status": "success"}
    return {"error": "Failed to delete session"}

@app.patch("/api/sessions/{session_id}/pin")
async def pin_session(session_id: str):
    success = toggle_pin_session(session_id)
    if success:
        return {"status": "success"}
    return {"error": "Failed to toggle pin"}

@app.patch("/api/sessions/{session_id}/rename")
async def rename_session(session_id: str, request: RenameRequest):
    success = rename_chat_session(session_id, request.new_name)
    if success:
        return {"status": "success"}
    return {"error": "Failed to rename session"}

# ========================================================================
# LIVE PRICING & STOCK (Never cached — always real-time from DigiKey)
# ========================================================================

def _fetch_digikey_pricing(part_number: str) -> dict:
    """Fetches live stock and price for a single part number from DigiKey.
    Returns {part_number, stock, price, currency} or error info.
    Does NOT write to database."""
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
            json={"Keywords": part_number, "Limit": 1, "Offset": 0},
            timeout=10
        )
        resp.raise_for_status()
        products = resp.json().get("Products", [])

        if not products:
            return {"part_number": part_number, "stock": None, "price": None, "currency": "USD", "error": "Not found on DigiKey"}

        product = products[0]
        stock = product.get("QuantityAvailable", 0)

        # Extract the HIGHEST unit price across all variations and price breaks
        all_prices = []
        variations = product.get("ProductVariations", [])
        for var in variations:
            pricing = var.get("StandardPricing", [])
            for pb in pricing:
                up = pb.get("UnitPrice")
                if up is not None:
                    all_prices.append(up)
        
        # Fallback: check top-level UnitPrice if variations didn't have it
        if not all_prices and product.get("UnitPrice") is not None:
            all_prices.append(product.get("UnitPrice"))
            
        price = max(all_prices) if all_prices else None

        # Extract datasheet URL — DigiKey v4 uses 'DatasheetUrl', older versions use 'PrimaryDatasheet'
        datasheet_url = product.get("DatasheetUrl") or product.get("PrimaryDatasheet") or ""
        digikey_url = product.get("ProductUrl", "")
        # DigiKey sometimes returns relative URLs
        if digikey_url and not digikey_url.startswith("http"):
            digikey_url = f"https://www.digikey.com{digikey_url}"

        print(f"📎 [PRICING] {part_number}: price=${price}, stock={stock}, datasheet={datasheet_url[:80] if datasheet_url else 'NONE'}")

        return {
            "part_number": part_number,
            "stock": stock,
            "price": price,
            "currency": "USD",
            "datasheet_url": datasheet_url,
            "digikey_url": digikey_url
        }

    except Exception as e:
        print(f"⚠️ Pricing fetch failed for {part_number}: {e}")
        return {"part_number": part_number, "stock": None, "price": None, "currency": "USD", "datasheet_url": "", "digikey_url": "", "error": str(e)}

@app.post("/api/pricing")
async def get_live_pricing(request: PricingRequest):
    """Fetches real-time stock and price from DigiKey for a list of part numbers.
    Never cached — always live. Does not write to database."""
    results = {}
    for mpn in request.part_numbers:
        results[mpn] = _fetch_digikey_pricing(mpn)
    return {"pricing": results}