import os
import json
import pdfplumber
import PyPDF2
from groq import Groq

# Initialize Groq client
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

def detect_component_type(pdf_path, available_types):
    """
    Reads only Page 1 of the PDF and uses the LLM to classify the component.
    """
    print(f"\n🔍 Analyzing Page 1 to detect exact component type...")
    try:
        with open(pdf_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            page_1_text = reader.pages[0].extract_text()
            
        prompt = f"""
        You are a highly precise hardware engineering assistant. Read the following text from page 1 of a datasheet.
        Your job is to classify this component into the MOST SPECIFIC category possible from the provided list.
        
        Available Categories:
        {json.dumps(available_types)}
        
        Datasheet Text:
        {page_1_text[:2000]}
        
        You must output valid JSON with a single key 'detected_type' containing the exact matching string from the Available Categories list. 
        If nothing matches, output 'Unknown'.
        """
        
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
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


def score_and_chunk_pdf(filepath, target_features, max_pages=8):
    """
    Reads the PDF, scores each page and its tables based on the target features,
    and returns only the most relevant chunks of text/tables for the LLM.
    """
    print(f"\n📄 Scanning PDF and scoring pages based on {len(target_features)} target features...")
    
    # Clean the features for easy text matching (lowercase, remove extra spaces)
    lower_features = [str(f).lower().strip() for f in target_features]
    
    scored_pages = []

    try:
        with pdfplumber.open(filepath) as pdf:
            for page_num, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                tables = page.extract_tables()
                
                score = 0
                text_lower = text.lower()

                # ---------------------------------------------------------
                # 1. PAGE TEXT SCORING
                # ---------------------------------------------------------
                for feature in lower_features:
                    if feature in text_lower:
                        score += 20  
                
                if any(junk in text_lower for junk in ["revision history", "package outline", "tape and reel", "soldering footprint"]):
                    score -= 100

                # ---------------------------------------------------------
                # 2. TABLE SCORING
                # ---------------------------------------------------------
                formatted_tables = ""
                for table in tables:
                    if not table: 
                        continue
                    
                    # 🚨 THE FIX: Properly nested list comprehension to flatten the table
                    table_str = " ".join([str(cell).lower() for row in table for cell in row if cell])
                    
                    if any(kw in table_str for kw in ["min", "max", "typ", "typical"]): 
                        score += 30
                    if any(unit in table_str for unit in ["mv", "ma", "khz", "mhz", "db", "µa", "ua"]): 
                        score += 15

                    for feature in lower_features:
                        if feature in table_str:
                            score += 50  
                            
                    if any(junk in table_str for junk in ["pin name", "register address", "bit description"]):
                        score -= 40

                    formatted_tables += f"\n[Table]\n"
                    for row in table:
                        clean_row = [str(cell).strip().replace('\n', ' ') if cell else "" for cell in row]
                        formatted_tables += " | ".join(clean_row) + "\n"

                # ---------------------------------------------------------
                # 3. SAVE THE PAGE DATA
                # ---------------------------------------------------------
                scored_pages.append({
                    "page_num": page_num + 1,
                    "score": score,
                    "text": text,
                    "tables": formatted_tables
                })

        # Sort the pages by score (highest to lowest)
        scored_pages.sort(key=lambda x: x["score"], reverse=True)
        
        # Keep only the pages with a positive score, up to our max_pages limit
        best_pages = [p for p in scored_pages if p["score"] > 0][:max_pages]
        
        print(f"🎯 Filtered down to the {len(best_pages)} most relevant pages out of {len(pdf.pages)}.")
        
        # Format the final chunks to send to the LLM
        final_chunks = []
        for p in best_pages:
            chunk = f"--- PAGE {p['page_num']} (Relevance Score: {p['score']}) ---\n"
            chunk += f"TEXT:\n{p['text'][:1000]}...\n" # Cap text length slightly to save tokens
            chunk += f"\nTABLES:\n{p['tables']}\n"
            final_chunks.append(chunk)

        return final_chunks

    except Exception as e:
        print(f"❌ Error reading PDF: {e}")
        return []