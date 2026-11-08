import asyncio
import json

from app import llm
from benchmark import run


def test_benchmark_scores_each_case_and_writes_reports(tmp_path, monkeypatch, png_bytes):
    (tmp_path / "menu_01.png").write_bytes(png_bytes)
    expected = {"restaurant_name": "Sushi Hana", "items": [{"name": "Temaki", "description": None,
                                                           "price": 29.9, "category": "Temakis"}]}
    (tmp_path / "menu_01.json").write_text(json.dumps(expected), encoding="utf-8")

    async def fake_chat(*_):
        answer = {**expected, "restaurant_name": "Sushi Rana"}  # one field wrong
        return llm.ChatReply(content=json.dumps(answer), duration_ms=5000, load_ms=1000, output_tokens=80)

    monkeypatch.setattr(llm, "chat", fake_chat)
    monkeypatch.setattr(run, "RESULTS_DIR", tmp_path / "results")

    report = asyncio.run(run.evaluate_model("fake", run.get_preset("menu"), run.load_cases(tmp_path)))
    assert report["fields"]["restaurant_name"] == 0.0
    assert report["fields"]["items.price"] == 1.0
    assert report["avg_inference_ms"] == 4000  # load time excluded

    saved = run.save({"date": "2026-11-08 10:00", "dataset": "t", "preset": "menu",
                      "prompt_version": "v1", "cases": 1, "reports": [report]})
    assert "`items.price`" in saved.read_text(encoding="utf-8")
    assert "| t | v1 | fake |" in (tmp_path / "results" / "history.md").read_text(encoding="utf-8")
