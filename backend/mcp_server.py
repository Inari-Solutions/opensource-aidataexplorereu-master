# MIT License
# Author: Inari Solutions Sp. z o.o.
# Project notice: Demonstration code prepared for a hackathon.
# Production notice: This code is not ready for production use.
# File role: Exposes MCP tools and resources backed by data service functions.
from __future__ import annotations

import json

from fastmcp import FastMCP

from data_service import (
    get_dataset_details_by_id,
    get_facets_metadata,
    get_system_prompt_text,
    highlight_datasets,
    search_dataset_window,
)

mcp = FastMCP(
    name="AIDEE MCP",
    instructions="Tools for searching and inspecting datasets from data.europa.eu.",
)


@mcp.tool(name="search_dataset_window")
def mcp_search_dataset_window(
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
) -> dict:
    return search_dataset_window(
        q=q,
        filters=filters,
        resource=resource,
        country=country,
        catalog=catalog,
        format=format,
        scoring=scoring,
        license=license,
        categories=categories,
        publisher=publisher,
        subject=subject,
        keywords=keywords,
        is_hvd=is_hvd,
        hvdCategory=hvdCategory,
        superCatalog=superCatalog,
        mostLiked=mostLiked,
    )


@mcp.tool(name="get_dataset_details_by_id")
def mcp_get_dataset_details_by_id(dataset_id: str) -> dict:
    return get_dataset_details_by_id(dataset_id=dataset_id)


@mcp.tool(name="highlight_datasets")
def mcp_highlight_datasets(ids: list[str], url: str = "", reason: str = "") -> dict:
    return highlight_datasets(ids=ids, url=url, reason=reason)


@mcp.resource("resource://system-prompt", name="system_prompt", mime_type="application/json")
def mcp_system_prompt() -> str:
    return get_system_prompt_text()


@mcp.resource("resource://facets-metadata", name="facets_metadata", mime_type="application/json")
def mcp_facets_metadata() -> str:
    return json.dumps(get_facets_metadata(), ensure_ascii=False)
