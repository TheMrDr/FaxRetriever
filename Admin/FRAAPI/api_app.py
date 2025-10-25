"""FRAAPI — FaxRetriever Admin FastAPI app

Purpose
- Standalone FastAPI application that exposes all Admin endpoints for FaxRetriever (FR) and the FRA GUI.
- Intended to be hosted by the Windows service (windows_service.py) in production.

Run for development (PowerShell, from Admin\licensing_server)
- uvicorn api_app:app --reload --port 8000
- Environment variables:
  - FRA_MONGO_URI: MongoDB connection string (e.g., mongodb://user:pass@host:27017/?authSource=fra2&tls=true)
  - FRAAPI_PORT: Port for the Windows service to listen on (defaults to 8000)

Routers/endpoints
- /init (routes.init_route)
- /bearer (routes.bearer_route)
- /assignments.list, /assignments.request, /assignments.unregister (routes.assignments_route)
- /admin/* (routes.admin_route) — Admin-only GUI helpers (never call MongoDB from the GUI)

Health check
- GET /health returns {"status": "ok", "service": "FaxRetrieverAdmin API", "version": "2.3"}
"""

from fastapi import FastAPI
from routes.admin_route import router as admin_router
from routes.assignments_route import router as assignments_router
from routes.bearer_route import router as bearer_router
from routes.init_route import router as init_router
from routes.libertyrx_route import router as libertyrx_router
from routes.sync_route import router as sync_router

app = FastAPI(title="FaxRetrieverAdmin", version="2.3")

# Route registrations
app.include_router(init_router, prefix="/init")
app.include_router(bearer_router, prefix="/bearer")
app.include_router(
    assignments_router
)  # exposes /assignments.list, /assignments.request, /assignments.unregister
app.include_router(admin_router, prefix="/admin")
app.include_router(libertyrx_router, prefix="/integrations/libertyrx")
app.include_router(sync_router, prefix="/sync")


# Health endpoint for service readiness checks
@app.get("/health")
async def health():
    return {"status": "ok", "service": "FaxRetrieverAdmin API", "version": "2.3"}


# Startup initialization: schedule DB index creation in background (non-blocking)
@app.on_event("startup")
def _startup_indexes():
    try:
        import logging
        import threading
        import time

        logger = logging.getLogger("fraapi.startup")
        logger.info("Scheduling non-blocking Mongo index initialization…")

        def _bg():
            t0 = time.time()
            try:
                from db.mongo_interface import ensure_indexes

                ensure_indexes()
                elapsed = time.time() - t0
                logger.info(f"Mongo index initialization completed in {elapsed:.1f}s")
            except Exception as e:
                logger.warning(f"Mongo index initialization skipped/failed: {e}")

        threading.Thread(target=_bg, daemon=True).start()
    except Exception:
        # Never block app startup due to initialization helpers
        pass


# Lightweight request timing middleware
@app.middleware("http")
async def add_process_time_header(request, call_next):
    try:
        import logging
        import time

        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000.0
        response.headers["X-Process-Time"] = f"{duration_ms:.1f}ms"
        if duration_ms > 800:  # warn on slow requests (>0.8s)
            logging.getLogger("fraapi.perf").warning(
                f"slow {request.method} {request.url.path} {duration_ms:.1f} ms"
            )
        return response
    except Exception:
        return await call_next(request)
