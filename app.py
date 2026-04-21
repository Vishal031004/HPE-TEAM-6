import os
import json
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

# Import the Enterprise Pipeline!
from core.pdf_processor import detect_component_type, parse_pdf_to_structured_pages
from core.database import get_or_build_component_data
from core.extractor import parse_datasheet_chunks
from core.similarity import rank_components

app = FastAPI()

# Supported categories
SUPPORTED_TYPES = [
    "Audio Codec", "LDO Regulator", "Buck Converter", "Op-Amp", 
    "Microcontroller", "Resistor", "Capacitor", "MOSFET"
]

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
    """STEP 1: Ingestion, Cache Check, and RAG Extraction."""
    os.makedirs("datasheets", exist_ok=True)
    file_path = os.path.join("datasheets", file.filename)
    
    # Save the uploaded file
    with open(file_path, "wb") as f:
        f.write(await file.read())
        
    # --- Execute Enterprise Pipeline ---
    
    # Stage 1: Detect Component
    detected_type = detect_component_type(file_path, SUPPORTED_TYPES)
    if detected_type == "Unknown":
        return {"error": "Could not detect component type. Please upload a clear datasheet."}
        
    # Stage 2: Cache & Schema Intelligence (DigiKey)
    target_specs, market_competitors = get_or_build_component_data(detected_type)
    if not target_specs or not market_competitors:
        return {"error": "Failed to generate market schema from DigiKey."}
        
    # Stage 3: Parse PDF into Structured Memory
    structured_pages = parse_pdf_to_structured_pages(file_path)
    if not structured_pages:
         return {"error": "Failed to extract readable text/tables from the PDF."}
         
    # Stage 4: Surgical RAG Extraction (Injecting market competitors for Few-Shot!)
    user_extracted_specs = parse_datasheet_chunks(
        structured_pages=structured_pages, 
        required_features=target_specs,
        market_competitors=market_competitors,
        component_name=file.filename
    )
    
    return {
        "detected_type": detected_type,
        "specs": user_extracted_specs
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