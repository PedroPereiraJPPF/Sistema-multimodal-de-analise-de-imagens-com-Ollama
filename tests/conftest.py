import io
import os
import tempfile
from pathlib import Path

import pytest
from PIL import Image

# Point the app to a throwaway SQLite database before it is imported.
_tmp = Path(tempfile.mkdtemp())
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp / 'test.db'}"
os.environ["UPLOAD_DIR"] = str(_tmp / "uploads")

from fastapi.testclient import TestClient  # noqa: E402

from app import llm  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (3000, 1500), "white").save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def fake_llm(monkeypatch):
    """Replace the Ollama call with a canned answer. Set `.content` to change it."""

    class Fake:
        def __init__(self):
            self.content = '{"summary": "Uma mesa com frutas", "main_objects": ["maçã"], "people_count": 0}'
            self.calls: list[dict] = []

        async def chat(self, model, system, prompt, image_b64, schema):
            self.calls.append({"model": model, "prompt": prompt, "schema": schema})
            return llm.ChatReply(content=self.content, duration_ms=1200, load_ms=0, output_tokens=42)

    fake = Fake()
    monkeypatch.setattr(llm, "chat", fake.chat)
    return fake
