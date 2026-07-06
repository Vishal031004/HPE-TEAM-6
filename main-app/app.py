import os
import requests
import json
from fastapi import FastAPI, UploadFile, File, Query, BackgroundTasks, Form
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
from typing import List
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

LLM_SERVER_URL = os.environ.get("LLM_SERVER_URL", "http://127.0.0.1:8086")
if LLM_SERVER_URL:
    LLM_SERVER_URL = LLM_SERVER_URL.strip("'\"")

PDF_PROCESSOR_SERVER_URL = os.environ.get("PDF_PROCESSOR_SERVER_URL")
if PDF_PROCESSOR_SERVER_URL:
    PDF_PROCESSOR_SERVER_URL = PDF_PROCESSOR_SERVER_URL.strip("'\"")

DATASHEETS_DIR = os.environ.get("DATASHEETS_DIR", "datasheets")
if DATASHEETS_DIR:
    DATASHEETS_DIR = DATASHEETS_DIR.strip("'\"")

DIGIKEY_CLIENT_ID = os.environ.get("DIGIKEY_CLIENT_ID", "")
if DIGIKEY_CLIENT_ID:
    DIGIKEY_CLIENT_ID = DIGIKEY_CLIENT_ID.strip("'\"")

def detect_component_type(pdf_path: str, available_types: list = None) -> str:
    try:
        res = requests.post(
            f"{PDF_PROCESSOR_SERVER_URL}/api/pdf/detect",
            json={
                "pdf_path": pdf_path,
                "available_types": available_types
            }
        )
        res.raise_for_status()
        return res.json().get("detected_type", "Unknown")
    except Exception as e:
        print(f"Error calling pdf_processor service detect_component_type: {e}")
        return "Unknown"

def pdf_hash(filepath: str) -> str:
    try:
        res = requests.post(
            f"{PDF_PROCESSOR_SERVER_URL}/api/pdf/hash",
            json={"filepath": filepath}
        )
        res.raise_for_status()
        return res.json().get("pdf_hash")
    except Exception as e:
        print(f"Error calling pdf_processor service pdf_hash: {e}")
        import hashlib
        h = hashlib.sha256()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

def process_pdf_for_rag(filepath: str, filename: str):
    try:
        res = requests.post(
            f"{PDF_PROCESSOR_SERVER_URL}/api/pdf/process_rag",
            json={
                "filepath": filepath,
                "filename": filename
            }
        )
        res.raise_for_status()
        return res.json()
    except Exception as e:
        print(f"Error calling pdf_processor service process_pdf_for_rag: {e}")
        return []
DB_SERVER_URL = os.environ.get("DB_SERVER_URL", "http://127.0.0.1:8081")
if DB_SERVER_URL:
    DB_SERVER_URL = DB_SERVER_URL.strip("'\"")

DIGIKEY_CLIENT_ID = os.environ.get("DIGIKEY_CLIENT_ID")
if DIGIKEY_CLIENT_ID:
    DIGIKEY_CLIENT_ID = DIGIKEY_CLIENT_ID.strip("'\"")

def register_user(username, password):
    try:
        res = requests.post(f"{DB_SERVER_URL}/api/register", json={"username": username, "password": password})
        res.raise_for_status()
        data = res.json()
        if "error" in data:
            return False, data["error"]
        return True, data["message"]
    except Exception as e:
        return False, f"Database service error: {e}"

def login_user(username, password):
    try:
        res = requests.post(f"{DB_SERVER_URL}/api/login", json={"username": username, "password": password})
        res.raise_for_status()
        data = res.json()
        if "error" in data:
            return None, data["error"]
        return data["user_id"], data["message"]
    except Exception as e:
        return None, f"Database service error: {e}"

def add_user_pdf(user_id, pdf_hash, filename):
    try:
        res = requests.post(f"{DB_SERVER_URL}/api/user/pdf", json={"user_id": user_id, "pdf_hash": pdf_hash, "filename": filename})
        res.raise_for_status()
    except Exception as e:
        print(f"Error calling database service add_user_pdf: {e}")

