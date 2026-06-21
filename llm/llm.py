import os
import re
import time
from typing import List, Dict, Any, Union
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables from local .env file
load_dotenv()

# Initialize OpenAI client
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
            print(f"     ⏳ OpenAI API throttled/retryable error. Retrying in {sleep_for:.2f}s (attempt {attempt}/{max_attempts})")
            time.sleep(sleep_for)
            delay = min(delay * 2, 4.0)

def generate_text(
    messages: List[Dict[str, Any]] = None,
    prompt: str = None,
    system_instruction: str = None,
    model: str = "gpt-4o",
    json_mode: bool = False,
    temperature: float = 0.0
) -> str:
    """Generates text completion based on prompt/system instruction or a message list."""
    if not messages:
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        if prompt:
            messages.append({"role": "user", "content": prompt})

    kwargs = {
        "model": model,
        "messages": messages,
        "temperature": temperature
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    response = _chat_completion_with_retry(**kwargs)
    return response.choices[0].message.content.strip()

def generate_from_image(
    prompt: str,
    image_b64: str,
    model: str = "gpt-4o",
    temperature: float = 0.0,
    json_mode: bool = False
) -> str:
    """Performs vision-based model completion using a base64 encoded image."""
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{image_b64}"},
                },
            ],
        }
    ]
    kwargs = {
        "model": model,
        "messages": messages,
        "temperature": temperature
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    response = _chat_completion_with_retry(**kwargs)
    return response.choices[0].message.content.strip()

def get_embeddings(
    input_data: Union[str, List[str]],
    model: str = "text-embedding-3-small"
) -> Union[List[float], List[List[float]]]:
    """Generates embeddings for a single text string or list of text strings."""
    response = client.embeddings.create(input=input_data, model=model)
    if isinstance(input_data, str):
        return response.data[0].embedding
    else:
        return [r.embedding for r in response.data]
