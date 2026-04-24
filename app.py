import os
import json
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

# Import the Enterprise Pipeline!
from core.pdf_processor import detect_component_type, pdf_hash
from core.database import (
    get_or_build_component_data,
    get_cached_pdf_extraction,
    save_pdf_extraction,
)
from core.extractor import parse_datasheet_staged
from core.similarity import rank_components

app = FastAPI()

# Expected JSON format for the ranking endpoint
class RankRequest(BaseModel):
    detected_type: str
    extracted_specs: dict
    weights: dict

@app.get("/")
async def serve_frontend():
    """Serves your index.html frontend."""
    with open("static/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read(), status_code=200)

@app.post("/api/upload")
async def upload_pdf(file: UploadFile = File(...)):
    """STEP 1: Upload -> PDF hash cache check -> staged extraction on cache miss."""
    os.makedirs("datasheets", exist_ok=True)
    file_path = os.path.join("datasheets", file.filename)
    
    # Save the uploaded file
    with open(file_path, "wb") as f:
        f.write(await file.read())
        
    # Stage 0: PDF hash cache check (same file bytes => skip extraction)
    pdf_sha = pdf_hash(file_path)
    cached_record = get_cached_pdf_extraction(pdf_sha)
    if cached_record:
        print(f"🧠 PDF CACHE HIT for {file.filename} ({pdf_sha[:12]}...)")
        return {
            "detected_type": cached_record.get("detected_type", "Unknown"),
            "specs": cached_record.get("specs", {}),
            "cache_hit": True,
        }

    # --- Execute extraction pipeline on cache miss ---
    
    # Stage 1: Detect Component
    detected_type = detect_component_type(file_path)
    if detected_type == "Unknown":
        return {"error": "Could not detect component type. Please upload a clear datasheet."}
        
    # Stage 2: Cache & Schema Intelligence (DigiKey)
    target_specs, market_competitors = get_or_build_component_data(detected_type)
    if not target_specs or not market_competitors:
        return {"error": "Failed to generate market schema from DigiKey."}
        
    # Stage 3/4/5: Notebook-style staged extraction
    user_extracted_specs = parse_datasheet_staged(
        filepath=file_path,
        component_type=detected_type,
        required_features=target_specs,
        market_competitors=market_competitors,
        component_name=file.filename,
        chunk_size=25,
    )

    save_pdf_extraction(
        pdf_sha256=pdf_sha,
        filename=file.filename,
        detected_type=detected_type,
        extracted_specs=user_extracted_specs,
    )
    
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