def get_user_pdfs(user_id):
    try:
        res = requests.get(f"{DB_SERVER_URL}/api/user/{user_id}/pdfs")
        res.raise_for_status()
        return res.json().get("pdfs", [])
    except Exception as e:
        print(f"Error calling database service get_user_pdfs: {e}")
        return []

def get_user_pdf_hashes(user_id):
    try:
        res = requests.get(f"{DB_SERVER_URL}/api/user/{user_id}/pdf_hashes")
        res.raise_for_status()
        return res.json().get("pdf_hashes", [])
    except Exception as e:
        print(f"Error calling database service get_user_pdf_hashes: {e}")
        return []

def create_chat_session(user_id: str, session_name: str):
    try:
        res = requests.post(f"{DB_SERVER_URL}/api/sessions/create", json={"user_id": user_id, "session_name": session_name})
        res.raise_for_status()
        return res.json().get("session_id")
    except Exception as e:
        print(f"Error calling database service create_chat_session: {e}")
        return None

def get_user_sessions(user_id: str):
    try:
        res = requests.get(f"{DB_SERVER_URL}/api/user/{user_id}/sessions")
        res.raise_for_status()
        return res.json().get("sessions", [])
    except Exception as e:
        print(f"Error calling database service get_user_sessions: {e}")
        return []

def attach_pdf_to_session(session_id: str, pdf_hash: str):
    try:
        res = requests.post(f"{DB_SERVER_URL}/api/sessions/attach", json={"session_id": session_id, "pdf_hash": pdf_hash})
        return res.status_code == 200
    except Exception as e:
        print(f"Error calling database service attach_pdf_to_session: {e}")
        return False

def get_session_data(session_id: str):
    try:
        res = requests.get(f"{DB_SERVER_URL}/api/sessions/{session_id}")
        if res.status_code == 404:
            return None
        res.raise_for_status()
        return res.json()
    except Exception as e:
        print(f"Error calling database service get_session_data: {e}")
        return None

def save_session_messages(session_id: str, new_messages: list):
    try:
        res = requests.post(f"{DB_SERVER_URL}/api/sessions/save_messages", json={"session_id": session_id, "new_messages": new_messages})
        res.raise_for_status()
    except Exception as e:
        print(f"Error calling database service save_session_messages: {e}")

def delete_chat_session(session_id: str):
    try:
        res = requests.delete(f"{DB_SERVER_URL}/api/sessions/{session_id}")
        return res.status_code == 200
    except Exception as e:
        print(f"Error calling database service delete_chat_session: {e}")
        return False

def rename_chat_session(session_id: str, new_name: str):
    try:
        res = requests.patch(f"{DB_SERVER_URL}/api/sessions/{session_id}/rename", json={"new_name": new_name})
        return res.status_code == 200
    except Exception as e:
        print(f"Error calling database service rename_chat_session: {e}")
        return False

def toggle_pin_session(session_id: str):
    try:
        res = requests.patch(f"{DB_SERVER_URL}/api/sessions/{session_id}/pin")
        return res.status_code == 200
    except Exception as e:
        print(f"Error calling database service toggle_pin_session: {e}")
        return False

def detach_pdf_from_session(session_id: str, pdf_hash: str):
    try:
        res = requests.post(f"{DB_SERVER_URL}/api/sessions/detach", json={"session_id": session_id, "pdf_hash": pdf_hash})
        return res.status_code == 200
    except Exception as e:
        print(f"Error calling database service detach_pdf_from_session: {e}")
        return False

def get_cached_pdf_extraction(pdf_sha256: str):
    try:
        res = requests.get(f"{DB_SERVER_URL}/api/extraction/{pdf_sha256}")
        if res.status_code == 404:
            return None
        res.raise_for_status()
        return res.json()
    except Exception as e:
        print(f"Error calling database service get_cached_pdf_extraction: {e}")
        return None

def save_pdf_extraction(pdf_sha256: str, filename: str, detected_type: str, extracted_specs: dict):
    try:
        res = requests.post(
            f"{DB_SERVER_URL}/api/extraction",
            json={
                "pdf_hash": pdf_sha256,
                "filename": filename,
                "detected_type": detected_type,
                "extracted_specs": extracted_specs
            }
        )
        res.raise_for_status()
    except Exception as e:
        print(f"Error calling database service save_pdf_extraction: {e}")

