import os
import re
import json
import hashlib
import base64
import pdfplumber
import fitz
from typing import List, Dict, Any, Optional
from openai import OpenAI

# Initialize OpenAI client (Unifying the stack!)
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))


def _normalize_detected_type(raw_type: str, available_types: Optional[List[str]], early_text: str) -> str:
    """Maps LLM output and common datasheet wording to canonical type names."""
    available_types = available_types or []
    if raw_type in available_types:
        return raw_type

    alias_map = {
        "gyroscope": "Gyroscope",
        "gyro": "Gyroscope",
        "angular rate": "Gyroscope",
        "accelerometer": "Accelerometer",
        "acceleration sensor": "Accelerometer",
        "pressure sensor": "Pressure Sensor",
        "barometric": "Pressure Sensor",
        "temperature sensor": "Temperature Sensor",
        "thermal sensor": "Temperature Sensor",
        "ldo": "LDO Regulator",
        "buck": "Buck Converter",
        "op amp": "Op-Amp",
        "op-amp": "Op-Amp",
    }

    candidates = [str(raw_type or "").lower(), str(early_text or "").lower()]
    for text in candidates:
        for token, canonical in alias_map.items():
            if token in text:
                if available_types:
                    if canonical in available_types:
                        return canonical
                else:
                    return canonical

    raw_clean = str(raw_type or "").strip()
    if not raw_clean or raw_clean.lower() == "unknown":
        return "Unknown"

    if available_types:
        return raw_clean if raw_clean in available_types else "Unknown"

    return raw_clean


def _extract_early_pdf_text(pdf_path: str, max_pages: int = 2) -> str:
    """
    Extracts text from the first few pages using resilient fallbacks.
    Avoids PyPDF2 AES decryption dependency issues.
    """
    chunks = []

    # Primary: pdfplumber
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages[:max_pages]:
                txt = page.extract_text() or ""
                if txt.strip():
                    chunks.append(txt)
        if chunks:
            return "\n\n".join(chunks)
    except Exception as e:
        print(f"⚠️ pdfplumber read failed during detection: {e}")

    # Fallback: PyMuPDF
    try:
        doc = fitz.open(pdf_path)
        try:
            for i in range(min(max_pages, len(doc))):
                txt = doc[i].get_text("text") or ""
                if txt.strip():
                    chunks.append(txt)
        finally:
            doc.close()
        if chunks:
            return "\n\n".join(chunks)
    except Exception as e:
        print(f"⚠️ PyMuPDF read failed during detection: {e}")

    return ""

def detect_component_type(pdf_path: str, available_types: Optional[List[str]] = None) -> str:
    """
    Reads Page 1 of the PDF and uses OpenAI to classify the component type.
    """
    print(f"\n🔍 [Stage 1] Analyzing Page 1 to detect component type...")
    try:
        early_text = _extract_early_pdf_text(pdf_path, max_pages=2)
        if not early_text.strip():
            print("❌ Error detecting component: could not extract readable text from first pages")
            return "Unknown"
            
        if available_types:
            prompt = f"""
            You are a highly precise hardware engineering assistant. Read the following text from the first pages of a datasheet.
            Classify this component into the MOST SPECIFIC category possible from the provided list.

            Available Categories:
            {json.dumps(available_types)}

            Datasheet Text (Snippet):
            {early_text[:4000]}

            Output valid JSON with a single key 'detected_type' containing the exact matching string from the Available Categories.
            If nothing matches, output 'Unknown'.
            """
        else:
            prompt = f"""
            You are a highly precise hardware engineering assistant. Read the following text from the first pages of a datasheet.
            Identify the MOST SPECIFIC component category (for example: Gyroscope, LDO Regulator, Buck Converter, Op-Amp, MOSFET, Microcontroller, Pressure Sensor, etc.).

            Datasheet Text (Snippet):
            {early_text[:4000]}

            Output valid JSON with one key: 'detected_type'.
            Return a concise category string, not a full sentence.
            If truly unclear, output 'Unknown'.
            """
        
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You output strict JSON only."},
                {"role": "user", "content": prompt}
            ],
            temperature=0,
            response_format={"type": "json_object"}
        )
        
        result = json.loads(response.choices[0].message.content)
        raw_detected_type = str(result.get("detected_type", "Unknown")).strip()
        detected_type = _normalize_detected_type(raw_detected_type, available_types, early_text)
        
        print(f"🎯 Component Detected: [ {detected_type} ]")
        return detected_type

    except Exception as e:
        print(f"❌ Error detecting component: {e}")
        return "Unknown"


