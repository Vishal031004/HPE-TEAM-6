import os
import json
import re
import time
import random
from typing import List, Dict, Any
from openai import OpenAI
from prompts import BATCH_EXTRACTION_PROMPT
import requests

PDF_PROCESSOR_SERVER_URL = os.environ.get("PDF_PROCESSOR_SERVER_URL", "http://127.0.0.1:8083")

def parse_pdf_chunk_to_structured_pages(filepath: str, start_page: int = 0, end_page: int = 25):
    try:
        res = requests.post(
            f"{PDF_PROCESSOR_SERVER_URL}/api/pdf/parse_chunks",
            json={
                "filepath": filepath,
                "start_page": start_page,
                "end_page": end_page
            }
        )
        res.raise_for_status()
        data = res.json()
        return data.get("structured_pages", []), data.get("total_pages", 0)
    except Exception as e:
        print(f"Error calling pdf_processor service parse_pdf_chunk_to_structured_pages: {e}")
        return [], 0

def get_figure_pages(filepath: str, start_page: int = 0, end_page: int = 25) -> List[int]:
    try:
        res = requests.post(
            f"{PDF_PROCESSOR_SERVER_URL}/api/pdf/figure_pages",
            json={
                "filepath": filepath,
                "start_page": start_page,
                "end_page": end_page
            }
        )
        res.raise_for_status()
        return res.json().get("figure_pages", [])
    except Exception as e:
        print(f"Error calling pdf_processor service get_figure_pages: {e}")
        return []

def render_page_to_base64(filepath: str, page_num_1indexed: int, dpi: int = 150) -> str:
    try:
        res = requests.post(
            f"{PDF_PROCESSOR_SERVER_URL}/api/pdf/render_page",
            json={
                "filepath": filepath,
                "page_num_1indexed": page_num_1indexed,
                "dpi": dpi
            }
        )
        res.raise_for_status()
        return res.json().get("image_b64", "")
    except Exception as e:
        print(f"Error calling pdf_processor service render_page_to_base64: {e}")
        return ""

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# ========================================================================
# ENGINE A: MATHEMATICAL SPEC EXTRACTION (Existing Logic)
# ========================================================================

def _parse_retry_delay_seconds(error_text: str, default_seconds: float = 0.5) -> float:
    """Parses rate-limit retry hints like 'Please try again in 10ms'."""
    if not error_text:
        return default_seconds

    ms_match = re.search(r"try again in\s*(\d+)\s*ms", error_text, flags=re.IGNORECASE)
    if ms_match:
        return max(default_seconds, int(ms_match.group(1)) / 1000.0)

    s_match = re.search(r"try again in\s*(\d+)\s*s", error_text, flags=re.IGNORECASE)
    if s_match:
        return max(default_seconds, float(s_match.group(1)))

    return default_seconds


def _chat_completion_with_retry(**kwargs):
    """Retries transient 429/5xx OpenAI errors with bounded exponential backoff."""
    max_attempts = 5
    delay = 0.5

    for attempt in range(1, max_attempts + 1):
        try:
            return client.chat.completions.create(**kwargs)
        except Exception as e:
            msg = str(e)
            lower = msg.lower()
            retryable = (
                "429" in lower
                or "rate limit" in lower
                or "rate_limit_exceeded" in lower
                or "503" in lower
                or "502" in lower
                or "500" in lower
            )

            if not retryable or attempt == max_attempts:
                raise

            sleep_for = _parse_retry_delay_seconds(msg, default_seconds=delay)
            print(f"     ⏳ API throttled/retryable error. Retrying in {sleep_for:.2f}s (attempt {attempt}/{max_attempts})")
            time.sleep(sleep_for)
            delay = min(delay * 2, 4.0)

def normalize_text_for_comparison(text: str) -> str:
    """Removes extra whitespaces and lowers case for robust substring matching."""
    if not text:
        return ""
    return " ".join(text.lower().split())