def get_digikey_token_lazy():
    try:
        res = requests.get(f"{DB_SERVER_URL}/api/digikey/token")
        res.raise_for_status()
        return res.json().get("access_token")
    except Exception as e:
        print(f"Error calling database service get_digikey_token_lazy: {e}")
        return None

def get_or_build_component_data(component_type: str):
    try:
        res = requests.post(f"{DB_SERVER_URL}/api/component_data", json={"component_type": component_type})
        if res.status_code != 200:
            return None, None
        data = res.json()
        return data.get("features"), data.get("competitors")
    except Exception as e:
        print(f"Error calling database service get_or_build_component_data: {e}")
        return None, None

def has_rag_chunks(pdf_sha256: str) -> bool:
    try:
        res = requests.get(f"{DB_SERVER_URL}/api/rag/has_chunks/{pdf_sha256}")
        res.raise_for_status()
        return res.json().get("has_chunks", False)
    except Exception as e:
        print(f"Error calling database service has_rag_chunks: {e}")
        return False

def store_rag_chunks(chunks: list, pdf_sha256: str):
    try:
        res = requests.post(f"{DB_SERVER_URL}/api/rag/store_chunks", json={"chunks": chunks, "pdf_hash": pdf_sha256})
        res.raise_for_status()
    except Exception as e:
        print(f"Error calling database service store_rag_chunks: {e}")

def retrieve_rag_context(query: str, filename: str = None, pdf_sha256 = None, top_k: int = 15):
    try:
        res = requests.post(
            f"{DB_SERVER_URL}/api/rag/retrieve",
            json={
                "query": query,
                "filename": filename,
                "pdf_sha256": pdf_sha256,
                "top_k": top_k
            }
        )
        res.raise_for_status()
        return res.json().get("results", [])
    except Exception as e:
        print(f"Error calling database service retrieve_rag_context: {e}")
        return []

EXTRACTOR_SERVER_URL = os.environ.get("EXTRACTOR_SERVER_URL", "http://127.0.0.1:8085")
if EXTRACTOR_SERVER_URL:
    EXTRACTOR_SERVER_URL = EXTRACTOR_SERVER_URL.strip("'\"")

def parse_datasheet_staged(filepath, component_type, required_features, market_competitors, component_name="Unknown Part", chunk_size=5):
    try:
        res = requests.post(
            f"{EXTRACTOR_SERVER_URL}/api/extractor/parse_staged",
            json={
                "filepath": filepath,
                "component_type": component_type,
                "required_features": required_features,
                "market_competitors": market_competitors,
                "component_name": component_name,
                "chunk_size": chunk_size
            }
        )
        res.raise_for_status()
        return res.json()
    except Exception as e:
        print(f"Error calling extractor service parse_datasheet_staged: {e}")
        return {f: "Not Found" for f in required_features}

def rerank_chunks_cross_encoder(query, chunks, top_k=5):
    try:
        res = requests.post(
            f"{EXTRACTOR_SERVER_URL}/api/extractor/rerank",
            json={
                "query": query,
                "chunks": chunks,
                "top_k": top_k
            }
        )
        res.raise_for_status()
        return res.json()
    except Exception as e:
        print(f"Error calling extractor service rerank: {e}")
        return chunks[:top_k]

def reformulate_query(query, chat_history, active_file=None):
    try:
        res = requests.post(
            f"{EXTRACTOR_SERVER_URL}/api/extractor/reformulate",
            json={
                "query": query,
                "chat_history": chat_history,
                "active_file": active_file
            }
        )
        res.raise_for_status()
        return res.json().get("query", query)
    except Exception as e:
        print(f"Error calling extractor service reformulate: {e}")
        return query

def route_user_intent(query, chat_history):
    try:
        res = requests.post(
            f"{EXTRACTOR_SERVER_URL}/api/extractor/route_intent",
            json={
                "query": query,
                "chat_history": chat_history
            }
        )
        res.raise_for_status()
        return res.json().get("intent", "information_retrieval")
    except Exception as e:
        print(f"Error calling extractor service route_intent: {e}")
        return "information_retrieval"

