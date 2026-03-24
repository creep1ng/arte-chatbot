"""Tool definitions for OpenAI function calling in Arte Chatbot.

This module provides the tool schemas for the `leer_ficha_tecnica` function
that allows the LLM to retrieve and analyze technical datasheets from S3.
"""

from typing import Any

# Valid categories for technical datasheets
DATASHEET_CATEGORIES = ["paneles", "inversores", "controladores", "baterias"]

# Tool definition for reading technical datasheets
LEER_FICHA_TECNICA_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "leer_ficha_tecnica",
        "description": (
            "Lee y analiza la ficha técnica PDF de un producto del catálogo "
            "de Arte Soluciones Energéticas. Usa esta herramienta cuando el "
            "usuario pregunte por especificaciones técnicas detalladas de un "
            "producto específico (panel solar, inversor, controlador, batería) "
            "y tengas la información necesaria: categoría, fabricante y modelo."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "ruta_s3": {
                    "type": "string",
                    "description": (
                        "Ruta completa del archivo PDF en S3. Ejemplo: "
                        "paneles/jinko-tiger-pro-460w.pdf"
                    ),
                },
                "categoria": {
                    "type": "string",
                    "description": (
                        "Categoría del producto. Opciones: paneles, inversores, "
                        "controladores, baterias"
                    ),
                    "enum": DATASHEET_CATEGORIES,
                },
                "fabricante": {
                    "type": "string",
                    "description": "Nombre del fabricante o marca del producto.",
                },
                "modelo": {
                    "type": "string",
                    "description": "Modelo o nombre comercial específico del producto.",
                },
            },
            "required": ["ruta_s3", "categoria", "fabricante", "modelo"],
            "additionalProperties": False,
        },
        "strict": True,
    },
}

# List of all available tools
AVAILABLE_TOOLS: list[dict[str, Any]] = [LEER_FICHA_TECNICA_TOOL]


def get_tool_definitions() -> list[dict[str, Any]]:
    """Return the list of tool definitions for OpenAI Chat Completions.

    Returns:
        List of tool definitions in OpenAI format.
    """
    return AVAILABLE_TOOLS
