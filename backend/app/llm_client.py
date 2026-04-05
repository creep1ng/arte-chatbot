"""LLM client module for Arte Chatbot.

Provides a client to interact with OpenAI Chat Completions API
for generating chatbot responses with tool calling support.
"""

import json
import logging
import os
from typing import Any, Optional

from openai import APIError, AuthenticationError, OpenAI

from backend.app.config import settings
from backend.app.tools import get_tool_definitions

logger = logging.getLogger(__name__)

DEFAULT_MODEL = settings.llm_model

ARTE_SYSTEM_PROMPT = (
    "Eres un asistente técnico de Arte Soluciones Energéticas, una empresa B2B "
    "de energía solar. Tu rol es ayudar a clientes con consultas sobre productos "
    "de energía solar como paneles, inversores, controladores y baterías.\n\n"
    "## Instrucciones generales\n"
    "- Responde de manera clara, profesional y enfocada en soluciones energéticas.\n"
    "- Si la pregunta del usuario es general (por ejemplo: qué componentes tiene un "
    "sistema solar, diferencias entre tipos de inversores, comparativas entre "
    "tecnologías de baterías, conceptos de energía solar, etc.), responde "
    "directamente con tu conocimiento sin necesidad de usar herramientas.\n\n"
    "## Cuándo usar la herramienta leer_ficha_tecnica\n"
    "- Usa la herramienta cuando el usuario consulte especificaciones técnicas "
    "detalladas de un producto concreto.\n"
    "- Si el usuario proporciona fabricante y modelo (por ejemplo: 'inversor "
    "Must PC1800F', 'panel Jinko Tiger Pro 460W'), realiza la tool call "
    "directamente con los datos disponibles.\n"
    "- Si el usuario hace una consulta parcial como 'tienen inversores de "
    "3000W?' o 'qué paneles de 500W manejan?', realiza la tool call con los "
    "datos que tengas. Si faltan campos como fabricante o modelo, déjalos "
    "vacíos o con el valor que puedas inferir. El sistema buscará en el "
    "catálogo y te devolverá las opciones disponibles.\n"
    "- No bloquees la tool call por falta de información. Es mejor intentar "
    "la búsqueda con datos parciales que pedir todos los campos al usuario.\n\n"
    "## Convención para rutas S3\n"
    "- NO intentes construir la ruta S3 manualmente. Deja el campo `ruta_s3` VACÍO cuando llames a leer_ficha_tecnica.\n"
    "- Proporciona solo `categoria`, `fabricante` y `modelo`. El sistema buscará automáticamente la ruta correcta en el catálogo.\n"
    "- Si necesitas ver qué productos existen, usa primero la herramienta `buscar_producto`.\n\n"
    "## Cuando uses datos de una ficha técnica\n"
    "- Cita los valores exactos del documento (potencia, voltaje, eficiencia, "
    "dimensiones, peso, etc.).\n"
    "- No inventes ni extrapoles datos que no estén en la ficha.\n"
    "- Si la ficha no contiene la información solicitada, indícalo claramente.\n"
    "- Presenta los datos de forma estructurada y fácil de leer.\n\n"
    "## Preguntas generales\n"
    "- Preguntas como '¿qué componentes tiene un sistema de energía solar?', "
    "'¿cuál es la diferencia entre inversor multifuncional e híbrido?', "
    "'¿cuál es la diferencia entre una batería de gel y una de litio?', o "
    "cualquier consulta conceptual se responden directamente sin usar "
    "herramientas. Usa tu conocimiento general sobre energía solar.\n\n"
    "## Herramientas\n"
    "- Usa la herramienta buscar_producto cuando el usuario pregunte por una "
    "categoría o tipo de producto sin especificar modelo exacto.\n"
    "- Usa la herramienta leer_ficha_tecnica únicamente cuando ya tengas la "
    "ruta_s3 del producto específico.\n"
    "- Si no hay un producto concreto y la pregunta es general, responde directamente.\n"
    "- Si buscar_producto no encuentra resultados, informa al usuario y sugiere "
    "contactar al equipo de ventas."
)

DATASHEET_SYSTEM_PROMPT = (
    "Eres un asistente técnico de Arte Soluciones Energéticas. "
    "Responde ÚNICAMENTE con base en los datos disponibles en la ficha técnica adjunta. "
    "Si un dato no está incluido en la ficha técnica, responde explícitamente que no "
    "tienes esa información y sugiere contactar al equipo de ventas para más detalles. "
    "Cita valores específicos (potencia, voltaje, eficiencia, dimensiones, etc.) cuando "
    "estén disponibles."
)


class LLMServiceError(Exception):
    """Raised when the LLM service returns an error."""

    pass


