"""LLM client module for Arte Chatbot.

Provides a client to interact with OpenAI Responses API
for generating chatbot responses with tool calling support.
"""

import logging
import os
from typing import Optional

from openai import APIError, AuthenticationError, OpenAI

from backend.app.config import settings
from backend.app.conversation_logger import redact_text
from backend.app.schemas import LLMResponse
from backend.app.tools import get_tool_definitions

logger = logging.getLogger(__name__)


def expand_query_with_context(message: str, history: list) -> str:
    """Expand query with conversational context (stub for future enhancement).

    Currently returns the original message unchanged. This function is intended
    to handle anaphoric references (e.g., "el panel del que hablábamos").

    Args:
        message: The user's message.
        history: List of conversation turns.

    Returns:
        The original message (placeholder for full implementation).
    """
    return message


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
    "- Cuando llames a leer_ficha_tecnica, construye la ruta S3 usando: "
    "raw/{categoria}/{fabricante}-{modelo}.pdf (todo en minúsculas, espacios "
    "reemplazados por guiones).\n"
    "- Ejemplo: para un panel Jinko Tiger Pro 460W, la ruta sería: "
    "raw/paneles/jinko-tiger-pro-460w.pdf\n\n"
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
    "## Clasificación de intención\n"
    "- Al INICIO de cada respuesta, incluye UN markers de clasificación:\n"
    "  - [INTENT: <tipo>] - clasificación de intención\n"
    "  - [CONFIDENCE: 0.XX] - confianza de tu clasificación (entre 0.00 y 1.00)\n"
    "- Tipos válidos: FAQ, product_info, escalate_quote, escalate_technical, escalate_order, fuera_de_dominio\n"
    "- FAQ: preguntas generales sobre energía solar, conceptos, diferencias entre tecnologías\n"
    "- product_info: consultas sobre especificaciones, modelos, características de productos\n"
    "- escalate_quote: solicitudes de cotización, presupuesto, precio de proyectos completos\n"
    "- escalate_technical: problemas técnicos que requieren revisión, errores en equipos\n"
    "- escalate_order: pedidos, compras, adquisición de productos\n"
    "- fuera_de_dominio: preguntas sobre temas que no están relacionados con energía solar, fichas técnicas, FAQ o productos del catálogo\n"
    "- Ejemplo: [INTENT: FAQ][CONFIDENCE: 0.95] Los paneles monocristalinos tienen mayor eficiencia...\n"
    "- Ejemplo: [INTENT: escalate_quote][CONFIDENCE: 0.98] Un agente de ventas te contactará..."
)

_WHATSAPP_SPLIT_INSTRUCTIONS = (
    "\n\n## Formato para WhatsApp y división de mensajes\n"
    "- No uses markdown que WhatsApp no soporte (sin ##, sin **, sin ```, sin []()).\n"
    "- Usa *texto* para negritas y _texto_ para cursiva.\n"
    "- Usa viñetas con • en lugar de - o *.\n"
    "- Mantén respuestas concisas y fáciles de leer en móvil.\n"
    "- Divide tu respuesta en mensajes cortos usando `---` como separador "
    "en una línea propia.\n"
    "- Para preguntas generales (FAQ): máximo 300 caracteres por mensaje, "
    "2-3 mensajes.\n"
    "- Para información de productos: máximo 800 caracteres por mensaje.\n"
    "- Cada mensaje debe tener sentido por sí solo.\n"
    "- No repitas información entre mensajes.\n"
    "- El primer mensaje debe captar la atención; el último debe incluir "
    "un cierre o pregunta.\n"
    "- NO uses separadores para respuestas de escalamiento "
    "(cotización, pedido, problema técnico).\n"
    "- Ejemplo de formato:\n"
    "  Los paneles monocristalinos tienen mejor rendimiento en espacios "
    "reducidos.\n"
    "  ---\n"
    "  Los policristalinos son más económicos pero necesitan más espacio.\n"
    "  ---\n"
    "  ¿Te gustaría más detalles sobre algún modelo en particular?"
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
    """Client for interacting with OpenAI Responses API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = DEFAULT_MODEL,
    ) -> None:
        self.api_key = (
            api_key if api_key is not None else os.getenv("OPENAI_API_KEY", "")
        )
        self.model = model

        # Build system prompt: base + WhatsApp formatting when enabled
        whatsapp_enabled = os.getenv(
            "WHATSAPP_FORMATTER_ENABLED", ""
        ).strip().lower() in (
            "1",
            "true",
            "yes",
        )
        if whatsapp_enabled:
            self.default_system_prompt = (
                ARTE_SYSTEM_PROMPT + _WHATSAPP_SPLIT_INSTRUCTIONS
            )
        else:
            self.default_system_prompt = ARTE_SYSTEM_PROMPT

        # OpenAI SDK client
        self._openai_client: Optional[OpenAI] = None

    @property
    def openai_client(self) -> OpenAI:
        """Lazy initialization of the OpenAI SDK client."""
        if self._openai_client is None:
            self._openai_client = OpenAI(
                api_key=self.api_key,
                timeout=settings.openai_timeout_seconds,
            )
        return self._openai_client

    def get_llm_response_with_tools(
        self,
        message: str,
        session_id: str,
        system_prompt: Optional[str] = None,
        context: str = "",
    ) -> LLMResponse:
        """Send a message to the LLM with tool definitions using Responses API.

        Args:
            message: The user's message.
            session_id: The session identifier for context.
            system_prompt: Optional system prompt override.
            context: Optional session context string with conversation history.

        Returns:
            An LLMResponse with text, tool_calls, and token usage.

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
            redact_text(message)[:100],
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

            # Extract token usage (response.usage can be None)
            input_tokens = response.usage.input_tokens if response.usage else 0
            output_tokens = response.usage.output_tokens if response.usage else 0
            total_tokens = response.usage.total_tokens if response.usage else 0

            return LLMResponse(
                text=output_text,
                tool_calls=tool_calls,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
            )

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
    ) -> LLMResponse:
        """Send a message to the LLM with a file attached using Responses API.

        Args:
            message: The user's message.
            file_id: The OpenAI file ID from the uploaded PDF.
            session_id: The session identifier for context.
            system_prompt: Optional system prompt override.

        Returns:
            An LLMResponse with text and token usage.

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
            redact_text(message)[:100],
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

            # Extract token usage (response.usage can be None)
            input_tokens = response.usage.input_tokens if response.usage else 0
            output_tokens = response.usage.output_tokens if response.usage else 0
            total_tokens = response.usage.total_tokens if response.usage else 0

            return LLMResponse(
                text=response.output_text,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
            )

        except AuthenticationError as e:
            logger.error("OpenAI authentication error (file): %s", e)
            raise LLMServiceError("Invalid OpenAI API key") from e
        except APIError as e:
            logger.error("OpenAI API error (file): %s", e)
            raise LLMServiceError(f"OpenAI API error: {e}") from e
        except Exception as e:
            logger.exception("Unexpected error calling OpenAI API (file): %s", e)
            raise LLMServiceError(f"LLM service error: {e}") from e