def answer_rag_question(query, retrieved_chunks, chat_history=None, is_global=False):
    try:
        res = requests.post(
            f"{EXTRACTOR_SERVER_URL}/api/extractor/answer_rag",
            json={
                "query": query,
                "retrieved_chunks": retrieved_chunks,
                "chat_history": chat_history,
                "is_global": is_global
            }
        )
        res.raise_for_status()
        return res.json().get("answer", "I encountered an error trying to generate an answer.")
    except Exception as e:
        print(f"Error calling extractor service answer_rag: {e}")
        return "I encountered an error trying to communicate with the generation service."
def run_agentic_chat_loop(request, max_iterations=5):
    system_prompt = (
        "You are an expert hardware engineering AI assistant. "
        "You have access to several tools. Use them to answer the user's request. "
        "1. If they ask about technical specs, search datasheets, use `search_datasheets`.\n"
        "2. If they ask about the current workspace, uploaded files, or metadata, use `get_workspace_metadata`.\n"
        "3. If they ask about live market pricing or stock, use `fetch_live_pricing`. If the user provides a filename (e.g. 'ADXRS453.pdf'), strip the extension and use the base part number (e.g. 'ADXRS453') for the tool.\n"
        "If a tool doesn't return enough info, you can call it again with different parameters or try another tool."
    )
    
    messages = [{"role": "system", "content": system_prompt}]
    
    if request.chat_history:
        # Bound to last 10 messages to prevent context bloat & hallucination in long chats
        for msg in request.chat_history[-10:]:
            messages.append({"role": msg.get("role", "user"), "content": msg.get("content") or ""})
    messages.append({"role": "user", "content": request.question})
    
    tools = [
        {
            "type": "function",
            "function": {
                "name": "search_datasheets",
                "description": "Searches the uploaded datasheet chunks for technical specs or text.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "The technical search query."}
                    },
                    "required": ["query"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_workspace_metadata",
                "description": "Returns metadata about the current workspace (uploaded files, session names, etc.).",
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "fetch_live_pricing",
                "description": "Fetches real-time price and stock from DigiKey.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "part_number": {"type": "string"}
                    },
                    "required": ["part_number"]
                }
            }
        }
    ]
    
    def execute_tool(name, args):
        if name == "search_datasheets":
            query = args.get("query", "")
            target_hashes = None
            if request.is_global and request.session_id:
                session_data = get_session_data(request.session_id)
                if session_data:
                    target_hashes = session_data.get("attached_pdfs", [])
            elif request.filename:
                file_path = os.path.join(DATASHEETS_DIR, request.filename)
                if os.path.exists(file_path):
                    target_hashes = [pdf_hash(file_path)]
                    
            if target_hashes is None:
                if request.user_id:
                    target_hashes = get_user_pdf_hashes(request.user_id)
                else:
                    target_hashes = []
                    
            if not target_hashes:
                return "There are no PDFs in your current workspace to search."
                
            raw_chunks = retrieve_rag_context(query, request.filename, pdf_sha256=target_hashes, top_k=15)
            if not raw_chunks:
                return "No relevant text found."
            
            ranked_chunks = rerank_chunks_cross_encoder(query, raw_chunks, top_k=5)
            context_text = ""
            for chunk in ranked_chunks:
                context_text += f"--- Source: {chunk.get('filename', 'Unknown')} (Page {chunk.get('page')}) ---\n{chunk.get('text')}\n\n"
            return context_text

        elif name == "get_workspace_metadata":
            if request.session_id:
                session_data = get_session_data(request.session_id)
                if session_data:
                    pdfs = session_data.get("attached_pdfs", [])
                    user_pdfs = get_user_pdfs(request.user_id) if request.user_id else []
                    hash_to_name = {p["pdf_hash"]: p["filename"] for p in user_pdfs}
                    files = [hash_to_name.get(h, "Unknown PDF") for h in pdfs]
                    return f"Workspace Name: {session_data.get('session_name')}\nAttached Files: {', '.join(files) if files else 'None'}"
                return "Workspace not found."
            elif request.filename:
                return f"Currently interacting directly with file: {request.filename}"
            return "No workspace or file selected."
                
        elif name == "fetch_live_pricing":
            pn = args.get("part_number", "")
            res = _fetch_digikey_pricing(pn)
            return json.dumps(res)
            
        return "Unknown tool."

    for _ in range(max_iterations):
        res = requests.post(
            f"{LLM_SERVER_URL}/api/llm/generate_text",
            json={"messages": messages, "model": "gpt-4o", "tools": tools, "temperature": 0.2}
        )
        if res.status_code != 200:
            return "Failed to communicate with LLM."
            
        payload = res.json()
        content = payload.get("content", "")
        tool_calls = payload.get("tool_calls", [])
        
        ast_msg = {"role": "assistant"}
        if content:
            ast_msg["content"] = content
        if tool_calls:
            ast_msg["tool_calls"] = tool_calls
        messages.append(ast_msg)
        
        if not tool_calls:
            return content
            
        for tc in tool_calls:
            name = tc["function"]["name"]
            try:
                args = json.loads(tc["function"]["arguments"])
            except:
                args = {}
                
            print(f"🛠️  Agent called tool: {name}({args})")
            tool_result = execute_tool(name, args)
            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": str(tool_result)
            })
            
    return "Agent loop exceeded max iterations."

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
    active_file: str = None

