import os
import requests

EXTRACTOR_SERVER_URL = os.environ.get("EXTRACTOR_SERVER_URL", "http://127.0.0.1:8082")

def parse_datasheet_chunks(structured_pages, required_features, market_competitors, component_name="Unknown Part"):
    try:
        res = requests.post(
            f"{EXTRACTOR_SERVER_URL}/api/extractor/parse_chunks",
            json={
                "structured_pages": structured_pages,
                "required_features": required_features,
                "market_competitors": market_competitors,
                "component_name": component_name
            }
        )
        res.raise_for_status()
        return res.json()
    except Exception as e:
        print(f"Error calling extractor service parse_datasheet_chunks: {e}")
        return {f: "Not Found" for f in required_features}

def parse_datasheet_staged(filepath, component_type, required_features, market_competitors, component_name="Unknown Part", chunk_size=5):
    try:
        res = requests.post(
            f"{EXTRACTOR_SERVER_URL}/api/extractor/parse_staged",
            json={
                "filepath": filepath,
                "component_type": component_type,
                "required_features": required_features,
                "market_competitors": market_competitors,
                "component_name": component_name,
                "chunk_size": chunk_size
            }
        )
        res.raise_for_status()
        return res.json()
    except Exception as e:
        print(f"Error calling extractor service parse_datasheet_staged: {e}")
        return {f: "Not Found" for f in required_features}

def rerank_chunks_cross_encoder(query, chunks, top_k=5):
    try:
        res = requests.post(
            f"{EXTRACTOR_SERVER_URL}/api/extractor/rerank",
            json={
                "query": query,
                "chunks": chunks,
                "top_k": top_k
            }
        )
        res.raise_for_status()
        return res.json()
    except Exception as e:
        print(f"Error calling extractor service rerank: {e}")
        return chunks[:top_k]

def reformulate_query(query, chat_history):
    try:
        res = requests.post(
            f"{EXTRACTOR_SERVER_URL}/api/extractor/reformulate",
            json={
                "query": query,
                "chat_history": chat_history
            }
        )
        res.raise_for_status()
        return res.json().get("query", query)
    except Exception as e:
        print(f"Error calling extractor service reformulate: {e}")
        return query

def route_user_intent(query, chat_history):
    try:
        res = requests.post(
            f"{EXTRACTOR_SERVER_URL}/api/extractor/route_intent",
            json={
                "query": query,
                "chat_history": chat_history
            }
        )
        res.raise_for_status()
        return res.json().get("intent", "information_retrieval")
    except Exception as e:
        print(f"Error calling extractor service route_intent: {e}")
        return "information_retrieval"

def answer_rag_question(query, retrieved_chunks, chat_history=None, is_global=False):
    try:
        res = requests.post(
            f"{EXTRACTOR_SERVER_URL}/api/extractor/answer_rag",
            json={
                "query": query,
                "retrieved_chunks": retrieved_chunks,
                "chat_history": chat_history,
                "is_global": is_global
            }
        )
        res.raise_for_status()
        return res.json().get("answer", "I encountered an error trying to generate an answer.")
    except Exception as e:
        print(f"Error calling extractor service answer_rag: {e}")
        return "I encountered an error trying to communicate with the generation service."
