"""Local FastAPI boundary. Run one worker; DuckDB owns local storage."""
import logging
import os
import time
from pathlib import Path
from typing import Literal
from uuid import UUID
from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from .models import ResearchConfig
from .services.storage import Storage
from .services.ledger import Ledger
from .services.analytics import analyze_pair, clean_json, curve_analysis, compare_all_pairs
from .services.genome import list_specs
from .services.analogs import find_analogs
from .services.replay import replay
from .services.scenarios import ghost_market, survival_map
from .services.red_team import audit
from .services.demo import create_demo
from .services.orchestration import investigate, reproduce

logger = logging.getLogger("aurum.api")
Mode = Literal["real", "synthetic"]


def create_app(data_dir=None, evidence_dir=None):
    app = FastAPI(title="AURUM X", version="0.1.0", description="Local commodity research. No brokerage execution.")
    storage = Storage(Path(data_dir or os.getenv("AURUM_DATA_DIR", "data")))
    ledger = Ledger(Path(evidence_dir or os.getenv("AURUM_EVIDENCE_DIR", "evidence")))
    app.state.storage, app.state.ledger = storage, ledger

    @app.middleware("http")
    async def request_boundary(request: Request, call_next):
        declared = request.headers.get("content-length", "0")
        if declared.isdigit() and int(declared) > 100 * 1024 * 1024:
            return JSONResponse({"detail": "Request exceeds100MiB; use a smaller import batch"}, status_code=413)
        start = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        logger.info("request path=%s status=%s seconds=%.3f", request.url.path, response.status_code, time.perf_counter()-start)
        return response

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=422)

    @app.exception_handler(FileNotFoundError)
    async def missing(request, exc):
        return JSONResponse({"detail": "Requested artifact was not found"}, status_code=404)

    @app.get("/health")
    def health():
        return {"status": "ok", "version": "0.1.0", "llm_required": False}

    @app.get("/api/summary")
    def summary(mode: Mode="real"):
        return clean_json(storage.summary(mode))

    @app.get("/api/contracts")
    def contracts(mode: Mode="real"):
        return clean_json(storage.contracts(mode))

    @app.get("/api/specifications")
    def specifications(mode: Mode="real"):
        return list_specs(mode)

    @app.get("/api/imports")
    def imports(mode: Mode | None=None):
        return storage.imports(mode)

    @app.get("/api/data")
    def data(mode: Mode="real", start: str | None=None, end: str | None=None, symbol: str | None=None, limit: int=Query(5000, ge=1, le=10000)):
        frame = storage.load(mode,start,end,[symbol] if symbol else None)
        return {"rows": clean_json(frame.head(limit).to_dict("records")), "total_rows": len(frame), "truncated": len(frame)>limit}

    @app.post("/api/import")
    async def import_files(files: list[UploadFile]=File(...), requested_date: str | None=Form(None), date_order: Literal["mdy","dmy"]=Form("mdy")):
        if len(files)>20:
            raise HTTPException(413,"At most20 files per batch")
        reports=[]
        total=0
        for file in files:
            content=await file.read(25*1024*1024+1)
            total+=len(content)
            if total>100*1024*1024:
                raise HTTPException(413,"Batch exceeds100MiB")
            reports.append(storage.import_bytes(file.filename or "upload",content,requested_date or None,date_order,"real"))
            await file.close()
        return {"reports":reports,"rows_imported":sum(r["rows_imported"] for r in reports)}

    class DemoConfig(BaseModel):
        seed: int=Field(42,ge=0,le=2**32-1)

    @app.post("/api/demo")
    def demo(config: DemoConfig):
        return create_demo(storage,config.seed)

    def dataset(config):
        # Keep prior observations for shifted estimates; the analytical service
        # enforces start for output and cutoff before any fitted statistic.
        ends=[x for x in [config.get("cutoff"),config.get("end")] if x]
        frame=storage.load(config["mode"],end=min(ends) if ends else None,symbols=config["pair"])
        if len(frame)>100000:
            raise ValueError("Too many observations for an interactive request")
        return frame

    @app.post("/api/analytics")
    def analytics(model: ResearchConfig):
        c=model.as_dict(); return analyze_pair(dataset(c),c)

    @app.post('/api/validate-config')
    def validate_config(model: ResearchConfig):
        return model.as_dict()

    @app.post("/api/scan")
    def scan(model: ResearchConfig):
        c=model.as_dict(); return compare_all_pairs(storage.load(c["mode"],end=c.get("cutoff") or c.get("end")),c)

    @app.post("/api/curves")
    def curves(model: ResearchConfig):
        c=model.as_dict(); frame=dataset(c)
        return curve_analysis(frame,c.get("cutoff") or c.get("end") or (frame.date.max() if len(frame) else "2025-01-01"),c["pair"][0])

    @app.post("/api/ghost")
    def ghost(model: ResearchConfig):
        c=model.as_dict(); return ghost_market(dataset(c),c)

    @app.post("/api/survival")
    def survival(model: ResearchConfig):
        c=model.as_dict(); return clean_json(survival_map(dataset(c),c))

    @app.post("/api/analogs")
    def analogs(model: ResearchConfig):
        c=model.as_dict(); return find_analogs(dataset(c),c)

    @app.post("/api/replay")
    def replay_route(model: ResearchConfig):
        c=model.as_dict(); return replay(dataset(c),c)

    @app.post("/api/audit")
    def red_team(model: ResearchConfig):
        c=model.as_dict(); frame=dataset(c)
        return audit(frame,c,replay_result=replay(frame,c))

    @app.post("/api/investigations")
    def investigation(model: ResearchConfig):
        return investigate(storage,ledger,model.as_dict())

    @app.get("/api/investigations")
    def history():
        return ledger.list()

    @app.get("/api/investigations/{key}")
    def certificate(key: UUID):
        return ledger.get(str(key))

    @app.post("/api/investigations/{key}/reproduce")
    def reproduction(key: UUID):
        return reproduce(ledger,str(key))

    return app


app = create_app()