class PricingRequest(BaseModel):
    part_numbers: List[str]

class SessionCreateRequest(BaseModel):
    user_id: str
    session_name: str

class AttachPdfRequest(BaseModel):
    session_id: str
    pdf_hash: str

class DetachPdfRequest(BaseModel):
    session_id: str
    pdf_hash: str

class FindAlternativesRequest(BaseModel):
    filename: str
    session_id: str = None
    user_id: str = None

class SaveMessagesRequest(BaseModel):
    session_id: str
    new_messages: list

class RenameRequest(BaseModel):
    new_name: str

def _safe_error_message(prefix: str, exc: Exception) -> str:
    message = str(exc).strip()
    return f"{prefix}: {message}" if message else prefix

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
    os.makedirs(DATASHEETS_DIR, exist_ok=True)
    file_path = os.path.join(DATASHEETS_DIR, file.filename)

    try:
        with open(file_path, "wb") as f:
            f.write(await file.read())
    except OSError as exc:
        return {"error": _safe_error_message("Could not save the uploaded PDF", exc)}

    try:
        pdf_sha = pdf_hash(file_path)
    except Exception as exc:
        return {"error": _safe_error_message("Could not process the uploaded PDF", exc)}

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

@app.post("/api/find_alternatives")
async def find_alternatives(request: FindAlternativesRequest):
    """Dedicated endpoint for the Find Alternatives button.
    Accepts a specific filename, extracts specs, and returns interactive_ranking data."""
    target_filename = request.filename
    
    if not target_filename:
        return {"error": "No filename provided."}
    
    file_path = os.path.join(DATASHEETS_DIR, target_filename)
    if not os.path.exists(file_path):
        return {"error": f"Cannot access the file '{target_filename}' to run the market analysis."}

    # We need the hash to check the database cache
    pdf_sha = pdf_hash(file_path)
    
    cached_record = get_cached_pdf_extraction(pdf_sha)
    
    if cached_record and cached_record.get("specs"):
        print(f"🧠 CACHE HIT! Loading previously extracted specs for {target_filename}")
        detected_type = cached_record.get("detected_type", "Unknown")
        user_extracted_specs = cached_record.get("specs")
    else:
        print(f"⚠️ CACHE MISS! Running heavy LLM extraction for {target_filename}...")
        
        detected_type = detect_component_type(file_path)
        if detected_type == "Unknown":
            return {"error": "Could not detect the specific component category needed to query the market."}
            
        target_specs, market_competitors = get_or_build_component_data(detected_type)
        
        user_extracted_specs = parse_datasheet_staged(
            filepath=file_path, component_type=detected_type, required_features=target_specs,
            market_competitors=market_competitors, component_name=target_filename, chunk_size=15
        )
        
        # Save to database so we never have to extract this specific PDF again
        save_pdf_extraction(pdf_sha, target_filename, detected_type, user_extracted_specs)

    return {
        "type": "interactive_ranking",
        "detected_type": detected_type,
        "extracted_specs": user_extracted_specs,
        "answer": f"I extracted the specs for **{target_filename}**. Adjust your parametric weights below, and click 'Run Math Engine' to fetch live market alternatives."
    }

