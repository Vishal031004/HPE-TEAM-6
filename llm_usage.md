# LLM Usage & Multi-Model Migration Guide

This document details where and how LLMs are utilized in this project, lists the exact files containing OpenAI API references, and provides a step-by-step walkthrough on how to transition the codebase to another provider, such as Google Gemini.

---

## 🔍 Current OpenAI API Integrations

The OpenAI API is imported and called in **three** core backend files. It covers text classifications/completions, vision-based graph processing, and vector embeddings.

### 1. `core/pdf_processor.py`
*   **Initialization:** `client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))`
*   **Location:** `detect_component_type()`
*   **Purpose:** Calls `gpt-4o` in JSON mode to read the first two pages of a datasheet and automatically classify the component category (e.g., Gyroscope, LDO Regulator).

### 2. `core/database.py`
*   **Initialization:** `openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))`
*   **Locations & Purpose:**
    *   `store_rag_chunks()`: Generates 1536-dimensional embeddings for PDF paragraphs/tables using the `text-embedding-3-small` model.
    *   `retrieve_rag_context()`: Generates an embedding for the user's search query to run MongoDB Atlas vector searches.

### 3. `core/extractor.py`
*   **Initialization:** `client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))`
*   **Locations & Purpose:**
    *   `_chat_completion_with_retry()`: Wrapper function implementing exponential backoff.
    *   `parse_datasheet_chunks()`: Uses `gpt-4o` (JSON mode) to extract multiple specifications in a single batch.
    *   `extract_specs_from_graph_page()`: Uses `gpt-4o`'s **vision capabilities** to parse graphs/charts from page images.
    *   `reformulate_query()`: Uses `gpt-4o-mini` to turn conversational questions into standalone search queries.
    *   `route_user_intent()`: Uses `gpt-4o-mini` to classify user intent (`find_alternatives` vs `information_retrieval`).
    *   `answer_rag_question()`: Uses `gpt-4o` to generate final grounded answers with page/chunk citations.
---

## 📋 The LLM Interface

To define a formal contract for any LLM provider integration, we establish a base interface. The following three abstract functions are **all and the only functions** required by the entire application to interact with an LLM:

1. **`generate_text(...)`**: Handles text completion, categories, chat QA, query reformulation, and intent routing.
2. **`generate_from_image(...)`**: Handles vision-based graph parsing.
3. **`get_embeddings(...)`**: Handles text vectorization for both single search queries and batched document chunks.

### Abstract Base Class Definition

```python
from abc import ABC, abstractmethod
from typing import Union, List

class LLMInterface(ABC):
    
    @abstractmethod
    def generate_text(
        self, 
        prompt: str, 
        system_instruction: str = None, 
        json_mode: bool = False, 
        model: str = None
    ) -> str:
        """
        Generate text response based on a prompt.
        
        Args:
            prompt: The main user prompt.
            system_instruction: Optional system level context/instructions.
            json_mode: If True, forces the model to output valid JSON.
            model: Optional model identifier string override.
            
        Returns:
            str: The raw text response.
        """
        pass

    @abstractmethod
    def generate_from_image(
        self, 
        prompt: str, 
        image_b64: str, 
        model: str = None
    ) -> str:
        """
        Analyze a base64 encoded image with a guided prompt.
        
        Args:
            prompt: Instructions guiding the vision query.
            image_b64: Base64-encoded string representing the image (PNG/JPEG).
            model: Optional model identifier string override.
            
        Returns:
            str: The text output from the vision model.
        """
        pass

    @abstractmethod
    def get_embeddings(
        self, 
        text_or_list: Union[str, List[str]], 
        model: str = None
    ) -> Union[List[float], List[List[float]]]:
        """
        Generate vector embedding(s) for a single string or a list of strings.
        
        Args:
            text_or_list: A single string or a list of strings to embed.
            model: Optional model identifier string override.
            
        Returns:
            Union[List[float], List[List[float]]]: A list of floats (for a single string) 
                                                   or a list of lists of floats (for multiple strings).
        """
        pass
```

---

## 🔄 How to Change LLM Providers (e.g., to Gemini)

Transitioning to another provider currently requires modifying code in all three files where `OpenAI` is imported and called. Because different SDKs have differing syntax for vision inputs, system prompts, and formatting, a direct replacement is necessary.

> [!WARNING]
> **Embedding Model Swaps require Reindexing:** If you change the embedding model (e.g., from `text-embedding-3-small` to `text-embedding-004` from Google), **you must delete your existing database vector chunks and re-index your documents**. Embeddings from different models reside in different vector spaces and are mathematically incompatible.

---

## 🛠️ Best Practice: Centralizing the LLM Interface

To make the codebase model-agnostic and allow transitions with a single configuration change, we recommend creating a centralized abstraction layer.

### Step 1: Create a Central Wrapper Client (`core/llm_client.py`)

Create a new file `core/llm_client.py` wrapping the Gemini API (using the `google-generativeai` library):

```python
import os
import google.generativeai as genai
from PIL import Image
import io
import base64

# Configure Gemini
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

def generate_text(prompt: str, system_instruction: str = None, json_mode: bool = False, model: str = "gemini-1.5-flash") -> str:
    """Standard chat completion replacement."""
    generation_config = {}
    if json_mode:
        generation_config["response_mime_type"] = "application/json"
        
    model_instance = genai.GenerativeModel(
        model_name=model,
        system_instruction=system_instruction,
        generation_config=generation_config
    )
    response = model_instance.generate_content(prompt)
    return response.text

def generate_from_image(prompt: str, image_b64: str, model: str = "gemini-1.5-flash") -> str:
    """Vision completion replacement."""
    # Convert base64 string back to bytes for PIL
    image_bytes = base64.b64decode(image_b64)
    image = Image.open(io.BytesIO(image_bytes))
    
    model_instance = genai.GenerativeModel(model_name=model)
    response = model_instance.generate_content([prompt, image])
    return response.text

def get_embedding(text_or_list, model: str = "models/text-embedding-004"):
    """Embedding replacement."""
    if isinstance(text_or_list, str):
        result = genai.embed_content(model=model, content=text_or_list, task_type="retrieval_query")
        return result['embedding']
    else:
        # Handles batch embeddings
        result = genai.embed_content(model=model, content=text_or_list, task_type="retrieval_document")
        return result['embedding']
```

### Step 2: Replace imports in core files

Instead of importing and initializing `OpenAI` client in `pdf_processor.py`, `database.py`, and `extractor.py`, you can now import these unified helper functions:

```python
from core.llm_client import generate_text, generate_from_image, get_embedding
```

For example, `extractor.py`'s vision parsing would change:

**Before (OpenAI):**
```python
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{page_b64}"}}
            ]
        }
    ],
    response_format={"type": "json_object"}
)
data = json.loads(response.choices[0].message.content)
```

**After (Unified Wrapper):**
```python
response_text = generate_from_image(prompt, page_b64)
data = json.loads(response_text)
```
This isolates provider-specific syntax to `core/llm_client.py` and makes swapping models as simple as changing the string arguments.
