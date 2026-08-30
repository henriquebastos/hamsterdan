# Copyright (c) 2026 Henrique Bastos

"""FastAPI boundary ending each webhook request at durable host custody."""

from __future__ import annotations

import asyncio
from typing import cast

from fastapi import FastAPI, Request, status
from pydantic import BaseModel, ConfigDict
from starlette.responses import JSONResponse, Response

from hamsterdan2.github_app.webhooks import (
    GitHubWebhook,
    WebhookRefusalError,
)
from hamsterdan2.github_app.webhooks import (
    RefusalReason as GitHubRefusalReason,
)
from hamsterdan2.host.delivery import (
    DeliveryCustody,
    DeliveryRefusalError,
)
from hamsterdan2.host.delivery import (
    RefusalReason as DeliveryRefusalReason,
)


type HttpRefusalReason = GitHubRefusalReason | DeliveryRefusalReason


class WebhookRefusalResponse(BaseModel):
    """Closed serialized refusal at the host HTTP boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    refusal: HttpRefusalReason


def refusal_response(reason: HttpRefusalReason) -> JSONResponse:
    status_code = (
        status.HTTP_503_SERVICE_UNAVAILABLE if reason == "custody_capacity_exhausted" else status.HTTP_400_BAD_REQUEST
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


def create_webhook_app(*, webhook: GitHubWebhook, custody: DeliveryCustody) -> FastAPI:
    app = FastAPI(title="Hamsterdan2 webhook custody")

    @app.post("/github/webhooks", status_code=status.HTTP_202_ACCEPTED)
    async def receive(request: Request) -> Response:
        try:
            body = await bounded_body(request, webhook.maximum_body_bytes)
            headers = cast("list[tuple[bytes, bytes]]", request.scope["headers"])
            normalized = webhook.normalize(headers, body)
            receipt = await asyncio.to_thread(custody.acquire, normalized)
        except (WebhookRefusalError, DeliveryRefusalError) as error:
            return refusal_response(error.reason)
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content=receipt.model_dump(mode="json"),
        )

    return app
