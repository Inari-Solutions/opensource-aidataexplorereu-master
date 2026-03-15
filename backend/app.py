# MIT License
# Author: Inari Solutions Sp. z o.o.
# Project notice: Demonstration code prepared for a hackathon.
# Production notice: This code is not ready for production use.
# File role: FastAPI entrypoint exposing conversation endpoints and SSE stream for the frontend.

# Requirements:
# - Azure variables are provisioned on host before app startup.
# - Required env vars: AZURE_AI_PROJECT_ENDPOINT, AZURE_AI_AGENT_NAME, AZURE_AI_MODEL_DEPLOYMENT_NAME, AZURE_AI_AGENT_VERSION.

from __future__ import annotations

import json
import logging
import os
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agent_creation import DEFAULT_AGENT_NAME, ensure_agent_version, openai_client
from conversation_handler import (
    append_conversation_items,
    call_agent_response_stream,
    collect_function_call_outputs,
    create_conversation,
)
from mcp_server import mcp

app = FastAPI()
logger = logging.getLogger(__name__)

logging.basicConfig(
    level=os.environ.get("AIDEE_LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

for azure_logger_name in (
    "azure",
    "azure.core.pipeline.policies.http_logging_policy",
    "azure.identity",
):
    logging.getLogger(azure_logger_name).setLevel(logging.WARNING)

cors_allow_origins = os.environ.get("AIDEE_CORS_ALLOW_ORIGINS", "*")
allow_origins = [origin.strip() for origin in cors_allow_origins.split(",") if origin.strip()]
if not allow_origins:
    allow_origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/mcp", mcp.http_app(transport="streamable-http"))


class ConversationRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None
    agent_name: Optional[str] = None
    agent_version: Optional[str] = None


class StreamRequest(BaseModel):
    conversation_id: str
    agent_name: Optional[str] = None
    agent_version: Optional[str] = None


class ConversationAckResponse(BaseModel):
    conversation_id: str
    agent_name: str
    agent_version: str
    requested_version: str


def _append_user_message(conversation_id: str, message: str) -> None:
    append_conversation_items(
        openai_client=openai_client,
        conversation_id=conversation_id,
        items=[{"type": "message", "role": "user", "content": message}],
    )


@app.get("/")
def root_redirect() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/request", response_model=ConversationAckResponse)
@app.post("/request", response_model=ConversationAckResponse)
def create_or_continue_conversation(request: ConversationRequest) -> ConversationAckResponse:
    agent_name = request.agent_name or DEFAULT_AGENT_NAME
    requested_version_label = (
        request.agent_version
        or os.environ["AZURE_AI_AGENT_VERSION"]
        or "latest available"
    )
    agent = ensure_agent_version(agent_name, request.agent_version)

    conversation_id = request.conversation_id
    if conversation_id:
        _append_user_message(conversation_id, request.message)
    else:
        conversation = create_conversation(
            openai_client=openai_client,
            initial_query=request.message,
        )
        conversation_id = conversation.id

    return ConversationAckResponse(
        conversation_id=conversation_id,
        agent_name=agent.name,
        agent_version=agent.version,
        requested_version=requested_version_label,
    )


@app.post("/api/stream")
@app.post("/stream")
def stream_conversation_run(request: StreamRequest) -> StreamingResponse:
    agent_name = request.agent_name or DEFAULT_AGENT_NAME
    requested_version_label = (
        request.agent_version
        or os.environ["AZURE_AI_AGENT_VERSION"]
        or "latest available"
    )
    agent = ensure_agent_version(agent_name, request.agent_version)

    def event_stream():
        raw_accumulated_text = ""
        visible_emitted_len = 0

        try:
            while True:
                with call_agent_response_stream(
                    openai_client=openai_client,
                    agent=agent,
                    conversation_id=request.conversation_id,
                ) as stream:
                    for event in stream:
                        if getattr(event, "type", "") != "response.output_text.delta":
                            continue

                        delta = getattr(event, "delta", "")
                        if not isinstance(delta, str) or not delta:
                            continue

                        raw_accumulated_text += delta
                        visible_text = raw_accumulated_text
                        next_chunk = visible_text[visible_emitted_len:]
                        if next_chunk:
                            visible_emitted_len = len(visible_text)
                            yield f"event: chunk\ndata: {json.dumps({'text': next_chunk}, ensure_ascii=False)}\n\n"

                    response = stream.get_final_response()

                for output_item in getattr(response, "output", []):
                    if getattr(output_item, "type", "") != "function_call":
                        continue

                    tool_payload = {
                        "name": getattr(output_item, "name", ""),
                        "call_id": getattr(output_item, "call_id", ""),
                    }
                    yield f"event: tool\ndata: {json.dumps(tool_payload, ensure_ascii=False)}\n\n"

                collected = collect_function_call_outputs(response)
                new_outputs = collected.get("outputs", [])
                emitted_events = collected.get("events", [])

                for emitted_event in emitted_events:
                    event_name = emitted_event.get("event")
                    payload = emitted_event.get("payload")
                    if not isinstance(event_name, str) or not isinstance(payload, dict):
                        continue

                    logger.warning(
                        "[debug] stream.event_emit event=%s status=%s url=%s payload=%s",
                        event_name,
                        payload.get("status", "-"),
                        payload.get("url", "-"),
                        json.dumps(payload, ensure_ascii=False, separators=(",", ":"))[:1200],
                    )
                    yield f"event: {event_name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

                if not new_outputs:
                    break

                append_conversation_items(
                    openai_client=openai_client,
                    conversation_id=request.conversation_id,
                    items=new_outputs,
                )

            response_text = raw_accumulated_text.strip()

            full_payload = {
                "conversation_id": request.conversation_id,
                "agent_name": agent.name,
                "agent_version": agent.version,
                "requested_version": requested_version_label,
                "response": response_text,
            }
            yield f"event: done\ndata: {json.dumps(full_payload, ensure_ascii=False)}\n\n"
        except Exception as exc:
            logger.exception("Streaming request failed")
            yield f"event: error\ndata: {json.dumps({'message': str(exc)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
