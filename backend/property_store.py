"""
Pinecone persistence helpers for the active property context.
"""

from __future__ import annotations

import json
from typing import Any

from property_models import PropertyContext


ACTIVE_PROPERTY_CONTEXT_ID = "active_property__current"


def _extract_metadata(record: Any) -> dict[str, Any]:
    if record is None:
        return {}
    if isinstance(record, dict):
        return dict(record.get("metadata", {}) or {})
    metadata = getattr(record, "metadata", None)
    return dict(metadata or {})


def _extract_vectors(payload: Any) -> dict[str, Any]:
    if payload is None:
        return {}
    if isinstance(payload, dict):
        return dict(payload.get("vectors", {}) or {})
    vectors = getattr(payload, "vectors", None)
    return dict(vectors or {})


def fetch_property_context(index: Any, namespace: str) -> PropertyContext | None:
    response = index.fetch(ids=[ACTIVE_PROPERTY_CONTEXT_ID], namespace=namespace)
    vectors = _extract_vectors(response)
    record = vectors.get(ACTIVE_PROPERTY_CONTEXT_ID)
    metadata = _extract_metadata(record)
    raw_json = metadata.get("property_context_json")
    if not raw_json:
        return None
    if isinstance(raw_json, bytes):
        raw_json = raw_json.decode("utf-8", errors="replace")
    return PropertyContext.model_validate_json(raw_json)


def upsert_property_context(index: Any, namespace: str, embedding: list[float], context: PropertyContext) -> None:
    index.upsert(
        vectors=[
            {
                "id": ACTIVE_PROPERTY_CONTEXT_ID,
                "values": embedding,
                "metadata": {
                    "text": context.property_brief,
                    "source": "Active Property Context",
                    "subject": "active_property_context",
                    "primary_bbl": context.primary_bbl,
                    "selected_bbls": ",".join(context.selected_bbls),
                    "address": context.address,
                    "borough": context.borough,
                    "property_context_json": context.model_dump_json(),
                },
            }
        ],
        namespace=namespace,
    )


def delete_property_context(index: Any, namespace: str) -> None:
    index.delete(ids=[ACTIVE_PROPERTY_CONTEXT_ID], namespace=namespace)


def dump_property_context(context: PropertyContext | None) -> str:
    if context is None:
        return json.dumps({})
    return context.model_dump_json()