class LLMClient:
    """Client for interacting with OpenAI Chat Completions API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = DEFAULT_MODEL,
    ) -> None:
        self.api_key = (
            api_key if api_key is not None else os.getenv("OPENAI_API_KEY", "")
        )
        self.model = model
        self.default_system_prompt = ARTE_SYSTEM_PROMPT

        # OpenAI SDK client
        self._openai_client: Optional[OpenAI] = None

    @property
    def openai_client(self) -> OpenAI:
        """Lazy initialization of the OpenAI SDK client."""
        if self._openai_client is None:
            self._openai_client = OpenAI(api_key=self.api_key)
        return self._openai_client

    @staticmethod
    def _extract_text_from_content(content: Any) -> str:
        """Convert chat completion message content into a plain string."""
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            text_parts: list[str] = []
            for block in content:
                if isinstance(block, dict):
                    block_text = block.get("text")
                    if block_text:
                        text_parts.append(str(block_text))
                else:
                    text_parts.append(str(block))
            return "\n".join(text_parts)
        return str(content)

    def get_llm_response_with_tools(
        self,
        message: Optional[str] = None,
        *,
        messages: Optional[list[dict[str, Any]]] = None,
        session_id: str,
        system_prompt: Optional[str] = None,
        context: str = "",
    ) -> dict[str, Any]:
        """Send messages to the LLM with tool definitions using Chat Completions.

        Args:
            message: Single-turn user input (legacy usage).
            messages: Full message list to send to the Responses API.
            session_id: The session identifier for context.
            system_prompt: Optional system prompt override.
            context: Optional session context string with conversation history.

        Returns:
            A dict with 'output_text' and optionally 'tool_calls'.

        Raises:
            LLMServiceError: If the API key is missing or the request fails.
        """
        if not self.api_key:
            raise LLMServiceError("Missing OpenAI API key.")

        instructions = system_prompt or self.default_system_prompt
        tools = get_tool_definitions()

        # Construir el input con contexto si está disponible
        user_input = message
        if context:
            user_input = (
                f"Contexto de la conversación:\n{context}\n\nPregunta actual: {message}"
            )

        logger.debug(
            "LLM call with tools: model=%s, session_id=%s, message_preview=%s, "
            "num_tools=%d",
            self.model,
            session_id,
            message[:100],
            len(tools),
        )

        try:
            response = self.openai_client.responses.create(
                model=self.model,
                instructions=instructions,
                input=user_input,
                tools=tools,
                max_output_tokens=2000,
                reasoning={"effort": "medium"},
                prompt_cache_key=session_id,
            )

            # Extract output text
            output_text = response.output_text

            # Extract tool calls from output
            tool_calls = []
            for item in response.output:
                if item.type == "function_call":
                    tool_calls.append(
                        {
                            "id": item.call_id,
                            "type": "function",
                            "function": {
                                "name": item.name,
                                "arguments": item.arguments,
                            },
                        }
                    )

            result: dict[str, Any] = {
                "output_text": output_text,
            }

            if tool_calls:
                result["tool_calls"] = tool_calls

            return result

        except AuthenticationError as e:
            logger.error("OpenAI authentication error: %s", e)
            raise LLMServiceError("Invalid OpenAI API key") from e
        except APIError as e:
            logger.error("OpenAI API error: %s", e)
            raise LLMServiceError(f"OpenAI API error: {e}") from e
        except Exception as e:
            logger.exception("Unexpected error calling OpenAI API: %s", e)
            raise LLMServiceError(f"LLM service error: {e}") from e

    def get_llm_response_with_file(
        self,
        message: str,
        file_id: str,
        session_id: str,
        system_prompt: Optional[str] = None,
    ) -> str:
        """Send a message to the LLM with a file attached using Responses API.

        Args:
            message: The user's message.
            file_id: The OpenAI file ID from the uploaded PDF.
            session_id: The session identifier for context.
            system_prompt: Optional system prompt override.

        Returns:
            The response content string from the LLM.

        Raises:
            LLMServiceError: If the API key is missing or the request fails.
        """
        if not self.api_key:
            raise LLMServiceError("Missing OpenAI API key.")

        instructions = system_prompt or DATASHEET_SYSTEM_PROMPT

        logger.debug(
            "LLM call with file: model=%s, session_id=%s, file_id=%s, "
            "message_preview=%s",
            self.model,
            session_id,
            file_id,
            message[:100],
        )

        try:
            response = self.openai_client.responses.create(
                model=self.model,
                instructions=instructions,
                input=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_file", "file_id": file_id},
                            {"type": "input_text", "text": message},
                        ],
                    }
                ],
                max_output_tokens=2000,
                reasoning={"effort": "medium"},
                prompt_cache_key=session_id,
            )

            return response.output_text

        except AuthenticationError as e:
            logger.error("OpenAI authentication error (file): %s", e)
            raise LLMServiceError("Invalid OpenAI API key") from e
        except APIError as e:
            logger.error("OpenAI API error (file): %s", e)
            raise LLMServiceError(f"OpenAI API error: {e}") from e
        except Exception as e:
            logger.exception("Unexpected error calling OpenAI API (file): %s", e)
            raise LLMServiceError(f"LLM service error: {e}") from e
