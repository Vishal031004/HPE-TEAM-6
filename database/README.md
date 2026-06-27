# HPE Component Database Microservice API Specification

The Database Microservice manages all MongoDB, session history, DigiKey API token caching, datasheet specification caching, and vector indexing operations.

* **Default Port**: `8081`
* **Base URL**: `http://localhost:8081`

---

## 🔑 1. User Management APIs

### Register User
* **Endpoint**: `POST /api/register`
* **Request Body**:
  ```json
  {
    "username": "string",
    "password": "string"
  }
  ```
* **Description**: Registers a new user with hashed passwords in the MongoDB `users` collection.
* **Response**:
  ```json
  {
    "message": "User registered successfully"
  }
  ```
  *(or `{"error": "Username already exists"}`)*

### Login User
* **Endpoint**: `POST /api/login`
* **Request Body**:
  ```json
  {
    "username": "string",
    "password": "string"
  }
  ```
* **Description**: Authenticates a user and returns their database UUID.
* **Response**:
  ```json
  {
    "user_id": "string-uuid",
    "message": "Login successful"
  }
  ```

### Associate PDF with User
* **Endpoint**: `POST /api/user/pdf`
* **Request Body**:
  ```json
  {
    "user_id": "string",
    "pdf_hash": "string",
    "filename": "string"
  }
  ```
* **Description**: Records that a user has uploaded/owns a specific PDF.
* **Response**: `{"status": "success"}`

### Get User Uploaded PDFs
* **Endpoint**: `GET /api/user/{user_id}/pdfs`
* **Description**: Returns list of filenames and hashes associated with the user.
* **Response**:
  ```json
  {
    "pdfs": [
      {
        "filename": "mic5365.pdf",
        "pdf_hash": "abc123hash..."
      }
    ]
  }
  ```

### Get User PDF Hashes
* **Endpoint**: `GET /api/user/{user_id}/pdf_hashes`
* **Description**: Returns a clean list of only SHA-256 hashes of all PDFs owned by the user.
* **Response**:
  ```json
  {
    "pdf_hashes": ["abc123hash1", "def456hash2"]
  }
  ```

---

## 💬 2. Session Management APIs

### Create Chat Session
* **Endpoint**: `POST /api/sessions/create`
* **Request Body**:
  ```json
  {
    "user_id": "string",
    "session_name": "string"
  }
  ```
* **Description**: Initializes a new chat session.
* **Response**: `{"session_id": "session-uuid"}`

### Get User Sessions
* **Endpoint**: `GET /api/user/{user_id}/sessions`
* **Description**: Retrieves all chat sessions created by the user, ordered by creation date (pinned sessions are prioritized).
* **Response**:
  ```json
  {
    "sessions": [
      {
        "session_id": "uuid",
        "session_name": "My Workspace",
        "is_pinned": false,
        "attached_pdfs": ["hash1"]
      }
    ]
  }
  ```

### Attach PDF to Session
* **Endpoint**: `POST /api/sessions/attach`
* **Request Body**:
  ```json
  {
    "session_id": "string",
    "pdf_hash": "string"
  }
  ```
* **Description**: Associates an uploaded PDF to the active chat context session.
* **Response**: `{"status": "success"}`

### Get Session Data
* **Endpoint**: `GET /api/sessions/{session_id}`
* **Description**: Retrieves session meta-information, attached PDF lists, and full chat message history.
* **Response**:
  ```json
  {
    "session_id": "uuid",
    "session_name": "My Session",
    "messages": [
      {
        "role": "user",
        "content": "Compare features"
      }
    ],
    "attached_pdfs": ["hash1"]
  }
  ```

### Save Session Messages
* **Endpoint**: `POST /api/sessions/save_messages`
* **Request Body**:
  ```json
  {
    "session_id": "string",
    "new_messages": [
      {
        "role": "string",
        "content": "string"
      }
    ]
  }
  ```
* **Description**: Appends new user or assistant dialogue entries to the session history.
* **Response**: `{"status": "success"}`