def get_full_json_examples(
    market_competitors: List[Dict],
    sample_size: int = 2,
    max_chars: int = 3500,
) -> str:
    """
    Grabs the full JSON spec objects from competitors.
    This shows the LLM exactly what industry-standard feature-value pairs look like.
    """
    valid_competitors = [c for c in market_competitors if c.get("specs")]
    
    if not valid_competitors:
        return "{}"

    samples = random.sample(valid_competitors, min(sample_size, len(valid_competitors)))
    
    example_string = ""
    for i, comp in enumerate(samples, 1):
        example_string += f"--- Industry Component {i} JSON Specs ---\n"
        example_string += json.dumps(comp["specs"], indent=2) + "\n\n"

    if len(example_string) > max_chars:
        return example_string[:max_chars]
        
    return example_string

def parse_datasheet_chunks(
    structured_pages: List[Dict[str, Any]], 
    required_features: List[str], 
    market_competitors: List[Dict], 
    component_name: str = "Unknown Part"
) -> Dict[str, Any]:
    """
    Batched extraction for a small page chunk.
    Makes one LLM call for all required features and validates evidence per feature.
    Works with small sliding windows (e.g., 5 pages) so every page gets full context.
    """
    extracted_data = {f: "Not Found" for f in required_features}
    
    print(f"\n🚀 [EXTRACTION] Starting LLM extraction for {component_name}...")

    dynamic_json_examples = get_full_json_examples(market_competitors)

    if not structured_pages:
        return extracted_data

    page_nums = [p['page_num'] for p in structured_pages]
    print(f"  📑 Pages in this window: {page_nums}")
    print(f"  🎯 Searching for {len(required_features)} features: {required_features}")

    context_blocks = []
    for p in structured_pages:
        block = f"--- PAGE {p['page_num']} ---\n"
        if p.get("tables"):
            block += "TABLES ON THIS PAGE:\n"
            for t in p["tables"]:
                block += f"{t}\n"
        block += f"TEXT ON THIS PAGE:\n{(p.get('text') or '')[:2000]}\n"
        context_blocks.append(block)

    context_string = "\n".join(context_blocks)
    if not context_string.strip():
        print("     ⚪ Context missing in PDF. Skipping LLM call.")
        return extracted_data

    print(f"  📊 Total context size: {len(context_string)} chars")

    feature_list = "\n".join([f"- {f}" for f in required_features])
    prompt = BATCH_EXTRACTION_PROMPT.format(
        feature_list=feature_list,
        market_examples=dynamic_json_examples,
        context=context_string,
    )

    print(f"  🤖 Sending to GPT-4o ({len(required_features)} features in one batch call)...")
    try:
        response = _chat_completion_with_retry(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            response_format={"type": "json_object"},
        )

        payload = json.loads(response.choices[0].message.content)
        results = payload.get("results", {}) if isinstance(payload, dict) else {}
        norm_context = normalize_text_for_comparison(context_string)

        print(f"\n  📋 [RESULTS] LLM returned data for {len(results)} features:")

        for feature in required_features:
            item = results.get(feature, {}) if isinstance(results, dict) else {}
            extracted_value = item.get("value") if isinstance(item, dict) else None
            evidence = item.get("evidence") if isinstance(item, dict) else None

            if extracted_value and evidence:
                norm_evidence = normalize_text_for_comparison(str(evidence))
                if norm_evidence and norm_evidence in norm_context:
                    extracted_data[feature] = extracted_value
                    print(f"     ✅ {feature}: {extracted_value}")
                    print(f"        Evidence: \"{str(evidence)[:120]}\"")
                else:
                    print(f"     🚨 {feature}: EVIDENCE VALIDATION FAILED")
                    print(f"        LLM Value:    \"{extracted_value}\"")
                    print(f"        LLM Evidence: \"{str(evidence)[:150]}\"")
                    print(f"        (This exact substring was NOT found in the raw PDF context)")
            elif extracted_value and not evidence:
                print(f"     ⚠️  {feature}: LLM returned value \"{extracted_value}\" but NO evidence string")
            else:
                print(f"     ⚪ {feature}: LLM returned null (not found in this window)")

    except Exception as e:
        print(f"     ❌ LLM Error (batch): {e}")
            
    return extracted_data


def get_missing_features(extracted_specs: Dict[str, Any]) -> List[str]:
    """Returns features still unresolved after extraction."""
    return [
        k for k, v in extracted_specs.items()
        if not v or str(v).strip().lower() in {"not found", "null", "none", ""}
    ]


