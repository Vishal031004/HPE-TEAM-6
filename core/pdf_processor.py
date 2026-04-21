import os
import re
import json
import pdfplumber
import PyPDF2
from typing import List, Dict, Any
from openai import OpenAI

# Initialize OpenAI client (Unifying the stack!)
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

def detect_component_type(pdf_path: str, available_types: List[str]) -> str:
    """
    Reads Page 1 of the PDF and uses OpenAI to classify the component type.
    """
    print(f"\n🔍 [Stage 1] Analyzing Page 1 to detect component type...")
    try:
        with open(pdf_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            page_1_text = reader.pages[0].extract_text()
            
        prompt = f"""
        You are a highly precise hardware engineering assistant. Read the following text from page 1 of a datasheet.
        Classify this component into the MOST SPECIFIC category possible from the provided list.
        
        Available Categories:
        {json.dumps(available_types)}
        
        Datasheet Text (Snippet):
        {page_1_text[:2000]}
        
        Output valid JSON with a single key 'detected_type' containing the exact matching string from the Available Categories. 
        If nothing matches, output 'Unknown'.
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
        detected_type = result.get("detected_type", "Unknown")
        
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