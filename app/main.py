"""FastAPI application: server-rendered UI plus a small JSON API."""

import csv
import io
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import quote

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import llm, service
from app.config import settings
from app.db import Analysis, get_session, init_db
from app.evaluation import changed_fields, field_accuracy, summarize
from app.presets import CUSTOM_KEY, DYNAMIC_LABELS, PRESETS, QUESTION_KEY, preset_label

BASE_DIR = Path(__file__).parent


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Analisador de Imagens", lifespan=lifespan)
settings.upload_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")

templates = Jinja2Templates(directory=BASE_DIR / "templates")
templates.env.filters["pretty"] = lambda value: json.dumps(value, ensure_ascii=False, indent=2)
templates.env.globals["preset_label"] = preset_label
templates.env.globals["QUESTION_KEY"] = QUESTION_KEY

# Every analysis type as {key: label}, for the select boxes.
PRESET_OPTIONS = {**{key: p.label for key, p in PRESETS.items()}, **DYNAMIC_LABELS}

SessionDep = Annotated[Session, Depends(get_session)]


def _to_dict(analysis: Analysis) -> dict[str, Any]:
    return {
        "id": analysis.id,
        "run_id": analysis.run_id,
        "created_at": analysis.created_at.isoformat(),
        "image_name": analysis.image_name,
        "preset": analysis.preset,
        "model": analysis.model,
        "result": analysis.result,
        "error": analysis.error,
        "duration_ms": analysis.duration_ms,
        "load_ms": analysis.load_ms,
        "output_tokens": analysis.output_tokens,
        "corrected": analysis.corrected,
    }


async def _run(session: Session, image: UploadFile, preset: str, models: list[str],
               fields: str, context: str) -> str:
    try:
        return await service.analyze_image(
            session,
            image=await image.read(),
            filename=image.filename or "imagem",
            preset_key=preset,
            models=models or [settings.default_model],
            fields_spec=fields,
            context=context,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# --- Web UI ------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index(request: Request, error: str = ""):
    models = await llm.list_vision_models()
    return templates.TemplateResponse(request, "index.html", {
        "error": error,
        "presets": PRESET_OPTIONS,
        "question_key": QUESTION_KEY,
        "custom_key": CUSTOM_KEY,
        "models": models,
        "default_model": settings.default_model,
    })


@app.post("/analyze")
async def analyze_form(
    session: SessionDep,
    image: Annotated[UploadFile, File()],
    preset: Annotated[str, Form()],
    models: Annotated[list[str], Form()] = [],
    fields: Annotated[str, Form()] = "",
    context: Annotated[str, Form()] = "",
):
    try:
        run_id = await _run(session, image, preset, models, fields, context)
    except HTTPException as exc:
        return RedirectResponse(f"/?error={quote(exc.detail)}", status_code=303)
    return RedirectResponse(f"/runs/{run_id}", status_code=303)


@app.get("/runs/{run_id}", response_class=HTMLResponse)
def run_page(request: Request, run_id: str, session: SessionDep, error: str = ""):
    analyses = service.get_run(session, run_id)
    if not analyses:
        raise HTTPException(status_code=404, detail="Análise não encontrada")
    cards = [
        {
            "analysis": a,
            "editable": a.corrected or a.result or service.empty_result(a),
            "changed": changed_fields(a.result, a.corrected) if a.corrected else [],
            "accuracy": field_accuracy(a.result, a.corrected) if a.corrected else None,
        }
        for a in analyses
    ]
    return templates.TemplateResponse(request, "run.html", {
        "first": analyses[0], "cards": cards, "error": error,
    })


@app.post("/analyses/{analysis_id}/review")
def review_form(analysis_id: int, session: SessionDep, corrected: Annotated[str, Form()]):
    analysis = session.get(Analysis, analysis_id)
    if analysis is None:
        raise HTTPException(status_code=404, detail="Análise não encontrada")
    url = f"/runs/{analysis.run_id}"
    try:
        service.review(session, analysis, corrected)
    except ValueError as exc:
        return RedirectResponse(f"{url}?error={quote(str(exc))}", status_code=303)
    return RedirectResponse(f"{url}#analysis-{analysis.id}", status_code=303)


@app.get("/history", response_class=HTMLResponse)
def history(request: Request, session: SessionDep, q: str = "", preset: str = "", model: str = ""):
    analyses = service.search(session, text=q, preset=preset, model=model)
    models = sorted(set(session.scalars(select(Analysis.model).distinct())))
    return templates.TemplateResponse(request, "history.html", {
        "analyses": analyses, "q": q, "preset": preset, "model": model,
        "presets": PRESET_OPTIONS, "models": models,
    })


@app.get("/metrics", response_class=HTMLResponse)
def metrics(request: Request, session: SessionDep):
    reports = summarize(list(session.scalars(select(Analysis))))
    return templates.TemplateResponse(request, "metrics.html", {"reports": reports})


@app.get("/export.csv")
def export_csv(session: SessionDep):
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["id", "created_at", "image", "preset", "model", "valid", "duration_ms",
                     "load_ms", "output_tokens", "reviewed", "field_accuracy", "result", "corrected"])
    for a in session.scalars(select(Analysis).order_by(Analysis.id)):
        accuracy = f"{field_accuracy(a.result, a.corrected):.2f}" if a.corrected else ""
        writer.writerow([
            a.id, a.created_at.isoformat(), a.image_name, a.preset, a.model, a.is_valid,
            a.duration_ms, a.load_ms, a.output_tokens, a.corrected is not None, accuracy,
            json.dumps(a.result, ensure_ascii=False), json.dumps(a.corrected, ensure_ascii=False),
        ])
    return Response(
        buffer.getvalue().encode("utf-8-sig"),  # BOM so Excel opens accents correctly
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=analises.csv"},
    )


# --- JSON API ----------------------------------------------------------------

@app.post("/api/analyze")
async def analyze_api(
    session: SessionDep,
    image: Annotated[UploadFile, File()],
    preset: Annotated[str, Form()] = "general",
    models: Annotated[list[str], Form()] = [],
    fields: Annotated[str, Form()] = "",
    context: Annotated[str, Form()] = "",
):
    run_id = await _run(session, image, preset, models, fields, context)
    return {"run_id": run_id, "analyses": [_to_dict(a) for a in service.get_run(session, run_id)]}


@app.get("/api/analyses")
def list_api(session: SessionDep, q: str = "", preset: str = "", model: str = "", limit: int = 50):
    return [_to_dict(a) for a in service.search(session, text=q, preset=preset, model=model, limit=limit)]


@app.get("/health")
async def health():
    return {"status": "ok", "vision_models": await llm.list_vision_models()}
