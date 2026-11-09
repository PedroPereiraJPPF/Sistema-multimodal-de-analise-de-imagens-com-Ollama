"""Analysis presets: what to extract from an image and the JSON schema of the answer.

Each preset pairs a focused instruction with a Pydantic model. The model is the
single source of truth: it becomes the JSON Schema sent to Ollama (constraining
the output), the field list in the prompt, and the validator of the answer.

Every field is optional on purpose: telling a small model "null is allowed"
is the most effective way to stop it from inventing values it cannot see.
"""

import re
from dataclasses import dataclass

from pydantic import BaseModel, Field, create_model


# --- Schemas -----------------------------------------------------------------

class GeneralDescription(BaseModel):
    summary: str | None = Field(None, description="One or two sentences describing the image")
    setting: str | None = Field(None, description="Where the scene takes place (e.g. kitchen, street, office)")
    main_objects: list[str] = Field(default_factory=list, description="Most relevant objects visible")
    people_count: int | None = Field(None, description="Number of people visible; 0 if none")
    visible_text: str | None = Field(None, description="Any readable text, transcribed exactly")


class ReceiptItem(BaseModel):
    description: str | None = Field(None, description="Item name as printed")
    quantity: float | None = Field(None, description="Quantity purchased")
    total_price: float | None = Field(None, description="Total price of the line")


class Receipt(BaseModel):
    store_name: str | None = Field(None, description="Name of the store or company")
    cnpj: str | None = Field(None, description="CNPJ/tax id exactly as printed")
    date: str | None = Field(None, description="Purchase date as printed (DD/MM/YYYY)")
    items: list[ReceiptItem] = Field(default_factory=list, description="Purchased items")
    total_amount: float | None = Field(None, description="Final amount paid")
    payment_method: str | None = Field(None, description="e.g. credit card, debit card, pix, cash")


class Bill(BaseModel):
    provider: str | None = Field(None, description="Company that issued the bill (energy, water, internet...)")
    customer_name: str | None = Field(None, description="Name of the customer")
    reference_month: str | None = Field(None, description="Billing month as printed (MM/YYYY)")
    due_date: str | None = Field(None, description="Due date as printed (DD/MM/YYYY)")
    amount: float | None = Field(None, description="Total amount due")
    consumption: str | None = Field(None, description="Consumption with unit, e.g. '215 kWh' or '12 m3'")


class ProductLabel(BaseModel):
    product_name: str | None = Field(None, description="Product name")
    brand: str | None = Field(None, description="Brand")
    net_content: str | None = Field(None, description="Net content with unit, e.g. '500 g'")
    expiration_date: str | None = Field(None, description="Expiration date as printed (DD/MM/YYYY)")
    batch: str | None = Field(None, description="Batch/lot code")
    allergens: list[str] = Field(default_factory=list, description="Allergens declared on the label")


class InventoryItem(BaseModel):
    name: str | None = Field(None, description="Object name")
    quantity: int | None = Field(None, description="How many of this object are visible")
    condition: str | None = Field(None, description="Apparent condition: new, good, worn or damaged")


class Inventory(BaseModel):
    location: str | None = Field(None, description="Room or place shown")
    items: list[InventoryItem] = Field(default_factory=list, description="Objects visible")


class MenuItem(BaseModel):
    name: str | None = Field(
        None,
        description="Short dish or drink title as printed, e.g. Feijoada Completa. Only the title: "
                    "never include the description. If the item has no title, use null; "
                    "never use the description as the name")
    description: str | None = Field(
        None,
        description="Text printed under or after the title (ingredients, side dishes), "
                    "without surrounding parentheses; null if none")
    price: float | None = Field(
        None,
        description="Price printed next to this item, as a number (R$ 32,90 becomes 32.9). "
                    "null if this item has no price of its own; never copy a nearby item's price")
    category: str | None = Field(
        None,
        description="Section heading the item is listed under, e.g. Pizzas. "
                    "null if the menu has no section headings; never repeat the item name")


