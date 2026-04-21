import os
import json
import random
from typing import List, Dict, Any
from openai import OpenAI
from core.prompts import DYNAMIC_EXTRACTION_PROMPT
from core.pdf_processor import retrieve_feature_context

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

def normalize_text_for_comparison(text: str) -> str:
    """Removes extra whitespaces and lowers case for robust substring matching."""
    if not text:
        return ""
    return " ".join(text.lower().split())

def get_full_json_examples(market_competitors: List[Dict], sample_size: int = 3) -> str:
    """
    Grabs the full JSON spec objects from 3 competitors.
    This shows the LLM exactly what industry-standard feature-value pairs look like.
    """
    valid_competitors = [c for c in market_competitors if c.get("specs")]
    
    if not valid_competitors:
        return "{}"

    # Pick 3 random competitors
    samples = random.sample(valid_competitors, min(sample_size, len(valid_competitors)))
    
    example_string = ""
    for i, comp in enumerate(samples, 1):
        example_string += f"--- Industry Component {i} JSON Specs ---\n"
        example_string += json.dumps(comp["specs"], indent=2) + "\n\n"
        
    return example_string

def parse_datasheet_chunks(
    structured_pages: List[Dict[str, Any]], 
    required_features: List[str], 
    market_competitors: List[Dict], 
    component_name: str = "Unknown Part"
) -> Dict[str, Any]:
    """
    The Hybrid RAG Pipeline. 
    Injects 3 full JSON market examples, queries the LLM, and validates the output.
    """
    extracted_data = {}
    
    print(f"\n🚀 [Stage 3] Starting surgical RAG extraction for {component_name}...")

    # Grab the 3 sets of JSON feature-value pairs ONCE to save processing time
    dynamic_json_examples = get_full_json_examples(market_competitors)

    for feature in required_features:
        print(f"  -> Hunting for: '{feature}'...")
        
        # 1. Retrieve ONLY the pages/tables relevant to this specific feature
        context_string = retrieve_feature_context(structured_pages, feature, top_k=2)
        
        if not context_string:
            print("     ⚪ Context missing in PDF. Skipping LLM call.")
            extracted_data[feature] = "Not Found"
            continue
            
        # 2. Build the Dynamic Prompt
        prompt = DYNAMIC_EXTRACTION_PROMPT.format(
            feature_name=feature,
            market_examples=dynamic_json_examples, # Injecting the 3 JSON sets here!
            context=context_string
        )
        
        try:
            # 3. Call OpenAI
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "user", "content": prompt}
                ],
                temperature=0, 
                response_format={"type": "json_object"} 
            )
            
            result = json.loads(response.choices[0].message.content)
            extracted_value = result.get("value")
            evidence = result.get("evidence")
            
            # 4. THE VALIDATION GATE (Anti-Hallucination Check)
            if extracted_value and evidence:
                norm_evidence = normalize_text_for_comparison(str(evidence))
                norm_context = normalize_text_for_comparison(context_string)
                
                if norm_evidence in norm_context:
                    print(f"     ✅ Validated: {extracted_value}")
                    extracted_data[feature] = extracted_value
                else:
                    print(f"     🚨 HALLUCINATION BLOCKED! Evidence not in PDF: '{evidence}'")
                    extracted_data[feature] = "Not Found"
            else:
                print("     ⚪ Not Found in datasheet.")
                extracted_data[feature] = "Not Found"

        except Exception as e:
            print(f"     ❌ LLM Error: {e}")
            extracted_data[feature] = "Not Found"
            
    return extracted_data