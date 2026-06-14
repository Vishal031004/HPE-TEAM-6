import os
import json
from fastapi import FastAPI, UploadFile, File, Query, BackgroundTasks
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

# ========================================================================
# IMPORT DUAL-ENGINE PIPELINE
# ========================================================================

# Engine A: Math/Market Extraction
from core.pdf_processor import detect_component_type, pdf_hash
from core.database import (
    get_or_build_component_data,
    get_cached_pdf_extraction,
    save_pdf_extraction,
)
from core.extractor import parse_datasheet_staged
from core.similarity import rank_components

# Engine B: Advanced RAG
from core.pdf_processor import process_pdf_for_rag, pdf_hash
from core.database import store_rag_chunks, retrieve_rag_context, has_rag_chunks
from core.extractor import rerank_chunks_cross_encoder, answer_rag_question, reformulate_query
app = FastAPI()

# Expected JSON format for the ranking endpoint
class RankRequest(BaseModel):
    detected_type: str
    extracted_specs: dict
    weights: dict

# Expected JSON format for the chat endpoint
class ChatRequest(BaseModel):
    question: str
    filename: str
    chat_history: list = []

# ========================================================================
# BACKGROUND RAG INGESTION (runs after response is sent)
# ========================================================================

def _run_rag_ingestion(file_path: str, filename: str, pdf_sha: str):
    """Background task: chunks, embeds, and stores vectors for the RAG chatbot."""
    print("\n--- [BACKGROUND] TRIGGERING RAG INGESTION PIPELINE ---")
    try:
        if not has_rag_chunks(pdf_sha):
            rag_chunks = process_pdf_for_rag(file_path, filename)
            if rag_chunks:
                store_rag_chunks(rag_chunks, pdf_sha)
                print(f"--- [BACKGROUND] RAG ingestion complete for {filename} ---")
            else:
                print(f"--- [BACKGROUND] No chunks generated for {filename} ---")
        else:
            print(f"--- [BACKGROUND] RAG chunks already exist for {filename} ---")
    except Exception as e:
        print(f"--- [BACKGROUND] RAG ingestion failed: {e} ---")

@app.get("/")
async def serve_frontend():
    """Serves your index.html frontend."""
    with open("static/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read(), status_code=200)

@app.post("/api/upload")
async def upload_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    force: bool = Query(False, description="Skip cache and force re-extraction"),
):
    """STEP 1: Upload -> Execute Math Engine. RAG ingestion runs in background."""
    os.makedirs("datasheets", exist_ok=True)
    file_path = os.path.join("datasheets", file.filename)
    
    # Save the uploaded file
    with open(file_path, "wb") as f:
        f.write(await file.read())
        
    # Stage 0: PDF hash cache check
    pdf_sha = pdf_hash(file_path)
    
    # Check cache (skip if force=true)
    if not force:
        cached_record = get_cached_pdf_extraction(pdf_sha)
        if cached_record:
            print(f"🧠 PDF CACHE HIT for {file.filename} ({pdf_sha[:12]}...)")
            
            # Schedule RAG ingestion in background (non-blocking)
            background_tasks.add_task(_run_rag_ingestion, file_path, file.filename, pdf_sha)
                
            return {
                "detected_type": cached_record.get("detected_type", "Unknown"),
                "specs": cached_record.get("specs", {}),
                "cache_hit": True,
            }
    else:
        print(f"⚡ FORCE RE-EXTRACTION for {file.filename} (cache bypassed)")

    # --- Execute Math Engine Pipeline on Cache Miss ---
    
    # ENGINE A: MATH EXTRACTION
    # Stage 1: Detect Component
    detected_type = detect_component_type(file_path)
    if detected_type == "Unknown":
        return {"error": "Could not detect component type. Please upload a clear datasheet."}
        
    # Stage 2: Cache & Schema Intelligence (DigiKey)
    target_specs, market_competitors = get_or_build_component_data(detected_type)
    if not target_specs or not market_competitors:
        return {"error": "Failed to generate market schema from DigiKey."}
        
    # Stage 3/4/5: Sliding-window staged extraction
    user_extracted_specs = parse_datasheet_staged(
        filepath=file_path,
        component_type=detected_type,
        required_features=target_specs,
        market_competitors=market_competitors,
        component_name=file.filename,
        chunk_size=15,
    )

    save_pdf_extraction(
        pdf_sha256=pdf_sha,
        filename=file.filename,
        detected_type=detected_type,
        extracted_specs=user_extracted_specs,
    )

    # Schedule RAG ingestion in background (non-blocking)
    background_tasks.add_task(_run_rag_ingestion, file_path, file.filename, pdf_sha)
    
    return {
        "detected_type": detected_type,
        "specs": user_extracted_specs,
        "cache_hit": False,
    }

@app.post("/api/rank")
async def rank_alternatives(request: RankRequest):
    """STEP 2: Executes the Math Engine to find the Top 5 alternatives."""
    # Quickly grab the competitors we cached in Step 1
    _, market_competitors = get_or_build_component_data(request.detected_type)
    
    # Stage 5: Weighted Similarity Math Engine
    top_5 = rank_components(
        user_extracted_specs=request.extracted_specs, 
        digikey_competitors=market_competitors, 
        feature_weights=request.weights
    )
    
    return {"results": top_5}

@app.post("/api/chat")
async def chat_with_datasheet(request: ChatRequest):
    """Executes the Advanced RAG Pipeline (Hybrid Search + Cross-Encoder Re-Ranking)."""
    
    # 0. Contextual Query Reformulation (Fixes Vector Search Amnesia)
    search_query = request.question
    if request.chat_history:
        search_query = reformulate_query(request.question, request.chat_history)
        print(f"\n🔄 Original Query: '{request.question}'")
        print(f"🎯 Reformulated for Vector Search: '{search_query}'")

    file_path = os.path.join("datasheets", request.filename)
    if os.path.exists(file_path):
        pdf_sha = pdf_hash(file_path)
    else:
        pdf_sha = None

    # 1. Execute DB Vector Search using the REFORMULATED query
    raw_chunks = retrieve_rag_context(search_query, request.filename, pdf_sha256=pdf_sha, top_k=35)
    
    if not raw_chunks:
        return {"answer": "I couldn't find any relevant text in the database to answer that question."}
    
    # 2. Local Cross-Encoder Re-Ranking
    ranked_chunks = rerank_chunks_cross_encoder(search_query, raw_chunks, top_k=5)
    
    # 3. Agentic Grounded Generation
    # We pass the ORIGINAL question to the final LLM so the conversation feels natural
    answer = answer_rag_question(request.question, ranked_chunks, request.chat_history)
    
    return {"answer": answer}