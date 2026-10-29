from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_project_env() -> None:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.is_file():
        return
    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        item = line.strip()
        if not item or item.startswith("#") or "=" not in item:
            continue
        name, value = item.split("=", 1)
        name = name.strip()
        value = value.strip()
        if not name or name.startswith("export "):
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(name, value)


_load_project_env()


_ENV_PREFIX = "V8_SYNC_"
_LEGACY_PREFIX = "REPAIR_SYNC_"


def _env(name: str, default: str = "") -> str:
    """读取配置：优先 V8_SYNC_*，回退旧键 REPAIR_SYNC_*（兼容未升级的部署）。"""
    if not name.startswith(_ENV_PREFIX):
        return os.getenv(name, default)
    value = os.getenv(name)
    if value is not None:
        return value
    legacy = _LEGACY_PREFIX + name[len(_ENV_PREFIX):]
    return os.getenv(legacy, default)


def _bool(name: str, default: bool = False) -> bool:
    value = _env(name, "")
    if not value:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)).strip())
    except (TypeError, ValueError):
        return default


def _csv(name: str, default: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in _env(name, default).split(",") if item.strip())


@dataclass(frozen=True)
class V8SyncConfig:
    enabled: bool = False
    base_url: str = ""
    snapshot_path: str = "/api/integrations/v8/snapshots"
    event_path: str = "/api/integrations/v8/events"
    client_id: str = "v8-factory-01"
    key_id: str = ""
    hmac_secret: str = ""
    mtls_cert: str = ""
    mtls_key: str = ""
    ca_bundle: str = ""
    schedule_time: str = "02:30"
    timezone: str = "Asia/Shanghai"
    allowed_check_status: tuple[str, ...] = ("manual_passed", "passed", "approved")
    max_body_mb: int = 10
    auto_activate: bool = True
    realtime_enabled: bool = False
    event_batch_size: int = 100
    event_flush_interval_seconds: int = 3
    event_max_pending: int = 10000
    source_bindings_table: str = "machine_component_bindings"
    source_materials_table: str = "materials"
    source_instances_table: str = "material_instances"
    source_photo_items_table: str = "photo_item_library"
    source_photo_config_table: str = "model_photo_config"

    @classmethod
    def from_env(cls) -> "V8SyncConfig":
        return cls(
            enabled=_bool("V8_SYNC_ENABLED"),
            base_url=_env("V8_SYNC_BASE_URL", "").strip(),
            snapshot_path=_env("V8_SYNC_SNAPSHOT_PATH", "/api/integrations/v8/snapshots").strip(),
            event_path=_env("V8_SYNC_EVENT_PATH", "/api/integrations/v8/events").strip(),
            client_id=_env("V8_SYNC_CLIENT_ID", "v8-factory-01").strip(),
            key_id=_env("V8_SYNC_KEY_ID", "").strip(),
            hmac_secret=_env("V8_SYNC_HMAC_SECRET", ""),
            mtls_cert=_env("V8_SYNC_MTLS_CERT", "").strip(),
            mtls_key=_env("V8_SYNC_MTLS_KEY", "").strip(),
            ca_bundle=_env("V8_SYNC_CA_BUNDLE", "").strip(),
            schedule_time=_env("V8_SYNC_TIME", "02:30").strip(),
            timezone=_env("V8_SYNC_TIMEZONE", "Asia/Shanghai").strip(),
            allowed_check_status=_csv(
                "V8_SYNC_ALLOWED_CHECK_STATUS", "manual_passed,passed,approved"
            ),
            max_body_mb=max(1, _int("V8_SYNC_MAX_BODY_MB", 10)),
            auto_activate=_bool("V8_SYNC_AUTO_ACTIVATE", True),
            realtime_enabled=_bool("V8_SYNC_REALTIME_ENABLED"),
            event_batch_size=max(1, _int("V8_SYNC_EVENT_BATCH_SIZE", 100)),
            event_flush_interval_seconds=max(1, _int("V8_SYNC_EVENT_FLUSH_INTERVAL_SECONDS", 3)),
            event_max_pending=max(1, _int("V8_SYNC_EVENT_MAX_PENDING", 10000)),
            source_bindings_table=_env(
                "V8_SYNC_SOURCE_BINDINGS_TABLE", "machine_component_bindings"
            ).strip(),
            source_materials_table=_env("V8_SYNC_SOURCE_MATERIALS_TABLE", "materials").strip(),
            source_instances_table=_env(
                "V8_SYNC_SOURCE_INSTANCES_TABLE", "material_instances"
            ).strip(),
            source_photo_items_table=_env(
                "V8_SYNC_SOURCE_PHOTO_ITEMS_TABLE", "photo_item_library"
            ).strip(),
            source_photo_config_table=_env(
                "V8_SYNC_SOURCE_PHOTO_CONFIG_TABLE", "model_photo_config"
            ).strip(),
        )


def get_config() -> V8SyncConfig:
    return V8SyncConfig.from_env()
