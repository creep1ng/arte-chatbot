"""
User profile inference module.
Infers user expertise levels (novato, intermedio, experto) based on
conversation history analysis.
"""

import re
from typing import List, Dict

PROFILE_INSTRUCTIONS = {
    "novato": "Explica con analogías simples. Evita siglas técnicas sin definirlas primero. Usa ejemplos cotidianos.",
    "intermedio": "Usa terminología estándar del sector fotovoltaico. Puedes mencionar siglas comunes (W, V, kWh).",
    "experto": "Responde con precisión técnica. Usa siglas estándar (Voc, Isc, MPPT, STC). Incluye valores numéricos exactos.",
}

# Technical vocabulary for detection
TECHNICAL_TERMS = {
    # Energy/Power
    "watts",
    "vatio",
    "kw",
    "kwh",
    "voc",
    "isc",
    "vmp",
    "imp",
    "pmpp",
    "potencia",
    "voltaje",
    "amperaje",
    "corriente",
    # Components
    "inversor",
    "controlador",
    "bateria",
    "modulo",
    "panel",
    "ficha tecnica",
    "string",
    "array",
    # Manufacturers and types
    "jinko",
    "canadian",
    "longi",
    "bifacial",
    "monocristalino",
    "policristalino",
    "heterojuncion",
    # Parameters
    "eficiencia",
    "temperatura",
    "degradacion",
    "garantia",
    "años",
    "coeficiente",
    "irradiancia",
    # Common acronyms
    "mppt",
    "pwm",
    "dc",
    "fotovoltaico",
    "pv",
}

# Technical acronyms and units
ACRONYMS_AND_UNITS = {
    "kw",
    "kwh",
    "w",
    "v",
    "a",
    "°c",
    "c",
    "m²",
    "m2",
    "mph",
    "dc",
    "ac",
    "mppt",
    "pwm",
    "voc",
    "isc",
    "vmp",
    "imp",
    "pmpp",
}


def _extract_technical_score(text: str) -> float:
    """
    Extract a technical vocabulary score (0-1) from text.

    Analyzes the density of technical terms in the text.

    Args:
        text: Input text to analyze.

    Returns:
        A score between 0 and 1 representing technical vocabulary density.
    """
    if not text or not isinstance(text, str):
        return 0.0

    # Normalize text
    text_lower = text.lower()
    # Remove punctuation and split into words, but preserve combined words with special chars
    words = re.findall(r"\b[\w°]+\b", text_lower)

    if not words:
        return 0.0

    # Count technical terms
    technical_count = 0
    for word in words:
        # Check if word matches any technical term
        if word in TECHNICAL_TERMS:
            technical_count += 1
        # Also check for partial matches (e.g., "monocristalino" contains terms)
        elif any(
            term in word
            for term in [
                "voc",
                "isc",
                "mppt",
                "pwm",
                "monocristalino",
                "policristalino",
            ]
        ):
            technical_count += 1

    # Score: proportion of technical terms, but boost if there are technical terms present
    score = technical_count / len(words)
    # Apply a mild multiplier if multiple technical terms are found
    if technical_count > 0:
        score = min(score * 1.5, 1.0)

    return min(score, 1.0)


def _extract_specificity_score(text: str) -> float:
    """
    Extract a specificity score (0-1) from text.

    Analyzes presence of specific models, values, and brands.

    Args:
        text: Input text to analyze.

    Returns:
        A score between 0 and 1 representing specificity level.
    """
    if not text or not isinstance(text, str):
        return 0.0

    text_lower = text.lower()

    # Check for specific model numbers and numbers with units
    has_model_number = bool(re.search(r"\b\d{2,4}[wW]\b", text))  # e.g., 460W, 300W
    has_temperature = bool(re.search(r"\d+\s*°?[cC]\b", text))  # e.g., 25°C
    has_other_values = bool(re.search(r"\d+\.\d+", text))  # e.g., 0.8
    has_parameter_name = bool(
        re.search(
            r"\b(?:voc|isc|vmp|imp|pmpp|eficiencia|degradaci[oó]n|garant[íi]a)\b",
            text_lower,
        )
    )

    # Check for specific brands
    has_brand = any(
        brand in text_lower
        for brand in [
            "jinko",
            "canadian",
            "longi",
            "silfab",
            "q.cells",
            "trina",
            "ja",
            "risen",
            "vivint",
        ]
    )

    score = 0.0
    if has_model_number:
        score += 0.25
    if has_temperature:
        score += 0.2
    if has_other_values:
        score += 0.15
    if has_brand:
        score += 0.2
    if has_parameter_name:
        score += 0.2

    return min(score, 1.0)


def _extract_acronym_score(text: str) -> float:
    """
    Extract a technical acronym/unit score (0-1) from text.

    Analyzes the density of technical acronyms and units.

    Args:
        text: Input text to analyze.

    Returns:
        A score between 0 and 1 representing acronym/unit density.
    """
    if not text or not isinstance(text, str):
        return 0.0

    text_lower = text.lower()

    # Count standalone W, kW, kWh, etc. more comprehensively
    unit_patterns = [
        r"\b\d+\s*w\b",  # e.g., 300W, 5 W
        r"\b\d+\s*kw\b",  # e.g., 5kW, 10 kW
        r"\b\d+\s*kwh\b",  # e.g., 100kWh
        r"\b(?:kw|kwh|w|v|a|°c|c|m²|m2|mph)\b",  # standalone units
        r"\b(?:mppt|pwm|dc|ac|voc|isc|vmp|imp|pmpp)\b",  # technical acronyms
    ]

    acronym_count = 0
    for pattern in unit_patterns:
        matches = re.findall(pattern, text_lower)
        acronym_count += len(matches)

    if acronym_count == 0:
        return 0.0

    # Normalize by word count
    words = re.findall(r"\b\w+\b", text_lower)
    if not words:
        return 0.0

    score = acronym_count / len(words)
    return min(score, 1.0)


def infer_user_profile(history: List[Dict[str, str]]) -> str:
    """
    Infer user expertise level based on conversation history.

    Analyzes the first up to 2 user messages to determine expertise level:
    - "novato": Beginner, generic questions, minimal technical vocabulary
    - "intermedio": Intermediate, some technical terms but not highly specific
    - "experto": Expert, specific technical parameters and detailed knowledge

    Args:
        history: List of conversation turns in format [{"role": "user", "content": "..."}].
                 Only "user" role messages are analyzed.

    Returns:
        One of "novato", "intermedio", or "experto".
    """
    # Filter user messages only and take first 2
    user_messages = [
        turn.get("content", "")
        for turn in history
        if turn.get("role") == "user" and turn.get("content")
    ][:2]

    # Default to intermedio if no user messages
    if not user_messages:
        return "intermedio"

    # Combine all user messages
    combined_text = " ".join(user_messages)

    # Calculate component scores
    technical_score = _extract_technical_score(combined_text)
    specificity_score = _extract_specificity_score(combined_text)
    acronym_score = _extract_acronym_score(combined_text)

    # Weighted combination with adjusted weights
    # Emphasize specificity as it's the strongest indicator of expertise
    final_score = (
        technical_score * 0.30 + specificity_score * 0.45 + acronym_score * 0.25
    )

    # Classification with better thresholds
    if final_score < 0.22:
        return "novato"
    elif final_score < 0.48:
        return "intermedio"
    else:
        return "experto"
