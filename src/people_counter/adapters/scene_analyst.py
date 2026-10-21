import base64
import json
import os
from typing import Protocol

import anthropic

from people_counter.domain.model import CapacityEvent, Role

DEFAULT_CLAUDE_MODEL = "claude-opus-5"

ROLE_DESCRIPTIONS = {
    Role.SAFETY: "Seguridad y Protección Civil: aforo, salidas, riesgos para las personas",
    Role.OPERATIONS: "Operaciones: logística de la sala, recursos, que todo funcione",
    Role.MANAGEMENT: "Dirección: impacto, decisiones de negocio, qué significa para la organización",
}

SYSTEM_PROMPT = """\
Eres el asistente de un demo en vivo en la reunión mensual del Comité de IT de Index Chihuahua
("Quick Wins con Inteligencia Artificial"). El público son gerentes de IT de empresas manufactureras.
Una cámara ve la sala; un modelo YOLO en la laptop cuenta a las personas en tiempo real, y tú
recibes una imagen de la sala cuando alguien pregunta o cuando pasa algo.

Reglas:
- Responde en español, en máximo 2 oraciones cortas (unas 40 palabras): se lee en un celular.
  Directo y concreto, sin saludos ni relleno.
- Describe lo que se ve (ropa, objetos, posturas, actividades), nunca quién es alguien:
  no identifiques personas ni adivines rasgos sensibles (edad, origen, salud, etc.).
- Para contar personas confía en el conteo de YOLO que te doy; tú aportas lo que YOLO no sabe:
  qué están haciendo, qué traen puesto, si hay riesgos.
- Si la imagen no permite responder con seguridad, dilo.
"""

DECISIONS_SCHEMA = {
    "type": "object",
    "properties": {role.value: {"type": "string"} for role in Role},
    "required": [role.value for role in Role],
    "additionalProperties": False,
}


class AnalystError(Exception):
    """Something the audience can read: why the AI couldn't answer."""


# The prompts are the same for every model; each adapter only knows how to talk to its own API.


def question_prompt(question: str, role: Role, count: int, capacity: int) -> str:
    return (
        f"Quien pregunta es del equipo de {ROLE_DESCRIPTIONS[role]}. Responde desde ese punto de vista.\n"
        f"YOLO cuenta {count} personas; el aforo de la sala es {capacity}.\n\n"
        f"Pregunta: {question}"
    )


def description_prompt(count: int, capacity: int) -> str:
    return (
        f"YOLO cuenta {count} personas; el aforo de la sala es {capacity}.\n\n"
        "Esto se proyecta en la pantalla grande para todo el público. Describe la sala en máximo "
        "3 oraciones cortas (unas 50 palabras): qué están haciendo las personas, si alguien trae "
        "equipo de seguridad y si ves algún riesgo (salidas, pasillos, gente de pie). "
        "Para esta respuesta ignora el límite de 40 palabras."
    )


def decisions_prompt(event: CapacityEvent) -> str:
    what = (
        f"La sala acaba de rebasar su aforo: YOLO cuenta {event.count} personas y el aforo es {event.capacity}."
        if event.exceeded
        else f"La sala volvió a estar dentro del aforo: {event.count} personas de {event.capacity}."
    )
    teams = "\n".join(f"- {role.value}: {description}" for role, description in ROLE_DESCRIPTIONS.items())
    return (
        f"{what}\n\nMira la imagen y decide qué debe hacer cada equipo ahora. Para cada uno escribe "
        f"una sola decisión de máximo 30 palabras: la acción concreta que le toca y por qué. "
        f"Cada equipo recibe un mensaje distinto.\n\nEquipos:\n{teams}"
    )


def parse_decisions(text: str) -> dict[Role, str]:
    try:
        decisions = json.loads(text)
        return {role: str(decisions[role.value]) for role in Role}
    except (ValueError, KeyError, TypeError) as error:
        raise AnalystError("La IA no devolvió las decisiones en el formato esperado.") from error


class SceneAnalyst(Protocol):
    name: str  # shown to the audience: "Claude", "Gemini"...

    def answer(self, image_jpeg: bytes, question: str, role: Role, count: int, capacity: int) -> str: ...

    def decide(self, image_jpeg: bytes, event: CapacityEvent) -> dict[Role, str]: ...

    def describe(self, image_jpeg: bytes, count: int, capacity: int) -> str: ...


class ClaudeSceneAnalyst:
    """Claude Vision: understands what YOLO only detects."""

    name = "Claude"

    def __init__(self, model: str = DEFAULT_CLAUDE_MODEL):
        self._model = model
        # Organization-wide keys (not scoped to a workspace) must say which workspace pays for each request.
        workspace = os.environ.get("ANTHROPIC_WORKSPACE_ID")
        headers = {"anthropic-workspace-id": workspace} if workspace else None
        self._client = anthropic.Anthropic(timeout=45.0, max_retries=1, default_headers=headers)

    def answer(self, image_jpeg: bytes, question: str, role: Role, count: int, capacity: int) -> str:
        return self._ask(image_jpeg, question_prompt(question, role, count, capacity), {"effort": "low"})

    def describe(self, image_jpeg: bytes, count: int, capacity: int) -> str:
        return self._ask(image_jpeg, description_prompt(count, capacity), {"effort": "low"})

    def decide(self, image_jpeg: bytes, event: CapacityEvent) -> dict[Role, str]:
        output_config: anthropic.types.beta.BetaOutputConfigParam = {
            "effort": "low",
            "format": {"type": "json_schema", "schema": DECISIONS_SCHEMA},
        }
        return parse_decisions(self._ask(image_jpeg, decisions_prompt(event), output_config))

    def _ask(self, image_jpeg: bytes, prompt: str, output_config: anthropic.types.beta.BetaOutputConfigParam) -> str:
        if not (self._client.api_key or self._client.auth_token):
            raise AnalystError("Falta la API key de Anthropic (ponla en el archivo .env como ANTHROPIC_API_KEY).")
        image = base64.standard_b64encode(image_jpeg).decode()
        try:
            response = self._client.beta.messages.create(
                model=self._model,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                output_config=output_config,
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image}},
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
            )
        except anthropic.AuthenticationError as error:
            raise AnalystError("Falta la API key de Anthropic o no es válida (revisa el archivo .env).") from error
        except anthropic.RateLimitError as error:
            raise AnalystError("Demasiadas preguntas a la vez; intenta en unos segundos.") from error
        except (anthropic.APIConnectionError, anthropic.APITimeoutError) as error:
            raise AnalystError("No hay conexión con Claude; revisa el internet de la sala.") from error
        except anthropic.BadRequestError as error:
            if "credit balance" in error.message:
                raise AnalystError("La cuenta de Anthropic se quedó sin crédito (Plans & Billing).") from error
            raise AnalystError(f"Claude respondió con un error ({error.status_code}).") from error
        except anthropic.APIStatusError as error:
            raise AnalystError(f"Claude respondió con un error ({error.status_code}).") from error

        if response.stop_reason == "refusal":
            raise AnalystError("Claude prefirió no responder esa pregunta.")
        text = "".join(block.text for block in response.content if block.type == "text").strip()
        if not text:
            raise AnalystError("Claude no dio una respuesta; intenta de nuevo.")
        return text