@app.post("/api/sessions/{session_id}/detach_pdf")
async def detach_pdf_endpoint(session_id: str, request: DetachPdfRequest):
    """Removes a PDF from a workspace's attached files."""
    success = detach_pdf_from_session(session_id, request.pdf_hash)
    if success:
        return {"status": "success"}
    return {"error": "Failed to detach PDF from workspace."}

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
        target_filename = request.filename
        
        # AGENTIC FILENAME RESOLUTION: If in global mode and multiple PDFs exist, figure out which one the user means
        if request.is_global and request.session_id:
            session_data = get_session_data(request.session_id)
            if session_data and session_data.get("attached_pdfs") and len(session_data["attached_pdfs"]) > 1:
                user_pdfs = get_user_pdfs(session_data.get("user_id", ""))
                hash_to_name = {p["pdf_hash"]: p["filename"] for p in user_pdfs} if user_pdfs else {}
                available_files = [hash_to_name.get(p, "Datasheet.pdf") for p in session_data["attached_pdfs"]]
                
                messages = [{"role": "system", "content": f"You are an assistant. The user wants to find alternatives for a component. Available files: {', '.join(available_files)}. Based on their query and chat history, return ONLY the exact filename of the component they are referring to. If it's ambiguous, return 'AMBIGUOUS'."}]
                if request.chat_history:
                    for msg in request.chat_history[-6:]:
                        messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})
                messages.append({"role": "user", "content": request.question})

                try:
                    res = requests.post(
                        f"{LLM_SERVER_URL}/api/llm/generate_text",
                        json={
                            "messages": messages,
                            "model": "gpt-4o-mini",
                            "temperature": 0.0
                        }
                    )
                    res.raise_for_status()
                    predicted_file = res.json().get("content", "").strip()
                    
                    # Fuzzy match the filename
                    matched = None
                    for f in available_files:
                        if predicted_file.lower() == f.lower() or predicted_file.lower() in f.lower() or f.lower() in predicted_file.lower():
                            matched = f
                            break
                            
                    if matched:
                        target_filename = matched
                        print(f"🎯 [AGENT] LLM disambiguated filename to: {target_filename}")
                    else:
                        print(f"⚠️ [AGENT] LLM could not disambiguate. Returned: {predicted_file}")
                        target_filename = "AMBIGUOUS"
                except Exception as e:
                    print(f"Error resolving filename: {e}")

        if not target_filename or target_filename == "AMBIGUOUS":
            return {"answer": "Please specify which component you want me to find alternatives for."}
            
        file_path = os.path.join(DATASHEETS_DIR, target_filename)
        if not os.path.exists(file_path):
            return {"answer": "I cannot access the file to run the market analysis."}

        # We need the hash to check the database cache
        pdf_sha = pdf_hash(file_path)
        
        # 🚨 RESTORED CACHING LOGIC
        cached_record = get_cached_pdf_extraction(pdf_sha)
        
        if cached_record and cached_record.get("specs"):
            print(f"🧠 CACHE HIT! Loading previously extracted specs for {target_filename}")
            detected_type = cached_record.get("detected_type", "Unknown")
            user_extracted_specs = cached_record.get("specs")
        else:
            print(f"⚠️ CACHE MISS! Running heavy LLM extraction for {target_filename}...")
            
            detected_type = detect_component_type(file_path)
            if detected_type == "Unknown":
                return {"answer": "I could not detect the specific component category needed to query the market."}
                
            target_specs, market_competitors = get_or_build_component_data(detected_type)
            
            user_extracted_specs = parse_datasheet_staged(
                filepath=file_path, component_type=detected_type, required_features=target_specs,
                market_competitors=market_competitors, component_name=target_filename, chunk_size=15
            )
            
            # Save to database so we never have to extract this specific PDF again
            save_pdf_extraction(pdf_sha, target_filename, detected_type, user_extracted_specs)

        return {
            "type": "interactive_ranking",
            "detected_type": detected_type,
            "extracted_specs": user_extracted_specs,
            "answer": f"I extracted the specs for **{target_filename}**. Adjust your parametric weights below, and click 'Run Math Engine' to fetch live market alternatives."
        }
    
    # ==========================================
    # PATH B: AGENTIC WORKFLOW
    # ==========================================
    answer = run_agentic_chat_loop(request)
    return {"answer": answer}

