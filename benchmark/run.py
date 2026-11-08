"""Run models over a labeled dataset and score them against the ground truth.

A dataset is a folder with one image per case and a JSON file with the same
name holding the expected answer:

    benchmark/datasets/menus-synthetic/menu_01.png
    benchmark/datasets/menus-synthetic/menu_01.json

Usage (inside the app container):

    python -m benchmark.run benchmark/datasets/menus-synthetic --preset menu
    python -m benchmark.run <dataset> --preset menu --models qwen3.5:4b gemma3:4b

Each run writes a Markdown report and the raw JSON to benchmark/results/ and
appends one line per model to benchmark/results/history.md, which is the place
to compare prompt versions over time.
"""

import argparse
import asyncio
import json
from datetime import datetime
from pathlib import Path
from statistics import mean

from app.config import settings
from app.evaluation import overall, score
from app.images import prepare_image
from app.presets import Preset, get_preset
from app.prompts import PROMPT_VERSION
from app.service import extract

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
RESULTS_DIR = Path(__file__).parent / "results"
HISTORY_HEADER = (
    "| Data | Dataset | Prompt | Modelo | Precisão geral | JSON válido | Inferência média |\n"
    "|---|---|---|---|---|---|---|\n"
)


def load_cases(dataset: Path) -> list[tuple[Path, dict]]:
    cases = []
    for image in sorted(dataset.iterdir()):
        truth = image.with_suffix(".json")
        if image.suffix.lower() in IMAGE_SUFFIXES and truth.exists():
            cases.append((image, json.loads(truth.read_text(encoding="utf-8"))))
    if not cases:
        raise SystemExit(f"Nenhum par imagem + .json encontrado em {dataset}")
    return cases


async def evaluate_model(model: str, preset: Preset, cases: list[tuple[Path, dict]]) -> dict:
    rows = []
    for number, (image, expected) in enumerate(cases, start=1):
        jpeg = prepare_image(image.read_bytes(), settings.max_image_side)
        extraction = await extract(preset, model, jpeg)
        scores = score(extraction.result, expected)
        rows.append({
            "image": image.name,
            "valid": extraction.result is not None,
            "error": extraction.error,
            # Load time is a one-off cost of the first request; report it apart.
            "inference_ms": extraction.duration_ms - extraction.load_ms,
            "output_tokens": extraction.output_tokens,
            "overall": overall(scores),
            "scores": scores,
            "result": extraction.result,
        })
        print(f"  [{number}/{len(cases)}] {image.name}: {rows[-1]['overall']:.0%}"
              f" em {rows[-1]['inference_ms'] / 1000:.1f}s", flush=True)

    field_names = sorted({name for row in rows for name in row["scores"]})
    return {
        "model": model,
        "overall": mean(row["overall"] for row in rows),
        "valid_rate": mean(row["valid"] for row in rows),
        "avg_inference_ms": mean(row["inference_ms"] for row in rows),
        "fields": {
            name: mean(row["scores"][name] for row in rows if name in row["scores"])
            for name in field_names
        },
        "cases": rows,
    }


def _pct(value: float) -> str:
    return f"{value:.0%}"


def to_markdown(run: dict) -> str:
    reports = run["reports"]
    lines = [
        f"# Benchmark: {run['dataset']} · prompt {run['prompt_version']}",
        "",
        f"{run['date']} · {run['cases']} imagens · preset `{run['preset']}`",
        "",
        "## Resumo",
        "",
        "| Modelo | Precisão geral | JSON válido | Inferência média |",
        "|---|---|---|---|",
        *(f"| {r['model']} | {_pct(r['overall'])} | {_pct(r['valid_rate'])} | "
          f"{r['avg_inference_ms'] / 1000:.1f} s |" for r in reports),
        "",
        "## Por campo",
        "",
        "| Campo | " + " | ".join(r["model"] for r in reports) + " |",
        "|---|" + "---|" * len(reports),
    ]
    field_names = sorted({name for r in reports for name in r["fields"]})
    for name in field_names:
        lines.append(f"| `{name}` | " + " | ".join(
            _pct(r["fields"][name]) if name in r["fields"] else "—" for r in reports) + " |")

    lines += ["", "## Por imagem", "",
              "| Imagem | " + " | ".join(r["model"] for r in reports) + " |",
              "|---|" + "---|" * len(reports)]
    for index, case in enumerate(reports[0]["cases"]):
        lines.append(f"| {case['image']} | " + " | ".join(
            _pct(r["cases"][index]["overall"]) + ("" if r["cases"][index]["valid"] else " ❌")
            for r in reports) + " |")
    return "\n".join(lines) + "\n"


def save(run: dict) -> Path:
    RESULTS_DIR.mkdir(exist_ok=True)
    stem = f"{datetime.now():%Y%m%d-%H%M%S}_{run['dataset']}_{run['prompt_version']}"
    (RESULTS_DIR / f"{stem}.json").write_text(json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")
    report = RESULTS_DIR / f"{stem}.md"
    report.write_text(to_markdown(run), encoding="utf-8")

    history = RESULTS_DIR / "history.md"
    if not history.exists():
        history.write_text(HISTORY_HEADER, encoding="utf-8")
    with history.open("a", encoding="utf-8") as file:
        for r in run["reports"]:
            file.write(f"| {run['date']} | {run['dataset']} | {run['prompt_version']} | {r['model']} | "
                       f"{_pct(r['overall'])} | {_pct(r['valid_rate'])} | {r['avg_inference_ms'] / 1000:.1f} s |\n")
    return report


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("dataset", type=Path, help="pasta com imagens e gabaritos .json")
    parser.add_argument("--preset", required=True, help="tipo de análise, ex.: menu, receipt")
    parser.add_argument("--models", nargs="+", default=[settings.default_model])
    args = parser.parse_args()

    preset = get_preset(args.preset)
    cases = load_cases(args.dataset)
    reports = []
    for model in args.models:
        print(f"{model} · prompt {PROMPT_VERSION} · {len(cases)} imagens", flush=True)
        reports.append(await evaluate_model(model, preset, cases))

    run = {
        "date": f"{datetime.now():%Y-%m-%d %H:%M}",
        "dataset": args.dataset.name,
        "preset": args.preset,
        "prompt_version": PROMPT_VERSION,
        "cases": len(cases),
        "reports": reports,
    }
    report = save(run)
    print("\n" + to_markdown(run))
    print(f"Relatório salvo em {report}")


if __name__ == "__main__":
    asyncio.run(main())
