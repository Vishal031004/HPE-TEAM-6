import os
import requests
from fastapi import FastAPI, UploadFile, File, Query, BackgroundTasks, Form
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import List
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

from core.pdf_processor import detect_component_type, pdf_hash, process_pdf_for_rag
from core.database import (
    get_or_build_component_data, get_cached_pdf_extraction, save_pdf_extraction,
    register_user, login_user, add_user_pdf, get_user_pdfs, get_user_pdf_hashes,
    store_rag_chunks, retrieve_rag_context, has_rag_chunks,
    get_digikey_token_lazy, DIGIKEY_CLIENT_ID
)
from core.extractor import parse_datasheet_staged, rerank_chunks_cross_encoder, answer_rag_question, reformulate_query
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
    is_global: bool = False
    chat_history: list = []

class PricingRequest(BaseModel):
    part_numbers: List[str]

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
    force: bool = Query(False)
):
    os.makedirs("datasheets", exist_ok=True)
    file_path = os.path.join("datasheets", file.filename)
    
    with open(file_path, "wb") as f:
        f.write(await file.read())
        
    pdf_sha = pdf_hash(file_path)

    if user_id:
        add_user_pdf(user_id, pdf_sha, file.filename)
    
    if not force:
        cached_record = get_cached_pdf_extraction(pdf_sha)
        if cached_record:
            background_tasks.add_task(_run_rag_ingestion, file_path, file.filename, pdf_sha)
            return {
                "pdf_hash": pdf_sha,
                "detected_type": cached_record.get("detected_type", "Unknown"),
                "specs": cached_record.get("specs", {}),
                "cache_hit": True,
            }

    detected_type = detect_component_type(file_path)
    if detected_type == "Unknown":
        return {"error": "Could not detect component type. Please upload a clear datasheet."}
        
    target_specs, market_competitors = get_or_build_component_data(detected_type)
    if not target_specs or not market_competitors:
        return {"error": "Failed to generate market schema from DigiKey."}
        
    user_extracted_specs = parse_datasheet_staged(
        filepath=file_path, component_type=detected_type, required_features=target_specs,
        market_competitors=market_competitors, component_name=file.filename, chunk_size=15
    )

    save_pdf_extraction(pdf_sha, file.filename, detected_type, user_extracted_specs)
    background_tasks.add_task(_run_rag_ingestion, file_path, file.filename, pdf_sha)
    
    return {"pdf_hash": pdf_sha, "detected_type": detected_type, "specs": user_extracted_specs, "cache_hit": False}

@app.post("/api/rank")
async def rank_alternatives(request: RankRequest):
    _, market_competitors = get_or_build_component_data(request.detected_type)
    top_5 = rank_components(request.extracted_specs, market_competitors, request.weights)
    return {"results": top_5}

@app.post("/api/chat")
async def chat_with_datasheet(request: ChatRequest):
    search_query = request.question
    if request.chat_history:
        search_query = reformulate_query(request.question, request.chat_history)

    target_hashes = None

    # Handle Global vs Single PDF Search
    if request.is_global and request.user_id:
        target_hashes = get_user_pdf_hashes(request.user_id) # Returns a list of hashes
    elif request.filename:
        file_path = os.path.join("datasheets", request.filename)
        if os.path.exists(file_path):
            target_hashes = pdf_hash(file_path) # Returns single string

    raw_chunks = retrieve_rag_context(search_query, request.filename, pdf_sha256=target_hashes, top_k=35)
    
    if not raw_chunks:
        return {"answer": "I couldn't find any relevant text in the database to answer that question."}
    
    ranked_chunks = rerank_chunks_cross_encoder(search_query, raw_chunks, top_k=5)
    answer = answer_rag_question(request.question, ranked_chunks, request.chat_history, is_global=request.is_global)
    
    return {"answer": answer}

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