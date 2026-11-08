"""Turn human-reviewed analyses into a labeled benchmark dataset.

This closes the loop: analyze real photos in the app, correct the answers on
the review screen, then export them as ground truth. Every future prompt or
model change can be measured on those real cases.

Usage (inside the app container):

    python -m benchmark.export_reviewed --preset menu --out benchmark/datasets/menus-real
"""

import argparse
import json
import shutil
from pathlib import Path

from sqlalchemy import select

from app.config import settings
from app.db import Analysis, SessionLocal, init_db


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--preset", required=True, help="tipo de análise, ex.: menu, receipt")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    init_db()
    with SessionLocal() as session:
        reviewed = session.scalars(
            select(Analysis)
            .where(Analysis.preset == args.preset, Analysis.corrected.is_not(None))
            .order_by(Analysis.reviewed_at)
        )
        # One case per image: if several models were reviewed, the latest review wins.
        latest = {analysis.run_id: analysis for analysis in reviewed}

    args.out.mkdir(parents=True, exist_ok=True)
    for analysis in latest.values():
        stem = args.out / f"{analysis.run_id[:8]}_{Path(analysis.image_name).stem}"
        shutil.copyfile(settings.upload_dir / analysis.image_file, stem.with_suffix(".jpg"))
        stem.with_suffix(".json").write_text(
            json.dumps(analysis.corrected, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(latest)} casos exportados para {args.out}")


if __name__ == "__main__":
    main()
