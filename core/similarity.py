import re

# Industry-standard electrical unit normalizers
# Everything gets converted to base units: Volts, Amps, Ohms, Hertz, Watts, Farads
UNIT_MULTIPLIERS = {
    # Current (Base: Amps)
    "ka": 1e3, "a": 1.0, "ma": 1e-3, "ua": 1e-6, "µa": 1e-6, "na": 1e-9,
    # Voltage (Base: Volts)
    "kv": 1e3, "v": 1.0, "mv": 1e-3, "uv": 1e-6, "µv": 1e-6,
    # Resistance (Base: Ohms)
    "mΩ": 1e6, "mohm": 1e6, "kΩ": 1e3, "kohm": 1e3, "Ω": 1.0, "ohm": 1.0, "mΩ": 1e-3, 
    # Frequency (Base: Hertz)
    "ghz": 1e9, "mhz": 1e6, "khz": 1e3, "hz": 1.0,
    # Power (Base: Watts)
    "kw": 1e3, "w": 1.0, "mw": 1e-3, "uw": 1e-6, "µw": 1e-6,
    # Capacitance (Base: Farads)
    "f": 1.0, "mf": 1e-3, "uf": 1e-6, "µf": 1e-6, "nf": 1e-9, "pf": 1e-12,
    # Time (Base: Seconds)
    "s": 1.0, "ms": 1e-3, "us": 1e-6, "µs": 1e-6, "ns": 1e-9
}

def extract_normalized_number(val_str: str) -> float:
    """
    Finds the first float/int in a string AND its unit, 
    then normalizes it to the base electrical unit.
    Example: "500mA" -> 0.5. "3.3 V" -> 3.3. "1.2 MHz" -> 1200000.0
    """
    if not val_str or not isinstance(val_str, str):
        return None
        
    # Regex captures the number in group 1, and the unit letters in group 2
    # e.g., "500 mA" -> Match 1: "500", Match 2: "mA"
    match = re.search(r"([-+]?\d*\.\d+|\d+)\s*([a-zA-Z\u03BC\u03A9]+)?", val_str)
    
    if not match:
        return None
        
    raw_number = float(match.group(1))
    unit = match.group(2).lower() if match.group(2) else ""
    
    # Apply multiplier if the unit exists in our dictionary
    multiplier = UNIT_MULTIPLIERS.get(unit, 1.0)
    
    return raw_number * multiplier

def calculate_feature_score(user_val_str: str, comp_val_str: str, weight: int = 10) -> float:
    """
    Calculates the mathematical distance between two values.
    """
    # 1. Strip the units and normalize to base math numbers!
    user_num = extract_normalized_number(user_val_str)
    comp_num = extract_normalized_number(comp_val_str)

    # 2. Mathematical Comparison (If both are numbers)
    if user_num is not None and comp_num is not None:
        if user_num == 0 and comp_num == 0:
            return weight  
        
        diff = abs(user_num - comp_num)
        max_val = max(abs(user_num), abs(comp_num))
        if max_val == 0:
            max_val = 1
        
        percent_diff = diff / max_val
        
        # Linear drop-off: 0% diff = 100% weight, 20% diff = 80% weight.
        match_quality = max(0, 1.0 - percent_diff)
        return weight * match_quality

    # 3. Text Comparison Fallback (For categorical things like "I2C" or "Surface Mount")
    u_str = str(user_val_str).lower()
    c_str = str(comp_val_str).lower()
    
    if u_str in c_str or c_str in u_str:
        return weight 
        
    return 0 

def rank_components(user_extracted_specs: dict, digikey_competitors: list, feature_weights: dict = None) -> list:
    """
    Ranks the 20 DigiKey competitors against the user's PDF specs using weighted math.
    Returns the top 5 closest matches.
    """
    print("\n🧮 [Stage 4] Running Mathematical Similarity Engine...")
    
    if feature_weights is None:
        feature_weights = {}

    ranked_results = []

    for comp in digikey_competitors:
        total_score = 0
        max_possible_score = 0
        comp_specs = comp.get("specs", {})
        
        for feature, user_val in user_extracted_specs.items():
            if user_val == "Not Found" or user_val is None:
                continue
                
            weight = feature_weights.get(feature, 10)
            max_possible_score += weight
            
            if feature in comp_specs:
                comp_val = comp_specs[feature]
                score = calculate_feature_score(user_val, comp_val, weight)
                total_score += score

        final_percentage = (total_score / max_possible_score * 100) if max_possible_score > 0 else 0

        ranked_results.append({
            "part_number": comp["part_number"],
            "score": round(final_percentage, 1),
            "specs": comp_specs
        })

    ranked_results.sort(key=lambda x: x["score"], reverse=True)
    return ranked_results[:5]