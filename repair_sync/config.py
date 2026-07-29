from __future__ import annotations

import os
from dataclasses import dataclass


def _bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)).strip())
    except (TypeError, ValueError):
        return default


def _csv(name: str, default: str) -> tuple[str, ...]:
    value = os.getenv(name, default)
    return tuple(item.strip() for item in value.split(",") if item.strip())


@dataclass(frozen=True)
class RepairSyncConfig:
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
    def from_env(cls) -> "RepairSyncConfig":
        return cls(
            enabled=_bool("REPAIR_SYNC_ENABLED"),
            base_url=os.getenv("REPAIR_SYNC_BASE_URL", "").strip(),
            snapshot_path=os.getenv("REPAIR_SYNC_SNAPSHOT_PATH", "/api/integrations/v8/snapshots").strip(),
            event_path=os.getenv("REPAIR_SYNC_EVENT_PATH", "/api/integrations/v8/events").strip(),
            client_id=os.getenv("REPAIR_SYNC_CLIENT_ID", "v8-factory-01").strip(),
            key_id=os.getenv("REPAIR_SYNC_KEY_ID", "").strip(),
            hmac_secret=os.getenv("REPAIR_SYNC_HMAC_SECRET", ""),
            mtls_cert=os.getenv("REPAIR_SYNC_MTLS_CERT", "").strip(),
            mtls_key=os.getenv("REPAIR_SYNC_MTLS_KEY", "").strip(),
            ca_bundle=os.getenv("REPAIR_SYNC_CA_BUNDLE", "").strip(),
            schedule_time=os.getenv("REPAIR_SYNC_TIME", "02:30").strip(),
            timezone=os.getenv("REPAIR_SYNC_TIMEZONE", "Asia/Shanghai").strip(),
            allowed_check_status=_csv(
                "REPAIR_SYNC_ALLOWED_CHECK_STATUS", "manual_passed,passed,approved"
            ),
            max_body_mb=max(1, _int("REPAIR_SYNC_MAX_BODY_MB", 10)),
            auto_activate=_bool("REPAIR_SYNC_AUTO_ACTIVATE", True),
            realtime_enabled=_bool("REPAIR_SYNC_REALTIME_ENABLED"),
            event_batch_size=max(1, _int("REPAIR_SYNC_EVENT_BATCH_SIZE", 100)),
            event_flush_interval_seconds=max(1, _int("REPAIR_SYNC_EVENT_FLUSH_INTERVAL_SECONDS", 3)),
            event_max_pending=max(1, _int("REPAIR_SYNC_EVENT_MAX_PENDING", 10000)),
            source_bindings_table=os.getenv(
                "REPAIR_SYNC_SOURCE_BINDINGS_TABLE", "machine_component_bindings"
            ).strip(),
            source_materials_table=os.getenv("REPAIR_SYNC_SOURCE_MATERIALS_TABLE", "materials").strip(),
            source_instances_table=os.getenv(
                "REPAIR_SYNC_SOURCE_INSTANCES_TABLE", "material_instances"
            ).strip(),
            source_photo_items_table=os.getenv(
                "REPAIR_SYNC_SOURCE_PHOTO_ITEMS_TABLE", "photo_item_library"
            ).strip(),
            source_photo_config_table=os.getenv(
                "REPAIR_SYNC_SOURCE_PHOTO_CONFIG_TABLE", "model_photo_config"
            ).strip(),
        )


def get_config() -> RepairSyncConfig:
    return RepairSyncConfig.from_env()
