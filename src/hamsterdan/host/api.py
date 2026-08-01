"""FastAPI ingress kept strictly separate from durable background work."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status

from hamsterdan.github_app.webhooks import MAX_BODY_BYTES, WebhookRejected

from .service import HostService


def create_app(service: HostService, *, reconcile_startup: bool = True) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if reconcile_startup:
            await asyncio.to_thread(service.reconcile_registration)
        task = asyncio.create_task(service.worker(), name="webhook-inbox-worker")
        try:
            yield
        finally:
            service.stop()
            try:
                await asyncio.wait_for(task, timeout=max(1.0, service.poll_interval * 2))
            except TimeoutError:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            finally:
                await asyncio.to_thread(service.close)

    app = FastAPI(title="Hamsterdan host", lifespan=lifespan)

    @app.get("/healthz")
    def health() -> dict[str, object]:
        return service.health()

    @app.post("/github/webhooks", status_code=status.HTTP_202_ACCEPTED)
    async def webhook(request: Request) -> dict[str, str]:
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > MAX_BODY_BYTES:
                raise HTTPException(status_code=400, detail="request body is too large")
        headers = [(name.decode("latin-1"), value.decode("latin-1")) for name, value in request.scope["headers"]]
        try:
            receipt = await asyncio.to_thread(service.custody.receive, headers, bytes(body))
        except WebhookRejected as error:
            raise HTTPException(status_code=400, detail=str(error)) from None
        return {"delivery_id": receipt.delivery_id, "disposition": receipt.disposition}

    return app
