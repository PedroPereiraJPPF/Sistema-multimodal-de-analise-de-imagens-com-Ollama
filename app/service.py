"""Use cases shared by the web UI and the JSON API."""

import base64
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import String, cast, or_, select
from sqlalchemy.orm import Session

from app import llm
from app.config import settings
from app.db import Analysis
from app.images import prepare_image
from app.presets import Preset, get_preset
from app.prompts import PROMPT_VERSION, SYSTEM_PROMPT, build_user_prompt


@dataclass
class Extraction:
    """Outcome of asking one model about one image."""

    result: dict | None = None
    raw_response: str = ""
    error: str | None = None
    duration_ms: int = 0
    load_ms: int = 0
    output_tokens: int = 0


NULL_WORDS = {"null", "none"}


def _clean_nulls(value):
    """Turn the text "null" into a real null: small models sometimes quote it."""
    if isinstance(value, str) and value.strip().casefold() in NULL_WORDS:
        return None
    if isinstance(value, list):
        return [_clean_nulls(item) for item in value]
    if isinstance(value, dict):
        return {key: _clean_nulls(item) for key, item in value.items()}
    return value


def _parse(preset: Preset, content: str) -> dict:
    try:
        data = _clean_nulls(json.loads(content))
    except json.JSONDecodeError:
        data = content  # let Pydantic report the malformed JSON as a schema error
    validate = preset.schema.model_validate_json if isinstance(data, str) else preset.schema.model_validate
    return validate(data).model_dump(mode="json")


async def extract(preset: Preset, model: str, jpeg: bytes, context: str = "") -> Extraction:
    """Prompt the model, then validate its answer against the preset schema.

    Shared by the web app and the offline evaluation, so both measure the same thing.
    """
    image_b64 = base64.b64encode(jpeg).decode()
    prompt = build_user_prompt(preset, context)
    try:
        reply = await llm.chat(model, SYSTEM_PROMPT, prompt, image_b64, preset.schema.model_json_schema())
    except llm.LLMError as exc:
        return Extraction(error=str(exc))

    extraction = Extraction(
        raw_response=reply.content,
        duration_ms=reply.duration_ms,
        load_ms=reply.load_ms,
        output_tokens=reply.output_tokens,
    )
    try:
        extraction.result = _parse(preset, reply.content)
    except ValidationError as exc:
        extraction.error = f"Resposta fora do schema ({exc.error_count()} erro(s)): {exc}"
    return extraction


async def analyze_image(
    session: Session,
    *,
    image: bytes,
    filename: str,
    preset_key: str,
    models: list[str],
    fields_spec: str = "",
    context: str = "",
) -> str:
    """Run every selected model on the image and store the results. Returns the run id."""
    preset = get_preset(preset_key, fields_spec)
    jpeg = prepare_image(image, settings.max_image_side)

    run_id = uuid4().hex
    image_file = f"{run_id}.jpg"
    (settings.upload_dir / image_file).write_bytes(jpeg)

    for model in models:
        extraction = await extract(preset, model, jpeg, context)
        session.add(Analysis(
            run_id=run_id, image_name=filename, image_file=image_file, preset=preset.key,
            fields_spec=fields_spec, context=context, model=model, prompt_version=PROMPT_VERSION,
            **asdict(extraction),
        ))

    session.commit()
    return run_id


def review(session: Session, analysis: Analysis, corrected_json: str) -> None:
    """Save the human-corrected version, validated against the same schema."""
    schema = get_preset(analysis.preset, analysis.fields_spec).schema
    try:
        corrected = schema.model_validate_json(corrected_json)
    except ValidationError as exc:
        raise ValueError(f"JSON inválido para este tipo de análise: {exc}") from exc
    analysis.corrected = corrected.model_dump(mode="json")
    analysis.reviewed_at = datetime.now(timezone.utc)
    session.commit()


def empty_result(analysis: Analysis) -> dict:
    """A blank template of the expected fields, used when the model failed."""
    return get_preset(analysis.preset, analysis.fields_spec).schema().model_dump(mode="json")


def get_run(session: Session, run_id: str) -> list[Analysis]:
    return list(session.scalars(select(Analysis).where(Analysis.run_id == run_id).order_by(Analysis.id)))


def search(session: Session, *, text: str = "", preset: str = "", model: str = "", limit: int = 200) -> list[Analysis]:
    query = select(Analysis).order_by(Analysis.id.desc()).limit(limit)
    if preset:
        query = query.where(Analysis.preset == preset)
    if model:
        query = query.where(Analysis.model == model)
    if text:
        pattern = f"%{text}%"
        query = query.where(or_(
            Analysis.image_name.ilike(pattern),
            cast(Analysis.result, String).ilike(pattern),
            cast(Analysis.corrected, String).ilike(pattern),
        ))
    return list(session.scalars(query))
