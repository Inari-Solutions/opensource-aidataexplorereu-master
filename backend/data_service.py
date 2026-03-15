# MIT License
# Author: Inari Solutions Sp. z o.o.
# Project notice: Demonstration code prepared for a hackathon.
# Production notice: This code is not ready for production use.
# File role: Handles data.europa.eu API calls, payload normalization, and tool-level result shaping.
from __future__ import annotations

import json
import logging
import os
import re
from html import unescape
from typing import Any

import requests

logger = logging.getLogger(__name__)

INVALID_SCOPE_TOKENS = {
    "dataset",
    "datasets",
    "editorial-content",
    "catalogue",
    "catalogues",
    "catalog",
}

DATA_API_BASE = "https://data.europa.eu/api/hub/search/search"
DATASET_DETAILS_API_BASE = "https://data.europa.eu/api/hub/repo/datasets"
ALLOWED_FACET_KEYS = (
    "country",
    "catalog",
    "format",
    "scoring",
    "license",
    "categories",
    "publisher",
    "subject",
    "keywords",
    "is_hvd",
    "hvdCategory",
    "superCatalog",
    "mostLiked",
)
DEFAULT_FACETS = {
    "country": [],
    "catalog": [],
    "format": [],
    "scoring": [],
    "license": [],
    "categories": [],
    "publisher": [],
    "subject": [],
    "keywords": [],
    "is_hvd": [],
    "hvdCategory": [],
    "superCatalog": [],
    "mostLiked": [],
}
ALLOWED_FILTER_VALUES = {"dataset", "datasets", "catalogue", "catalogues", "editorial-content"}
ALLOWED_RESOURCE_VALUES = {"editorial-content", "dataset", "catalogue"}
QUERY_RESULTS_ALLOWED_FACETS = {"country", "format", "subject"}

UUID_PATTERN = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)


def _short(value: str, max_len: int = 400) -> str:
    return value if len(value) <= max_len else value[: max_len - 3] + "..."


def _debug_checkpoint(message: str) -> None:
    logger.warning(message)
    print(message, flush=True)


def _serialize_facets_for_api(payload_facets: dict[str, list[str]]) -> str:
    normalized_payload: dict[str, list[str]] = {}
    for key, values in payload_facets.items():
        normalized_values: list[str] = []
        for value in values or []:
            if isinstance(value, str):
                candidate = value.strip()
            elif isinstance(value, dict):
                raw = value.get("id") or value.get("title")
                candidate = raw.strip() if isinstance(raw, str) else ""
            else:
                candidate = ""

            if (
                len(candidate) >= 2
                and candidate[0] == candidate[-1]
                and candidate[0] in {"'", '"'}
            ):
                candidate = candidate[1:-1].strip()

            if key == "country":
                candidate = candidate.lower()

            if key in {"catalog", "format"} and candidate.lower() in INVALID_SCOPE_TOKENS:
                continue

            if candidate:
                normalized_values.append(candidate)

        normalized_payload[key] = normalized_values

    return json.dumps(normalized_payload, ensure_ascii=False, separators=(",", ":"))


