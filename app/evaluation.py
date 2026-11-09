"""Quality metrics: compare a model's answer with the expected one.

The expected answer is either a human correction (web app) or a labeled
ground truth (benchmark/). Both use the same scoring, so numbers are comparable.

Scoring rules:
- Scalar fields: 1 if equal after normalization, else 0.
- Lists (e.g. menu items): items are paired by their identifying value (the first
  field, e.g. the dish name) with fuzzy matching, so order and tiny OCR slips do
  not make a list "all wrong". The list itself gets the F1 of that pairing
  (did the model find the right items, without extras?), and each sub-field
  gets its accuracy over the paired items ("items.price": were prices right?).
- Overall accuracy is the mean of all those scores.
"""

from collections import defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from statistics import mean
from typing import Any

from app.db import Analysis

# Two item names this similar are considered the same item ("Pizza Margherita"
# vs "Pizza Marguerita"). Whether the name was transcribed exactly is scored
# separately, in the "<list>.<name field>" metric.
ITEM_MATCH_THRESHOLD = 0.8


def _normalize(value: Any) -> Any:
    """Make cosmetic differences irrelevant: case, extra spaces, 10 vs 10.0."""
    if isinstance(value, str):
        return " ".join(value.split()).casefold() or None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    if isinstance(value, dict):
        return {key: _normalize(item) for key, item in value.items()}
    return value


def _same(a: Any, b: Any) -> bool:
    return _normalize(a) == _normalize(b)


def _identity(item: Any) -> str:
    """The value that identifies a list item: its first filled field, or the item itself.

    Usually the first field is the name. When it is null (a dish printed with only
    a description), the next filled field identifies the item instead.
    """
    if isinstance(item, dict):
        item = next((value for value in item.values() if value not in (None, "", [])), None)
    return str(_normalize(item) or "")


def _similarity(a: Any, b: Any) -> float:
    return SequenceMatcher(None, _identity(a), _identity(b)).ratio()


def match_items(predicted: list, expected: list) -> list[tuple[Any, Any]]:
    """Pair each expected item with its most similar, still unused, predicted item."""
    pairs, unused = [], list(predicted)
    for truth in expected:
        best = max(unused, key=lambda guess: _similarity(guess, truth), default=None)
        if best is not None and _similarity(best, truth) >= ITEM_MATCH_THRESHOLD:
            pairs.append((best, truth))
            unused.remove(best)
    return pairs


def _f1(matched: int, predicted: int, expected: int) -> float:
    if predicted == expected == 0:
        return 1.0
    precision = matched / predicted if predicted else 0.0
    recall = matched / expected if expected else 0.0
    return 2 * precision * recall / (precision + recall) if matched else 0.0


def score(predicted: dict | None, expected: dict) -> dict[str, float]:
    """Per-field scores in [0, 1] for one answer. See the module docstring."""
    if predicted is None:  # invalid answer: everything is wrong
        return {name: 0.0 for name in score(expected, expected)}

    scores: dict[str, float] = {}
    for field, truth in expected.items():
        guess = predicted.get(field)
        if not isinstance(truth, list) and not isinstance(guess, list):
            scores[field] = float(_same(guess, truth))
            continue

        guess, truth = guess or [], truth or []
        pairs = match_items(guess, truth)
        scores[field] = _f1(len(pairs), len(guess), len(truth))
        sub_fields = {key for item in truth if isinstance(item, dict) for key in item}
        for sub in sorted(sub_fields):
            if pairs:
                scores[f"{field}.{sub}"] = mean(float(_same(g.get(sub), t.get(sub))) for g, t in pairs)
    return scores


def overall(scores: dict[str, float]) -> float:
    return mean(scores.values()) if scores else 1.0


def field_accuracy(predicted: dict | None, corrected: dict) -> float:
    """Overall accuracy of the model's answer, according to the reviewer."""
    return overall(score(predicted, corrected))


def changed_fields(predicted: dict | None, corrected: dict) -> list[str]:
    """Top-level fields the reviewer had to change."""
    predicted = predicted or {}
    keys = sorted(predicted.keys() | corrected.keys())
    return [key for key in keys if not _same(predicted.get(key), corrected.get(key))]


@dataclass(frozen=True)
class ModelReport:
    model: str
    preset: str
    prompt_version: str
    runs: int
    valid_rate: float
    avg_duration_ms: float
    avg_load_ms: float
    reviewed: int
    accuracy: float | None


def summarize(analyses: list[Analysis]) -> list[ModelReport]:
    groups: dict[tuple[str, str, str], list[Analysis]] = defaultdict(list)
    for analysis in analyses:
        groups[(analysis.model, analysis.preset, analysis.prompt_version)].append(analysis)

    reports = []
    for (model, preset, prompt_version), items in sorted(groups.items()):
        reviewed = [a for a in items if a.corrected is not None]
        reports.append(ModelReport(
            model=model,
            preset=preset,
            prompt_version=prompt_version,
            runs=len(items),
            valid_rate=sum(a.is_valid for a in items) / len(items),
            avg_duration_ms=mean(a.duration_ms for a in items),
            avg_load_ms=mean(a.load_ms for a in items),
            reviewed=len(reviewed),
            accuracy=mean(field_accuracy(a.result, a.corrected) for a in reviewed) if reviewed else None,
        ))
    return reports
