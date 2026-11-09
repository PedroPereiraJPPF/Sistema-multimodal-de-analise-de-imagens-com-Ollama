import pytest

from app.evaluation import field_accuracy, match_items, overall, score

EXPECTED = {
    "restaurant_name": "Cantina da Nonna",
    "items": [
        {"name": "Pizza Margherita", "price": 42.9, "category": "Pizzas"},
        {"name": "Calabresa", "price": 40.0, "category": "Pizzas"},
        {"name": "Pudim de Leite", "price": 12.5, "category": "Sobremesas"},
    ],
}


def test_perfect_answer_scores_100_percent():
    assert overall(score(EXPECTED, EXPECTED)) == 1.0


def test_items_are_matched_regardless_of_order_and_small_typos():
    predicted = [{"name": "Pudim de leite"}, {"name": "Pizza Marguerita"}, {"name": "Calabresa"}]
    pairs = match_items(predicted, EXPECTED["items"])
    assert [truth["name"] for _, truth in pairs] == ["Pizza Margherita", "Calabresa", "Pudim de Leite"]


def test_items_without_name_are_matched_by_their_next_filled_field():
    expected = [
        {"name": None, "description": "Ravioli recheado com carne", "price": 32.9},
        {"name": None, "description": "Filé de frango grelhado", "price": 35.9},
    ]
    predicted = [
        {"name": None, "description": "Filé de frango grelhado", "price": 35.9},
        {"name": None, "description": "Ravioli recheado com carne", "price": 32.9},
    ]
    pairs = match_items(predicted, expected)
    assert all(guess == truth for guess, truth in pairs) and len(pairs) == 2


def test_list_scores_detection_and_each_sub_field_separately():
    predicted = {
        "restaurant_name": "Cantina da Nonna",
        "items": [
            {"name": "Pizza Margherita", "price": 42.9, "category": "Pizzas"},
            {"name": "Calabresa", "price": 4.0, "category": "Pizzas"},     # wrong price
            {"name": "Coca-Cola", "price": 6.0, "category": "Bebidas"},   # invented item
        ],
    }
    scores = score(predicted, EXPECTED)

    assert scores["restaurant_name"] == 1.0
    assert scores["items"] == pytest.approx(2 / 3)       # 2 of 3 found, 1 extra: F1 = 2/3
    assert scores["items.price"] == pytest.approx(1 / 2)  # over the 2 matched items
    assert scores["items.category"] == 1.0


def test_invalid_answer_scores_zero_everywhere():
    scores = score(None, EXPECTED)
    assert scores and set(scores.values()) == {0.0}


def test_empty_lists_on_both_sides_are_correct():
    assert field_accuracy({"allergens": []}, {"allergens": []}) == 1.0
