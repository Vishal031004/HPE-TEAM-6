import os
import requests
import pymongo
from datetime import datetime, timezone
from collections import Counter
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.environ.get("MONGO_URI")
DIGIKEY_CLIENT_ID = os.environ.get("DIGIKEY_CLIENT_ID")
DIGIKEY_CLIENT_SECRET = os.environ.get("DIGIKEY_CLIENT_SECRET")
MONGO_DB = "datasheet_hpe" # Update this to your teammate's exact DB name if different

# ── Teammate's Constants ───────────────────────────────────────────────────────
CATALOG_ONLY_FIELDS = {
    "Package / Case", "Mounting Type", "Supplier Device Package",
    "Output Configuration", "Output Type", "Control Features",
    "Protection Features", "DigiKey Programmable", "Utilized IC / Part",
    "Contents", "Grade", "Qualification", "Number of Regulators",
    "Number of Circuits", "Ratio - Input:Output", "Differential - Input:Output",
    "PLL", "Input", "Output", "Height", "Height - Seated (Max)",
    "Size / Dimension", "Operating Mode", "Ratings", "Termination",
    "Sensor Type", "RF Family/Standard", "Antenna Type", "Protocol",
    "Modulation", "Serial Interfaces", "GPIO", "Memory Format",
    "Memory Organization", "Memory Interface", "Memory Type", "Technology",
    "Write Cycle Time - Word, Page", "Features", "Type", "Platform",
    "Function", "Test Condition", "Packaging", "Product Status", "Series", "Base Product Number"
}

COMPONENT_SEARCH_KEYWORDS = {
    "LDO Regulator": "LDO voltage regulator", "Buck Converter": "buck converter DC-DC",
    "Boost Converter": "boost converter DC-DC", "DC-DC Converter": "DC-DC switching converter",
    "MOSFET": "N-channel MOSFET", "BJT": "NPN transistor BJT",
    "Op-Amp": "operational amplifier op-amp", "Comparator": "voltage comparator IC",
    "Microcontroller": "microcontroller MCU", "Capacitor": "ceramic capacitor MLCC",
    "Resistor": "thick film resistor", "Inductor": "power inductor SMD",
    "Diode": "rectifier diode", "Zener Diode": "zener diode",
    "Schottky Diode": "schottky diode", "LED": "LED indicator",
    "IGBT": "IGBT transistor", "Voltage Reference": "voltage reference IC",
    "ADC": "analog to digital converter ADC", "DAC": "digital to analog converter DAC",
    "Temperature Sensor": "digital temperature sensor IC", "Pressure Sensor": "pressure sensor MEMS",
    "Accelerometer": "accelerometer IC MEMS", "Gyroscope": "gyroscope IC MEMS",
    "RF Transceiver": "RF transceiver IC", "Bluetooth Module": "bluetooth module BLE",
    "WiFi Module": "WiFi module SoC", "Memory IC": "flash memory IC SPI",
    "Crystal Oscillator": "crystal oscillator SMD", "Clock Generator": "clock generator IC",
    "Audio Codec": "audio codec IC" # Added the one you are testing!
}
# ───────────────────────────────────────────────────────────────────────────────

def get_digikey_token_lazy():
    """Fetches a fresh token using your teammate's exact logic."""
    resp = requests.post(
        "https://api.digikey.com/v1/oauth2/token",
        data={
            "client_id": DIGIKEY_CLIENT_ID,
            "client_secret": DIGIKEY_CLIENT_SECRET,
            "grant_type": "client_credentials",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    resp.raise_for_status()
    return resp.json()["access_token"]

def get_or_build_component_data(component_type):
    """
    Checks MongoDB for the component. If missing, uses teammate's logic to hit DigiKey,
    calculate the 30% threshold schema, and save BOTH the schema and the competitors.
    """
    if not MONGO_URI:
        print("❌ MONGO_URI missing from .env file!")
        return None, None

    client = pymongo.MongoClient(MONGO_URI)
    db = client[MONGO_DB]
    schema_col = db["feature_schemas"]
    
    # 1. CACHE CHECK
    cached_data = schema_col.find_one({"component_type": component_type})
    
    if cached_data and cached_data.get("features") and cached_data.get("competitors"):
        raw_features = cached_data["features"]
        # Filter just to be safe, even though they should be clean in the DB
        filtered = [f for f in raw_features if f not in CATALOG_ONLY_FIELDS]
        print(f"🧠 CACHE HIT! Loaded schema and competitors for '{component_type}'.")
        return filtered, cached_data["competitors"]
        
    # 2. CACHE MISS -> DIGIKEY API FALLBACK
    print(f"⚠️ CACHE MISS! '{component_type}' not found. Fetching from DigiKey...")
    
    try:
        token = get_digikey_token_lazy()
        keyword = COMPONENT_SEARCH_KEYWORDS.get(component_type, component_type)

        resp = requests.post(
            "https://api.digikey.com/products/v4/search/keyword",
            headers={
                "X-DIGIKEY-Client-Id": DIGIKEY_CLIENT_ID,
                "Authorization": f"Bearer {token}",
                "X-DIGIKEY-Locale-Site": "US",
                "X-DIGIKEY-Locale-Language": "en",
                "X-DIGIKEY-Locale-Currency": "USD",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json={
                "Keywords": keyword, 
                "Limit": 20, # We pull 20 to populate our competitor math engine
                "Offset": 0,
                "FilterOptionsRequest": {"StatusFilter": [{"Id": 0}]}
            }
        )
        resp.raise_for_status()
        products = resp.json().get("Products", [])

        if not products:
            print("❌ DigiKey returned 0 products.")
            return None, None

        # 3. TEAMMATE'S SCHEMA LOGIC (30% Threshold) & COMPETITOR EXTRACTION
        param_counter = Counter()
        competitors = []

        for p in products:
            name = str(p.get("ManufacturerProductNumber", "Unknown"))
            params_raw = p.get("Parameters", [])
            
            param_dict = {}
            for param in params_raw:
                k = param.get("ParameterText", "").strip()
                v = param.get("ValueText", "").strip()
                if k:
                    param_counter[k] += 1
                    if v:
                        param_dict[k] = v
            
            competitors.append({"part_number": name, "specs": param_dict})

        # Keep features that appear in at least 30% of the products
        min_count = max(1, len(products) * 0.3)
        features = [name for name, cnt in param_counter.items() if cnt >= min_count]
        filtered_features = [f for f in features if f not in CATALOG_ONLY_FIELDS]

        # 4. STORE IN MONGODB
        schema_col.update_one(
            {"component_type": component_type},
            {"$set": {
                "component_type": component_type,
                "features": features, # We store the raw 30% threshold list
                "competitors": competitors, # We also store the 20 market competitors!
                "sampled_products": len(products),
                "stored_at": datetime.now(timezone.utc).isoformat(),
                "source": "digikey_api"
            }},
            upsert=True
        )
        
        print(f"💾 SAVED! Extracted {len(filtered_features)} clean specs and {len(competitors)} competitors.")
        return filtered_features, competitors

    except Exception as e:
        print(f"❌ DigiKey fetch failed: {e}")
        return None, None