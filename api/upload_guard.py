import os
from fastapi import HTTPException


def require_uploads_enabled() -> None:
    enabled = os.getenv("V8_UPLOADS_ENABLED", "false").strip().lower()
    if enabled not in {"1", "true", "yes", "on"}:
        raise HTTPException(status_code=503, detail="V8 文件上传功能暂时关闭")