def extract_specs_from_graph_page(
    page_b64: str,
    missing_features: List[str],
    component_type: str,
) -> Dict[str, str]:
    """Attempts to extract missing specs from a rendered graph/image page."""
    if not missing_features:
        return {}

    feature_list = "\n".join([f"- {f}" for f in missing_features])
    prompt = f"""
You are reading a datasheet graph page for component type: {component_type}.

Extract values only for these features if clearly visible:
{feature_list}

Rules:
1) Return strict JSON object only.
2) Output keys must be feature names from the list above.
3) Value should include units if visible.
4) If not readable or not present, use "Not Found".

Example output:
{{
  "Output Voltage": "5 V",
  "Dropout Voltage": "Not Found"
}}
"""

    try:
        response = _chat_completion_with_retry(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{page_b64}"},
                        },
                    ],
                }
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )

        data = json.loads(response.choices[0].message.content)
        if not isinstance(data, dict):
            return {}
        return {k: str(v) for k, v in data.items() if k in missing_features}
    except Exception as e:
        print(f"     ⚠️ Vision extraction failed: {e}")
        return {}


def parse_datasheet_staged(
    filepath: str,
    component_type: str,
    required_features: List[str],
    market_competitors: List[Dict],
    component_name: str = "Unknown Part",
    chunk_size: int = 5,
) -> Dict[str, Any]:
    """
    Sliding-window staged extraction:
    1) Process a small window of pages (default 5) — text + tables
    2) Extract all possible features via LLM with semantic mapping
    3) Run vision fallback on graph pages in the same window for still-missing features
    4) Slide to next window and repeat only for features still not found
    5) Stop when all features are resolved or entire PDF is exhausted
    """
    print(f"\n{'='*70}")
    print(f"🚀 STAGED EXTRACTION PIPELINE for {component_name}")
    print(f"   Component Type: {component_type}")
    print(f"   Total Features to Extract: {len(required_features)}")
    print(f"   Window Size: {chunk_size} pages")
    print(f"{'='*70}")
    
    extracted_specs = {f: "Not Found" for f in required_features}

    start = 0
    total_pages = None
    window_num = 0

    while True:
        window_num += 1
        end = start + chunk_size
        
        print(f"\n{'─'*60}")
        print(f"📄 WINDOW {window_num}: Pages {start + 1} to {end}")
        print(f"{'─'*60}")

        chunk_pages, chunk_total = parse_pdf_chunk_to_structured_pages(filepath, start, end)
        total_pages = chunk_total if total_pages is None else total_pages
        
        actual_end = min(end, total_pages)
        print(f"   PDF has {total_pages} total pages. This window covers pages {start + 1}-{actual_end}.")

        if not chunk_pages:
            print("   ⚠️ No readable pages found in this window. Ending.")
            break

        missing = get_missing_features(extracted_specs)
        if not missing:
            print("   🎉 All features already found! Stopping early.")
            break

        print(f"\n   🔍 TEXT/TABLE PASS — searching for {len(missing)} missing features:")
        for f in missing:
            print(f"      • {f}")

        chunk_result = parse_datasheet_chunks(
            structured_pages=chunk_pages,
            required_features=missing,
            market_competitors=market_competitors,
            component_name=component_name,
        )

        found_this_window = []
        for feature, value in chunk_result.items():
            if value and str(value).strip().lower() not in {"not found", "null", "none", ""}:
                extracted_specs[feature] = value
                found_this_window.append(feature)

        print(f"\n   📊 WINDOW {window_num} TEXT RESULTS: Found {len(found_this_window)} features")
        if found_this_window:
            for f in found_this_window:
                print(f"      ✅ {f} = {extracted_specs[f]}")

        missing = get_missing_features(extracted_specs)
        if missing:
            print(f"\n   👁️ VISION FALLBACK — {len(missing)} features still missing:")
            for f in missing:
                print(f"      • {f}")
            
            figure_pages = get_figure_pages(filepath, start, end)
            if figure_pages:
                print(f"   Found {len(figure_pages)} graph/image pages in this window: {figure_pages}")
            else:
                print(f"   No graph/image pages found in this window.")
                
            for page_num in figure_pages[:4]:
                still_missing = get_missing_features(extracted_specs)
                if not still_missing:
                    break
                print(f"     🔬 Scanning graph page {page_num} for: {still_missing}")
                try:
                    page_b64 = render_page_to_base64(filepath, page_num)
                    graph_result = extract_specs_from_graph_page(page_b64, still_missing, component_type)
                    for feature, value in graph_result.items():
                        if value and str(value).strip().lower() not in {"not found", "null", "none", ""}:
                            extracted_specs[feature] = value
                            print(f"     ✅ Vision found: {feature} = {value}")
                except Exception as e:
                    print(f"     ⚠️ Graph parse error on page {page_num}: {e}")

        # End-of-window summary
        resolved_so_far = len([k for k, v in extracted_specs.items() if str(v).strip().lower() != "not found"])
        still_missing = get_missing_features(extracted_specs)
        print(f"\n   📈 PROGRESS: {resolved_so_far}/{len(required_features)} features resolved")
        
        if not still_missing:
            print(f"   🎉 All features found! Stopping.")
            break
        else:
            print(f"   Still missing ({len(still_missing)}): {still_missing}")

        if end >= total_pages:
            print(f"\n   📄 Reached end of PDF ({total_pages} pages). Stopping.")
            break

        start = end

    resolved = len([k for k, v in extracted_specs.items() if str(v).strip().lower() != "not found"])
    print(f"\n{'='*70}")
    print(f"✅ EXTRACTION COMPLETE: {resolved}/{len(required_features)} features resolved")
    not_found = [k for k, v in extracted_specs.items() if str(v).strip().lower() == "not found"]
    if not_found:
        print(f"❌ Not found: {not_found}")
    print(f"{'='*70}")
    return extracted_specs


