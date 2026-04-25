import os
import json
import re
import time
import random
from typing import List, Dict, Any
from openai import OpenAI
from core.prompts import BATCH_EXTRACTION_PROMPT
from core.pdf_processor import (
    parse_pdf_chunk_to_structured_pages,
    get_figure_pages,
    render_page_to_base64,
)

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))


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
    Grabs the full JSON spec objects from 3 competitors.
    This shows the LLM exactly what industry-standard feature-value pairs look like.
    """
    valid_competitors = [c for c in market_competitors if c.get("specs")]
    
    if not valid_competitors:
        return "{}"

    # Pick random competitors
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
    Batched extraction for a chunk.
    Makes one LLM call for all required features and validates evidence per feature.
    """
    extracted_data = {f: "Not Found" for f in required_features}
    
    print(f"\n🚀 [Stage 3] Starting surgical RAG extraction for {component_name}...")

    # Grab the 3 sets of JSON feature-value pairs ONCE to save processing time
    dynamic_json_examples = get_full_json_examples(market_competitors)

    if not structured_pages:
        return extracted_data

    context_blocks = []
    for p in structured_pages:
        block = f"--- PAGE {p['page_num']} ---\n"
        if p.get("tables"):
            block += "TABLES ON THIS PAGE:\n"
            for t in p["tables"]:
                block += f"{t}\n"
        block += f"TEXT ON THIS PAGE:\n{(p.get('text') or '')[:1200]}\n"
        context_blocks.append(block)

    context_string = "\n".join(context_blocks)
    if not context_string.strip():
        print("     ⚪ Context missing in PDF. Skipping LLM call.")
        return extracted_data

    feature_list = "\n".join([f"- {f}" for f in required_features])
    prompt = BATCH_EXTRACTION_PROMPT.format(
        feature_list=feature_list,
        market_examples=dynamic_json_examples,
        context=context_string[:12000],
    )

    print(f"  -> Batch extracting {len(required_features)} features in one call")
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

        for feature in required_features:
            item = results.get(feature, {}) if isinstance(results, dict) else {}
            extracted_value = item.get("value") if isinstance(item, dict) else None
            evidence = item.get("evidence") if isinstance(item, dict) else None

            if extracted_value and evidence:
                norm_evidence = normalize_text_for_comparison(str(evidence))
                if norm_evidence and norm_evidence in norm_context:
                    extracted_data[feature] = extracted_value
                    print(f"     ✅ {feature}: {extracted_value}")
                else:
                    print(f"     🚨 {feature}: evidence validation failed")
            else:
                print(f"     ⚪ {feature}: Not Found")

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
    chunk_size: int = 25,
) -> Dict[str, Any]:
    """
    Notebook-style staged extraction:
    1) First 25 pages text/tables
    2) Graph pages in same chunk for missing
    3) Next 25 pages repeat until done or PDF ends
    """
    print(f"\n🚀 Starting staged extraction for {component_name}...")
    extracted_specs = {f: "Not Found" for f in required_features}

    start = 0
    total_pages = None

    while True:
        end = start + chunk_size
        print(f"\n📄 Processing pages {start + 1} to {end}...")

        chunk_pages, chunk_total = parse_pdf_chunk_to_structured_pages(filepath, start, end)
        total_pages = chunk_total if total_pages is None else total_pages

        if not chunk_pages:
            print("⚠️ No readable pages found in this chunk.")
            break

        missing = get_missing_features(extracted_specs)
        if not missing:
            break

        print(f"  -> Text/table pass for {len(missing)} missing features")
        chunk_result = parse_datasheet_chunks(
            structured_pages=chunk_pages,
            required_features=missing,
            market_competitors=market_competitors,
            component_name=component_name,
        )

        for feature, value in chunk_result.items():
            if value and str(value).strip().lower() not in {"not found", "null", "none", ""}:
                extracted_specs[feature] = value

        missing = get_missing_features(extracted_specs)
        if missing:
            print(f"  -> Graph pass for {len(missing)} still-missing features")
            figure_pages = get_figure_pages(filepath, start, end)
            for page_num in figure_pages[:4]:
                still_missing = get_missing_features(extracted_specs)
                if not still_missing:
                    break
                print(f"     Scanning graph page {page_num}...")
                try:
                    page_b64 = render_page_to_base64(filepath, page_num)
                    graph_result = extract_specs_from_graph_page(page_b64, still_missing, component_type)
                    for feature, value in graph_result.items():
                        if value and str(value).strip().lower() not in {"not found", "null", "none", ""}:
                            extracted_specs[feature] = value
                except Exception as e:
                    print(f"     ⚠️ Graph parse error on page {page_num}: {e}")

        if not get_missing_features(extracted_specs):
            break

        if end >= total_pages:
            break

        start = end

    resolved = len([k for k, v in extracted_specs.items() if str(v).strip().lower() != "not found"])
    print(f"✅ Staged extraction complete: {resolved}/{len(required_features)} resolved")
    return extracted_specs