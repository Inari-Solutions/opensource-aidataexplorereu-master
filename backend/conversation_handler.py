# MIT License
# Author: Inari Solutions Sp. z o.o.
# Project notice: Demonstration code prepared for a hackathon.
# Production notice: This code is not ready for production use.
# File role: Orchestrates conversation operations and maps agent function calls to local tool handlers.
import json
import logging
import os
from typing import Any, Dict, List

from data_service import get_dataset_details_by_id, highlight_datasets, search_dataset_window

ToolHandler = Any
logger = logging.getLogger(__name__)

DEFAULT_RESPONSE_MODEL = os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"]
DEBUG_FACET_KEYS = (
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

def _query_results_handler(args: Dict[str, Any]) -> Dict[str, Any]:
    return search_dataset_window(**args)


def _count_checker_handler(args: Dict[str, Any]) -> Dict[str, Any]:
    return get_dataset_details_by_id(**args)


def _query_topic_results_handler(args: Dict[str, Any]) -> Dict[str, Any]:
    return highlight_datasets(**args)


TOOL_HANDLERS: Dict[str, ToolHandler] = {
    "search_dataset_window": _query_results_handler,
    "get_dataset_details_by_id": _count_checker_handler,
    "highlight_datasets": _query_topic_results_handler,
}

TOOL_DEBUG_NAMES: Dict[str, str] = {
    "search_dataset_window": "search_dataset_window",
    "get_dataset_details_by_id": "dataset_details",
    "highlight_datasets": "highlight_datasets",
}


def _short(value: str, max_len: int = 400) -> str:
    return value if len(value) <= max_len else value[: max_len - 3] + "..."


def _safe_json_compact(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        return "<unserializable>"


def _top_level_result_fields(result: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(result, dict):
        return {"result_type": type(result).__name__}

    summary: Dict[str, Any] = {}
    for key in ("query", "query_url", "count", "topic_id", "topic_title", "error"):
        if key in result and isinstance(result.get(key), (str, int, float, bool)):
            summary[key] = result.get(key)

    rows = result.get("rows")
    if isinstance(rows, list):
        summary["rows"] = len(rows)

    payload = result.get("payload")
    if isinstance(payload, dict):
        for key in ("count",):
            payload_value = payload.get(key)
            if isinstance(payload_value, (str, int, float, bool)):
                summary.setdefault(key, payload_value)

    return summary


def _agent_reference(agent: Any) -> Dict[str, Any]:
    return {"agent": {"name": agent.name, "type": "agent_reference"}}


def create_conversation(openai_client: Any, initial_query: str) -> Any:
    """Start a new Conversation object with the first user query."""
    return openai_client.conversations.create(
        items=[{"type": "message", "role": "user", "content": initial_query}]
    )


def call_agent_response_stream(
    openai_client: Any,
    agent: Any,
    conversation_id: str,
    input_payload: Any = "",
    model: str = DEFAULT_RESPONSE_MODEL,
) -> Any:
    """Request an agent response stream scoped to the provided Conversation."""
    return openai_client.responses.stream(
        model=model,
        conversation=conversation_id,
        extra_body=_agent_reference(agent),
        input=input_payload,
    )


def append_conversation_items(
    openai_client: Any, conversation_id: str, items: List[Dict[str, Any]]
) -> None:
    """Send additional items (function outputs, follow-up user messages) to the conversation."""
    openai_client.conversations.items.create(conversation_id=conversation_id, items=items)


def collect_function_call_outputs(response: Any) -> Dict[str, List[Dict[str, Any]]]:
    """Convert tool outputs into payloads the agent expects after function calls and expose SSE events."""
    outputs: List[Dict[str, Any]] = []
    emitted_events: List[Dict[str, Any]] = []

    for item in getattr(response, "output", []):
        if item.type != "function_call":
            continue

        handler = TOOL_HANDLERS.get(item.name)
        if handler is None:
            continue

        args = json.loads(item.arguments)
        tool_debug_name = TOOL_DEBUG_NAMES.get(item.name, item.name)
        q_value = args.get("q") if isinstance(args.get("q"), str) else ""
        filters_value = args.get("filters") if isinstance(args.get("filters"), str) else ""
        resource_value = args.get("resource") if isinstance(args.get("resource"), str) else ""
        selected_facet_values = {
            key: args.get(key)
            for key in DEBUG_FACET_KEYS
            if isinstance(args.get(key), list) and len(args.get(key)) > 0
        }
        logger.warning(
            "[debug] %s.start tool=%s call_id=%s q=%s filters=%s resource=%s selected_facet_values=%s args=%s",
            tool_debug_name,
            item.name,
            item.call_id,
            _short(q_value),
            filters_value or "dataset",
            resource_value or "editorial-content",
            selected_facet_values,
            _safe_json_compact(args),
        )

        result = handler(args)

        top_level_summary = _top_level_result_fields(result)
        summary_parts = [f"{key}={value}" for key, value in top_level_summary.items()]
        logger.warning("[debug] %s.done %s", tool_debug_name, " ".join(summary_parts))
        called_url = result.get("query_url") if isinstance(result, dict) else None
        logger.warning("[debug] %s.called_url=%s", tool_debug_name, called_url or "-")

        tool_events = []
        if isinstance(result, dict):
            raw_events = result.pop("_events", [])
            if isinstance(raw_events, list):
                tool_events = [event for event in raw_events if isinstance(event, dict)]

        for event in tool_events:
            event_name = event.get("event")
            payload = event.get("payload")
            if not isinstance(event_name, str) or not isinstance(payload, dict):
                continue
            emitted_events.append({"event": event_name, "payload": payload})

        result_json = json.dumps(result, ensure_ascii=False, separators=(",", ":"))

        outputs.append(
            {
                "type": "function_call_output",
                "call_id": item.call_id,
                "output": result_json,
            }
        )
    return {"outputs": outputs, "events": emitted_events}