# ========================================================================
# ENGINE B: ADVANCED RAG Q&A (New Logic)
# ========================================================================

# Global variable to cache the model in memory (loaded lazily on first query, NOT on app startup)
_cross_encoder_instance = None
_cross_encoder_loaded = False

def _get_cross_encoder():
    """Lazily loads the Cross-Encoder model on first use. Cached for all subsequent calls."""
    global _cross_encoder_instance, _cross_encoder_loaded
    if _cross_encoder_loaded:
        return _cross_encoder_instance
    
    try:
        print("⚙️ Loading Cross-Encoder model into memory (This happens ONCE per server lifetime)...")
        from sentence_transformers import CrossEncoder
        _cross_encoder_instance = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2', max_length=512)
        _cross_encoder_loaded = True
        print("✅ Cross-Encoder loaded successfully!")
        return _cross_encoder_instance
    except ImportError:
        print("⚠️ sentence-transformers not installed. Cross-encoder reranking disabled.")
        _cross_encoder_loaded = True  # Don't retry
        return None
    except Exception as e:
        print(f"⚠️ Cross-encoder loading failed: {e}")
        _cross_encoder_loaded = True  # Don't retry
        return None

def rerank_chunks_cross_encoder(query: str, chunks: List[Dict], top_k: int = 5) -> List[Dict]:
    """
    Phase 3: Cross-Encoder Re-Ranking.
    Model is loaded lazily on first query, NOT on server startup.
    """
    if not chunks:
        return []

    model = _get_cross_encoder()
    if model is None:
        # No cross-encoder available — fall back to returning top chunks by vector score
        return chunks[:top_k]

    try:
        print(f"🧠 Re-Ranking {len(chunks)} retrieved chunks using Cross-Encoder...")
        pairs = [[query, chunk.get('text', '')] for chunk in chunks]
        scores = model.predict(pairs)
        
        # Attach scores and sort
        for i, chunk in enumerate(chunks):
            chunk['cross_score'] = float(scores[i])
            
        sorted_chunks = sorted(chunks, key=lambda x: x['cross_score'], reverse=True)
        return sorted_chunks[:top_k]
        
    except Exception as e:
        print(f"⚠️ Cross-encoder reranking failed: {e}")
        return chunks[:top_k]
    
