import os
import time as _time
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Union
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

DIGIKEY_CLIENT_ID = os.environ.get("DIGIKEY_CLIENT_ID")
if DIGIKEY_CLIENT_ID:
    DIGIKEY_CLIENT_ID = DIGIKEY_CLIENT_ID.strip("'\"")

DIGIKEY_CLIENT_SECRET = os.environ.get("DIGIKEY_CLIENT_SECRET")
if DIGIKEY_CLIENT_SECRET:
    DIGIKEY_CLIENT_SECRET = DIGIKEY_CLIENT_SECRET.strip("'\"")

app = FastAPI(
    title="HPE Hardware API Microservice",
    description="Microservice providing decoupled access to hardware vendor APIs (e.g. DigiKey).",
    version="1.0.0"
)

# Cached DigiKey token (valid for 30 min, we refresh at 25 min to be safe)
_digikey_token_cache = {"token": None, "expires_at": 0}

def get_digikey_token_lazy():
    now = _time.time()
    if _digikey_token_cache["token"] and now < _digikey_token_cache["expires_at"]:
        return _digikey_token_cache["token"]
    
    if not DIGIKEY_CLIENT_ID or not DIGIKEY_CLIENT_SECRET:
        raise ValueError("DIGIKEY_CLIENT_ID or DIGIKEY_CLIENT_SECRET is missing from environment variables.")

    resp = requests.post(
        "https://api.digikey.com/v1/oauth2/token",
        data={
            "client_id": DIGIKEY_CLIENT_ID,
            "client_secret": DIGIKEY_CLIENT_SECRET,
            "grant_type": "client_credentials",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=10
    )
    resp.raise_for_status()
    resp_data = resp.json()
    token = resp_data["access_token"]
    expires_in = int(resp_data.get("expires_in", 300))
    _digikey_token_cache["token"] = token
    # Cache for slightly less than the actual expiration time to be safe
    _digikey_token_cache["expires_at"] = _time.time() + max(0, expires_in - 30)
    return token

# Pydantic Request Models
class SearchRequest(BaseModel):
    keywords: str
    limit: int = 20

class PricingRequest(BaseModel):
    part_number: str

@app.get("/")
def test():
    return {"message": "Hardware API Service is up and running!"}

@app.post("/api/hardware/search")
def search_hardware(request: SearchRequest):
    """Searches DigiKey for keyword matching products and returns provider-independent product data."""
    try:
        token = get_digikey_token_lazy()
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
                "Keywords": request.keywords, 
                "Limit": request.limit, 
                "Offset": 0,
                "FilterOptionsRequest": {"StatusFilter": [{"Id": 0}]}
            },
            timeout=15
        )
        resp.raise_for_status()
        products = resp.json().get("Products", [])
        
        standard_products = []
        for p in products:
            name = str(p.get("ManufacturerProductNumber", "Unknown"))
            params_raw = p.get("Parameters", [])
            
            param_list = []
            for param in params_raw:
                k = param.get("ParameterText", "").strip()
                v = param.get("ValueText", "").strip()
                if k and v:
                    param_list.append({"parameter_text": k, "value_text": v})
            
            standard_products.append({
                "part_number": name,
                "parameters": param_list
            })
            
        return {"products": standard_products}
        
    except Exception as e:
        print(f"❌ DigiKey search failed: {e}")
        raise HTTPException(status_code=500, detail=f"DigiKey search failed: {str(e)}")

@app.post("/api/hardware/pricing")
def get_pricing(request: PricingRequest):
    """Fetches live stock and price for a single part number from DigiKey."""
    part_number = request.part_number
    try:
        token = get_digikey_token_lazy()
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
            json={"Keywords": part_number, "Limit": 1, "Offset": 0},
            timeout=10
        )
        resp.raise_for_status()
        products = resp.json().get("Products", [])

        if not products:
            return {
                "part_number": part_number,
                "stock": None,
                "price": None,
                "currency": "USD",
                "datasheet_url": "",
                "digikey_url": "",
                "error": "Not found on DigiKey"
            }

        product = products[0]
        stock = product.get("QuantityAvailable", 0)

        # Extract the HIGHEST unit price across all variations and price breaks
        all_prices = []
        variations = product.get("ProductVariations", [])
        for var in variations:
            pricing = var.get("StandardPricing", [])
            for pb in pricing:
                up = pb.get("UnitPrice")
                if up is not None:
                    all_prices.append(up)
        
        # Fallback: check top-level UnitPrice if variations didn't have it
        if not all_prices and product.get("UnitPrice") is not None:
            all_prices.append(product.get("UnitPrice"))
            
        price = max(all_prices) if all_prices else None

        # Extract datasheet URL
        datasheet_url = product.get("DatasheetUrl") or product.get("PrimaryDatasheet") or ""
        digikey_url = product.get("ProductUrl", "")
        if digikey_url and not digikey_url.startswith("http"):
            digikey_url = f"https://www.digikey.com{digikey_url}"

        print(f"📎 [PRICING HWAPI] {part_number}: price={price}, stock={stock}, datasheet={datasheet_url[:80] if datasheet_url else 'NONE'}")

        return {
            "part_number": part_number,
            "stock": stock,
            "price": price,
            "currency": "USD",
            "datasheet_url": datasheet_url,
            "digikey_url": digikey_url
        }

    except Exception as e:
        print(f"⚠️ Pricing fetch failed for {part_number} via HWAPI: {e}")
        return {
            "part_number": part_number,
            "stock": None,
            "price": None,
            "currency": "USD",
            "datasheet_url": "",
            "digikey_url": "",
            "error": str(e)
        }

if __name__ == "__main__":
    import uvicorn
    # Default port for Hardware API Service is 8087
    uvicorn.run("hwapiServer:app", host="0.0.0.0", port=8087, reload=True)