class Menu(BaseModel):
    restaurant_name: str | None = Field(
        None,
        description="Restaurant name, usually in the logo. Words like Cardápio or Menu are not "
                    "a restaurant name; null if no name is shown")
    items: list[MenuItem] = Field(default_factory=list, description="Every dish and drink on the menu, in order")


# --- Presets -----------------------------------------------------------------

@dataclass(frozen=True)
class Preset:
    key: str
    label: str
    task: str
    schema: type[BaseModel]


PRESETS: dict[str, Preset] = {
    preset.key: preset
    for preset in [
        Preset("general", "Descrição geral",
               "Describe the image: the scene, the main objects, people and any readable text.",
               GeneralDescription),
        Preset("receipt", "Nota fiscal / cupom",
               "Extract the purchase data from this receipt or invoice.",
               Receipt),
        Preset("menu", "Cardápio",
               "Transcribe this restaurant menu into a catalog: every item with its price and section.",
               Menu),
        Preset("bill", "Conta (luz, água, internet...)",
               "Extract the billing data from this utility bill.",
               Bill),
        Preset("product_label", "Rótulo de produto",
               "Extract the information printed on this product label or package.",
               ProductLabel),
        Preset("inventory", "Inventário de objetos",
               "List the objects visible in this place, counting repeated objects.",
               Inventory),
    ]
}

# Presets built at request time from text the user types (stored in `fields_spec`).
QUESTION_KEY = "question"
CUSTOM_KEY = "custom"
DYNAMIC_LABELS = {QUESTION_KEY: "Pergunta livre", CUSTOM_KEY: "Campos personalizados"}

MAX_FIELD_NAME = 40


class FreeAnswer(BaseModel):
    answer: str | None = Field(None, description="Direct answer to the question, in Brazilian Portuguese")
    items: list[str] = Field(
        default_factory=list,
        description="When the question asks for things to be listed or named, one entry per thing; otherwise empty",
    )


def question_preset(question: str) -> Preset:
    question = question.strip()
    if not question:
        raise ValueError("Escreva a pergunta sobre a imagem.")
    # The question is user input: keep it inside tags so it reads as data, not as rules.
    task = f"Answer the user's question about the image.\n<question>\n{question}\n</question>"
    return Preset(QUESTION_KEY, DYNAMIC_LABELS[QUESTION_KEY], task, FreeAnswer)


def parse_custom_fields(spec: str) -> dict[str, str]:
    """Parse lines like 'field name: description' into {field_name: description}."""
    fields: dict[str, str] = {}
    for line in spec.splitlines():
        name, _, description = line.partition(":")
        key = re.sub(r"\W+", "_", name.strip().lower()).strip("_")
        if len(key) > MAX_FIELD_NAME:
            raise ValueError(
                f"O nome do campo \"{name.strip()[:30]}…\" é longo demais. Use nomes curtos "
                "(ex.: placa: placa do veículo) ou escolha \"Pergunta livre\" para perguntar algo sobre a imagem."
            )
        if key:
            fields[key] = description.strip() or name.strip()
    return fields


def custom_preset(spec: str) -> Preset:
    fields = parse_custom_fields(spec)
    if not fields:
        raise ValueError("Informe ao menos um campo para a análise personalizada.")
    schema = create_model(
        "CustomExtraction",
        **{name: (str | None, Field(None, description=desc)) for name, desc in fields.items()},
    )
    return Preset(CUSTOM_KEY, DYNAMIC_LABELS[CUSTOM_KEY], "Extract the requested fields from the image.", schema)


def get_preset(key: str, spec: str = "") -> Preset:
    if key == QUESTION_KEY:
        return question_preset(spec)
    if key == CUSTOM_KEY:
        return custom_preset(spec)
    try:
        return PRESETS[key]
    except KeyError:
        raise ValueError(f"Tipo de análise desconhecido: {key}") from None


def preset_label(key: str) -> str:
    return PRESETS[key].label if key in PRESETS else DYNAMIC_LABELS.get(key, key)
