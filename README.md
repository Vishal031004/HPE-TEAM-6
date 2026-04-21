# ⚡ Enterprise Hardware Components Assistant

An intelligent, hybrid Retrieval-Augmented Generation (RAG) pipeline that automates the engineering task of finding alternative electronic components. It reads raw PDF datasheets, dynamically discovers industry-standard specifications via the DigiKey API, extracts data with strict anti-hallucination guardrails, and mathematically ranks the best market alternatives.

---

## The Problem It Solves

Hardware engineers spend hours manually reading 40-page datasheets to find alternative parts when a component goes out of stock. Standard AI systems fail because they hallucinate values or cannot interpret complex table layouts.

This system solves that by treating the LLM strictly as a **semantic parser**, controlled by deterministic software logic, validation rules, and unit-aware mathematical engines.

---

## Key Features

* **Dynamic Schema Discovery**
  Automatically queries the DigiKey API, analyzes top competitors, and builds feature schemas dynamically (no hardcoding).

* **Hybrid RAG + Few-Shot Learning**
  Extracts only relevant sections from PDFs and injects real-world JSON examples to guide accurate LLM outputs.

* **Zero-Hallucination Validation Gate**
  Every extracted value is verified against the original PDF text using strict substring matching.

* **Unit-Aware Math Engine**
  Normalizes units (e.g., `500 mA → 0.5 A`) and calculates accurate similarity scores.

* **Weighted Ranking System**
  Generates a match score (0–100%) based on user-defined importance of features.

* **Production-Ready UI**
  Clean dark-mode interface with drag-and-drop support and interactive controls.

---

## System Architecture

1. **PDF Ingestion & Classification**
   Detects component type using LLM (e.g., MOSFET, Audio Codec)

2. **Market Intelligence Layer**
   Fetches competitor data from DigiKey and builds dynamic schemas

3. **Structured PDF Parsing**
   Converts unstructured text + tables into structured JSON format

4. **Feature Extraction (LLM)**
   Performs precise, context-aware extraction using RAG + few-shot prompts

5. **Validation Layer**
   Blocks hallucinated values via strict verification

6. **Similarity Engine**
   Computes weighted scores between input component and market alternatives

---

## Tech Stack

* **Backend:** Python, FastAPI
* **AI/LLM:** OpenAI API (GPT-4o)
* **Market Data:** DigiKey API
* **Database:** MongoDB
* **PDF Processing:** pdfplumber, PyPDF2
* **Frontend:** HTML, CSS, JavaScript

---

## Installation

### 1. Clone Repository

```bash
git clone https://github.com/Vishal031004/HPE-TEAM-6.git
cd HPE-TEAM-6
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Setup Environment Variables

Create a `.env` file:

```env
OPENAI_API_KEY=your_openai_key
MONGO_URI=your_mongodb_uri
DIGIKEY_CLIENT_ID=your_client_id
DIGIKEY_CLIENT_SECRET=your_client_secret
```

---

## Usage

### Run Web App

```bash
uvicorn app:app --reload
```

Open:
http://127.0.0.1:8000

---

### Run CLI Version

```bash
python run_test.py
```

Outputs:

```text
final_report.json
```

---

## Project Structure

```
hpe_team_6/
│
├── core/
│   ├── database.py
│   ├── extractor.py
│   ├── pdf_processor.py
│   ├── prompts.py
│   └── similarity.py
│
├── static/
│   └── index.html
│
├── app.py
├── run_test.py
├── requirements.txt
├── .env
└── README.md
```

---

## Key Highlights

* Built for **real-world hardware engineers**
* Combines **LLMs + deterministic validation**
* Eliminates hallucination risk
* Scalable and production-oriented design

---

## Authors

HPE Team 6