def _extract_payload_summary(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    result_section = payload.get("result", payload)
    if not isinstance(result_section, dict):
        return {}

    summary: dict[str, Any] = {}
    for key in ["count", "facets"]:
        if key in result_section:
            summary[key] = result_section[key]
    return summary


def _normalize_search_scope(filters: str, resource: str) -> tuple[str, str]:
    normalized_filters = filters.strip() if isinstance(filters, str) else ""
    normalized_resource = resource.strip() if isinstance(resource, str) else ""

    if normalized_filters not in ALLOWED_FILTER_VALUES:
        normalized_filters = "dataset"

    if normalized_resource not in ALLOWED_RESOURCE_VALUES:
        normalized_resource = "editorial-content"

    return (
        normalized_filters or "dataset",
        normalized_resource or "editorial-content",
    )


def _extract_results(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []

    result_section = payload.get("result", payload)
    if isinstance(result_section, dict):
        results = result_section.get("results", [])
        if isinstance(results, list):
            return [item for item in results if isinstance(item, dict)]

    top_level_results = payload.get("results")
    if isinstance(top_level_results, list):
        return [item for item in top_level_results if isinstance(item, dict)]
    return []


def _pick_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        preferred_keys = ("pl", "en", "label", "title", "name", "id", "resource")
        for key in preferred_keys:
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        for candidate in value.values():
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
    return ""


def _extract_first_url(value: Any) -> str:
    if isinstance(value, str):
        candidate = value.strip()
        return candidate if candidate.startswith(("http://", "https://")) else ""
    if isinstance(value, dict):
        for key in ("resource", "url", "uri", "href", "@id", "id"):
            candidate = value.get(key)
            if isinstance(candidate, str):
                candidate = candidate.strip()
                if candidate.startswith(("http://", "https://")):
                    return candidate
        return ""
    if isinstance(value, list):
        for item in value:
            url = _extract_first_url(item)
            if url:
                return url
    return ""


def _strip_html(text: str) -> str:
    no_tags = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", unescape(no_tags)).strip()


def _extract_file_types(item: dict[str, Any]) -> list[str]:
    file_types: list[str] = []

    def _add_file_type(raw_value: Any) -> None:
        if raw_value is None:
            return
        if isinstance(raw_value, list):
            for nested in raw_value:
                _add_file_type(nested)
            return
        candidate = _pick_text(raw_value)
        if candidate and candidate not in file_types:
            file_types.append(candidate)

    for list_key in ("resources", "distributions"):
        entries = item.get(list_key, [])
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            _add_file_type(entry.get("format"))
            _add_file_type(entry.get("type"))
            _add_file_type(entry.get("mediaType"))
            _add_file_type(entry.get("mimeType"))
    return file_types


def _extract_dataset_id(item: dict[str, Any]) -> str:
    candidates: list[str] = []

    for key in ("id", "datasetId", "dataset_id", "resource", "datasetUri", "uri"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            candidates.append(value.strip())

    identifiers = item.get("identifier")
    if isinstance(identifiers, list):
        for value in identifiers:
            if isinstance(value, str) and value.strip():
                candidates.append(value.strip())
    elif isinstance(identifiers, str) and identifiers.strip():
        candidates.append(identifiers.strip())

    for candidate in candidates:
        uuid_match = UUID_PATTERN.search(candidate)
        if uuid_match:
            return uuid_match.group(0).lower()

    for candidate in candidates:
        if candidate.startswith(("http://", "https://")):
            tail = candidate.rstrip("/").split("/")[-1]
            if tail:
                return tail

    for candidate in candidates:
        if candidate:
            return candidate
    return ""


def _extract_title_en(title_value: Any) -> str:
    if isinstance(title_value, dict):
        en_value = title_value.get("en")
        if isinstance(en_value, str) and en_value.strip():
            return en_value.strip()
    return _pick_text(title_value)


def _normalize_dataset_row(item: dict[str, Any]) -> dict[str, Any]:
    title_value = item.get("title") or item.get("label") or item.get("name") or "Untitled dataset"
    title = _pick_text(title_value) or "Untitled dataset"
    title_en = _extract_title_en(title_value) or title
    dataset_id = _extract_dataset_id(item)

    description_value = item.get("description") or item.get("summary") or ""
    description = _strip_html(_pick_text(description_value))

    dataset_url_value = (
        item.get("datasetUri")
        or item.get("dataset_url")
        or item.get("url")
        or item.get("uri")
        or item.get("permalink")
    )
    dataset_url = _extract_first_url(dataset_url_value)

    if not dataset_url:
        for list_key in ("landing_page", "download_url", "access_url", "identifier"):
            dataset_url = _extract_first_url(item.get(list_key))
            if dataset_url:
                break

    if not dataset_url:
        distributions = item.get("distributions", [])
        if isinstance(distributions, list):
            for distribution in distributions:
                if not isinstance(distribution, dict):
                    continue
                dataset_url = (
                    _extract_first_url(distribution.get("access_url"))
                    or _extract_first_url(distribution.get("download_url"))
                    or _extract_first_url(distribution.get("resource"))
                    or _extract_first_url(distribution.get("url"))
                )
                if dataset_url:
                    break

    publisher_value = item.get("publisher")
    publisher = _pick_text(publisher_value)
    if not publisher:
        catalog_value = item.get("catalog")
        if isinstance(catalog_value, dict):
            publisher = _pick_text(catalog_value.get("publisher"))
            if not publisher:
                publisher = _pick_text(catalog_value.get("title") or catalog_value.get("name"))

    license_value = item.get("license")
    license_name = _pick_text(license_value)
    if not license_name:
        distributions = item.get("distributions", [])
        if isinstance(distributions, list):
            for distribution in distributions:
                if not isinstance(distribution, dict):
                    continue
                license_name = _pick_text(distribution.get("license"))
                if license_name:
                    break

    return {
        "id": dataset_id,
        "title_en": title_en,
        "title": title,
        "description": description,
        "publisher": publisher,
        "license": license_name,
        "dataset_url": dataset_url,
        "file_types": _extract_file_types(item),
    }


def _filter_payload_facets_for_query_results(payload_summary: dict[str, Any]) -> list[dict[str, Any]]:
    raw_facets = payload_summary.get("facets")
    if not isinstance(raw_facets, list):
        return []

    filtered: list[dict[str, Any]] = []
    for facet in raw_facets:
        if not isinstance(facet, dict):
            continue
        facet_id = facet.get("id")
        if isinstance(facet_id, str) and facet_id in QUERY_RESULTS_ALLOWED_FACETS:
            normalized_facet = dict(facet)
            if facet_id == "subject":
                items = normalized_facet.get("items")
                if isinstance(items, list):
                    normalized_items: list[dict[str, Any]] = []
                    for item in items:
                        if not isinstance(item, dict):
                            continue
                        normalized_item = dict(item)
                        title = normalized_item.get("title")
                        if isinstance(title, dict):
                            en_value = title.get("en")
                            if isinstance(en_value, str):
                                normalized_item["title"] = {"en": en_value}
                            else:
                                normalized_item["title"] = {}
                        normalized_items.append(normalized_item)
                    normalized_facet["items"] = normalized_items
            filtered.append(normalized_facet)
    return filtered


def _make_search_url_event_payload(*, url: str, q: str, count_hint: int, mode: str, status: str) -> dict[str, Any]:
    return {
        "url": url,
        "status": status,
        "q": q,
        "count_hint": count_hint,
        "mode": mode,
    }


def _search_api_call(
    *,
    q: str,
    filters: str,
    resource: str,
    payload_facets: dict[str, list[str]],
    limit: int,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    normalized_filters, normalized_resource = _normalize_search_scope(filters, resource)
    params = {
        "q": q,
        "filters": normalized_filters,
        "resource": normalized_resource,
        "facets": _serialize_facets_for_api(payload_facets),
        "limit": max(1, min(limit, 500)),
    }

    response = requests.get(DATA_API_BASE, params=params, timeout=20)
    response.raise_for_status()
    raw_payload = response.json()
    summary = _extract_payload_summary(raw_payload)
    query_url = requests.Request("GET", DATA_API_BASE, params=params).prepare().url
    return raw_payload, summary, query_url


def search_dataset_window(
    q: str,
    filters: str = "dataset",
    resource: str = "editorial-content",
    country: list[str] | None = None,
    catalog: list[str] | None = None,
    format: list[str] | None = None,
    scoring: list[str] | None = None,
    license: list[str] | None = None,
    categories: list[str] | None = None,
    publisher: list[str] | None = None,
    subject: list[str] | None = None,
    keywords: list[str] | None = None,
    is_hvd: list[str] | None = None,
    hvdCategory: list[str] | None = None,
    superCatalog: list[str] | None = None,
    mostLiked: list[str] | None = None,
) -> dict[str, Any]:
    payload_facets = {
        "country": country if country is not None else DEFAULT_FACETS["country"],
        "catalog": catalog if catalog is not None else DEFAULT_FACETS["catalog"],
        "format": format if format is not None else DEFAULT_FACETS["format"],
        "scoring": scoring if scoring is not None else DEFAULT_FACETS["scoring"],
        "license": license if license is not None else DEFAULT_FACETS["license"],
        "categories": categories if categories is not None else DEFAULT_FACETS["categories"],
        "publisher": publisher if publisher is not None else DEFAULT_FACETS["publisher"],
        "subject": subject if subject is not None else DEFAULT_FACETS["subject"],
        "keywords": keywords if keywords is not None else DEFAULT_FACETS["keywords"],
        "is_hvd": is_hvd if is_hvd is not None else DEFAULT_FACETS["is_hvd"],
        "hvdCategory": hvdCategory if hvdCategory is not None else DEFAULT_FACETS["hvdCategory"],
        "superCatalog": superCatalog if superCatalog is not None else DEFAULT_FACETS["superCatalog"],
        "mostLiked": mostLiked if mostLiked is not None else DEFAULT_FACETS["mostLiked"],
    }

    _debug_checkpoint(
        "[debug] search_dataset_window.start"
        f" q={_short(q)}"
        f" filters={filters}"
        f" resource={resource}"
    )

    try:
        raw_payload, summary, query_url = _search_api_call(
            q=q,
            filters=filters,
            resource=resource,
            payload_facets=payload_facets,
            limit=500,
        )
        count = summary.get("count", 0) if isinstance(summary, dict) else 0
        count = count if isinstance(count, int) else 0

        if count >= 500:
            event_payload = _make_search_url_event_payload(
                url=query_url,
                q=q,
                count_hint=count,
                mode="too_many",
                status="warning",
            )
            return {
                "query": q,
                "query_url": query_url,
                "count": count,
                "system_message": "The result requires refining the search query with the user or applying filters.",
                "_events": [{"event": "search_url", "payload": event_payload}],
            }

        filtered_facets = _filter_payload_facets_for_query_results(summary)
        rows = [_normalize_dataset_row(item) for item in _extract_results(raw_payload)]
        simplified_rows = [
            {
                "id": row.get("id", ""),
                "title_en": row.get("title_en", ""),
                "title": row.get("title", ""),
                "dataset_url": row.get("dataset_url", ""),
            }
            for row in rows[:500]
        ]

        event_payload = _make_search_url_event_payload(
            url=query_url,
            q=q,
            count_hint=count,
            mode="candidate_window",
            status="ok",
        )
        return {
            "query": q,
            "query_url": query_url,
            "count": count,
            "payload": {
                "count": count,
                "facets": filtered_facets,
            },
            "rows": simplified_rows,
            "_events": [{"event": "search_url", "payload": event_payload}],
        }
    except requests.RequestException as exc:
        _debug_checkpoint(f"[debug] search_dataset_window.error q={_short(q)} error={exc}")
        return {
            "query": q,
            "error": str(exc),
            "_events": [
                {
                    "event": "search_url",
                    "payload": {
                        "url": "",
                        "status": "error",
                        "q": q,
                        "count_hint": 0,
                        "mode": "too_many",
                        "message": str(exc),
                    },
                }
            ],
        }


def get_dataset_details_by_id(dataset_id: str) -> dict[str, Any]:
    cleaned_id = dataset_id.strip()
    if not cleaned_id:
        return {"dataset_id": dataset_id, "error": "dataset_id is required"}

    url = f"{DATASET_DETAILS_API_BASE}/{cleaned_id}"
    try:
        _debug_checkpoint(f"[debug] dataset_details.start id={cleaned_id}")
        response = requests.get(url, timeout=20)
        response.raise_for_status()
        payload = response.json()
        _debug_checkpoint(f"[debug] dataset_details.done id={cleaned_id}")
        return {
            "dataset_id": cleaned_id,
            "details_url": url,
            "payload": payload,
        }
    except requests.RequestException as exc:
        _debug_checkpoint(f"[debug] dataset_details.error id={cleaned_id} error={exc}")
        return {
            "dataset_id": cleaned_id,
            "details_url": url,
            "error": str(exc),
        }


def highlight_datasets(
    ids: list[str],
    url: str = "",
    reason: str = "",
) -> dict[str, Any]:
    normalized_ids = [dataset_id.strip() for dataset_id in ids if isinstance(dataset_id, str) and dataset_id.strip()]
    event_payload = {
        "url": url,
        "status": "ok" if normalized_ids else "warning",
        "ids": normalized_ids,
        "reason": reason,
    }

    return {
        "highlighted_ids": normalized_ids,
        "count": len(normalized_ids),
        "_events": [{"event": "ai_highlight", "payload": event_payload}],
    }


def get_facets_metadata() -> dict[str, Any]:
    return {
        "allowed_keys": list(ALLOWED_FACET_KEYS),
        "default_facets": DEFAULT_FACETS,
    }


def get_system_prompt_text() -> str:
    system_prompt_path = os.path.join(os.path.dirname(__file__), "PROMPT", "system_prompt.json")
    with open(system_prompt_path, "r", encoding="utf-8") as prompt_file:
        return prompt_file.read()