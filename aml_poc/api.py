import asyncio
import json
from contextlib import asynccontextmanager
from typing import Annotated, Literal

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel

from .models import EvidenceDocument, ReplayRequest, ReviewDecision, Transaction
from .service import Service


class InvestigationRequest(BaseModel):
    failure: Literal[
        "none",
        "missing_document",
        "missing_profile",
        "transaction_unavailable",
        "unreadable_document",
        "policy_conflict",
    ] = "none"
    force: bool = False


class ClockRequest(BaseModel):
    as_of: str


def create_app(service=None):
    @asynccontextmanager
    async def lifespan(app):
        app.state.service = service or Service()
        yield
        if service is None:
            app.state.service.close()

    app = FastAPI(title="AML Investigation POC", version="0.1.0", lifespan=lifespan)

    @app.middleware("http")
    async def strip_backend_prefix(request: Request, call_next):
        path = request.scope.get("path", "")
        if path == "/backend" or path.startswith("/backend/"):
            request.scope["path"] = path[len("/backend") :] or "/"
        return await call_next(request)

    @app.exception_handler(ValueError)
    async def invalid(request: Request, error: ValueError):
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=409, content={"detail": str(error)})

    def svc(request):
        return request.app.state.service

    @app.get("/health")
    def health(request: Request):
        return {"status": "ok", "mode": svc(request).mode}

    @app.get("/status")
    def status(request: Request):
        return svc(request).status()

    @app.post("/replay/start")
    def start(request: Request, body: ReplayRequest):
        return svc(request).start(**body.model_dump())

    @app.post("/replay/pause")
    def pause(request: Request):
        return svc(request).pause()

    @app.post("/replay/clock")
    def clock(request: Request, body: ClockRequest):
        return svc(request).advance_clock(body.as_of)

    @app.post("/transactions")
    def ingest(request: Request, body: Transaction):
        return svc(request).ingest(body)

    @app.get("/transactions")
    def transactions(request: Request, limit: int = 30):
        return svc(request).recent(min(max(limit, 1), 1000))

    @app.get("/customers")
    def customers(request: Request):
        return [
            {k: v for k, v in customer.items() if k != "assigned_pattern_ids"}
            for customer in svc(request).data.customers.values()
        ]

    @app.get("/customers/{customer_id}/kyc")
    def customer_kyc(request: Request, customer_id: str):
        data = svc(request).data
        customer = data.customers.get(customer_id)
        if customer is None:
            raise HTTPException(404, "Customer not found")
        return {
            "customer": {k: v for k, v in customer.items() if k != "assigned_pattern_ids"},
            "accounts": [a for a in data.accounts.values() if a["customer_id"] == customer_id],
            "counterparties": [
                c for c in data.counterparties.values() if customer_id in c.get("associated_customer_ids", [])
            ],
        }

    @app.get("/alerts")
    def alerts(request: Request, scope: Literal["all", "stream", "history"] = "all"):
        return svc(request).list_alerts(scope)

    @app.get("/alerts/{alert_id}")
    def alert(request: Request, alert_id: str):
        with svc(request).lock:
            result = svc(request).store.get_alert(alert_id)
            if not result:
                raise HTTPException(404, "Alert not found")
            return result

    @app.post("/alerts/{alert_id}/investigate")
    def investigate(request: Request, alert_id: str, body: InvestigationRequest):
        return svc(request).investigate(alert_id, **body.model_dump())

    @app.get("/alerts/{alert_id}/case")
    def case(request: Request, alert_id: str):
        with svc(request).lock:
            return svc(request).store.latest_case(alert_id)

    @app.get("/cases/{case_id}")
    def case_version(request: Request, case_id: str):
        with svc(request).lock:
            result = svc(request).store.get_case(case_id)
            if not result:
                raise HTTPException(404, "Case not found")
            return result

    @app.post("/alerts/{alert_id}/review")
    def review(request: Request, alert_id: str, body: ReviewDecision):
        return svc(request).review(alert_id, body.model_dump())

    @app.post("/alerts/{alert_id}/request-documents")
    def request_documents(request: Request, alert_id: str):
        return svc(request).request_customer_documents(alert_id)

    @app.get("/alerts/{alert_id}/document-requests")
    def document_requests(request: Request, alert_id: str):
        service = svc(request)
        with service.lock:
            if not service.store.get_alert(alert_id):
                raise HTTPException(404, "Alert not found")
            return service.store.requests_for_alert(alert_id)

    @app.post("/alerts/{alert_id}/demo-packet")
    def packet(
        request: Request,
        alert_id: str,
        resolution: Literal["unresolved", "documented_legitimate"] = "unresolved",
    ):
        return svc(request).add_demo_packet(alert_id, resolution=resolution)

    @app.get("/alerts/{alert_id}/documents")
    def alert_documents(request: Request, alert_id: str):
        service = svc(request)
        with service.lock:
            alert = service.store.get_alert(alert_id)
            if not alert:
                raise HTTPException(404, "Alert not found")
            from .files import viewable

            return [
                {**doc, "viewable": viewable(doc)}
                for doc in service.store.documents(alert["customer_id"])
                if not doc.get("transaction_ids")
                or set(doc["transaction_ids"]).intersection(alert["transaction_ids"])
            ]

    @app.get("/documents/{document_id}/file")
    def document_file(request: Request, document_id: str):
        from fastapi.responses import FileResponse

        found = svc(request).document_file(document_id)
        if not found:
            raise HTTPException(404, "Original file is not available")
        path, media, filename = found
        return FileResponse(path, media_type=media, filename=filename)

    @app.post("/documents")
    def document(request: Request, body: EvidenceDocument):
        return svc(request).add_document(body.model_dump())

    @app.post("/documents/extract")
    async def extract_document(
        request: Request,
        file: Annotated[UploadFile, File()],
        alert_id: Annotated[str, Form()],
        evidence_types: Annotated[str, Form()],
    ):
        from .documents import extract

        try:
            requirements = json.loads(evidence_types)
        except json.JSONDecodeError as error:
            raise HTTPException(422, "evidence_types must be a JSON array") from error
        if (
            not isinstance(requirements, list)
            or not requirements
            or not all(isinstance(item, str) for item in requirements)
        ):
            raise HTTPException(422, "Select at least one evidence requirement")
        content = await file.read(5 * 1024 * 1024 + 1)
        try:
            return await asyncio.to_thread(
                extract,
                svc(request),
                alert_id,
                file.filename or "document",
                file.content_type or "application/octet-stream",
                content,
                requirements,
            )
        except ValueError:
            raise
        except Exception as error:
            raise HTTPException(
                502, "Document extraction failed. No evidence was accepted; inspect the server log."
            ) from error

    @app.get("/audit")
    def audit(request: Request, case_id: str | None = None):
        with svc(request).lock:
            return {
                "valid": svc(request).store.verify_audit(),
                "events": svc(request).store.audit_rows(case_id),
            }

    @app.get("/policies")
    def policies(request: Request):
        return {"hash": svc(request).data.policy_hash, "patterns": list(svc(request).data.enabled.values())}

    @app.get("/cases/{case_id}/report", response_class=PlainTextResponse)
    def report(request: Request, case_id: str):
        with svc(request).lock:
            result = svc(request).store.get_case(case_id)
            if not result:
                raise HTTPException(404, "Case not found")
            return result.get("report", "Report is still being assembled.")

    @app.get("/events")
    async def events(request: Request):
        async def generate():
            sequence = 0
            while not await request.is_disconnected():
                snapshot = await asyncio.to_thread(svc(request).status)
                yield f"id: {sequence}\nevent: status\ndata: {json.dumps(snapshot)}\n\n"
                sequence += 1
                await asyncio.sleep(1)

        return StreamingResponse(
            generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
        )

    import os

    import psycopg
    from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
    from fastapi.staticfiles import StaticFiles

    from .config import ROOT
    from .kyc_postgres import app as kyc_app

    @app.exception_handler(psycopg.OperationalError)
    async def database_unavailable(request, error):
        import logging

        logging.getLogger(__name__).exception("RDS operational error")
        return JSONResponse(
            status_code=503,
            content={
                "detail": "RDS database unavailable. Check the DB_* settings and that this host can reach the database port."
            },
        )

    app.include_router(kyc_app.router)

    dashboard = ROOT / "kyc-dashboard" / "dist"
    serve_console = os.environ.get("AML_SERVE_CONSOLE", "").lower() in {"1", "true", "yes"}
    if dashboard.exists() and serve_console:
        app.mount("/kyc-assets", StaticFiles(directory=dashboard), name="kyc-assets")

        @app.get("/{path:path}")
        def console(path: str):
            return FileResponse(dashboard / "index.html", headers={"Cache-Control": "no-cache"})
    else:

        @app.get("/kyc")
        @app.get("/kyc/{customer_id}")
        def dashboard_window(request: Request):
            console_url = os.environ.get("AML_CONSOLE_URL", "http://127.0.0.1:8501").rstrip("/")
            suffix = f"?{request.url.query}" if request.url.query else ""
            return RedirectResponse(console_url + request.url.path + suffix)

    return app


app = create_app()
