
The system consists of five distinct services communicating over HTTP REST APIs:

    Client[Web Browser] -->|Port 8000| MainApp[main-app]
    MainApp -->|Port 8081| DBService[database]
    MainApp -->|Port 8085| Extractor[extractor]
    MainApp -->|Port 8084| PDFProcessor[pdf_processor]
    Extractor -->|Port 8084| PDFProcessor
    Extractor -->|Port 8086| LLMService[llm]
    PDFProcessor -->|Port 8086| LLMService
    DBService -->|Port 8086| LLMService


1. Main Orchestrator (`main-app`)
Path: 'main-app/.env'
Default Port: 8000 (FastAPI)
Purpose: Handles the web dashboard, user authentication gateway, and orchestrates calls across other microservices.

Variable Name: **DB_SERVER_URL**
Type: URL
Example Value: http://127.0.0.1:8081
Description: REST URL of the Database Service

Variable Name: **EXTRACTOR_SERVER_URL**
Type: URL
Example Value: http://127.0.0.1:8085
Description: REST URL of the Extractor Service

Variable Name: **PDF_PROCESSOR_SERVER_URL**
Type: URL
Example Value: http://127.0.0.1:8084
Description: REST URL of the PDF Processor Service

Variable Name: **DATASHEETS_DIR**
Type: Path
Example Value: C:/projects/HPE-TEAM-6/main-app/datasheets
Description: Absolute path of the folder where uploaded PDFs are stored

2. Centralized LLM Service ('llm')
Path: 'llm/.env'
Default Port: 8086
Purpose: Central gateway for all OpenAI API calls (text completions, embeddings, and vision processing). No other service talks to OpenAI directly.

Variable Name: **OPENAI_API_KEY**
Type: String
Example Value: sk-proj-...
Description: Your private OpenAI API Key

3. Database & Caching Service ('database')
Path: 'database/.env'
Default Port: 8081
Purpose: Manages MongoDB interactions, vector search, RAG chunk metadata, user authentication state, and DigiKey access token caches.

Variable Name: **MONGO_URI**
Type: Connection String
Example Value: mongodb+srv://...
Description: MongoDB connection string

Variable Name: **DIGIKEY_CLIENT_ID**
Type: String
Example Value: zXOQ75gd...
Description: Developer API ID from DigiKey Portal

Variable Name: **DIGIKEY_CLIENT_SECRET**
Type: String
Example Value: mfb7qJnxx...
Description: Developer API Secret from DigiKey Portal

Variable Name: **LLM_SERVER_URL**
Type: URL
Example Value: http://127.0.0.1:8086
Description: REST URL of the LLM Service (used for generating vector embeddings)

4. PDF Processor Service ('pdf_processor')
Path: 'pdf_processor/.env'
Default Port: 8084
Purpose: Performs text extraction, layout parsing, and page rendering of PDF documents.

Variable Name: **LLM_SERVER_URL**
Type: URL
Example Value: http://127.0.0.1:8086
Description: REST URL of the LLM Service (used for page type analysis)

Variable Name: **DATASHEETS_DIR**
Type: Path
Example Value: C:/projects/HPE-TEAM-6/main-app/datasheets
Description: Path to the shared datasheet mount directory

5. Extractor Service ('extractor')
Path: 'extractor/.env'
Default Port: 8085
Purpose: Runs the multi-stage parametric extraction pipelines, RAG context generation, ms-marco reranking, and conversational agents.

Variable Name: **LLM_SERVER_URL**
Type: URL
Example Value: http://127.0.0.1:8086
Description: REST URL of the LLM Service

Variable Name: **PDF_PROCESSOR_SERVER_URL**
Type: URL
Example Value: http://127.0.0.1:8084
Description: REST URL of the PDF Processor Service


[!IMPORTANT]
**Shared File System Alignment:**  
The `DATASHEETS_DIR` variable must point to the same directory on your machine (Option A) or target the same mounted persistent volume in a containerized setup (Option B). If these do not align, the `pdf_processor` will throw a `500 FileNotFoundError` when trying to open files uploaded by `main-app`.

