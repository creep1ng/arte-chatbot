"""Tool definitions for OpenAI function calling in Arte Chatbot.

This module provides the tool schemas for the `leer_ficha_tecnica` function
that allows the LLM to retrieve and analyze technical datasheets from S3.
"""

from typing import Any

# Valid categories for technical datasheets
DATASHEET_CATEGORIES = ["paneles", "inversores", "controladores", "baterias"]

# Tool definition for reading technical datasheets (Responses API format)
LEER_FICHA_TECNICA_TOOL: dict[str, Any] = {
    "type": "function",
    "name": "leer_ficha_tecnica",
    "description": (
        "Lee y analiza la ficha técnica PDF de un producto del catálogo "
        "de Arte Soluciones Energéticas. Úsala cuando el usuario pregunte "
        "por especificaciones técnicas de un producto. Puedes invocarla "
        "con datos parciales (solo categoría, o categoría + fabricante, "
        "etc.) para buscar opciones disponibles en el catálogo."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "ruta_s3": {
                "type": "string",
                "description": (
                    "Ruta completa del archivo PDF en S3. Ejemplo: "
                    "paneles/jinko-tiger-pro-460w.pdf. Si no se conoce "
                    "la ruta exacta, se puede omitir y el sistema "
                    "buscará por los demás campos."
                ),
            },
            "categoria": {
                "type": "string",
                "description": (
                    "Categoría del producto. Opciones: paneles, inversores, "
                    "controladores, baterias."
                ),
                "enum": DATASHEET_CATEGORIES,
            },
            "fabricante": {
                "type": "string",
                "description": (
                    "Nombre del fabricante o marca del producto. "
                    "Opcional si no se conoce."
                ),
            },
            "modelo": {
                "type": "string",
                "description": (
                    "Modelo o nombre comercial específico del producto. "
                    "Opcional si no se conoce."
                ),
            },
        },
        "required": ["categoria"],
        "additionalProperties": False,
    },
    "strict": False,
}

# List of all available tools
AVAILABLE_TOOLS: list[dict[str, Any]] = [LEER_FICHA_TECNICA_TOOL]


def get_tool_definitions() -> list[dict[str, Any]]:
    """Return the list of tool definitions for OpenAI Responses API.

    Returns:
        List of tool definitions in OpenAI Responses API format.
    """
    return AVAILABLE_TOOLS
