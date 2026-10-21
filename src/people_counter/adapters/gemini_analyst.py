import logging
import os
import time
from typing import Any

import httpx
import httpx2
from google import genai
from google.genai import errors, types

from people_counter.adapters.scene_analyst import (
    DECISIONS_SCHEMA,
    SYSTEM_PROMPT,
    AnalystError,
    decisions_prompt,
    description_prompt,
    parse_decisions,
    question_prompt,
)
from people_counter.domain.model import CapacityEvent, Role

log = logging.getLogger(__name__)

# Newest first. When one is saturated ("high demand"), the next one answers.
DEFAULT_GEMINI_MODELS = ("gemini-3.8-flash", "gemini-3.5-flash", "gemini-3.1-flash-lite")


class GeminiSceneAnalyst:
    """Gemini as the vision model: same prompts as Claude, another API. The rest of the app doesn't change."""

    name = "Gemini"

    def __init__(self, models: tuple[str, ...] = DEFAULT_GEMINI_MODELS):
        self._models = models
        api_key = os.environ.get("GEMINI_API_KEY")
        self._client = (
            genai.Client(
                api_key=api_key,
                # One try per model and a short timeout: moving to the next model beats waiting on a busy one.
                http_options=types.HttpOptions(timeout=15_000, retry_options=types.HttpRetryOptions(attempts=1)),
            )
            if api_key
            else None
        )

    def answer(self, image_jpeg: bytes, question: str, role: Role, count: int, capacity: int) -> str:
        return self._ask(image_jpeg, question_prompt(question, role, count, capacity))

    def describe(self, image_jpeg: bytes, count: int, capacity: int) -> str:
        return self._ask(image_jpeg, description_prompt(count, capacity))

    def decide(self, image_jpeg: bytes, event: CapacityEvent) -> dict[Role, str]:
        text = self._ask(
            image_jpeg,
            decisions_prompt(event),
            {"response_mime_type": "application/json", "response_json_schema": DECISIONS_SCHEMA},
        )
        return parse_decisions(text)

    def _ask(self, image_jpeg: bytes, prompt: str, output: dict[str, Any] | None = None) -> str:
        if self._client is None:
            raise AnalystError("Falta la API key de Gemini (ponla en el archivo .env como GEMINI_API_KEY).")
        config = types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT, **(output or {}))
        contents: list[Any] = [types.Part.from_bytes(data=image_jpeg, mime_type="image/jpeg"), prompt]
        busy = False
        for model in self._models:
            started = time.monotonic()
            try:
                response = self._client.models.generate_content(model=model, contents=contents, config=config)
            except httpx.TimeoutException, httpx2.TimeoutException:  # too slow right now: try the next model
                log.warning("%s timed out", model)
                busy = True
                continue
            except errors.ServerError:  # saturated or failing: try the next model
                log.warning("%s is busy", model)
                busy = True
                continue
            except errors.ClientError as error:
                if error.code == 429:
                    busy = True
                    continue
                if error.code == 404:  # retired model
                    continue
                if error.code in (400, 401, 403) and "API key" in str(error.message):
                    raise AnalystError("La API key de Gemini no es válida (revisa el archivo .env).") from error
                raise AnalystError(f"Gemini respondió con un error ({error.code}).") from error
            except (
                httpx.TransportError,
                httpx2.TransportError,
            ) as error:  # the SDK uses either, depending on what's installed
                raise AnalystError("No hay conexión con Gemini; revisa el internet de la sala.") from error
            text = (response.text or "").strip()
            if text:
                log.warning("%s answered in %.1f s", model, time.monotonic() - started)
                return text
        if busy:
            raise AnalystError("Gemini está saturado en este momento; intenta en unos segundos.")
        raise AnalystError("Gemini no dio una respuesta; intenta de nuevo.")
