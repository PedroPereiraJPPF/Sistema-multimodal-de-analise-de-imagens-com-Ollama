import io

import pytest
from PIL import Image

from app.evaluation import changed_fields, field_accuracy
from app.images import prepare_image
from app.presets import PRESETS, custom_preset, get_preset, parse_custom_fields
from app.prompts import build_user_prompt


def test_prepare_image_downscales_to_jpeg(png_bytes):
    result = Image.open(io.BytesIO(prepare_image(png_bytes, max_side=1024)))
    assert result.format == "JPEG"
    assert max(result.size) == 1024


def test_prepare_image_rejects_non_images():
    with pytest.raises(ValueError):
        prepare_image(b"not an image", max_side=1024)


def test_parse_custom_fields_normalizes_names():
    assert parse_custom_fields("Placa do carro: placa\n\ncor") == {"placa_do_carro": "placa", "cor": "cor"}


def test_custom_preset_requires_fields():
    with pytest.raises(ValueError):
        custom_preset("   ")


def test_prompt_lists_fields_and_isolates_context():
    prompt = build_user_prompt(PRESETS["receipt"], context="compra no mercado")
    assert "- total_amount:" in prompt
    assert "<context>\ncompra no mercado\n</context>" in prompt


def test_field_accuracy_ignores_cosmetic_differences():
    predicted = {"store": "Mercado  Bom", "total": 10, "date": "2026-01-01", "city": None}
    corrected = {"store": "mercado bom", "total": 10.0, "date": "2026-01-02", "city": "Recife"}
    assert changed_fields(predicted, corrected) == ["city", "date"]
    assert field_accuracy(predicted, corrected) == 0.5


def test_question_preset_isolates_the_question():
    preset = get_preset("question", "Quais blocos aparecem?")
    assert "<question>\nQuais blocos aparecem?\n</question>" in build_user_prompt(preset)


def test_sentence_as_field_name_points_to_question_preset():
    with pytest.raises(ValueError, match="Pergunta livre"):
        parse_custom_fields("quero que você me diga quais os blocos que estão lá e o nome de cada um")