@app.post("/api/chat/stream")
async def chat_stream(request: ChatRequest):
    """SSE streaming endpoint for RAG Q&A.
    All chat queries go through here as pure information retrieval.
    Find Alternatives is handled by the dedicated /api/find_alternatives endpoint."""
    from fastapi.responses import StreamingResponse
    
    # 1. Intent Routing
    intent = route_user_intent(request.question, request.chat_history)
    print(f"\n🧠 [AGENT ROUTER] Detected Intent: {intent.upper()}")
    
    if intent == "fetch_pricing":
        answer = run_agentic_chat_loop(request)
        return {"answer": answer}
    
    # Build the RAG context, then stream the LLM response
    reformulated = reformulate_query(request.question, request.chat_history, request.active_file)
    
    target_hashes = None
    if request.is_global and request.session_id:
        session_data = get_session_data(request.session_id)
        if session_data:
            target_hashes = session_data.get("attached_pdfs", [])
    elif request.filename:
        file_path = os.path.join(DATASHEETS_DIR, request.filename)
        if os.path.exists(file_path):
            target_hashes = [pdf_hash(file_path)]
    
    if target_hashes is None and request.user_id:
        target_hashes = get_user_pdf_hashes(request.user_id)
        
    # Wait for background ingestion if chunks aren't ready
    import time
    if target_hashes:
        for _ in range(8): # Wait up to 12 seconds total
            all_ready = True
            for h in target_hashes:
                try:
                    res = requests.get(f"{DB_SERVER_URL}/api/chunks/check/{h}")
                    if res.status_code == 200 and not res.json().get("has_chunks"):
                        all_ready = False
                        break
                except:
                    pass
            if all_ready:
                break
            time.sleep(1.5)
            
    raw_chunks = retrieve_rag_context(reformulated, request.filename, pdf_sha256=target_hashes, top_k=15)
    
    ranked_chunks = rerank_chunks_cross_encoder(reformulated, raw_chunks, top_k=5)
    
    # Build Workspace Metadata Context
    workspace_metadata_text = ""
    if target_hashes:
        workspace_metadata_text += "--- START WORKSPACE METADATA ---\n"
        workspace_metadata_text += "The following files are currently attached to the user's workspace:\n"
        for h in target_hashes:
            cached = get_cached_pdf_extraction(h)
            if cached:
                fname = cached.get("filename", "Unknown")
                ctype = cached.get("detected_type", "Unknown")
                workspace_metadata_text += f"- Filename: {fname} | Detected Component Class: {ctype}\n"
        workspace_metadata_text += "--- END WORKSPACE METADATA ---\n\n"

    if request.active_file:
        workspace_metadata_text += f"CRITICAL CONTEXT: The user most recently interacted with the file '{request.active_file}'. If they use pronouns like 'it', 'this component', or 'the datasheet', assume they are referring to '{request.active_file}'.\n\n"

    # Build context for streaming
    context_text = ""
    source_docs = set()
    if ranked_chunks:
        for chunk in ranked_chunks:
            source_docs.add(chunk.get('filename', 'Unknown'))
            context_text += f"\n--- CHUNK ID: {chunk.get('chunk_id')} | SOURCE: {chunk.get('filename', 'Unknown')} (Page {chunk.get('page')}) ---\n"
            context_text += f"{chunk.get('text')}\n"
    
    doc_list = ", ".join(source_docs) if source_docs else "None"
    system_prompt = (
        "You are an expert hardware engineering assistant with access to MULTIPLE datasheets from a user's component library. "
        f"Source documents with matching text chunks: {doc_list}\n\n"
        f"{workspace_metadata_text}"
        "CRITICAL RULES:\n"
        "1. MULTI-DOCUMENT AWARENESS: Synthesize data from the provided context.\n"
        "2. ZERO HALLUCINATION: If data is missing from context, say so. If a user asks for stock/price and it's not in the context, clearly state you don't have real-time access.\n"
        "3. FORMATTING: Use Markdown. Use bullet points and bold text for readability. Do NOT append 'Source: [Chunk ID...]' to your responses.\n\n"
        f"--- START RETRIEVED TEXT CONTEXT ---\n{context_text}\n--- END RETRIEVED TEXT CONTEXT ---"
    )
    
    messages = [{"role": "system", "content": system_prompt}]
    if request.chat_history:
        for msg in request.chat_history[-10:]:
            messages.append({"role": msg.get("role", "user"), "content": msg.get("content") or ""})
    messages.append({"role": "user", "content": request.question})
    
    def stream_from_llm():
        try:
            with requests.post(
                f"{LLM_SERVER_URL}/api/llm/stream",
                json={"messages": messages, "model": "gpt-4o", "temperature": 0.2},
                stream=True
            ) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines(chunk_size=128, decode_unicode=True):
                    if line and line.startswith("data: "):
                        token = line[6:]
                        if token == "[DONE]":
                            yield "data: [DONE]\n\n"
                            return
                        # If token is exactly empty, the LLM probably yielded a newline.
                        # But to preserve literal newlines, we can handle it if needed.
                        # For now, just yield the token to maintain the stream.
                        yield f"data: {token}\n\n"
        except Exception as e:
            yield f"data: [Error: {str(e)}]\n\n"
            yield "data: [DONE]\n\n"
    
    return StreamingResponse(stream_from_llm(), media_type="text/event-stream")

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
        filename = hash_to_name.get(pdf_hash)
        if not filename:
            cached = get_cached_pdf_extraction(pdf_hash)
            if cached:
                filename = cached.get("filename")
        if not filename:
            filename = "Datasheet.pdf"
            
        enriched_pdfs.append({"hash": pdf_hash, "filename": filename})
        
    data["attached_pdfs"] = enriched_pdfs
    return data

