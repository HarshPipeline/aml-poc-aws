"""React frontend server with a same-origin proxy to the single Python API."""

import os
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask

from .config import ROOT

DIST = ROOT / "kyc-dashboard" / "dist"
API = os.environ.get("AML_API_URL", "http://127.0.0.1:8001")


@asynccontextmanager
async def lifespan(app):
    async with httpx.AsyncClient(base_url=API, timeout=240) as client:
        app.state.client = client
        yield


app = FastAPI(title="AML React Console", lifespan=lifespan)


@app.api_route("/backend/{path:path}", methods=["GET", "POST"])
@app.api_route("/api/{path:path}", methods=["GET"])
async def proxy(request: Request, path: str):
    target = ("/api/" if request.url.path.startswith("/api/") else "/") + path
    headers = {k: v for k, v in request.headers.items() if k.lower() in {"content-type", "accept"}}
    try:
        outgoing = request.app.state.client.build_request(
            request.method, target, params=request.query_params, headers=headers, content=await request.body()
        )
        response = await request.app.state.client.send(outgoing, stream=True)
    except httpx.RequestError as error:
        raise HTTPException(503, "Python API is unavailable. Restart ./run.sh serve.") from error
    return StreamingResponse(
        response.aiter_bytes(),
        status_code=response.status_code,
        media_type=response.headers.get("content-type"),
        background=BackgroundTask(response.aclose),
    )


@app.get("/_health")
def health():
    return {"status": "ok", "frontend": "react"}


if DIST.exists():
    app.mount("/kyc-assets", StaticFiles(directory=DIST), name="assets")


@app.get("/{path:path}")
def index(path: str):
    if not (DIST / "index.html").exists():
        return Response("React build missing. Run npm run build --prefix kyc-dashboard.", status_code=503)
    return FileResponse(DIST / "index.html", headers={"Cache-Control": "no-cache"})
