"""
LLM Client for Arte Soluciones Energéticas Chatbot

Provider: OpenAI (https://platform.openai.com/docs/api-reference)

- Loads API key from environment (OPENAI_API_KEY)
- Implements system prompt for Arte Soluciones Energéticas
- Raises LLMServiceError on failures instead of returning error strings
- Provides get_llm_response(message: str, session_id: str, system_prompt: str) -> str
"""

import logging
import os

import requests

logger = logging.getLogger(__name__)

OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = "gpt-5.4-nano"

ARTE_SYSTEM_PROMPT = (
    "Eres un asistente de Arte Soluciones Energéticas. "
    "Responde de manera clara, profesional y enfocada en soluciones energéticas."
)


class LLMServiceError(Exception):
    """Raised when the LLM service is unavailable or returns an error."""


class LLMClient:
    def __init__(
        self,
        api_key: str | None = None,
        api_url: str = OPENAI_API_URL,
        model: str = DEFAULT_MODEL,
    ):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.api_url = api_url
        self.model = model
        self.default_system_prompt = ARTE_SYSTEM_PROMPT

    # TODO: Add conversation history support for multi-turn context (session_id currently unused for memory)
    def get_llm_response(
        self, message: str, session_id: str, system_prompt: str | None = None
    ) -> str:
        """Send a message to the LLM and return the assistant's reply.

        Raises:
            LLMServiceError: If the API key is missing or the request fails.
        """
        if not self.api_key:
            raise LLMServiceError("Missing OpenAI API key.")

        prompt = system_prompt or self.default_system_prompt
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        data = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": message},
            ],
            "user": session_id,
        }

        try:
            response = requests.post(
                self.api_url, headers=headers, json=data, timeout=15
            )
            response.raise_for_status()
            result = response.json()
            return result["choices"][0]["message"]["content"]
        except requests.Timeout:
            logger.exception("OpenAI API request timed out")
            raise LLMServiceError("LLM request timed out.")
        except requests.HTTPError as e:
            logger.exception("OpenAI API returned an HTTP error: %s", e)
            raise LLMServiceError(f"LLM HTTP error: {e}") from e
        except (KeyError, IndexError) as e:
            logger.exception("Unexpected response structure from OpenAI API")
            raise LLMServiceError("Unexpected LLM response format.") from e
        except Exception as e:
            logger.exception("Unexpected error calling OpenAI API: %s", e)
            raise LLMServiceError(f"LLM service error: {e}") from e
