"""Database setup and the single table of the application."""

import json
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import JSON, String, Text, create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


class Analysis(Base):
    """One model's answer for one image. Analyses of the same upload share a run_id."""

    __tablename__ = "analyses"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))

    image_name: Mapped[str] = mapped_column(String(255))
    image_file: Mapped[str] = mapped_column(String(255))
    preset: Mapped[str] = mapped_column(String(50), index=True)
    fields_spec: Mapped[str] = mapped_column(Text, default="")
    context: Mapped[str] = mapped_column(Text, default="")
    model: Mapped[str] = mapped_column(String(100), index=True)
    prompt_version: Mapped[str] = mapped_column(String(20), default="")

    result: Mapped[dict | None] = mapped_column(JSON)
    raw_response: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str | None] = mapped_column(Text)

    duration_ms: Mapped[int] = mapped_column(default=0)
    load_ms: Mapped[int] = mapped_column(default=0)
    output_tokens: Mapped[int] = mapped_column(default=0)

    corrected: Mapped[dict | None] = mapped_column(JSON)
    reviewed_at: Mapped[datetime | None]

    @property
    def is_valid(self) -> bool:
        return self.result is not None


_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(
    settings.database_url,
    connect_args=_connect_args,
    # Keep accents readable in stored JSON so text search finds "São Paulo".
    json_serializer=lambda obj: json.dumps(obj, ensure_ascii=False),
)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def init_db() -> None:
    if settings.database_url.startswith("sqlite:///"):
        db_file = Path(settings.database_url.removeprefix("sqlite:///"))
        db_file.parent.mkdir(parents=True, exist_ok=True)
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)
    _add_missing_columns()


def _add_missing_columns() -> None:
    """Minimal migration for databases created before a column existed.

    create_all() only creates missing tables. With a single table and additive
    changes, this is enough; a real migration tool (Alembic) would be the next step.
    """
    existing = {column["name"] for column in inspect(engine).get_columns(Analysis.__tablename__)}
    if "prompt_version" not in existing:
        with engine.begin() as connection:
            connection.execute(text(
                "ALTER TABLE analyses ADD COLUMN prompt_version VARCHAR(20) NOT NULL DEFAULT ''"
            ))


def get_session() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session
