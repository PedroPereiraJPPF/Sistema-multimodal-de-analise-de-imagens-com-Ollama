import json


def _analyze(client, png_bytes, **form):
    return client.post("/api/analyze", files={"image": ("mesa.png", png_bytes, "image/png")}, data=form)


def test_analyze_stores_validated_result(client, png_bytes, fake_llm):
    response = _analyze(client, png_bytes, preset="general", models=["model-a"])

    assert response.status_code == 200
    analysis = response.json()["analyses"][0]
    assert analysis["model"] == "model-a"
    assert analysis["result"]["summary"] == "Uma mesa com frutas"
    assert analysis["error"] is None
    assert fake_llm.calls[0]["schema"]["title"] == "GeneralDescription"


def test_compare_runs_every_selected_model(client, png_bytes, fake_llm):
    response = _analyze(client, png_bytes, preset="general", models=["model-a", "model-b"])

    assert [a["model"] for a in response.json()["analyses"]] == ["model-a", "model-b"]


def test_answer_outside_schema_is_flagged(client, png_bytes, fake_llm):
    fake_llm.content = '{"people_count": "muitas"}'

    analysis = _analyze(client, png_bytes, preset="general", models=["m"]).json()["analyses"][0]

    assert analysis["result"] is None
    assert "fora do schema" in analysis["error"]


def test_null_written_as_text_becomes_a_real_null(client, png_bytes, fake_llm):
    fake_llm.content = json.dumps({
        "restaurant_name": "null",
        "items": [{"name": "Água", "description": "Null", "price": 6, "category": " none "}],
    })

    analysis = _analyze(client, png_bytes, preset="menu", models=["m"]).json()["analyses"][0]

    assert analysis["result"]["restaurant_name"] is None
    assert analysis["result"]["items"][0] == {"name": "Água", "description": None, "price": 6.0, "category": None}


def test_invalid_image_returns_422(client, fake_llm):
    response = client.post("/api/analyze", files={"image": ("x.png", b"oops", "image/png")})
    assert response.status_code == 422


def test_review_updates_accuracy_metrics(client, png_bytes, fake_llm):
    analysis = _analyze(client, png_bytes, preset="general", models=["m"]).json()["analyses"][0]
    corrected = {**analysis["result"], "people_count": 2}

    response = client.post(f"/analyses/{analysis['id']}/review", data={"corrected": json.dumps(corrected)})

    assert response.status_code == 200  # followed the redirect to the run page
    assert "precisão 80%" in response.text  # 4 of 5 fields were right
    assert "Avaliação dos modelos" in client.get("/metrics").text


def test_history_search_finds_text_in_results(client, png_bytes, fake_llm):
    _analyze(client, png_bytes, preset="general", models=["m"])

    assert client.get("/api/analyses", params={"q": "frutas"}).json()
    assert client.get("/api/analyses", params={"q": "inexistente-xyz"}).json() == []


def test_form_error_is_shown_on_the_page(client, png_bytes, fake_llm):
    response = client.post(
        "/analyze",
        files={"image": ("x.png", png_bytes, "image/png")},
        data={"preset": "custom", "fields": "uma frase muito longa que claramente é uma pergunta e não um campo"},
    )

    assert response.status_code == 200  # followed the redirect back to the form
    assert "Pergunta livre" in response.text
    assert fake_llm.calls == []  # the model was never called
