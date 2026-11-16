"""POST /api/v1/assistant/chat — pytania do lokalnego modelu z bezpiecznymi funkcjami."""

from typing import Annotated, Literal

import httpx
import psycopg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.assistant.presentation import Evidence
from app.assistant.service import AssistantUnavailable, chat
from app.assistant.tools import ToolError, get_attached_crossing
from app.config import Settings, get_settings
from app.db import get_connection

router = APIRouter(tags=["asystent"])


class HistoryItem(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=500)
    history: list[HistoryItem] = Field(default_factory=list, max_length=8)
    crossing_id: int | None = Field(default=None, strict=True, gt=0)


class ToolCallOut(BaseModel):
    name: str
    arguments: dict
    ok: bool


class ChatResponse(BaseModel):
    answer: str
    model: str
    grounded: bool
    tool_calls: list[ToolCallOut]
    disclaimer: str
    evidence: Evidence = Field(default_factory=Evidence)


def get_http_client(
    settings: Annotated[Settings, Depends(get_settings)],
) -> httpx.Client:
    return httpx.Client(timeout=settings.assistant_timeout_s)


@router.post("/assistant/chat", response_model=ChatResponse)
def assistant_chat(
    body: ChatRequest,
    conn: Annotated[psycopg.Connection, Depends(get_connection)],
    http: Annotated[httpx.Client, Depends(get_http_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ChatResponse:
    try:
        context = None
        if body.crossing_id is not None:
            try:
                context = get_attached_crossing(conn, body.crossing_id)
            except ToolError as error:
                raise HTTPException(404, str(error)) from error
        reply = chat(
            conn,
            http,
            settings.ollama_base_url,
            settings.ollama_model,
            body.message.strip(),
            [item.model_dump() for item in body.history],
            attached_crossing=context,
        )
    except AssistantUnavailable as error:
        raise HTTPException(
            503,
            "Asystent jest niedostępny: lokalny model nie odpowiada albo nie został "
            "jeszcze pobrany. Mapa i ranking działają bez niego.",
        ) from error
    finally:
        http.close()
    return ChatResponse(
        answer=reply.answer,
        model=reply.model,
        grounded=reply.grounded,
        tool_calls=[ToolCallOut(**vars(call)) for call in reply.tool_calls],
        disclaimer=reply.disclaimer,
        evidence=reply.evidence,
    )
