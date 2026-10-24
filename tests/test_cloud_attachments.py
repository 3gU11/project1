import hashlib
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

import crud.cloud_attachments as attachments


@pytest.fixture()
def local(monkeypatch, tmp_path):
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE dealer_orders(order_no TEXT, line_no INTEGER, contract_no TEXT, "
            "customer_name TEXT, updated_at TEXT)"
        ))
        conn.execute(text(
            "CREATE TABLE contract_records(id INTEGER PRIMARY KEY AUTOINCREMENT, contract_id TEXT, "
            "customer TEXT, file_name TEXT, file_path TEXT, file_hash TEXT, uploader TEXT, upload_time TEXT)"
        ))
        conn.execute(
            text("INSERT INTO dealer_orders VALUES(:order_no, 1, :contract_no, :customer, :updated_at)"),
            {"order_no": "ORDER-1", "contract_no": "HT2026-001", "customer": "测试客户",
             "updated_at": "2026-10-24 09:00:00"},
        )
    monkeypatch.setattr(attachments, "get_engine", lambda: engine)
    monkeypatch.setattr(attachments, "BASE_DIR", str(tmp_path))
    return engine, tmp_path


def _stub_cloud(monkeypatch, content: bytes, sha256: str, *, name="合同.pdf", size=None):
    calls = {"list": 0, "download": 0}

    def fake_list(order_no):
        calls["list"] += 1
        assert order_no == "ORDER-1"
        return [{
            "id": "att-1", "fileName": name, "mimeType": "application/pdf",
            "size": len(content) if size is None else size, "sha256": sha256,
        }]

    def fake_download(order_no, attachment_id):
        calls["download"] += 1
        assert attachment_id == "att-1"
        return content, {"X-Attachment-Sha256": sha256}

    monkeypatch.setattr(attachments, "fetch_cloud_attachments", fake_list)
    monkeypatch.setattr(attachments, "download_cloud_attachment", fake_download)
    return calls


def test_cloud_attachment_is_downloaded_into_contract_records_idempotently(local, monkeypatch):
    engine, root = local
    content = b"%PDF-1.7\nsigned contract"
    sha256 = hashlib.sha256(content).hexdigest()
    calls = _stub_cloud(monkeypatch, content, sha256)

    first = attachments.sync_cloud_order_attachments(
        [{"order_no": "ORDER-1", "updated_at": "2026-10-24 09:00:00"}]
    )

    assert first["synced"] == 1
    assert first["failed"] == 0
    target = root / "data" / "HT2026-001" / "合同.pdf"
    assert target.read_bytes() == content
    with engine.begin() as conn:
        record = conn.execute(text(
            "SELECT contract_id, customer, file_name, file_path, file_hash, uploader FROM contract_records"
        )).mappings().one()
        assert record["contract_id"] == "HT2026-001"
        assert record["customer"] == "测试客户"
        assert record["file_name"] == "合同.pdf"
        assert record["file_path"] == "data/HT2026-001/合同.pdf"
        assert record["file_hash"] == sha256
        assert record["uploader"] == "云端附件"
        row = conn.execute(text(
            "SELECT state, sha256 FROM cloud_order_attachment_sync WHERE attachment_id='att-1'"
        )).mappings().one()
        assert row["state"] == "synced"
        assert row["sha256"] == sha256

    # 订单未变更时不再重复调用云端列表，也不重复下载。
    second = attachments.sync_cloud_order_attachments(
        [{"order_no": "ORDER-1", "updated_at": "2026-10-24 09:00:00"}]
    )
    assert second["scanned"] == 1
    assert second["synced"] == 0
    assert calls == {"list": 1, "download": 1}


def test_attachment_hash_mismatch_keeps_failed_state_and_no_local_file(local, monkeypatch):
    engine, root = local
    content = b"%PDF-1.7\ntampered"
    _stub_cloud(monkeypatch, content, "0" * 64)

    result = attachments.sync_cloud_order_attachments(
        [{"order_no": "ORDER-1", "updated_at": "2026-10-24 09:00:00"}]
    )

    assert result["failed"] == 1
    assert result["synced"] == 0
    assert not (root / "data" / "HT2026-001" / "合同.pdf").exists()
    with engine.begin() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM contract_records")).scalar_one() == 0
        row = conn.execute(text(
            "SELECT state, last_error FROM cloud_order_attachment_sync WHERE attachment_id='att-1'"
        )).mappings().one()
        assert row["state"] == "failed"
        assert "sha256" in row["last_error"]


def test_changed_order_retries_and_reuses_existing_file(local, monkeypatch):
    engine, root = local
    content = b"%PDF-1.7\nsigned contract"
    sha256 = hashlib.sha256(content).hexdigest()
    calls = _stub_cloud(monkeypatch, content, sha256)

    attachments.sync_cloud_order_attachments(
        [{"order_no": "ORDER-1", "updated_at": "2026-10-24 09:00:00"}]
    )
    again = attachments.sync_cloud_order_attachments(
        [{"order_no": "ORDER-1", "updated_at": "2026-10-24 10:00:00"}]
    )

    assert again["skipped"] == 1
    assert calls == {"list": 2, "download": 1}
    assert (root / "data" / "HT2026-001" / "合同.pdf").read_bytes() == content


def test_order_pull_worker_wires_attachment_sync():
    source = Path(__file__).parents[1].joinpath("crud", "cloud_dealer_order_sync.py").read_text(encoding="utf-8")
    assert "from crud.cloud_attachments import sync_cloud_order_attachments" in source
    assert '"attachments": attachment_result' in source


def test_local_attachment_listing_and_lookup_expose_local_files(local, monkeypatch):
    engine, root = local
    content = b"%PDF-1.7\nsigned contract"
    sha256 = hashlib.sha256(content).hexdigest()
    _stub_cloud(monkeypatch, content, sha256)
    attachments.sync_cloud_order_attachments(
        [{"order_no": "ORDER-1", "updated_at": "2026-10-24 09:00:00"}]
    )

    rows = attachments.list_local_order_attachments("ORDER-1")
    assert len(rows) == 1
    assert rows[0]["id"] == "att-1"
    assert rows[0]["fileName"] == "合同.pdf"
    assert rows[0]["contractId"] == "HT2026-001"
    assert rows[0]["size"] == len(content)
    assert rows[0]["mimeType"] == "application/pdf"
    assert rows[0]["sha256"] == sha256
    assert rows[0]["downloadUrl"].endswith("/attachments/att-1/download")

    hit = attachments.find_local_order_attachment("ORDER-1", "att-1")
    assert hit is not None
    assert Path(hit["absolutePath"]).read_bytes() == content
    assert attachments.find_local_order_attachment("ORDER-1", "missing") is None
    assert attachments.list_local_order_attachments("OTHER-ORDER") == []

