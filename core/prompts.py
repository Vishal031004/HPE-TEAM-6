EXTRACTION_PROMPT = """
You are a highly precise hardware datasheet extraction engine.
Extract the exact values for the following target features from the provided text/table data.
Do not guess or infer. If a feature is not explicitly present in this specific chunk, output null for that feature.
Include units if present (e.g., '100 dB', '3.1 mW').

Target Features: {features}

Provided Data Chunk:
{chunk}
"""