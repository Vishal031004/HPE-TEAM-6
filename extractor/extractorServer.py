import os
import sys
from typing import List, Dict, Any, Union
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv

# Load environment variables from local .env file
load_dotenv()

from extractor import (
    parse_datasheet_chunks,
    parse_datasheet_staged,
    rerank_chunks_cross_encoder,
    reformulate_query,
    route_user_intent,
    answer_rag_question
)

app = FastAPI(
    title="HPE Component Extractor Microservice",
    description="Microservice providing API endpoints for PDF spec extraction, intent routing, cross-encoder reranking, and RAG QA.",
    version="1.0.0"
)

# Pydantic Schemas for Request Bodies
class ParseChunksRequest(BaseModel):
    structured_pages: List[Dict[str, Any]]
    required_features: List[str]
    market_competitors: List[Dict[str, Any]]
    component_name: str = "Unknown Part"

class ParseStagedRequest(BaseModel):
    filepath: str
    component_type: str
    required_features: List[str]
    market_competitors: List[Dict[str, Any]]
    component_name: str = "Unknown Part"
    chunk_size: int = 5

class RerankRequest(BaseModel):
    query: str
    chunks: List[Dict[str, Any]]
    top_k: int = 5

class ReformulateRequest(BaseModel):
    query: str
    chat_history: List[Dict[str, Any]]
    active_file: str = None

class RouteIntentRequest(BaseModel):
    query: str
    chat_history: List[Dict[str, Any]]

class AnswerRagRequest(BaseModel):
    query: str
    retrieved_chunks: List[Dict[str, Any]]
    chat_history: Union[List[Dict[str, Any]], None] = None
    is_global: bool = False

#checking if the server is up
@app.get("/")
def test():
    return {"message": "Extractor Microservice is up and running!"}

# Extractor Service Endpoints
@app.post("/api/extractor/parse_chunks")
def parse_chunks_endpoint(request: ParseChunksRequest):
    try:
        specs = parse_datasheet_chunks(
            structured_pages=request.structured_pages,
            required_features=request.required_features,
            market_competitors=request.market_competitors,
            component_name=request.component_name
        )
        return specs
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/extractor/parse_staged")
def parse_staged_endpoint(request: ParseStagedRequest):
    try:
        specs = parse_datasheet_staged(
            filepath=request.filepath,
            component_type=request.component_type,
            required_features=request.required_features,
            market_competitors=request.market_competitors,
            component_name=request.component_name,
            chunk_size=request.chunk_size
        )
        return specs
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/extractor/rerank")
def rerank_endpoint(request: RerankRequest):
    try:
        reranked = rerank_chunks_cross_encoder(
            query=request.query,
            chunks=request.chunks,
            top_k=request.top_k
        )
        return reranked
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/extractor/reformulate")
def reformulate_endpoint(request: ReformulateRequest):
    try:
        query = reformulate_query(
            query=request.query,
            chat_history=request.chat_history,
            active_file=request.active_file
        )
        return {"query": query}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/extractor/route_intent")
def route_intent_endpoint(request: RouteIntentRequest):
    try:
        intent = route_user_intent(
            query=request.query,
            chat_history=request.chat_history
        )
        return {"intent": intent}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/extractor/answer_rag")
def answer_rag_endpoint(request: AnswerRagRequest):
    try:
        answer = answer_rag_question(
            query=request.query,
            retrieved_chunks=request.retrieved_chunks,
            chat_history=request.chat_history,
            is_global=request.is_global
        )
        return {"answer": answer}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Entry point for direct execution
if __name__ == "__main__":
    import uvicorn
    # Default port for extractor microservice is 8085
    uvicorn.run("extractorServer:app", host="0.0.0.0", port=8085, reload=True)
