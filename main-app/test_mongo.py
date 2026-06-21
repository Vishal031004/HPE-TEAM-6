import os
import pymongo
from dotenv import load_dotenv

load_dotenv()
mongo_client = pymongo.MongoClient(os.environ.get("MONGO_URI"))
db = mongo_client["datasheet_hpe"]

TARGET_FILE = "21374D_1.pdf"

print(f"🧼 Scouring database to clear cache for: {TARGET_FILE}...")

# 1. Clear file-specific chunks and extractions
for collection_name in db.list_collection_names():
    col = db[collection_name]
    result = col.delete_many({"filename": TARGET_FILE})
    if result.deleted_count > 0:
        print(f"  🗑️ Deleted {result.deleted_count} cached entries from '{collection_name}'")

# 2. HARD RESET: Drop the global category/schema caches
# (Replace these names with the exact collection names you see in your Atlas UI, e.g., 'component_types', 'digikey_cache')
collections_to_wipe = ["component_metadata", "digikey_competitors", "schemas"] 

for col_name in collections_to_wipe:
    if col_name in db.list_collection_names():
        db[col_name].drop()
        print(f"  💥 Dropped global cache collection: '{col_name}'")

# 3. Clear local FAISS files
if os.path.exists("local_faiss.index"): os.remove("local_faiss.index")
if os.path.exists("local_faiss_meta.json"): os.remove("local_faiss_meta.json")

print("\n✨ Every single trace of file memory and category schema has been eliminated.")