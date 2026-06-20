DYNAMIC_EXTRACTION_PROMPT = """
You are a highly precise hardware engineering semantic parser.
Your task is to extract the value for a SINGLE target feature from the provided context (which contains text and tables from a datasheet).

=== STRICT ANTI-HALLUCINATION RULES ===
1. You must output ONLY valid JSON containing exactly two keys: "value" and "evidence".
2. "evidence" MUST BE AN EXACT SUBSTRING copied directly from the provided context. If you cannot copy the exact text, do not extract it.
3. If the feature is not explicitly present in the context, output exactly: {{"value": null, "evidence": null}}
4. NEVER guess, infer, or calculate values. 
5. CRITICAL: I am providing 'Industry Examples' below so you know what FORMAT to expect. DO NOT blindly copy these examples. You must find the ACTUAL value in the 'Provided Context'.

=== INDUSTRY EXAMPLES FOR '{feature_name}' ===
To help you recognize the data type and units, here is how other components in the market format this feature:
{market_examples}

=== YOUR TASK ===
Target Feature: {feature_name}

Provided Context:
{context}
"""


BATCH_EXTRACTION_PROMPT = """
You are a highly precise hardware engineering semantic parser.
Your task is to extract values for MULTIPLE target features from the provided datasheet context (text + tables).

=== SEMANTIC TERMINOLOGY MAPPING ===
Electronic component datasheets frequently use manufacturer-specific, non-standard, or
abbreviated terminology for parameters. The target feature names below use industry-standard
DigiKey nomenclature, but the PDF may use completely different wording for the same
electrical property.

You MUST use your hardware engineering expertise to:
1. Recognize when a PDF parameter refers to the same electrical concept as a target feature,
   even if the naming is entirely different (e.g. abbreviated, symbolic, or vendor-specific).
2. Match based on the UNDERLYING ELECTRICAL CONCEPT, not the exact wording.
3. Consider abbreviations, acronyms, schematic symbols, and alternate engineering conventions
   that manufacturers use across different datasheets.
4. Look inside BOTH the text paragraphs AND the table rows/columns for relevant data.

=== STRICT ANTI-HALLUCINATION RULES ===
1. Output ONLY valid JSON with this exact shape:
{{
	"results": {{
		"Feature A": {{"value": "... or null", "evidence": "... or null"}},
		"Feature B": {{"value": "... or null", "evidence": "... or null"}}
	}}
}}
2. For every feature, "evidence" MUST BE AN EXACT SUBSTRING copied from Provided Context.
3. If a feature cannot be found even after considering terminology variations,
   use {{"value": null, "evidence": null}} for that feature.
4. Semantic NAME-MAPPING is allowed and encouraged. However, NEVER fabricate, guess,
   or calculate numerical values. The extracted value must exist in the PDF.
5. Industry Examples are only formatting hints; do not copy values from them.

=== TARGET FEATURES ===
{feature_list}

=== INDUSTRY EXAMPLES (format hints only) ===
{market_examples}

=== PROVIDED CONTEXT ===
{context}
"""