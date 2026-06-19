# HPE Component Extractor Microservice API Specification

The Extractor Microservice manages all heavy LLM interactions, surgical spec extraction, graph page vision analysis, intent classification, query reformulation, and cross-encoder semantic reranking.

* **Default Port**: `8082`
* **Base URL**: `http://localhost:8082`

---

## 🤖 API Endpoints

### 1. Route User Intent
* **Endpoint**: `POST /api/extractor/route_intent`
* **Request Body**:
  ```json
  {
    "query": "string",
    "chat_history": [
      {
        "role": "user",
        "content": "string"
      }
    ]
  }
  ```
* **Description**: The agentic classifier routing brain. Evaluates user intent to route it either for:
  - `information_retrieval` (reading & explaining uploaded datasheets via local RAG Q&A)
  - `find_alternatives` (performing market research on DigiKey/competitors)
* **Response**:
  ```json
  {
    "intent": "information_retrieval"
  }
  ```

### 2. Reformulate Conversational Query
* **Endpoint**: `POST /api/extractor/reformulate`
* **Request Body**:
  ```json
  {
    "query": "string",
    "chat_history": [
      {
        "role": "string",
        "content": "string"
      }
    ]
  }
  ```
* **Description**: Contextualizes pronouns, shorthand, or indirect references (e.g., "what is its dropout voltage?") into standalone search queries based on active session history.
* **Response**:
  ```json
  {
    "query": "What is the dropout voltage of MIC5365?"
  }
  ```

### 3. Cross-Encoder Chunk Reranking
* **Endpoint**: `POST /api/extractor/rerank`
* **Request Body**:
  ```json
  {
    "query": "string",
    "chunks": [
      {
        "chunk_id": "string",
        "text": "string",
        "page": 1,
        "filename": "string"
      }
    ],
    "top_k": 5
  }
  ```
* **Description**: Performs high-accuracy neural reranking of vector-retrieved text context chunks using `sentence-transformers/cross-encoder/ms-marco-MiniLM-L-6-v2`. Reranking is loaded lazily on the first request to preserve memory on start.
* **Response**:
  ```json
  [
    {
      "chunk_id": "string",
      "text": "string",
      "page": 1,
      "filename": "string",
      "cross_score": 0.941
    }
  ]
  ```

### 4. Answer RAG Question
* **Endpoint**: `POST /api/extractor/answer_rag`
* **Request Body**:
  ```json
  {
    "query": "string",
    "retrieved_chunks": [
      {
        "chunk_id": "string",
        "text": "string",
        "page": 1,
        "filename": "string",
        "cross_score": 0.94
      }
    ],
    "chat_history": [
      {
        "role": "string",
        "content": "string"
      }
    ],
    "is_global": false
  }
  ```
* **Description**: Invokes GPT-4o with strict grounding rules to produce a technically precise, memory-informed, and cited answer based on the provided reranked snippets. When `is_global` is set to `true`, the prompt triggers multi-document synthesis to contrast specifications across multiple datasheets.
* **Response**:
  ```json
  {
    "answer": "According to [chunk-1] (Page 2), the MIC5365 has a maximum output voltage of..."
  }
  ```

### 5. Parse Datasheet Chunk
* **Endpoint**: `POST /api/extractor/parse_chunks`
* **Request Body**:
  ```json
  {
    "structured_pages": [
      {
        "page_num": 1,
        "text": "string",
        "tables": ["string"]
      }
    ],
    "required_features": ["Dropout Voltage", "Output Current"],
    "market_competitors": [
      {
        "part_number": "MCP1700",
        "specs": {
          "Dropout Voltage": "178 mV"
        }
      }
    ],
    "component_name": "mic5365.pdf"
  }
  ```
* **Description**: Scans a specific sequence of pages using GPT-4o JSON mode, maps features to standardized industry values, and checks that raw matching context is present in the text to validate against hallucination.
* **Response**:
  ```json
  {
    "Dropout Voltage": "200 mV",
    "Output Current": "150 mA"
  }
  ```

### 6. Staged Datasheet Parser
* **Endpoint**: `POST /api/extractor/parse_staged`
* **Request Body**:
  ```json
  {
    "filepath": "string",
    "component_type": "string",
    "required_features": ["string"],
    "market_competitors": [{}],
    "component_name": "string",
    "chunk_size": 5
  }
  ```
* **Description**: Orchestrates sliding-window parsing over a local PDF datasheet. For each window, it attempts standard LLM text/table extraction. If specs are still missing, it falls back to GPT-4o Vision scans of graphs/figures in that window before advancing to the next sliding window.
* **Response**:
  ```json
  {
    "Dropout Voltage": "200 mV",
    "Output Current": "150 mA"
  }
  ```