def reformulate_query(query: str, chat_history: List[Dict]) -> str:
    """
    Step 0: Translates conversational queries with pronouns/references into 
    standalone search queries using the chat history.
    """
    if not chat_history:
        return query

    system_msg = (
        "Given the following conversation history and the user's next question, "
        "rephrase the user's question to be a standalone search query that contains all "
        "the necessary context. Replace pronouns like 'it', 'those', or references like 'the second feature' "
        "with the actual technical subject from the history.\n"
        "If the question is already standalone, return it exactly as is.\n"
        "Output ONLY the rephrased query, nothing else."
    )

    # Build memory context (we only need the last few messages to get the context)
    messages = [{"role": "system", "content": system_msg}]
    for msg in chat_history[-4:]: 
        safe_content = msg.get("content") or ""
        messages.append({"role": msg.get("role", "user"), "content": safe_content})
        
    messages.append({"role": "user", "content": f"Rewrite this query: {query}"})

    try:
        # We use a fast model for this to minimize latency
        response = client.chat.completions.create(
            model="gpt-4o-mini", # or "gpt-3.5-turbo" if you don't have mini access
            messages=messages,
            temperature=0.0
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"⚠️ Query reformulation failed: {e}")
        return query

def route_user_intent(query: str, chat_history: List[Dict]) -> str:
    """
    Step 0.5: The Agentic Brain.
    Classifies if the user wants standard RAG Q&A or a heavy market analysis.
    """
    system_msg = (
        "You are an intent classification routing AI. Analyze the user's latest message.\n"
        "Classify the user's intent into exactly one of these two categories:\n"
        "1. 'find_alternatives': The user is explicitly asking to find NEW external alternatives on the open market, search DigiKey, or find cheaper replacements.\n"
        "2. 'information_retrieval': The user is asking to summarize, compare, or explain the datasheets ALREADY uploaded in the chat. (e.g., 'compare these two', 'how is this different from the other one', 'what is the max temp').\n\n"
        "Output ONLY the category name as a raw string."
    )
    
    messages = [{"role": "system", "content": system_msg}]
    if chat_history:
        # We only need the last couple of messages for intent context
        for msg in chat_history[-2:]: 
            messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})
            
    messages.append({"role": "user", "content": query})

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.0
        )
        intent = response.choices[0].message.content.strip().lower()
        if "find_alternatives" in intent:
            return "find_alternatives"
        return "information_retrieval"
    except Exception as e:
        print(f"⚠️ Intent routing failed: {e}")
        return "information_retrieval" # Safe fallback to standard RAG

