from pathlib import Path
import asyncio
import logging

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from api.routes import inventory, users, auth, planning, logs, traceability, model_dictionary, roles, sandbox, dealer_orders

logger = logging.getLogger(__name__)

app = FastAPI(
    title="V8betaVer1.0 API",
    description="FastAPI layer for the Finished Goods Management System",
    version="1.0.0"
)


@app.on_event("startup")
async def on_startup():
    from database import init_mysql_tables_v2
    try:
        result = init_mysql_tables_v2()
        if result.get("initialized"):
            logger.info("DB migration: %s", result.get("message", ""))
    except Exception as e:
        logger.warning("DB migration skipped: %s", e)
    try:
        from crud.cloud_sync_outbox import cloud_sync_worker_loop, ensure_cloud_sync_outbox_table
        ensure_cloud_sync_outbox_table()
        app.state.cloud_sync_worker_task = asyncio.create_task(cloud_sync_worker_loop())
    except Exception as e:
        logger.warning("cloud sync worker not started: %s", e)
    try:
        from crud.cloud_dealer_order_sync import cloud_pull_worker_loop
        app.state.cloud_pull_worker_task = asyncio.create_task(cloud_pull_worker_loop())
    except Exception as e:
        logger.warning("cloud pull worker not started: %s", e)
    try:
        app.state.watch_dealer_orders_task = asyncio.create_task(watch_dealer_orders_db())
    except Exception as e:
        logger.warning("dealer orders db watch worker not started: %s", e)
    try:
        app.state.watch_finished_goods_task = asyncio.create_task(watch_finished_goods_db())
    except Exception as e:
        logger.warning("finished goods db watch worker not started: %s", e)



@app.on_event("shutdown")
async def on_shutdown():
    task = getattr(app.state, "cloud_sync_worker_task", None)
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    pull_task = getattr(app.state, "cloud_pull_worker_task", None)
    if pull_task:
        pull_task.cancel()
        try:
            await pull_task
        except asyncio.CancelledError:
            pass

    watch_task = getattr(app.state, "watch_dealer_orders_task", None)
    if watch_task:
        watch_task.cancel()
        try:
            await watch_task
        except asyncio.CancelledError:
            pass

    watch_fg_task = getattr(app.state, "watch_finished_goods_task", None)
    if watch_fg_task:
        watch_fg_task.cancel()
        try:
            await watch_fg_task
        except asyncio.CancelledError:
            pass


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

# Register global WebSocket endpoint
@app.websocket("/api/v1/ws")
async def websocket_endpoint(websocket: WebSocket):
    from api.websockets.manager import manager
    from api.routes.auth import get_current_user_context
    token = websocket.query_params.get("token", "")
    try:
        if token:
            get_current_user_context(token)
        else:
            await websocket.close(code=4001, reason="Unauthorized")
            return
    except Exception:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            import json
            try:
                msg = json.loads(data)
                if msg.get("event") == "ping":
                    await websocket.send_json({"event": "pong"})
            except Exception:
                pass
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)

async def watch_dealer_orders_db() -> None:
    """
    Periodically checks the dealer_orders table for modifications (updates/inserts/deletes)
    and broadcasts the updated pending counts via WebSockets when any change is detected.
    """
    import asyncio
    from sqlalchemy import text
    from database import get_engine
    from api.websockets.manager import manager
    from crud.dealer_orders import get_dealer_orders_pending_counts, ensure_dealer_order_tables

    logger.info("Dealer orders database change monitor started")
    try:
        ensure_dealer_order_tables()
    except Exception as e:
        logger.warning(f"Failed to ensure dealer order tables at watch startup: {e}")

    last_val = None
    while True:
        try:
            with get_engine().begin() as conn:
                res = conn.execute(text("SELECT MAX(updated_at), COUNT(*) FROM dealer_orders")).fetchone()
                val = (res[0], res[1]) if res else (None, 0)

            if last_val is not None and val != last_val:
                logger.info(f"Dealer orders table change detected: {last_val} -> {val}. Broadcasting updated counts...")
                counts = get_dealer_orders_pending_counts()
                await manager.broadcast({
                    "event": "dealer_orders_changed",
                    "data": counts
                })
            last_val = val
        except Exception as e:
            logger.debug(f"Error in watch_dealer_orders_db loop: {e}")
        await asyncio.sleep(1.0)

async def watch_finished_goods_db() -> None:
    """
    Periodically checks the finished_goods_data table for modifications (updates/inserts/deletes)
    and triggers a WeChat batch summary sync to the cloud when any change is detected.
    """
    import asyncio
    from sqlalchemy import text
    from database import get_engine
    from crud.cloud_sync_outbox import enqueue_wechat_batch_summary_sync

    logger.info("Finished goods database change monitor started")
    
    last_val = None
    while True:
        try:
            with get_engine().begin() as conn:
                table_check = conn.execute(text("SHOW TABLES LIKE 'finished_goods_data'")).fetchone()
                if table_check:
                    res = conn.execute(text("SELECT MAX(`更新时间`), COUNT(*) FROM finished_goods_data")).fetchone()
                    val = (res[0], res[1]) if res else (None, 0)
                else:
                    val = (None, 0)

            if last_val is not None and val != last_val:
                logger.info(f"finished_goods_data change detected: {last_val} -> {val}. Enqueueing wechat_batch_summary sync...")
                enqueue_wechat_batch_summary_sync("db_change_auto_sync")
            last_val = val
        except Exception as e:
            logger.debug(f"Error in watch_finished_goods_db loop: {e}")
        await asyncio.sleep(2.0)


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
