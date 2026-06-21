# LLM Service

This is the decoupled LLM microservice for the HPE Datasheet Parsing project. It acts as the single gateway for all interactions with LLMs and embedding models, isolating direct API calls from the rest of the application.

## 🏗️ Architecture

By extracting direct OpenAI SDK imports from `pdf_processor`, `database`, and `extractor`, this service achieves:
- **Centralized OpenAI Management**: API key validation, rate-limiting, and error-handling reside in a single place.
- **Model Agnosticism**: Swapping to another LLM/Embedding provider (e.g., Google Gemini, Groq, or local LLaMA/Mistral models) only requires updating `llm.py` and `llmServer.py`.

---

## 🚀 Setup & Execution

### Prerequisites
Ensure your `.env` file in the root directory contains the `OPENAI_API_KEY` and the `LLM_SERVER_URL`:
```env
OPENAI_API_KEY="sk-..."
LLM_SERVER_URL="http://127.0.0.1:8086"
```

### Running the Server
To start the LLM server, run the following from the project root:
```bash
python core/llm/llmServer.py
```
By default, the server runs on **port 8086** (`http://127.0.0.1:8086`).

---

## 📡 API Endpoints

### 1. Test Endpoint
- **URL**: `/`
- **Method**: `GET`
- **Response**:
  ```json
  {"message": "LLM Microservice is up and running!"}
  ```

### 2. Generate Text
Used for standard text completion, chat generation, query reformulation, and intent routing.
- **URL**: `/api/llm/generate_text`
- **Method**: `POST`
- **Payload**:
  - `messages` *(optional)*: List of message dictionaries (`role` and `content`).
  - `prompt` *(optional)*: Direct prompt string.
  - `system_instruction` *(optional)*: Custom system message instruction.
  - `model`: Model identifier (defaults to `gpt-4o`).
  - `json_mode`: Forces output to be strict JSON (defaults to `false`).
  - `temperature`: Model temperature parameter (defaults to `0.0`).
- **Response**:
  ```json
  {"content": "..."}
  ```

### 3. Generate From Image (Vision)
Used for reading graphs and charts from rendered page images.
- **URL**: `/api/llm/generate_from_image`
- **Method**: `POST`
- **Payload**:
  - `prompt`: String instructions for the vision query.
  - `image_b64`: Base64 encoded string representing the image (PNG/JPEG).
  - `model`: Vision model identifier (defaults to `gpt-4o`).
  - `temperature`: Model temperature parameter (defaults to `0.0`).
  - `json_mode`: Forces output to be strict JSON (defaults to `false`).
- **Response**:
  ```json
  {"content": "..."}
  ```

### 4. Get Embeddings
Used to vectorize query texts and batched document chunks.
- **URL**: `/api/llm/embeddings`
- **Method**: `POST`
- **Payload**:
  - `input_data`: A single text string or list of text strings to embed.
  - `model`: Embedding model identifier (defaults to `text-embedding-3-small`).
- **Response**:
  ```json
  {"embeddings": [...]}  // float list for single string, list of lists for list input
  ```
