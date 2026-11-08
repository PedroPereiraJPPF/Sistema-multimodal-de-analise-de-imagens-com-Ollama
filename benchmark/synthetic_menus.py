"""Generate synthetic restaurant menus with a known ground truth.

Synthetic data is a starting point: it makes the benchmark reproducible from
day one and exercises layout variations (two layouts, fonts, price formats,
items with and without description, slight rotation and blur). Real photos,
labeled through the review screen, should be added next (see export_reviewed.py).

Usage (inside the app container, which has the fonts installed):

    python -m benchmark.synthetic_menus --count 12 --out benchmark/datasets/menus-synthetic
"""

import argparse
import json
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")
FONTS = {
    "sans": ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf"),
    "serif": ("DejaVuSerif.ttf", "DejaVuSerif-Bold.ttf"),
}
PALETTES = [  # (background, text, accent)
    ("#fbf6ec", "#2b2118", "#8a3b12"),
    ("#ffffff", "#1c1c1c", "#b0121b"),
    ("#1f2a24", "#f1ede4", "#e2b44b"),
]

RESTAURANTS = ["Cantina da Nonna", "Sabor do Sertão", "Burger Brothers", "Sushi Hana",
               "Boteco do Zé", "Tempero Mineiro", "Pizzaria Bella Napoli", "Açaí da Praia"]

# category -> [(name, description or None, (min price, max price))]
CATALOG = {
    "Entradas": [
        ("Bruschetta", "Pão italiano, tomate e manjericão", (18, 32)),
        ("Pastel de Carne", None, (8, 15)),
        ("Bolinho de Bacalhau", "Porção com 6 unidades", (28, 45)),
        ("Dadinho de Tapioca", "Com geleia de pimenta", (22, 36)),
    ],
    "Pratos Principais": [
        ("Feijoada Completa", "Acompanha arroz, couve e farofa", (45, 79)),
        ("Parmegiana de Frango", "Com arroz e fritas", (38, 62)),
        ("Moqueca de Peixe", "Serve duas pessoas", (89, 139)),
        ("Escondidinho de Carne Seca", None, (36, 54)),
        ("Risoto de Cogumelos", "Arroz arbóreo e parmesão", (48, 72)),
    ],
    "Pizzas": [
        ("Margherita", "Molho, muçarela e manjericão", (42, 65)),
        ("Calabresa", "Calabresa fatiada e cebola", (40, 60)),
        ("Quatro Queijos", None, (48, 72)),
        ("Portuguesa", "Presunto, ovo, ervilha e cebola", (46, 69)),
    ],
    "Lanches": [
        ("X-Burger", "Pão, hambúrguer 150 g e queijo", (24, 36)),
        ("X-Bacon", None, (28, 40)),
        ("Smash Duplo", "Dois smash de 90 g e cheddar", (32, 46)),
    ],
    "Sobremesas": [
        ("Pudim de Leite", None, (12, 22)),
        ("Petit Gâteau", "Com sorvete de creme", (24, 34)),
        ("Brigadeiro de Colher", None, (10, 18)),
    ],
    "Bebidas": [
        ("Refrigerante Lata", "350 ml", (6, 9)),
        ("Suco Natural", "Laranja, limão ou maracujá", (9, 15)),
        ("Água Mineral", None, (4, 7)),
        ("Cerveja Long Neck", None, (10, 16)),
    ],
}

WIDTH, MARGIN = 900, 50


def random_menu(rng: random.Random) -> dict:
    categories = rng.sample(list(CATALOG), k=rng.randint(2, 3))
    items = []
    for category in categories:
        for name, description, (low, high) in rng.sample(CATALOG[category], k=rng.randint(2, 3)):
            price = round(rng.randint(low, high) + rng.choice([0, 0.5, 0.9, 0.99]), 2)
            items.append({"name": name, "description": description, "price": price, "category": category})
    return {"restaurant_name": rng.choice(RESTAURANTS), "items": items}


def format_price(price: float, with_symbol: bool) -> str:
    text = f"{price:.2f}".replace(".", ",")
    return f"R$ {text}" if with_symbol else text


def render(menu: dict, rng: random.Random) -> Image.Image:
    regular, bold = (FONT_DIR / name for name in FONTS[rng.choice(list(FONTS))])
    title_font = ImageFont.truetype(str(bold), 46)
    section_font = ImageFont.truetype(str(bold), 30)
    item_font = ImageFont.truetype(str(regular), 26)
    small_font = ImageFont.truetype(str(regular), 20)
    background, ink, accent = rng.choice(PALETTES)
    with_symbol = rng.random() < 0.5
    dotted = rng.random() < 0.5  # "Name ........ 32,90" vs. price aligned right

    image = Image.new("RGB", (WIDTH, 2000), background)
    draw = ImageDraw.Draw(image)
    y = MARGIN
    draw.text((WIDTH / 2, y), menu["restaurant_name"], font=title_font, fill=accent, anchor="mt")
    y += 90

    current_category = None
    for item in menu["items"]:
        if item["category"] != current_category:
            current_category = item["category"]
            y += 20
            draw.text((MARGIN, y), current_category.upper(), font=section_font, fill=accent)
            y += 50
        price = format_price(item["price"], with_symbol)
        draw.text((MARGIN, y), item["name"], font=item_font, fill=ink)
        draw.text((WIDTH - MARGIN, y), price, font=item_font, fill=ink, anchor="ra")
        if dotted:
            start = MARGIN + draw.textlength(item["name"], font=item_font) + 10
            end = WIDTH - MARGIN - draw.textlength(price, font=item_font) - 10
            draw.text((start, y), "." * int((end - start) / draw.textlength(".", font=item_font)),
                      font=item_font, fill=ink)
        y += 36
        if item["description"]:
            draw.text((MARGIN + 10, y), item["description"], font=small_font, fill=ink)
            y += 32
        y += 12

    image = image.crop((0, 0, WIDTH, y + MARGIN))
    # A little rotation and blur so it looks less like a perfect screenshot.
    image = image.rotate(rng.uniform(-1.5, 1.5), expand=True, fillcolor=background)
    return image.filter(ImageFilter.GaussianBlur(rng.uniform(0, 0.8)))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--count", type=int, default=12)
    parser.add_argument("--seed", type=int, default=7, help="mesma semente = mesmo dataset")
    parser.add_argument("--out", type=Path, default=Path("benchmark/datasets/menus-synthetic"))
    args = parser.parse_args()

    rng = random.Random(args.seed)
    args.out.mkdir(parents=True, exist_ok=True)
    for number in range(1, args.count + 1):
        menu = random_menu(rng)
        stem = args.out / f"menu_{number:02d}"
        render(menu, rng).save(stem.with_suffix(".png"))
        stem.with_suffix(".json").write_text(json.dumps(menu, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{args.count} cardápios gerados em {args.out}")


if __name__ == "__main__":
    main()
