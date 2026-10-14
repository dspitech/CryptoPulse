"""Etape 2 : validation du fichier bronze avant chargement."""
from __future__ import annotations

import json
from datetime import datetime

from .clients import get_blob
from .config import Settings
from .ingest import build_blob_path

REQUIRED_FIELDS = {"id", "symbol", "current_price"}


def validate_payload(payload: dict) -> int:
    if not isinstance(payload, dict) or not payload.get("records"):
        raise ValueError("Fichier bronze vide ou mal forme")
    for record in payload["records"]:
        missing = REQUIRED_FIELDS - record.keys()
        if missing:
            raise ValueError(f"Champs manquants {sorted(missing)} pour {record.get('id')}")
        price = record["current_price"]
        if not isinstance(price, (int, float)) or price <= 0:
            raise ValueError(f"Prix invalide pour {record['id']} : {price}")
    return len(payload["records"])


def run(ts: datetime, settings: Settings) -> int:
    payload = json.loads(get_blob(settings, settings.bronze_container, build_blob_path(ts)))
    return validate_payload(payload)
