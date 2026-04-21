import os
import json
from dotenv import load_dotenv

load_dotenv()

from core.pdf_processor import detect_component_type, parse_pdf_to_structured_pages
from core.database import get_or_build_component_data
from core.extractor import parse_datasheet_chunks
from core.similarity import rank_components

def get_user_weights(user_specs):
    """Prompts the user in the terminal to assign weights to each extracted feature."""
    print("\n" + "="*50)
    print("⚖️  ASSIGN FEATURE WEIGHTS")
    print("="*50)
    print("Assign an importance score (0-100) to each feature.")
    print("Press ENTER to keep the default weight (10).")
    print("Type '0' if you don't care about the feature at all.\n")

    feature_weights = {}
    
    for feature, val in user_specs.items():
        if val == "Not Found" or val is None:
            continue 
        
        while True:
            user_input = input(f"Weight for '{feature}' (PDF says: {val}) [Default: 10]: ").strip()
            
            if not user_input:
                feature_weights[feature] = 10  
                break
            
            try:
                weight = float(user_input)
                if 0 <= weight <= 100:
                    feature_weights[feature] = weight
                    break
                else:
                    print("  ❌ Please enter a number between 0 and 100.")
            except ValueError:
                print("  ❌ Invalid input. Please enter a valid number.")
                
    return feature_weights


def main():
    datasheet_dir = "datasheets"
    if not os.path.exists(datasheet_dir):
        os.makedirs(datasheet_dir)
        
    pdf_files = [f for f in os.listdir(datasheet_dir) if f.lower().endswith('.pdf')]
    if not pdf_files:
        print("⚠️ No PDFs found! Please add your datasheet to the 'datasheets' folder.")
        return

    pdf_path = os.path.join(datasheet_dir, pdf_files[0])
    
    supported_types = [
        "Audio Codec", "LDO Regulator", "Buck Converter", "Op-Amp", 
        "Microcontroller", "Resistor", "Capacitor", "MOSFET"
    ]

    print("\n" + "="*50)
    print("🚀 ENTERPRISE PIPELINE STARTING")
    print("="*50)

    # Stage 1: Detect Component
    detected_type = detect_component_type(pdf_path, supported_types)
    if detected_type == "Unknown":
        return

    # Stage 2: Auto-Populating Cache (Query API, Get 20, Extract Schema)
    target_specs, market_competitors = get_or_build_component_data(detected_type)
    if not target_specs or not market_competitors:
        return

    # Stage 3: Parse PDF into Structured Memory
    structured_pages = parse_pdf_to_structured_pages(pdf_path)
    if not structured_pages:
        print("⚠️ No readable text/tables found in PDF.")
        return

    # Stage 4: Surgical RAG Extraction (Injecting market competitors!)
    user_extracted_specs = parse_datasheet_chunks(
        structured_pages=structured_pages, 
        required_features=target_specs,
        market_competitors=market_competitors,
        component_name=os.path.basename(pdf_path)
    )
    
    print("\n📄 YOUR DATASHEET SPECS (Extracted via Hybrid RAG):")
    print(json.dumps(user_extracted_specs, indent=2))

    # Stage 5: Display & Ask for Weights
    custom_weights = get_user_weights(user_extracted_specs)

    # Stage 6: Compute Similarity Engine & Top 5
    top_5_matches = rank_components(user_extracted_specs, market_competitors, feature_weights=custom_weights)

    # Stage 7: Display and Cache Final Results
    print("\n" + "="*50)
    print(f"🏆 TOP 5 RECOMMENDED ALTERNATIVES FOR {detected_type.upper()}")
    print("="*50)
    
    for i, match in enumerate(top_5_matches, 1):
        print(f"\n{i}. {match['part_number']} (Match Score: {match['score']}%)")
        print("   --- Key Specs ---")
        preview_specs = list(match['specs'].items())[:4]
        for k, v in preview_specs:
            print(f"   • {k}: {v}")

    report_data = {
        "original_pdf": os.path.basename(pdf_path),
        "component_type": detected_type,
        "extracted_specs": user_extracted_specs,
        "applied_weights": custom_weights,
        "top_5_recommendations": top_5_matches
    }
    
    with open("final_report.json", "w") as f:
        json.dump(report_data, f, indent=4)
        
    print("\n💾 Final Top 5 results have been cached to 'final_report.json'")

if __name__ == "__main__":
    main()