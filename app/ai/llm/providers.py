import json
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import TypeVar

import httpx
from google import genai
from google.genai.errors import APIError
from google.genai import types
from pydantic import BaseModel, ValidationError

from app.ai.llm.base import InvalidStructuredOutputError, ProviderRequestError

T = TypeVar("T", bound=BaseModel)


def _parse_result(raw: str, schema: type[T]) -> T:
    try:
        return schema.model_validate_json(raw)
    except (TypeError, ValidationError, ValueError) as exc:
        raise InvalidStructuredOutputError("Provider returned invalid structured output") from exc


class GeminiProvider:
    name = "gemini"

    def __init__(self, *, api_key: str, model: str):
        self.client = genai.Client(api_key=api_key)
        self.model = model

    async def generate_structured(
        self, *, system: str, user: str, schema: type[T], timeout_s: float
    ) -> T:
        try:
            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=user,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    response_mime_type="application/json",
                    response_schema=schema,
                    http_options=types.HttpOptions(timeout=int(timeout_s * 1000)),
                ),
            )
        except (APIError, TimeoutError, OSError) as exc:
            raise ProviderRequestError("Gemini request failed") from exc
        if not response.text:
            raise InvalidStructuredOutputError("Gemini returned an empty response")
        return _parse_result(response.text, schema)


class OpenRouterProvider:
    name = "openrouter"
    endpoint = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self, *, api_key: str, models: list[str]):
        self.api_key = api_key
        self.models = models

    async def generate_structured(
        self, *, system: str, user: str, schema: type[T], timeout_s: float
    ) -> T:
        failures = []
        retry_after_s = None
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            for model in self.models:
                try:
                    response = await client.post(
                        self.endpoint,
                        headers={"Authorization": f"Bearer {self.api_key}"},
                        json={
                            "model": model,
                            "messages": [
                                {"role": "system", "content": system},
                                {"role": "user", "content": user},
                            ],
                            "response_format": {
                                "type": "json_schema",
                                "json_schema": {
                                    "name": schema.__name__,
                                    "strict": True,
                                    "schema": schema.model_json_schema(),
                                },
                            },
                        },
                    )
                    response.raise_for_status()
                    content = response.json()["choices"][0]["message"]["content"]
                    return _parse_result(content, schema)
                except InvalidStructuredOutputError:
                    raise
                except httpx.HTTPStatusError as exc:
                    retry = exc.response.headers.get("Retry-After")
                    if exc.response.status_code == 429 and retry:
                        try:
                            retry_seconds = float(retry)
                        except ValueError:
                            try:
                                retry_time = parsedate_to_datetime(retry)
                                retry_seconds = max(
                                    0,
                                    (retry_time - datetime.now(timezone.utc)).total_seconds(),
                                )
                            except (TypeError, ValueError, OverflowError):
                                retry_seconds = 0
                        retry_after_s = max(retry_after_s or 0, retry_seconds)
                    detail = " ".join(exc.response.text.split())[:500]
                    failures.append(
                        f"HTTP {exc.response.status_code}: {detail or type(exc).__name__}"
                    )
                except (httpx.HTTPError, KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
                    failures.append(type(exc).__name__)
        raise ProviderRequestError(
            "All OpenRouter models failed: " + ", ".join(failures or ["no models configured"]),
            retry_after_s=retry_after_s,
        )


class OllamaProvider:
    name = "ollama"

    def __init__(self, *, base_url: str, model: str):
        self.endpoint = base_url.rstrip("/") + "/api/chat"
        self.model = model

    async def generate_structured(
        self, *, system: str, user: str, schema: type[T], timeout_s: float
    ) -> T:
        try:
            async with httpx.AsyncClient(timeout=timeout_s) as client:
                response = await client.post(
                    self.endpoint,
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ],
                        "format": schema.model_json_schema(),
                        "stream": False,
                    },
                )
                response.raise_for_status()
                content = response.json()["message"]["content"]
        except (httpx.HTTPError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ProviderRequestError("Ollama request failed") from exc
        return _parse_result(content, schema)
