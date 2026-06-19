import os
import sys
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add the workspace root directory to system path to ensure absolute imports function correctly
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from core.pdf_processor.pdf_processor import (
    detect_component_type,
    pdf_hash,
    process_pdf_for_rag,
    parse_pdf_chunk_to_structured_pages,
    get_figure_pages,
    render_page_to_base64,
    parse_pdf_to_structured_pages
)

app = FastAPI(
    title="HPE Component PDF Processor Microservice",
    description="Microservice providing API endpoints for PDF metadata, text extraction, vision rendering, and structured chunking.",
    version="1.0.0"
)

# ========================================================================
# Pydantic Schemas for Request Bodies
# ========================================================================

class DetectComponentRequest(BaseModel):
    pdf_path: str
    available_types: Optional[List[str]] = None

class PdfHashRequest(BaseModel):
    filepath: str

class ProcessRagRequest(BaseModel):
    filepath: str
    filename: str

class ParseChunksRequest(BaseModel):
    filepath: str
    start_page: int = 0
    end_page: int = 25

class FigurePagesRequest(BaseModel):
    filepath: str
    start_page: int = 0
    end_page: int = 25

class RenderPageRequest(BaseModel):
    filepath: str
    page_num_1indexed: int
    dpi: int = 150

class ParseStructuredRequest(BaseModel):
    filepath: str

# ========================================================================
# PDF Processor Service Endpoints
# ========================================================================

@app.post("/api/pdf/detect")
def detect_endpoint(request: DetectComponentRequest):
    try:
        detected_type = detect_component_type(
            pdf_path=request.pdf_path,
            available_types=request.available_types
        )
        return {"detected_type": detected_type}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/pdf/hash")
def hash_endpoint(request: PdfHashRequest):
    try:
        hash_val = pdf_hash(filepath=request.filepath)
        return {"pdf_hash": hash_val}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/pdf/process_rag")
def process_rag_endpoint(request: ProcessRagRequest):
    try:
        chunks = process_pdf_for_rag(
            filepath=request.filepath,
            filename=request.filename
        )
        return chunks
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/pdf/parse_chunks")
def parse_chunks_endpoint(request: ParseChunksRequest):
    try:
        structured_pages, total_pages = parse_pdf_chunk_to_structured_pages(
            filepath=request.filepath,
            start_page=request.start_page,
            end_page=request.end_page
        )
        return {
            "structured_pages": structured_pages,
            "total_pages": total_pages
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/pdf/figure_pages")
def figure_pages_endpoint(request: FigurePagesRequest):
    try:
        figure_pages = get_figure_pages(
            filepath=request.filepath,
            start_page=request.start_page,
            end_page=request.end_page
        )
        return {"figure_pages": figure_pages}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/pdf/render_page")
def render_page_endpoint(request: RenderPageRequest):
    try:
        base64_data = render_page_to_base64(
            filepath=request.filepath,
            page_num_1indexed=request.page_num_1indexed,
            dpi=request.dpi
        )
        return {"image_b64": base64_data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/pdf/parse_structured")
def parse_structured_endpoint(request: ParseStructuredRequest):
    try:
        structured_pages = parse_pdf_to_structured_pages(filepath=request.filepath)
        return {"structured_pages": structured_pages}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ========================================================================
# Entry point for direct execution
# ========================================================================
if __name__ == "__main__":
    import uvicorn
    # Default port for pdf_processor microservice is 8083
    uvicorn.run("pdfProcessorServer:app", host="0.0.0.0", port=8083, reload=True)
