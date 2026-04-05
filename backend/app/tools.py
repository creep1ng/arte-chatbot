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

# Tool definition for searching products in the catalog
BUSCAR_PRODUCTO_TOOL: dict[str, Any] = {
    "type": "function",
    "name": "buscar_producto",
    "description": (
        "Busca productos en el catálogo de Arte Soluciones Energéticas por "
        "categoría, fabricante, capacidad u otras características. Devuelve "
        "una lista de productos coincidentes con sus rutas S3 para poder "
        "leer sus fichas técnicas con la herramienta leer_ficha_tecnica."
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
                "description": (
                    "Nombre del fabricante o marca. Búsqueda parcial "
                    "(case-insensitive). Opcional."
                ),
            },
            "capacidad_min": {
                "type": "number",
                "description": (
                    "Capacidad o potencia mínima (W para paneles/inversores, "
                    "Ah para baterías). Opcional."
                ),
            },
            "capacidad_max": {
                "type": "number",
                "description": ("Capacidad o potencia máxima. Opcional."),
            },
            "tipo": {
                "type": "string",
                "description": (
                    "Tipo de producto (mppt, pwm, onda_pura, multifuncional, "
                    "gel, litio, monocristalino, etc.). Opcional."
                ),
            },
            "modelo_contiene": {
                "type": "string",
                "description": (
                    "Texto que debe contener el nombre del modelo. "
                    "Búsqueda parcial (case-insensitive). Opcional."
                ),
            },
        },
        "required": ["categoria"],
        "additionalProperties": False,
    },
    "strict": False,
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
