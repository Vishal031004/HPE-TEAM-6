import json
import os
from groq import Groq
from core.prompts import EXTRACTION_PROMPT

# Initialize Groq client
# Ensure the API key is loaded in your main script
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

def parse_datasheet_chunks(filtered_chunks, required_features, component_name="Unknown Part"):
    """
    Parses chunks sequentially, asks the LLM only for missing features, 
    and exits immediately once all features are found.
    """
    extracted_data = {}
    missing_features = required_features.copy()
    
    print(f"🚀 Starting extraction for {component_name}. Targets: {len(missing_features)}")

    for i, chunk in enumerate(filtered_chunks):
        if not missing_features:
            print(f"✅ Early Exit! All features found by chunk {i}. Saving tokens.")
            break
            
        print(f"Processing chunk {i+1}/{len(filtered_chunks)}... Looking for: {missing_features}")
        
        # Format the prompt with the current state
        prompt = EXTRACTION_PROMPT.format(
            features=json.dumps(missing_features),
            chunk=chunk
        )
        
        try:
            response = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {"role": "system", "content": "You are a JSON-only data API. Output strict JSON matching the requested keys."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0,  
                seed=42,        
                response_format={"type": "json_object"} 
            )
            
            chunk_result = json.loads(response.choices[0].message.content)
            features_found_in_this_chunk = []
            
            for feature in missing_features[:]: 
                if feature in chunk_result and chunk_result[feature] is not None:
                    extracted_data[feature] = chunk_result[feature]
                    missing_features.remove(feature)
                    features_found_in_this_chunk.append(feature)
            
            if features_found_in_this_chunk:
                print(f"  -> Extracted: {features_found_in_this_chunk}")
            else:
                print(f"  -> No targets found. Moving to next chunk.")

        except Exception as e:
            print(f"❌ Error processing chunk {i+1}: {e}")
            
    if missing_features:
        print(f"⚠️ Extraction finished, but missed: {missing_features}")
        for feature in missing_features:
            extracted_data[feature] = None
            
    return extracted_data