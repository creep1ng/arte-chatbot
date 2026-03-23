"""LLM client module for Arte Chatbot.

Provides a client to interact with LLM APIs (OpenAI-compatible)
for generating chatbot responses with tool calling support.
"""

import logging
import os
from typing import Any, Optional

import requests
from openai import OpenAI
from openai import APIError, AuthenticationError

from backend.app.tools import get_tool_definitions

logger = logging.getLogger(__name__)

OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = "gpt-5.4-nano"

ARTE_SYSTEM_PROMPT = (
    "Eres un asistente técnico de Arte Soluciones Energéticas, una empresa B2B "
    "de energía solar. Tu rol es ayudar a clientes con consultas sobre productos "
    "de energía solar como paneles, inversores, controladores y baterías.\n\n"
    "## Instrucciones generales\n"
    "- Responde de manera clara, profesional y enfocada en soluciones energéticas.\n"
    "- Cuando el usuario pregunte por especificaciones técnicas de un producto "
    "  específico, usa la herramienta leer_ficha_tecnica para consultar la ficha técnica real.\n"
    "- Si no tienes suficiente información para identificar el producto exacto, "
    "  pregunta al usuario por los campos faltantes: categoría, fabricante, modelo o nombre comercial.\n\n"
    "## Convention for S3 paths\n"
    "- Cuando debas llamar a leer_ficha_tecnica, construye la ruta S3 usando: "
    "  {categoria}/{fabricante}-{modelo}.pdf (todo en minúsculas, espacios reemplazados por guiones)\n"
    "- Ejemplo: para un panel Jinko Tiger Pro 460W, la ruta sería: "
    "  paneles/jinko-tiger-pro-460w.pdf\n\n"
    "## Cuando uses datos de una ficha técnica\n"
    "- Cita los valores exactos del documento (potencia, voltaje, eficiencia, dimensiones, peso, etc.).\n"
    "- No inventes ni extrapoles datos que no estén en la ficha.\n"
    "- Si la ficha no contiene la información solicitada, indícalo claramente.\n"
    "- Presenta los datos de forma estructurada y fácil de leer."
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
    """Client for interacting with OpenAI-compatible LLM APIs."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_url: str = OPENAI_API_URL,
        model: str = DEFAULT_MODEL,
    ) -> None:
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.api_url = api_url
        self.model = model
        self.default_system_prompt = ARTE_SYSTEM_PROMPT

        # OpenAI SDK client for new methods
        self._openai_client: Optional[OpenAI] = None

    @property
    def openai_client(self) -> OpenAI:
        """Lazy initialization of the OpenAI SDK client."""
        if self._openai_client is None:
            self._openai_client = OpenAI(api_key=self.api_key)
        return self._openai_client

    def get_llm_response(
        self,
        message: str,
        session_id: str,
        system_prompt: Optional[str] = None,
    ) -> str:
        """Send a message to the LLM and return the response text.

        This is the original method using requests. Kept for backward compatibility.
        """
        if not self.api_key:
            raise LLMServiceError("Missing OpenAI API key.")

        prompt = system_prompt or self.default_system_prompt

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": message},
            ],
            "temperature": 0.7,
            "max_tokens": 500,
            "user": session_id,
        }

        try:
            response = requests.post(
                self.api_url, headers=headers, json=payload, timeout=30
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except requests.exceptions.Timeout:
            raise LLMServiceError("LLM service timed out")
        except requests.exceptions.RequestException as e:
            raise LLMServiceError(f"LLM service error: {e}")
        except (KeyError, IndexError) as e:
            raise LLMServiceError(f"Unexpected LLM response format: {e}")

    def get_llm_response_with_tools(
        self,
        message: str,
        session_id: str,
        system_prompt: Optional[str] = None,
    ) -> dict[str, Any]:
        """Send a message to the LLM with tool definitions and return the full response.

        This method allows the LLM to decide whether to call tools (like leer_ficha_tecnica)
        based on the user's query.

        Args:
            message: The user's message.
            session_id: The session identifier for context.
            system_prompt: Optional system prompt override.

        Returns:
            The full response dict from OpenAI, which may contain tool_calls.

        Raises:
            LLMServiceError: If the API key is missing or the request fails.
        """
        if not self.api_key:
            raise LLMServiceError("Missing OpenAI API key.")

        prompt = system_prompt or self.default_system_prompt
        tools = get_tool_definitions()

        try:
            response = self.openai_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": message},
                ],
                tools=tools,
                temperature=0.7,
                max_tokens=500,
                user=session_id,
            )

            # Convert response to dict format for easier inspection
            result: dict[str, Any] = {
                "choices": [
                    {
                        "message": {
                            "role": response.choices[0].message.role,
                            "content": response.choices[0].message.content,
                        }
                    }
                ]
            }

            # Include tool_calls if present
            if response.choices[0].message.tool_calls:
                result["choices"][0]["message"]["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": tc.type,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in response.choices[0].message.tool_calls
                ]

            return result

        except AuthenticationError as e:
            logger.error(f"OpenAI authentication error: {e}")
            raise LLMServiceError("Invalid OpenAI API key") from e
        except APIError as e:
            logger.error(f"OpenAI API error: {e}")
            raise LLMServiceError(f"OpenAI API error: {e}") from e
        except Exception as e:
            logger.exception(f"Unexpected error calling OpenAI API: {e}")
            raise LLMServiceError(f"LLM service error: {e}") from e

    def get_llm_response_with_file(
        self,
        message: str,
        file_id: str,
        session_id: str,
        system_prompt: Optional[str] = None,
    ) -> str:
        """Send a message to the LLM with a file attached for analysis.

        This method is used for the second LLM call when analyzing a technical
        datasheet that has been uploaded to OpenAI Files API.

        Args:
            message: The user's message.
            file_id: The OpenAI file ID from the uploaded PDF.
            session_id: The session identifier for context.
            system_prompt: Optional system prompt override. Defaults to DATASHEET_SYSTEM_PROMPT.

        Returns:
            The response content string from the LLM.

        Raises:
            LLMServiceError: If the API key is missing or the request fails.
        """
        if not self.api_key:
            raise LLMServiceError("Missing OpenAI API key.")

        prompt = system_prompt or DATASHEET_SYSTEM_PROMPT

        try:
            response = self.openai_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": prompt},
                    {
                        "role": "user",
                        "content": message,
                        "file citations": [
                            {"type": "file", "file_id": file_id}
                        ],
                    },
                ],
                temperature=0.7,
                max_tokens=1000,
                user=session_id,
            )

            return response.choices[0].message.content or ""

        except AuthenticationError as e:
            logger.error(f"OpenAI authentication error: {e}")
            raise LLMServiceError("Invalid OpenAI API key") from e
        except APIError as e:
            logger.error(f"OpenAI API error: {e}")
            raise LLMServiceError(f"OpenAI API error: {e}") from e
        except Exception as e:
            logger.exception(f"Unexpected error calling OpenAI API: {e}")
            raise LLMServiceError(f"LLM service error: {e}") from e