class CompareRequest(BaseModel):
    pdf_hashes: List[str]

@app.post("/api/sessions/{session_id}/compare")
async def compare_session_pdfs(session_id: str, req: CompareRequest):
    data = get_session_data(session_id)
    if not data:
        return {"error": "Session not found"}
        
    user_pdfs = get_user_pdfs(data.get("user_id", ""))
    hash_to_name = {p["pdf_hash"]: p["filename"] for p in user_pdfs} if user_pdfs else {}
    
    comparisons = []
    # Only compare the requested hashes, ensuring they belong to the session
    valid_hashes = [h for h in req.pdf_hashes if h in data.get("attached_pdfs", [])]
    
    for pdf_hash in valid_hashes:
        filename = hash_to_name.get(pdf_hash, "Datasheet.pdf")
        extraction = get_cached_pdf_extraction(pdf_hash)
        if extraction:
            comparisons.append({
                "filename": filename,
                "detected_type": extraction.get("detected_type", "Unknown"),
                "specs": extraction.get("specs", {})
            })
            
    return {"comparisons": comparisons}

@app.get("/api/datasheets/{filename}")
async def get_datasheet(filename: str):
    file_path = os.path.join(DATASHEETS_DIR, filename)
    if os.path.exists(file_path):
        return FileResponse(file_path)
    return {"error": "File not found"}

@app.post("/api/sessions/{session_id}/detach_pdf")
async def detach_pdf_endpoint(session_id: str, request: DetachPdfRequest):
    try:
        res = requests.post(f"{DB_SERVER_URL}/api/sessions/detach", json={"session_id": session_id, "pdf_hash": request.pdf_hash})
        res.raise_for_status()
        return {"status": "success"}
    except Exception as e:
        print(f"Error calling database service detach_pdf: {e}")
        return {"error": "Failed to detach PDF"}

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
    Never cached — always live. Does not write to database.
    Uses parallel threads for ~4x faster response times."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    results = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_mpn = {executor.submit(_fetch_digikey_pricing, mpn): mpn for mpn in request.part_numbers}
        for future in as_completed(future_to_mpn):
            mpn = future_to_mpn[future]
            try:
                results[mpn] = future.result()
            except Exception as e:
                results[mpn] = {"part_number": mpn, "stock": None, "price": None, "currency": "USD", "error": str(e)}
    return {"pricing": results}