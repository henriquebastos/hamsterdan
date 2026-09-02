# Copyright (c) 2026 Henrique Bastos

"""FastAPI boundary ending each valid signed webhook at raw inbox storage."""

from __future__ import annotations

import asyncio
from typing import Literal, cast

from fastapi import FastAPI, Request, status
from pydantic import BaseModel, ConfigDict
from starlette.responses import JSONResponse, Response

from hamsterdan2.github_app.webhooks import GitHubWebhook, RefusalReason, WebhookRefusalError
from hamsterdan2.host.webhook_inbox import WebhookInbox, WebhookInboxCapacityError


type HttpRefusalReason = RefusalReason | Literal["inbox_capacity_exhausted"]


class WebhookRefusalResponse(BaseModel):
    """Closed serialized refusal at the host HTTP boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    refusal: HttpRefusalReason


def refusal_response(reason: HttpRefusalReason) -> JSONResponse:
    status_code = (
        status.HTTP_503_SERVICE_UNAVAILABLE if reason == "inbox_capacity_exhausted" else status.HTTP_400_BAD_REQUEST
    )
    content = WebhookRefusalResponse(refusal=reason).model_dump(mode="json")
    return JSONResponse(status_code=status_code, content=content)


async def bounded_body(request: Request, maximum_body_bytes: int) -> bytes:
    body = bytearray()
    async for chunk in request.stream():
        if len(chunk) > maximum_body_bytes - len(body):
            raise WebhookRefusalError("body_too_large")
        body.extend(chunk)
    return bytes(body)


def create_webhook_app(*, webhook: GitHubWebhook, inbox: WebhookInbox) -> FastAPI:
    app = FastAPI(title="Hamsterdan Webhook Inbox")

    @app.post("/github/webhooks", status_code=status.HTTP_200_OK)
    async def receive(request: Request) -> Response:
        try:
            body = await bounded_body(request, webhook.maximum_body_bytes)
            headers = cast("list[tuple[bytes, bytes]]", request.scope["headers"])
            verified = webhook.verify(headers, body)
            receipt = await asyncio.to_thread(inbox.record, verified)
        except WebhookRefusalError as error:
            return refusal_response(error.reason)
        except WebhookInboxCapacityError:
            return refusal_response("inbox_capacity_exhausted")
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=receipt.model_dump(mode="json"),
        )

    return app
