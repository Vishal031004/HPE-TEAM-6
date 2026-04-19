import os
import json
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

# Import your entire enterprise pipeline!
from core.pdf_processor import detect_component_type, score_and_chunk_pdf
from core.database import get_or_build_component_data
from core.extractor import parse_datasheet_chunks
from core.similarity import rank_components

app = FastAPI()

# Supported categories
SUPPORTED_TYPES = [
    "Audio Codec", "LDO Regulator", "Buck Converter", "Op-Amp", 
    "Microcontroller", "Resistor", "Capacitor", "MOSFET"
]

# Define the expected JSON format for Step 2
class RankRequest(BaseModel):
    detected_type: str
    extracted_specs: dict
    weights: dict

@app.get("/")
async def serve_frontend():
    """Serves your beautiful index.html when you open the browser."""
    with open("static/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read(), status_code=200)

@app.post("/api/upload")
async def upload_pdf(file: UploadFile = File(...)):
    """STEP 1: Accepts the PDF, detects it, populates the database, and extracts specs."""
    os.makedirs("datasheets", exist_ok=True)
    file_path = os.path.join("datasheets", file.filename)
    
    # Save the uploaded file
    with open(file_path, "wb") as f:
        f.write(await file.read())
        
    # --- Execute Pipeline Stages 1, 2, and 3 ---
    detected_type = detect_component_type(file_path, SUPPORTED_TYPES)
    if detected_type == "Unknown":
        return {"error": "Could not detect component type."}
        
    target_specs, _ = get_or_build_component_data(detected_type)
    if not target_specs:
        return {"error": "Failed to generate market schema."}
        
    batched_chunks = score_and_chunk_pdf(file_path, target_specs, max_pages=8)
    user_extracted_specs = parse_datasheet_chunks(
        filtered_chunks=batched_chunks, 
        required_features=target_specs,
        component_name=file.filename
    )
    
    return {
        "detected_type": detected_type,
        "specs": user_extracted_specs
    }

@app.post("/api/rank")
async def rank_alternatives(request: RankRequest):
    """STEP 2: Accepts the user's weights from the sliders and runs the math engine."""
    # Quickly grab the 20 competitors we cached in Step 1
    _, market_competitors = get_or_build_component_data(request.detected_type)
    
    # --- Execute Pipeline Stage 5 ---
    top_5 = rank_components(
        user_extracted_specs=request.extracted_specs, 
        digikey_competitors=market_competitors, 
        feature_weights=request.weights
    )
    
    return {"results": top_5}