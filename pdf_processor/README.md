# HPE Component PDF Processor Microservice API Specification

The PDF Processor Microservice handles raw PDF text extraction, metadata extraction, structural page chunking for RAG ingestion, figure detection, page rendering (DPI to base64 images), and automated component type detection.

* **Default Port**: `8084`
* **Base URL**: `http://localhost:8084`

---

## 🤖 API Endpoints

### 1. Detect Component Type
* **Endpoint**: `POST /api/pdf/detect`
* **Request Body**:
  ```json
  {
    "pdf_path": "string",
    "available_types": ["LDO Regulator", "Buck Converter", ...] (optional)
  }
  ```
* **Description**: Extracts the first 2 pages of the PDF and uses LLM classification to detect and normalize the component type based on the available categories.
* **Response**:
  ```json
  {
    "detected_type": "LDO Regulator"
  }
  ```

### 2. Compute PDF Hash
* **Endpoint**: `POST /api/pdf/hash`
* **Request Body**:
  ```json
  {
    "filepath": "string"
  }
  ```
* **Description**: Computes a SHA-256 hash of the specified file to serve as a persistent unique cache key across microservices.
* **Response**:
  ```json
  {
    "pdf_hash": "4bfac948715dac62785985c00cf48d75ffc4dce3460c9f9c52c2446d318fab6e"
  }
  ```

### 3. Process PDF for RAG Chunks
* **Endpoint**: `POST /api/pdf/process_rag`
* **Request Body**:
  ```json
  {
    "filepath": "string",
    "filename": "string"
  }
  ```
* **Description**: Processes the PDF page-by-page. It performs hierarchical chunking by extracting and formatting 2D tables into markdown grids and paragraph blocks, returning them with metadata (source page, type) for embedding.
* **Response**:
  ```json
  [
    {
      "chunk_id": "page_1_table_0",
      "filename": "mic5365.pdf",
      "page": 1,
      "type": "table",
      "text": "--- TABLE ON PAGE 1 ---\n..."
    }
  ]
  ```

### 4. Parse PDF Chunks
* **Endpoint**: `POST /api/pdf/parse_chunks`
* **Request Body**:
  ```json
  {
    "filepath": "string",
    "start_page": 0,
    "end_page": 25
  }
  ```
* **Description**: Extracts structured page text and formatted tables only for the specified slice range `[start_page, end_page)`.
* **Response**:
  ```json
  {
    "structured_pages": [
      {
        "page_num": 1,
        "text": "...",
        "tables": ["..."]
      }
    ],
    "total_pages": 8
  }
  ```

### 5. Get Figure Pages
* **Endpoint**: `POST /api/pdf/figure_pages`
* **Request Body**:
  ```json
  {
    "filepath": "string",
    "start_page": 0,
    "end_page": 25
  }
  ```
* **Description**: Analyzes the page vector representations in PyMuPDF/fitz and returns the 1-indexed numbers of pages that contain figures or diagrams.
* **Response**:
  ```json
  {
    "figure_pages": [2, 3, 5]
  }
  ```

### 6. Render PDF Page to Base64
* **Endpoint**: `POST /api/pdf/render_page`
* **Request Body**:
  ```json
  {
    "filepath": "string",
    "page_num_1indexed": 1,
    "dpi": 150
  }
  ```
* **Description**: Renders a specific 1-indexed page of the PDF to a PNG image and encodes it in base64. Ideal for supplying graphs to Vision LLMs.
* **Response**:
  ```json
  {
    "image_b64": "iVBORw0KGgoAAAANSUhEUgAA..."
  }
  ```

### 7. Parse Structured PDF Pages
* **Endpoint**: `POST /api/pdf/parse_structured`
* **Request Body**:
  ```json
  {
    "filepath": "string"
  }
  ```
* **Description**: Parses all pages of the PDF to extract structured text and formatted tables.
* **Response**:
  ```json
  {
    "structured_pages": [
      {
        "page_num": 1,
        "text": "...",
        "tables": ["..."]
      }
    ]
  }
  ```
