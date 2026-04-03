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
    "function": {
        "name": "leer_ficha_tecnica",
        "description": (
            "Lee y analiza la ficha técnica PDF de un producto del catálogo "
            "de Arte Soluciones Energéticas. Úsala cuando el usuario pregunte "
            "por especificaciones técnicas de un producto. ruta_s3 es obligatoria. "
            "Usa buscar_producto primero si no conoces la ruta exacta."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "ruta_s3": {
                    "type": "string",
                    "description": (
                        "Ruta completa del archivo PDF en S3 (obligatoria). "
                        "Ejemplo: paneles/jinko-tiger-pro-460w.pdf. "
                        "Usa buscar_producto para obtener la ruta_s3 si no la conoces."
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
    },
}

BUSCAR_PRODUCTO_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "buscar_producto",
        "description": (
            "Busca productos en el catálogo por categoría, fabricante, "
            "capacidad u otras características. Devuelve lista de productos "
            "coincidentes con sus rutas S3 para poder leer sus fichas técnicas."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "categoria": {
                    "type": "string",
                    "enum": DATASHEET_CATEGORIES,
                    "description": "Categoría del producto a buscar.",
                },
                "fabricante": {
                    "type": "string",
                    "description": "Nombre del fabricante o marca. Opcional.",
                },
                "capacidad_min": {
                    "type": "number",
                    "description": (
                        "Capacidad mínima (W para paneles/inversores, Ah para baterías). "
                        "Opcional."
                    ),
                },
                "capacidad_max": {
                    "type": "number",
                    "description": "Capacidad máxima. Opcional.",
                },
                "tipo": {
                    "type": "string",
                    "description": (
                        "Tipo de producto (mppt, multifuncional, gel, litio, monocristalino, etc.). "
                        "Opcional."
                    ),
                },
            },
            "required": ["categoria"],
            "additionalProperties": False,
        },
        "strict": False,
    },
}

# List of all available tools
AVAILABLE_TOOLS: list[dict[str, Any]] = [
    LEER_FICHA_TECNICA_TOOL,
    BUSCAR_PRODUCTO_TOOL,
]


def get_tool_definitions() -> list[dict[str, Any]]:
    """Return the list of tool definitions for OpenAI Responses API.

    Returns:
        List of tool definitions in OpenAI Responses API format.
    """
    return AVAILABLE_TOOLS
