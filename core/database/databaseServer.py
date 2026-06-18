import os
import sys
from typing import List, Dict, Any, Union
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add the workspace root directory to system path to ensure absolute imports function correctly
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from core.database.database import (
    register_user, login_user, add_user_pdf, get_user_pdfs, get_user_pdf_hashes,
    create_chat_session, get_user_sessions, attach_pdf_to_session, get_session_data,
    save_session_messages, delete_chat_session, rename_chat_session, toggle_pin_session,
    get_cached_pdf_extraction, save_pdf_extraction, get_digikey_token_lazy,
    get_or_build_component_data, has_rag_chunks, store_rag_chunks, retrieve_rag_context
)

app = FastAPI(
    title="HPE Component Database Microservice",
    description="Microservice providing API endpoints for all MongoDB, session cache, user profile, and vector search operations.",
    version="1.0.0"
)

# ========================================================================
# Pydantic Schemas for Request Bodies
# ========================================================================

class AuthRequest(BaseModel):
    username: str
    password: str

class UserPdfRequest(BaseModel):
    user_id: str
    pdf_hash: str
    filename: str

class SessionCreateRequest(BaseModel):
    user_id: str
    session_name: str

class SessionAttachRequest(BaseModel):
    session_id: str
    pdf_hash: str

class SaveMessagesRequest(BaseModel):
    session_id: str
    new_messages: List[Dict[str, Any]]

class RenameRequest(BaseModel):
    new_name: str

class SaveExtractionRequest(BaseModel):
    pdf_hash: str
    filename: str
    detected_type: str
    extracted_specs: Dict[str, Any]

class ComponentDataRequest(BaseModel):
    component_type: str

class StoreRagChunksRequest(BaseModel):
    chunks: List[Dict[str, Any]]
    pdf_hash: str

class RetrieveRagContextRequest(BaseModel):
    query: str
    filename: Union[str, None] = None
    pdf_sha256: Union[str, List[str], None] = None
    top_k: int = 15

# ========================================================================
# User Management Endpoints
# ========================================================================

@app.get("/")
def root():
    return {"message": "Welcome to the Database Server"}

@app.post("/api/register")
def register(request: AuthRequest):
    success, msg = register_user(request.username, request.password)
    if not success:
        return {"error": msg}
    return {"message": msg}

@app.post("/api/login")
def login(request: AuthRequest):
    user_id, msg = login_user(request.username, request.password)
    if not user_id:
        return {"error": msg}
    return {"user_id": user_id, "message": msg}

@app.post("/api/user/pdf")
def add_pdf(request: UserPdfRequest):
    try:
        add_user_pdf(request.user_id, request.pdf_hash, request.filename)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/user/{user_id}/pdfs")
def get_pdfs(user_id: str):
    return {"pdfs": get_user_pdfs(user_id)}

@app.get("/api/user/{user_id}/pdf_hashes")
def get_pdf_hashes(user_id: str):
    return {"pdf_hashes": get_user_pdf_hashes(user_id)}

# ========================================================================
# Session Management Endpoints
# ========================================================================

@app.post("/api/sessions/create")
def create_session(request: SessionCreateRequest):
    session_id = create_chat_session(request.user_id, request.session_name)
    if not session_id:
        raise HTTPException(status_code=500, detail="Failed to create chat session")
    return {"session_id": session_id}

@app.get("/api/user/{user_id}/sessions")
def get_sessions(user_id: str):
    return {"sessions": get_user_sessions(user_id)}

@app.post("/api/sessions/attach")
def attach_pdf(request: SessionAttachRequest):
    success = attach_pdf_to_session(request.session_id, request.pdf_hash)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to attach PDF to session")
    return {"status": "success"}

@app.get("/api/sessions/{session_id}")
def get_session(session_id: str):
    data = get_session_data(session_id)
    if not data:
        raise HTTPException(status_code=404, detail="Session not found")
    return data

@app.post("/api/sessions/save_messages")
def save_messages(request: SaveMessagesRequest):
    try:
        save_session_messages(request.session_id, request.new_messages)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/sessions/{session_id}")
def delete_session(session_id: str):
    success = delete_chat_session(session_id)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to delete session")
    return {"status": "success"}

@app.patch("/api/sessions/{session_id}/rename")
def rename_session(session_id: str, request: RenameRequest):
    success = rename_chat_session(session_id, request.new_name)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to rename session")
    return {"status": "success"}

@app.patch("/api/sessions/{session_id}/pin")
def pin_session(session_id: str):
    success = toggle_pin_session(session_id)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to toggle pin session")
    return {"status": "success"}

# ========================================================================
# Spec Extraction Cache Endpoints
# ========================================================================

@app.get("/api/extraction/{pdf_hash}")
def get_extraction(pdf_hash: str):
    record = get_cached_pdf_extraction(pdf_hash)
    if not record:
        raise HTTPException(status_code=404, detail="Extraction cache not found")
    return record

@app.post("/api/extraction")
def save_extraction(request: SaveExtractionRequest):
    try:
        save_pdf_extraction(
            request.pdf_hash,
            request.filename,
            request.detected_type,
            request.extracted_specs
        )
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ========================================================================
# DigiKey API Cache Endpoints
# ========================================================================

@app.get("/api/digikey/token")
def get_digikey_token():
    try:
        token = get_digikey_token_lazy()
        return {"access_token": token}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/component_data")
def get_component_data(request: ComponentDataRequest):
    features, competitors = get_or_build_component_data(request.component_type)
    if features is None or competitors is None:
        raise HTTPException(status_code=500, detail="Failed to retrieve component category data from DigiKey")
    return {"features": features, "competitors": competitors}

# ========================================================================
# Vector Search & RAG Chunks Endpoints
# ========================================================================

@app.get("/api/rag/has_chunks/{pdf_hash}")
def get_has_chunks(pdf_hash: str):
    return {"has_chunks": has_rag_chunks(pdf_hash)}

@app.post("/api/rag/store_chunks")
def store_chunks(request: StoreRagChunksRequest):
    try:
        store_rag_chunks(request.chunks, request.pdf_hash)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/rag/retrieve")
def retrieve_chunks(request: RetrieveRagContextRequest):
    try:
        results = retrieve_rag_context(
            query=request.query,
            filename=request.filename,
            pdf_sha256=request.pdf_sha256,
            top_k=request.top_k
        )
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ========================================================================
# Entry point for direct execution
# ========================================================================
if __name__ == "__main__":
    import uvicorn
    # Default port for database microservice is 8081
    uvicorn.run("databaseServer:app", host="0.0.0.0", port=8081, reload=True)
