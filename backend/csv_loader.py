import hashlib
from io import BytesIO
from typing import Any

import pandas as pd

from .db import insert_alert


REQUIRED_COLUMNS = {"title"}
EXPECTED_COLUMNS = {
    "id",
    "title",
    "description",
    "source_type",
    "category",
    "country",
    "institution",
    "source_url",
    "presentation_date",
    "full_text",
}


def _clean(value: Any) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def _stable_id(row: dict[str, Any]) -> str:
    raw = "|".join(
        [
            _clean(row.get("source_url")),
            _clean(row.get("title")),
            _clean(row.get("presentation_date")),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _normalize_row(row: dict[str, Any]) -> dict[str, str]:
    normalized = {key: _clean(row.get(key)) for key in EXPECTED_COLUMNS}
    normalized["id"] = normalized["id"] or _stable_id(row)
    normalized["full_text"] = normalized["full_text"] or normalized["description"]
    return normalized


def load_alerts_from_csv_bytes(content: bytes) -> dict[str, Any]:
    last_error: Exception | None = None
    for encoding in ["utf-8-sig", "latin-1"]:
        try:
            chunks = pd.read_csv(BytesIO(content), dtype=str, chunksize=1000, encoding=encoding)
            inserted = 0
            skipped = 0
            total = 0
            columns_seen: set[str] | None = None

            for chunk in chunks:
                chunk.columns = [str(column).strip() for column in chunk.columns]
                columns = set(chunk.columns)
                columns_seen = columns
                missing = REQUIRED_COLUMNS - columns
                has_unique_key = "id" in columns or "source_url" in columns
                if missing or not has_unique_key:
                    missing_list = sorted(missing)
                    if not has_unique_key:
                        missing_list.append("id o source_url")
                    raise ValueError(f"Faltan columnas mínimas: {', '.join(missing_list)}")

                for row in chunk.to_dict(orient="records"):
                    total += 1
                    try:
                        if insert_alert(_normalize_row(row)):
                            inserted += 1
                        else:
                            skipped += 1
                    except Exception:
                        skipped += 1

            return {
                "total_rows": total,
                "inserted": inserted,
                "skipped_duplicates_or_invalid": skipped,
                "columns": sorted(columns_seen or []),
            }
        except UnicodeDecodeError as exc:
            last_error = exc
            continue

    raise ValueError(f"No se pudo leer el CSV: {last_error}")