### Delete Chat Session
* **Endpoint**: `DELETE /api/sessions/{session_id}`
* **Description**: Permanently removes a chat session and its history.
* **Response**: `{"status": "success"}`

### Rename Chat Session
* **Endpoint**: `PATCH /api/sessions/{session_id}/rename`
* **Request Body**:
  ```json
  {
    "new_name": "string"
  }
  ```
* **Response**: `{"status": "success"}`

### Toggle Pin Session
* **Endpoint**: `PATCH /api/sessions/{session_id}/pin`
* **Description**: Pins or unpins the chat session in the sidebar.
* **Response**: `{"status": "success"}`

---

## ⚡ 3. Spec Extraction Cache APIs

### Get Cached PDF Extraction
* **Endpoint**: `GET /api/extraction/{pdf_hash}`
* **Description**: Looks up whether the component specifications for the given PDF SHA-256 have already been extracted.
* **Response**:
  ```json
  {
    "pdf_hash": "hash...",
    "filename": "mic5365.pdf",
    "detected_type": "LDO Regulator",
    "extracted_specs": {
      "Dropout Voltage": "200 mV",
      "Output Current": "150 mA"
    }
  }
  ```

### Save PDF Extraction
* **Endpoint**: `POST /api/extraction`
* **Request Body**:
  ```json
  {
    "pdf_hash": "string",
    "filename": "string",
    "detected_type": "string",
    "extracted_specs": {}
  }
  ```
* **Description**: Saves newly extracted specifications to MongoDB to avoid repeating heavy LLM extraction passes.
* **Response**: `{"status": "success"}`

---

## 🏷️ 4. DigiKey Caching APIs

### Get DigiKey Token
* **Endpoint**: `GET /api/digikey/token`
* **Description**: Returns the active OAuth2 access token for DigiKey API. If expired or missing, it triggers auto-renewal transparently.
* **Response**: `{"access_token": "token-string..."}`

### Get or Build Component Category Data
* **Endpoint**: `POST /api/component_data`
* **Request Body**:
  ```json
  {
    "component_type": "string"
  }
  ```
* **Description**: Returns the standard specification schema and retrieves up to 20 top competitor components from DigiKey for similarity ranking.
* **Response**:
  ```json
  {
    "features": ["Dropout Voltage", "Output Current"],
    "competitors": [
      {
        "part_number": "MCP1700",
        "specs": {
          "Dropout Voltage": "178 mV"
        }
      }
    ]
  }
  ```

---

## 🔍 5. Vector search & RAG Indexing APIs

### Check if PDF Has Chunks
* **Endpoint**: `GET /api/rag/has_chunks/{pdf_hash}`
* **Description**: Returns true if the PDF has already been processed, chunked, and embedded into the MongoDB vector index.
* **Response**: `{"has_chunks": true}`

### Store RAG Chunks
* **Endpoint**: `POST /api/rag/store_chunks`
* **Request Body**:
  ```json
  {
    "chunks": [
      {
        "chunk_id": "string",
        "text": "string",
        "page": 1,
        "embeddings": [0.1, 0.2, ...]
      }
    ],
    "pdf_hash": "string"
  }
  ```
* **Description**: Saves vector embedding chunks to the RAG vector collection.
* **Response**: `{"status": "success"}`

### Retrieve RAG Context
* **Endpoint**: `POST /api/rag/retrieve`
* **Request Body**:
  ```json
  {
    "query": "string",
    "filename": "string" (optional),
    "pdf_sha256": "string" or ["list", "of", "strings"] (optional),
    "top_k": 15
  }
  ```
* **Description**: Matches queries using cosine similarity against the vector index, scoped globally or limited to specified file hashes.
* **Response**:
  ```json
  {
    "results": [
      {
        "chunk_id": "chunk-1",
        "text": "The MIC5365 features a low dropout voltage...",
        "page": 2,
        "score": 0.892,
        "filename": "mic5365.pdf"
      }
    ]
  }
  ```
