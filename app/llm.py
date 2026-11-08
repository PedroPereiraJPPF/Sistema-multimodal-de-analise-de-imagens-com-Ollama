"""Thin client for the Ollama HTTP API."""

import asyncio
from dataclasses import dataclass

import httpx

from app.config import settings

# A 6 GB GPU fits one vision model at a time. Serializing requests avoids two
# models fighting for VRAM (which would push layers to the CPU and get slow).
_gpu_lock = asyncio.Lock()


class LLMError(Exception):
    """Ollama could not be reached or rejected the request."""


@dataclass(frozen=True)
class ChatReply:
    content: str
    duration_ms: int
    load_ms: int
    output_tokens: int


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=settings.ollama_url, timeout=settings.request_timeout_s)


def _ns_to_ms(value: int | None) -> int:
    return (value or 0) // 1_000_000


async def chat(model: str, system: str, prompt: str, image_b64: str, schema: dict) -> ChatReply:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt, "images": [image_b64]},
        ],
        "format": schema,     # constrained decoding: output must match the schema
        "stream": False,
        "think": False,       # reasoning tokens cost time and add nothing to extraction
        "keep_alive": settings.keep_alive,
        "options": {"temperature": 0, "num_ctx": settings.num_ctx},
    }
    try:
        async with _gpu_lock, _client() as client:
            response = await client.post("/api/chat", json=payload)
    except httpx.HTTPError as exc:
        raise LLMError(f"Não foi possível conectar ao Ollama em {settings.ollama_url}: {exc}") from exc
    if response.is_error:
        raise LLMError(f"Ollama respondeu {response.status_code}: {response.text}")

    data = response.json()
    return ChatReply(
        content=data["message"]["content"],
        duration_ms=_ns_to_ms(data.get("total_duration")),
        load_ms=_ns_to_ms(data.get("load_duration")),
        output_tokens=data.get("eval_count", 0),
    )


async def list_vision_models() -> list[str]:
    """Installed models that accept images. Returns [] if Ollama is unreachable."""
    try:
        async with _client() as client:
            tags = (await client.get("/api/tags")).json().get("models", [])
            names = [model["name"] for model in tags]
            details = await asyncio.gather(
                *(client.post("/api/show", json={"model": name}) for name in names)
            )
    except httpx.HTTPError:
        return []
    return sorted(
        name for name, detail in zip(names, details)
        if "vision" in detail.json().get("capabilities", [])
    )
