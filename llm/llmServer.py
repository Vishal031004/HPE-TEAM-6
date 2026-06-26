import os
import sys
from typing import List, Dict, Any, Union, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv

# Load environment variables from local .env file
load_dotenv()

# Ensure the core/llm directory is in the import path
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from llm import generate_text, generate_from_image, get_embeddings

app = FastAPI(
    title="HPE Component LLM Microservice",
    description="Microservice providing centralized API endpoints for OpenAI text generation, vision analysis, and embeddings.",
    version="1.0.0"
)

# Pydantic Schemas for Request Bodies
class GenerateTextRequest(BaseModel):
    messages: Optional[List[Dict[str, Any]]] = None
    prompt: Optional[str] = None
    system_instruction: Optional[str] = None
    model: str = "gpt-4o"
    json_mode: bool = False
    temperature: float = 0.0
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None

class GenerateFromImageRequest(BaseModel):
    prompt: str
    image_b64: str
    model: str = "gpt-4o"
    temperature: float = 0.0
    json_mode: bool = False

class EmbeddingsRequest(BaseModel):
    input_data: Union[str, List[str]]
    model: str = "text-embedding-3-small"

# Checking if the server is up
@app.get("/")
def test():
    return {"message": "LLM Microservice is up and running!"}

# LLM Service Endpoints
@app.post("/api/llm/generate_text")
def generate_text_endpoint(request: GenerateTextRequest):
    try:
        result = generate_text(
            messages=request.messages,
            prompt=request.prompt,
            system_instruction=request.system_instruction,
            model=request.model,
            json_mode=request.json_mode,
            temperature=request.temperature,
            tools=request.tools,
            tool_choice=request.tool_choice
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/llm/generate_from_image")
def generate_from_image_endpoint(request: GenerateFromImageRequest):
    try:
        content = generate_from_image(
            prompt=request.prompt,
            image_b64=request.image_b64,
            model=request.model,
            temperature=request.temperature,
            json_mode=request.json_mode
        )
        return {"content": content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/llm/embeddings")
def embeddings_endpoint(request: EmbeddingsRequest):
    try:
        embeddings = get_embeddings(
            input_data=request.input_data,
            model=request.model
        )
        return {"embeddings": embeddings}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    # Default port for LLM microservice is 8086
    uvicorn.run("llmServer:app", host="127.0.0.1", port=8086, reload=True)
