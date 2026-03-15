# MIT License
# Author: Inari Solutions Sp. z o.o.
# Project notice: Demonstration code prepared for a hackathon.
# Production notice: This code is not ready for production use.
# File role: Creates and resolves Azure AI Agent versions and defines tool schemas used by the hosted agent.
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import FunctionTool, PromptAgentDefinition
from azure.identity import DefaultAzureCredential

AZURE_AI_PROJECT_ENDPOINT = os.environ["AZURE_AI_PROJECT_ENDPOINT"]
AZURE_AI_AGENT_NAME = os.environ["AZURE_AI_AGENT_NAME"]
AZURE_AI_MODEL_DEPLOYMENT_NAME = os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"]

DEFAULT_AGENT_NAME = AZURE_AI_AGENT_NAME
SYSTEM_PROMPT_PATH = Path(__file__).with_name("PROMPT") / "system_prompt.json"
SYSTEM_PROMPT_TEXT = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")

project_client = AIProjectClient(
    endpoint=AZURE_AI_PROJECT_ENDPOINT,
    credential=DefaultAzureCredential(),
)
openai_client = project_client.get_openai_client()


def _parse_version_str(version: str) -> tuple[int, ...]:
    parts = tuple(int(part) for part in re.split(r"[^0-9]", version) if part)
    return parts if parts else (0,)


search_dataset_window_tool = FunctionTool(
    name="search_dataset_window",
    description=(
        "Primary smart search tool. Always calls data.europa.eu search API with limit=500. "
        "If count>=500 returns count plus refinement system message; if count<500 returns count, selected facets and rows with id/title_en."
    ),
    parameters={
        "type": "object",
        "properties": {
            "q": {
                "type": "string",
                "description": "Searchwords boolean query string for data.europa.eu",
            },
            "filters": {
                "type": "string",
                "description": "Optional search scope parameter (defaults to dataset); do not reuse this value as a facet item",
            },
            "resource": {
                "type": "string",
                "description": "Optional resource type (defaults to editorial-content); do not reuse this value as a facet item",
            },
            "country": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional facet override for country",
            },
            "catalog": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional facet override for catalog ids only (example: dane-gov-pl); never use scope tokens like dataset/editorial-content",
            },
            "format": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional facet override for format ids only (example: CSV, XLS, XLSX); never use scope tokens like dataset/editorial-content",
            },
            "scoring": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional facet override for scoring",
            },
            "license": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional facet override for license",
            },
            "categories": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional facet override for categories",
            },
            "publisher": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional facet override for publisher",
            },
            "subject": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional facet override for subject",
            },
            "keywords": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional API facet filter override for keywords (not q searchwords)",
            },
            "is_hvd": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional facet override for is_hvd",
            },
            "hvdCategory": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional facet override for hvdCategory",
            },
            "superCatalog": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional facet override for superCatalog",
            },
            "mostLiked": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional facet override for mostLiked",
            },
        },
        "required": [
            "q",
            "filters",
            "resource",
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
        ],
        "additionalProperties": False,
    },
    strict=True,
)


get_dataset_details_by_id_tool = FunctionTool(
    name="get_dataset_details_by_id",
    description="Returns full dataset metadata payload from data.europa.eu repo endpoint for a provided dataset id.",
    parameters={
        "type": "object",
        "properties": {
            "dataset_id": {
                "type": "string",
                "description": "Dataset identifier used in /api/hub/repo/datasets/{id}.",
            },
        },
        "required": ["dataset_id"],
        "additionalProperties": False,
    },
    strict=True,
)


highlight_datasets_tool = FunctionTool(
    name="highlight_datasets",
    description=(
        "Highlights chosen datasets on frontend list by emitting ai_highlight event. "
        "Pass dataset ids selected by the agent."
    ),
    parameters={
        "type": "object",
        "properties": {
            "ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Dataset IDs to highlight in the current frontend table.",
            },
            "url": {
                "type": "string",
                "description": "Optional current search URL for debug context.",
            },
            "reason": {
                "type": "string",
                "description": "Optional short explanation why those datasets are highlighted.",
            },
        },
        "required": ["ids", "url", "reason"],
        "additionalProperties": False,
    },
    strict=True,
)


def create_agent_version():
    agent = project_client.agents.create_version(
        agent_name=DEFAULT_AGENT_NAME,
        definition=PromptAgentDefinition(
            model=AZURE_AI_MODEL_DEPLOYMENT_NAME,
            instructions=SYSTEM_PROMPT_TEXT,
            tools=[
                search_dataset_window_tool,
                get_dataset_details_by_id_tool,
                highlight_datasets_tool,
            ],
        ),
    )
    print(f"Created agent version: {agent.name} v{agent.version}")
    return agent


def get_agent_version(agent_name: str, agent_version: str):
    agent = project_client.agents.get_version(
        agent_name=agent_name,
        agent_version=agent_version,
    )
    print(f"Using agent version: {agent.name} v{agent.version}")
    return agent


def ensure_agent_version(agent_name: str, agent_version: str | None):
    if agent_version:
        return get_agent_version(agent_name, agent_version)

    versions = list(project_client.agents.list_versions(agent_name=agent_name))
    if not versions:
        raise SystemExit(f"No versions found for agent {agent_name}; create one before running the conversation")

    def _version_sort_key(version_obj: Any):
        updated = getattr(version_obj, "updated_at", None)
        updated_flag = updated is not None
        return (
            updated_flag,
            str(updated) if updated is not None else "",
            _parse_version_str(version_obj.version),
        )

    latest_version = max(versions, key=_version_sort_key)
    return project_client.agents.get_version(
        agent_name=agent_name,
        agent_version=latest_version.version,
    )


if __name__ == "__main__":
    create_agent_version()