def answer_rag_question(query: str, retrieved_chunks: List[Dict], chat_history: List[Dict] = None, is_global: bool = False) -> str:
    """
    Phase 4: Agentic Generation & Validation.
    Generates a grounded, cited answer using the retrieved and re-ranked MongoDB Atlas chunks.
    Strictly enforces anti-hallucination rules.
    
    When is_global=True, the prompt switches to multi-document mode:
    - Chunk context includes the source filename
    - System prompt instructs the LLM to organize answers per component/document
    """
    if not retrieved_chunks:
        return "I couldn't find any relevant information in the datasheet to answer that question."

    # --- DIAGNOSTIC PRINT BLOCK ---
    print("\n🔬 [DIAGNOSTIC] Top Chunks Passed to LLM after Re-Ranking:")
    for idx, chunk in enumerate(retrieved_chunks):
        score = chunk.get('cross_score', 'N/A')
        score_str = f"{score:.4f}" if isinstance(score, (float, int)) else str(score)
        src = f" | Source: {chunk.get('filename', '?')}" if is_global else ""
        
        print(f"   Rank #{idx+1} | ID: {chunk.get('chunk_id')} | Cross-Score: {score_str}{src}")
        print(f"   Snippet: {chunk.get('text', '')[:150]}...\n")
    # -------------------------------------

    # 1. Format Chunks for the LLM Context Window
    context_text = ""
    for chunk in retrieved_chunks:
        if is_global:
            # Global mode: include source filename so LLM knows which document each chunk belongs to
            context_text += f"\n--- CHUNK ID: {chunk.get('chunk_id')} | SOURCE: {chunk.get('filename', 'Unknown')} (Page {chunk.get('page')}) ---\n"
        else:
            # Single-doc mode: existing format (unchanged)
            context_text += f"\n--- CHUNK ID: {chunk.get('chunk_id')} (Page {chunk.get('page')}) ---\n"
        context_text += f"{chunk.get('text')}\n"

    # 2. Formulate system prompt based on mode
    if is_global:
        # GLOBAL MODE: Multi-document awareness prompt
        # Collect unique source documents for the prompt
        source_docs = list(set(chunk.get('filename', 'Unknown') for chunk in retrieved_chunks))
        doc_list = ", ".join(source_docs)
        
        system_prompt = (
            "You are an expert hardware engineering assistant with access to MULTIPLE datasheets from a user's component library. "
            "The retrieved context below contains chunks from DIFFERENT documents/components. "
            f"Source documents in this context: {doc_list}\n\n"
            "CRITICAL RULES:\n"
            "1. MULTI-DOCUMENT AWARENESS: Each chunk is tagged with its SOURCE filename. You MUST clearly attribute every piece of data to its source document. "
            "When answering, organize your response BY COMPONENT/DOCUMENT so the user can clearly see which data comes from which datasheet.\n"
            "2. STRICT GROUNDING: Every technical specification or numerical value you provide MUST be attributed to its source chunk ID and source document.\n"
            "3. COMPARATIVE ANALYSIS: When the user asks a comparative question (e.g., 'which has better X?', 'compare the Y across all components'), "
            "present a structured comparison across all available documents. Use tables or bullet points to make differences clear.\n"
            "4. COMPLETENESS: If the user asks about ALL components but some documents don't have the requested data, explicitly state which documents are missing that information rather than silently omitting them.\n"
            "5. ENGINEERING REASONING: You are allowed to perform logical analysis and comparisons across documents.\n"
            "6. ZERO HALLUCINATION: If the specific data is missing from the context, say so. Do not assume or infer values from one component's datasheet to another.\n\n"
            f"--- START RETRIEVED CONTEXT (from {len(source_docs)} documents) ---\n{context_text}\n--- END RETRIEVED CONTEXT ---"
        )
    else:
        # SINGLE-DOC MODE: Existing prompt (completely unchanged)
        system_prompt = (
            "You are an expert hardware engineering assistant specialized in technical datasheet analysis. "
            "Engage in a natural, conversational dialogue with the user while maintaining absolute technical accuracy.\n\n"
            "CRITICAL RULES:\n"
            "1. STRICT GROUNDING: Every technical specification or numerical value you provide MUST be suffixed with its exact source chunk ID tag in the format.\n"
            "2. ENGINEERING REASONING: You are explicitly allowed to perform logical analysis. If the user asks 'Is 45°C safe?', and the context states the operating range is -40°C to +125°C, you MUST answer contextually: 'Yes, 45°C is perfectly safe because it falls within the specified operating range of -40°C to +125°C.'\n"
            "3. CONVERSATIONAL MEMORY: You have access to the conversation history. If the user asks a follow-up question using pronouns (e.g., 'explain those features', 'is that voltage fine?'), use the chat history to understand what they are referring to and elaborate naturally.\n"
            "4. ZERO HALLUCINATION: If the specific data required to answer the question or evaluate the condition is missing from both the context snippets and the chat history, you must politely decline. Reply: 'I cannot find the specifications for that in the provided datasheet.' Do not assume standard industry values.\n\n"
            f"--- START RETRIEVED CONTEXT ---\n{context_text}\n--- END RETRIEVED CONTEXT ---"
        )

    # 3. Assemble message payload with conversational memory structures
    messages = [{"role": "system", "content": system_prompt}]
    if chat_history:
        for msg in chat_history:
            # FIX: If content is explicitly None/null, force it to an empty string safely
            safe_content = msg.get("content") or ""
            messages.append({"role": msg.get("role", "user"), "content": safe_content})
    messages.append({"role": "user", "content": query})

    # 4. Trigger localized agentic completion block
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            temperature=0.2  # Force maximum deterministic spec grounding
        )
        answer = response.choices[0].message.content.strip()
        return answer
    except Exception as e:
        print(f"❌ OpenAI generation failed in answer_rag_question: {e}")
        return "I encountered an internal error trying to process this answer via the LLM engine."