def parse_pdf_to_structured_pages(filepath: str) -> List[Dict[str, Any]]:
    """
    Converts a raw PDF into an intermediate JSON-like structure.
    Extracts text and carefully formats 2D tables per page.
    """
    print(f"\n📄 [Stage 2] Parsing raw PDF into structured memory...")
    structured_pages = []

    try:
        with pdfplumber.open(filepath) as pdf:
            for page_num, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                raw_tables = page.extract_tables()
                
                formatted_tables = []
                for table in raw_tables:
                    if not table:
                        continue
                    # Clean and format the table into a markdown-like grid for the LLM
                    table_str = ""
                    for row in table:
                        clean_row = [str(cell).replace('\n', ' ').strip() if cell else "" for cell in row]
                        table_str += " | ".join(clean_row) + "\n"
                    formatted_tables.append(table_str)

                structured_pages.append({
                    "page_num": page_num + 1,
                    "text": text,
                    "tables": formatted_tables
                })
                
        print(f"✅ Successfully structured {len(structured_pages)} pages.")
        return structured_pages

    except Exception as e:
        print(f"❌ Error parsing PDF: {e}")
        return []


def pdf_hash(filepath: str) -> str:
    """Returns SHA-256 hash for a PDF file to use as a cache key."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_pdf_chunk_to_structured_pages(
    filepath: str,
    start_page: int = 0,
    end_page: int = 25,
):
    """
    Extracts structured page data only for [start_page, end_page).
    Returns (structured_pages, total_pages).
    """
    structured_pages = []

    with pdfplumber.open(filepath) as pdf:
        total_pages = len(pdf.pages)
        page_slice = pdf.pages[start_page:min(end_page, total_pages)]

        for i, page in enumerate(page_slice):
            page_num = start_page + i + 1
            text = page.extract_text() or ""
            raw_tables = page.extract_tables() or []

            formatted_tables = []
            for table in raw_tables:
                if not table:
                    continue
                table_str = ""
                for row in table:
                    clean_row = [str(cell).replace("\n", " ").strip() if cell else "" for cell in row]
                    table_str += " | ".join(clean_row) + "\n"
                formatted_tables.append(table_str)

            structured_pages.append({
                "page_num": page_num,
                "text": text,
                "tables": formatted_tables,
            })

    return structured_pages, total_pages


def get_figure_pages(filepath: str, start_page: int = 0, end_page: int = 25) -> List[int]:
    """Returns 1-indexed page numbers in range [start_page, end_page) containing images."""
    figure_pages = []
    doc = fitz.open(filepath)
    try:
        for i in range(start_page, min(end_page, len(doc))):
            if doc[i].get_images(full=True):
                figure_pages.append(i + 1)
    finally:
        doc.close()
    return figure_pages


def render_page_to_base64(filepath: str, page_num_1indexed: int, dpi: int = 150) -> str:
    """Renders a PDF page to PNG and returns base64 content for vision models."""
    doc = fitz.open(filepath)
    try:
        page = doc[page_num_1indexed - 1]
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat)
        img_bytes = pix.tobytes("png")
        return base64.standard_b64encode(img_bytes).decode("utf-8")
    finally:
        doc.close()


def retrieve_feature_context(structured_pages: List[Dict[str, Any]], feature_name: str, top_k: int = 2) -> str:
    """
    RAG Retrieval Engine: Hunts through the structured pages for the specific feature.
    Returns a highly concentrated prompt context containing only the relevant tables/text.
    """
    # 1. Clean the feature name to generate search keywords
    # Converts "Voltage - Output (Min/Fixed)" -> ["voltage", "output", "min", "fixed"]
    clean_string = re.sub(r'[^a-zA-Z0-9\s]', ' ', feature_name).lower()
    keywords = [word for word in clean_string.split() if len(word) > 2]
    
    scored_pages = []

    for page in structured_pages:
        score = 0
        page_text_lower = page["text"].lower()
        
        # Check text
        for kw in keywords:
            if kw in page_text_lower:
                score += 1
                
        # Check tables (tables are much more valuable for spec extraction)
        for table in page["tables"]:
            table_lower = table.lower()
            for kw in keywords:
                if kw in table_lower:
                    score += 3 # Weight tables heavily

        if score > 0:
            scored_pages.append({"score": score, "data": page})

    # Sort pages by relevance
    scored_pages.sort(key=lambda x: x["score"], reverse=True)
    best_pages = [p["data"] for p in scored_pages[:top_k]]

    # 2. Build the LLM Context String
    if not best_pages:
        return "" # If completely missing, return empty so LLM skips it
        
    context_blocks = []
    for p in best_pages:
        block = f"--- PAGE {p['page_num']} ---\n"
        
        if p["tables"]:
            block += "TABLES ON THIS PAGE:\n"
            for t in p["tables"]:
                block += f"{t}\n"
                
        block += f"TEXT ON THIS PAGE:\n{p['text'][:1500]}...\n" # Cap text length to save tokens
        context_blocks.append(block)

    return "\n".join(context_blocks)