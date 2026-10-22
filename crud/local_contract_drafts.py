import hashlib
import json
from datetime import datetime
from typing import Any
from sqlalchemy import text
from database import get_engine
from contract_bridge.renderer import render

REQUIRED = ("supplier_name", "buyer_name", "signing_place", "signed_date", "settlement_terms")

def _value(obj: dict[str, Any], *names: str) -> str:
    for name in names:
        value = obj.get(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""

def map_order_to_contract(order: dict[str, Any]) -> dict[str, str]:
    items = order.get("items") if isinstance(order.get("items"), list) else [order]
    fields = {
        "supplier_name": _value(order, "supplierName", "supplier_name"),
        "contract_no": _value(order, "contractNo", "contract_no"),
        "buyer_name": _value(order, "customerName", "customer_name", "buyerName", "buyer_name"),
        "signing_place": _value(order, "signingPlace", "signing_place"),
        "signed_date": _value(order, "signedDate", "signed_date"),
        "delivery_date": _value(order, "deliveryDate", "delivery_date", "expectedDeliveryDate"),
        "settlement_terms": _value(order, "settlementTerms", "settlement_terms"),
        "total_upper": _value(order, "totalUpper", "total_upper"),
        "buyer_address": _value(order, "deliveryAddress", "delivery_address", "buyerAddress", "buyer_address"),
        "contact_name": _value(order, "contactName", "contact_name"),
        "contact_phone": _value(order, "contactPhone", "contact_phone"),
        "special_requirements": _value(order, "specialRequirements", "special_requirements"),
        "remark": _value(order, "remark", "remarks"),
        "accessories": _value(order, "accessories"),
    }
    for index in range(1, 5):
        fields.update({f"item{index}_{suffix}": "" for suffix in ("product", "brand", "spec", "qty", "price")})
    for index, item in enumerate(items[:4], 1):
        if not isinstance(item, dict):
            continue
        fields.update({
            f"item{index}_product": _value(item, "productName", "product_name", "model"),
            f"item{index}_brand": _value(item, "brand"),
            f"item{index}_spec": _value(item, "productCode", "product_code", "spec", "model"),
            f"item{index}_qty": _value(item, "quantity", "qty"),
            f"item{index}_price": _value(item, "unitPrice", "unit_price", "price"),
        })
    return fields

def missing_required(fields: dict[str, str]) -> list[str]:
    return [key for key in REQUIRED if not str(fields.get(key, "")).strip()]

def ensure_table() -> None:
    with get_engine().begin() as conn:
        dialect = conn.dialect.name
        suffix = ", UNIQUE (source_order_no, source_hash)" if dialect == 'sqlite' else ", UNIQUE KEY uq_v8_contract_source (source_order_no, source_hash)"
        conn.execute(text(f"""CREATE TABLE IF NOT EXISTS v8_contract_drafts (
            id CHAR(36) PRIMARY KEY, source_order_no VARCHAR(100) NOT NULL,
            source_hash CHAR(64) NOT NULL, source_snapshot TEXT NOT NULL,
            fields_json TEXT NOT NULL, state VARCHAR(30) NOT NULL DEFAULT 'submitted',
            preview MEDIUMBLOB NULL, preview_hash CHAR(64) NULL, template_hash CHAR(64) NULL,
            reviewer VARCHAR(100) NULL, review_note VARCHAR(1000) NULL,
            created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL
            {suffix}
        )""" + (" ENGINE=InnoDB DEFAULT CHARSET=utf8mb4" if dialect != 'sqlite' else "")))

def create_from_order(order: dict[str, Any]) -> dict[str, Any] | None:
    ensure_table()
    order_no = _value(order, "orderNo", "order_no", "id")
    if not order_no:
        return None
    snapshot = json.dumps(order, ensure_ascii=False, sort_keys=True, default=str)
    source_hash = hashlib.sha256(snapshot.encode()).hexdigest()
    fields = map_order_to_contract(order)
    now = datetime.now()
    draft_id = __import__('uuid').uuid4()
    with get_engine().begin() as conn:
        row = conn.execute(text("SELECT id FROM v8_contract_drafts WHERE source_order_no=:no AND source_hash=:hash"), {"no": order_no, "hash": source_hash}).fetchone()
        if row:
            existing_id = str(row[0])
            existing = get(existing_id)
            return {**existing, "_created": False} if existing else None
        conn.execute(text("""INSERT INTO v8_contract_drafts
            (id, source_order_no, source_hash, source_snapshot, fields_json, state, created_at, updated_at)
            VALUES (:id,:no,:hash,:snapshot,:fields,'submitted',:now,:now)"""),
            {"id": str(draft_id), "no": order_no, "hash": source_hash, "snapshot": snapshot, "fields": json.dumps(fields, ensure_ascii=False), "now": now})
    created = get(str(draft_id))
    return {**created, "_created": True} if created else None

def get(draft_id: str) -> dict[str, Any] | None:
    ensure_table()
    with get_engine().begin() as conn:
        row = conn.execute(text("SELECT * FROM v8_contract_drafts WHERE id=:id"), {"id": draft_id}).mappings().first()
    if not row: return None
    result = dict(row)
    result.pop("preview", None)
    for key in ("fields_json", "source_snapshot"):
        result[key[:-5] if key == "fields_json" else "source_order_snapshot"] = json.loads(result.pop(key) or "{}")
    result["missing_fields"] = missing_required(result["fields"])
    return result

def list_drafts(page=1, size=100):
    ensure_table()
    with get_engine().begin() as conn:
        rows = conn.execute(text("SELECT * FROM v8_contract_drafts ORDER BY created_at DESC LIMIT :limit OFFSET :offset"), {"limit": size, "offset": (page-1)*size}).mappings().all()
    return [get(str(row["id"])) for row in rows]

def update(draft_id: str, fields: dict[str, Any]) -> dict[str, Any] | None:
    current = get(draft_id)
    if not current: return None
    if current['state'] == 'approved': raise ValueError('已审批通过的合同不能修改')
    merged = {str(k): str(v or "") for k, v in fields.items()}
    with get_engine().begin() as conn:
        conn.execute(text("UPDATE v8_contract_drafts SET fields_json=:fields, state='submitted', preview=NULL, preview_hash=NULL, updated_at=:now WHERE id=:id AND state NOT IN ('approved')"), {"fields": json.dumps(merged, ensure_ascii=False), "now": datetime.now(), "id": draft_id})
    return get(draft_id)

def prepare(draft_id: str) -> dict[str, Any]:
    row = get(draft_id)
    if not row: raise KeyError('合同草稿不存在')
    content, template_hash = render(row['fields'])
    digest = hashlib.sha256(content).hexdigest()
    with get_engine().begin() as conn:
        conn.execute(text("UPDATE v8_contract_drafts SET state='preview_ready', preview=:preview, preview_hash=:hash, template_hash=:template, updated_at=:now WHERE id=:id"), {"preview": content, "hash": digest, "template": template_hash, "now": datetime.now(), "id": draft_id})
    return get(draft_id)

def review(draft_id: str, preview_hash: str, decision: str, reviewer: str, note: str = '') -> dict[str, Any]:
    row = get(draft_id)
    if not row or row.get('preview_hash') != preview_hash: raise ValueError('预览版本已变化，请刷新')
    if decision == 'approved' and row.get('missing_fields'):
        raise ValueError('请先补齐字段：' + '、'.join(row['missing_fields']))
    if decision == 'rejected' and not note.strip(): raise ValueError('驳回时请填写原因')
    with get_engine().begin() as conn:
        conn.execute(text("UPDATE v8_contract_drafts SET state=:state, reviewer=:reviewer, review_note=:note, updated_at=:now WHERE id=:id"), {"state": decision, "reviewer": reviewer, "note": note, "now": datetime.now(), "id": draft_id})
    return get(draft_id)
