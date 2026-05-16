from pathlib import Path
import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from api.routes import inventory, users, auth, planning, logs, traceability, model_dictionary, roles, sandbox, dealer_orders

logger = logging.getLogger(__name__)

app = FastAPI(
    title="V7ex API",
    description="FastAPI layer for the Finished Goods Management System",
    version="1.0.0"
)


@app.on_event("startup")
def on_startup():
    from database import init_mysql_tables_v2
    try:
        result = init_mysql_tables_v2()
        if result.get("initialized"):
            logger.info("DB migration: %s", result.get("message", ""))
    except Exception as e:
        logger.warning("DB migration skipped: %s", e)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIST_DIR = PROJECT_ROOT / "frontend" / "dist"
FRONTEND_INDEX_FILE = FRONTEND_DIST_DIR / "index.html"

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(inventory.router, prefix="/api/v1/inventory", tags=["Inventory"])
app.include_router(users.router, prefix="/api/v1/users", tags=["Users"])
app.include_router(planning.router, prefix="/api/v1/planning", tags=["Planning"])
app.include_router(planning.internal_router, prefix="/internal/planning", tags=["Internal"])
app.include_router(logs.router, prefix="/api/v1/logs", tags=["Logs"])
app.include_router(traceability.router, prefix="/api/v1/traceability", tags=["Traceability"])
app.include_router(model_dictionary.router, prefix="/api/v1/model-dictionary", tags=["ModelDictionary"])
app.include_router(roles.router, prefix="/api/v1/roles", tags=["Roles"])
app.include_router(sandbox.router, prefix="/api/v1/sandbox", tags=["Sandbox"])
app.include_router(dealer_orders.router, prefix="/api/v1/dealer-orders", tags=["DealerOrders"])

# Register sandbox WS directly on app (bypasses router-level HTTP dependencies)
app.websocket("/api/v1/sandbox/ws")(sandbox.proxy_ws)

@app.get("/health")
def health_check():
    return {"status": "ok"}


if (FRONTEND_DIST_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST_DIR / "assets"), name="frontend-assets")


@app.get("/{full_path:path}", include_in_schema=False)
def serve_frontend(full_path: str):
    if not FRONTEND_INDEX_FILE.exists():
        raise HTTPException(status_code=404, detail="Frontend build not found")

    clean_path = str(full_path or "").strip("/")
    if clean_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not Found")

    candidate = FRONTEND_DIST_DIR / clean_path if clean_path else FRONTEND_INDEX_FILE
    if clean_path and candidate.is_file():
        return FileResponse(candidate)

    return FileResponse(FRONTEND_INDEX_FILE)
