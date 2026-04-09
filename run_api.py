import uvicorn
import os


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}

if __name__ == "__main__":
    host = os.environ.get("UVICORN_HOST", "0.0.0.0")
    port = int(os.environ.get("UVICORN_PORT", "8000"))
    reload = _env_bool("UVICORN_RELOAD", True)
    log_level = os.environ.get("UVICORN_LOG_LEVEL", "info")
    workers = max(1, int(os.environ.get("UVICORN_WORKERS", "1")))

    run_kwargs = {
        "host": host,
        "port": port,
        "reload": reload,
        "log_level": log_level,
    }
    if not reload:
        run_kwargs["workers"] = workers

    uvicorn.run("api.main:app", **run_kwargs)
