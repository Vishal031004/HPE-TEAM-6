import re

def extract_numbers_from_string(val_str):
    """
    Teammate's Universal Normalizer: Finds the first float/int in a string, 
    ignoring units like V, mA, kHz, etc.
    Example: "500mA" -> 500.0, "3.3 V" -> 3.3
    """
    if not val_str or not isinstance(val_str, str):
        return None
    # Regex to find numbers with optional decimals and negative signs
    matches = re.findall(r"[-+]?\d*\.\d+|\d+", val_str)
    return float(matches[0]) if matches else None

def calculate_feature_score(user_val_str, comp_val_str, weight=10):
    """
    Calculates the mathematical distance between two values.
    """
    # 1. Strip the units and extract the pure math numbers
    user_num = extract_numbers_from_string(user_val_str)
    comp_num = extract_numbers_from_string(comp_val_str)

    # 2. Mathematical Comparison (If both are numbers)
    if user_num is not None and comp_num is not None:
        if user_num == 0 and comp_num == 0:
            return weight  # Perfect match
        
        # Calculate percentage difference
        diff = abs(user_num - comp_num)
        max_val = max(abs(user_num), abs(comp_num))
        if max_val == 0:
            max_val = 1
        
        percent_diff = diff / max_val
        
        # Score drops off mathematically as the difference increases. 
        # Example: 0% diff = 100% of the weight. 20% diff = 80% of the weight.
        match_quality = max(0, 1.0 - percent_diff)
        return weight * match_quality

    # 3. Text Comparison Fallback (For categorical things like "I2S" or "Surface Mount")
    u_str = str(user_val_str).lower()
    c_str = str(comp_val_str).lower()
    
    if u_str in c_str or c_str in u_str:
        return weight # Perfect text match
        
    return 0 # No match

def rank_components(user_extracted_specs, digikey_competitors, feature_weights=None):
    """
    Ranks the 20 DigiKey competitors against the user's PDF specs using weighted math.
    Returns the top 5 closest matches.
    """
    print("\n🧮 Running Mathematical Similarity Engine...")
    
    # If the user hasn't provided a specific weights dictionary, we default everything
    if feature_weights is None:
        feature_weights = {}

    ranked_results = []

    for comp in digikey_competitors:
        total_score = 0
        max_possible_score = 0
        comp_specs = comp.get("specs", {})
        
        # Compare each feature from the user's PDF to this DigiKey component
        for feature, user_val in user_extracted_specs.items():
            if user_val == "Not Found" or user_val is None:
                continue
                
            # Get the weight for this specific feature (Defaults to 10 points if not specified)
            weight = feature_weights.get(feature, 10)
            max_possible_score += weight
            
            # If the DigiKey part has this feature, calculate how mathematically close it is
            if feature in comp_specs:
                comp_val = comp_specs[feature]
                score = calculate_feature_score(user_val, comp_val, weight)
                total_score += score

        # Convert the raw score to a clean 0-100% format
        final_percentage = (total_score / max_possible_score * 100) if max_possible_score > 0 else 0

        ranked_results.append({
            "part_number": comp["part_number"],
            "score": round(final_percentage, 1),
            "specs": comp_specs
        })

    # Sort by highest percentage score first
    ranked_results.sort(key=lambda x: x["score"], reverse=True)
    
    # Return Top 5
    return ranked_results[:5]