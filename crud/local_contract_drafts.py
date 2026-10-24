import hashlib
import json
import re
from datetime import datetime
from typing import Any
from sqlalchemy import bindparam, text
from database import get_engine
from contract_bridge.renderer import render_order_form

# 「瑞钧科技办事处订货单」必填项：这四项都能从订单直接推导，缺了说明订单数据本身有问题
REQUIRED = ("supplier_name", "dealer_name", "signed_date", "buyer_name")
DEFAULT_SUPPLIER = "苏州瑞钧智能科技有限公司"
DEFAULT_PRODUCT = "瑞钧中走丝线切割"
ITEM_FIELDS = ("product", "spec", "qty", "tax")
BASE_ITEM_ROWS = 4      # 模板自带 4 行明细，少了留空、多了渲染时自动加行
MAX_ITEM_ROWS = 30      # 防止异常数据把表格撑爆

# 表单字段 → 订单里可能出现的键名。
# 小程序表单是中文的，接口也可能直接传中文字段，所以中英文、驼峰、下划线一并认，
# 不靠逐个字段试错，新增来源字段时只要往这里补一个别名即可。
FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "supplier_name": ("supplierName", "supplier_name", "供方", "供方名称", "供应商"),
    "dealer_name": ("dealerName", "dealer_name", "agentName", "agent_name", "经销商", "需方", "代理商"),
    "office_name": ("officeName", "office_name", "belongOffice", "belong_office",
                    "regionalOffice", "region", "salesOffice", "sales_office", "所属办事处"),
    "signed_date": ("signedDate", "signed_date", "submitTime", "submit_time",
                    "createdAt", "created_at", "签订时间", "下单时间", "提交时间"),
    "remark": ("remark", "remarks", "备注"),
    "delivery_date": ("deliveryDate", "delivery_date", "expectedDeliveryDate", "交货时间", "交期"),
    "settlement_terms": ("settlementTerms", "settlement_terms", "settlement", "settlementMethod",
                         "settlement_method", "paymentTerms", "payment_terms", "paymentMethod",
                         "payMethod", "结算方式", "结算方式及期限", "付款方式"),
    "buyer_name": ("customerName", "customer_name", "buyerName", "buyer_name",
                   "购货单位", "客户名称", "客户"),
    "buyer_address": ("deliveryAddress", "delivery_address", "buyerAddress", "buyer_address",
                      "address", "地址", "收货地址", "交货地址"),
    "contact_name": ("contactName", "contact_name", "联系人"),
    "contact_phone": ("contactPhone", "contact_phone", "phone", "联系电话", "联系方式"),
    "office_branch": ("officeBranch", "office_branch", "serviceOffice", "service_office", "办事处"),
    "office_contact": ("officeContact", "office_contact", "办事处联系人"),
    "office_phone": ("officePhone", "office_phone", "办事处电话", "办事处联系方式"),
    "special_requirements": ("specialRequirements", "special_requirements",
                             "extraRemark", "extra_remark", "其他特殊要求", "特殊要求"),
}

ITEM_ALIASES: dict[str, tuple[str, ...]] = {
    "product": ("productName", "product_name", "产品名称", "产品"),
    "spec": ("productCode", "product_code", "spec", "model", "规格型号", "机型"),
    "qty": ("quantity", "qty", "数量"),
    "tax": ("taxIncluded", "tax_included", "tax", "invoiceType", "taxType", "税票", "含税"),
}

# 只出现在「订货合同」旧字段集里的键，用来识别换模板之前生成的草稿
LEGACY_FIELD_KEYS = frozenset({
    "contract_no", "signing_place", "total_upper", "accessories",
    "item1_price", "item1_brand",
})

# 云端把数量传成 Decimal 时会变成 "5.000"，只去掉纯整数的小数尾零
_INTEGER_DECIMAL = re.compile(r'^(-?\d+)\.0+$')


def _clean_text(value: Any) -> str:
    """统一取值格式：去空白，纯整数的 Decimal 去掉小数尾零（5.000 → 5）。"""
    text_value = str(value).strip()
    integer = _INTEGER_DECIMAL.match(text_value)
    return integer.group(1) if integer else text_value


def _lookup(obj: dict[str, Any], aliases: tuple[str, ...]) -> str:
    for name in aliases:
        if name in obj:
            value = obj.get(name)
            if value is not None and str(value).strip():
                return _clean_text(value)
    return ""


def _value(obj: dict[str, Any], *names: str) -> str:
    return _lookup(obj, tuple(names))


def map_order_to_contract(order: dict[str, Any]) -> dict[str, str]:
    """把云端经销商订单映射成「订货单」字段。

    表单是纯表格：值单元格一个字段，标签是固定文字，所以这里只产出值，不拼标签。
    数据源缺字段时留空，由审批人在「编辑字段」里补齐，不要编造商业条款。
    """
    raw_items = order.get("items") if isinstance(order.get("items"), list) else [order]
    items = [item for item in raw_items if isinstance(item, dict)] or [order]
    # 顺序与表单从上到下一致，前端「编辑字段」按这个顺序展示
    fields = {
        "supplier_name": _lookup(order, FIELD_ALIASES["supplier_name"]) or DEFAULT_SUPPLIER,
        "dealer_name": _lookup(order, FIELD_ALIASES["dealer_name"]),
        "office_name": _lookup(order, FIELD_ALIASES["office_name"]),
        "signed_date": _lookup(order, FIELD_ALIASES["signed_date"]),
    }
    item_rows = min(max(len(items), BASE_ITEM_ROWS), MAX_ITEM_ROWS)
    for index in range(1, item_rows + 1):
        fields.update({f"item{index}_{suffix}": "" for suffix in ITEM_FIELDS})
    for index, item in enumerate(items[:MAX_ITEM_ROWS], 1):
        spec = _lookup(item, ITEM_ALIASES["spec"])
        fields.update({
            # 产品名称优先用订单传的；没传但这一行有机型时补默认名，没机型就留空
            f"item{index}_product": _lookup(item, ITEM_ALIASES["product"])
            or (DEFAULT_PRODUCT if spec else ""),
            f"item{index}_spec": spec,
            f"item{index}_qty": _lookup(item, ITEM_ALIASES["qty"]),
            # 税票（含税/不含税）订单没采集就留空，等审批人补
            f"item{index}_tax": _lookup(item, ITEM_ALIASES["tax"]),
        })
    for name in ("remark", "delivery_date", "settlement_terms", "buyer_name", "buyer_address",
                 "contact_name", "contact_phone", "office_branch", "office_contact",
                 "office_phone", "special_requirements"):
        fields[name] = _lookup(order, FIELD_ALIASES[name])
    if not fields["office_contact"]:
        # 区域经理通常就是办事处的对接人，订单没有单独的办事处联系人时用它兜底
        fields["office_contact"] = _lookup(order, ("regionalManagerName", "regional_manager_name"))
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
            reviewed_at DATETIME NULL,
            created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL
            {suffix}
        )""" + (" ENGINE=InnoDB DEFAULT CHARSET=utf8mb4" if dialect != 'sqlite' else "")))
        # 兼容旧库：CREATE TABLE IF NOT EXISTS 不会补列，这里按需 ALTER 出审批时间。
        if dialect == 'sqlite':
            columns = {str(row[1]) for row in conn.execute(text("PRAGMA table_info('v8_contract_drafts')")).fetchall()}
        else:
            columns = {str(row[0]) for row in conn.execute(text("SHOW COLUMNS FROM v8_contract_drafts")).fetchall()}
        if 'reviewed_at' not in columns:
            conn.execute(text("ALTER TABLE v8_contract_drafts ADD COLUMN reviewed_at DATETIME NULL"))

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

def _upgrade_legacy_fields(fields: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    """把换模板之前生成的草稿字段升级成订货单字段集。

    旧草稿存的是「订货合同」的键（contract_no / signing_place / item1_price…），
    新模板要的 dealer_name / office_* / item*_tax 根本不存在，直接渲染整张表单会空白。
    这里按当时的订单快照重算一遍：以新字段集为底，旧值里非空的覆盖上去，
    既补全缺失项，也不会冲掉审批人改过的内容。
    """
    if not isinstance(snapshot, dict) or not snapshot:
        return fields
    if not LEGACY_FIELD_KEYS & set(fields):
        return fields  # 已经是新字段集，不动
    upgraded = dict(map_order_to_contract(snapshot))
    for key, value in fields.items():
        if value:
            upgraded[key] = _clean_text(value)
    return upgraded


def get(draft_id: str) -> dict[str, Any] | None:
    ensure_table()
    with get_engine().begin() as conn:
        row = conn.execute(text("SELECT * FROM v8_contract_drafts WHERE id=:id"), {"id": draft_id}).mappings().first()
    if not row: return None
    result = dict(row)
    result.pop("preview", None)
    for key in ("fields_json", "source_snapshot"):
        result[key[:-5] if key == "fields_json" else "source_order_snapshot"] = json.loads(result.pop(key) or "{}")
    result["fields"] = _upgrade_legacy_fields(result["fields"], result.get("source_order_snapshot") or {})
    result["missing_fields"] = missing_required(result["fields"])
    return result

def list_drafts(page=1, size=100, order_no: str = ''):
    """列出合同草稿。

    order_no 不为空时只返回该经销商订单的草稿：合同附件审批已经并入订单行，
    审批人只能看到当前这张订单的合同，不再跨订单浏览。
    """
    ensure_table()
    order_no = str(order_no or '').strip()
    with get_engine().begin() as conn:
        if order_no:
            rows = conn.execute(text(
                "SELECT * FROM v8_contract_drafts WHERE TRIM(source_order_no)=:order_no "
                "ORDER BY created_at DESC LIMIT :limit OFFSET :offset"),
                {"order_no": order_no, "limit": size, "offset": (page-1)*size}).mappings().all()
        else:
            rows = conn.execute(text("SELECT * FROM v8_contract_drafts ORDER BY created_at DESC LIMIT :limit OFFSET :offset"), {"limit": size, "offset": (page-1)*size}).mappings().all()
    return [get(str(row["id"])) for row in rows]

def update(draft_id: str, fields: dict[str, Any]) -> dict[str, Any] | None:
    current = get(draft_id)
    if not current: return None
    if current['state'] == 'approved': raise ValueError('已审批通过的合同不能修改')
    merged = {str(k): str(v or "") for k, v in fields.items()}
    with get_engine().begin() as conn:
        # 重新提交=重新走一遍审批，旧的审批人/意见/时间要清掉，避免页面显示过期结论。
        conn.execute(text("UPDATE v8_contract_drafts SET fields_json=:fields, state='submitted', preview=NULL, preview_hash=NULL, reviewer=NULL, review_note=NULL, reviewed_at=NULL, updated_at=:now WHERE id=:id AND state NOT IN ('approved')"), {"fields": json.dumps(merged, ensure_ascii=False), "now": datetime.now(), "id": draft_id})
    return get(draft_id)

def prepare(draft_id: str) -> dict[str, Any]:
    row = get(draft_id)
    if not row: raise KeyError('合同草稿不存在')
    content, template_hash = render_order_form(row['fields'])
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
        conn.execute(text("UPDATE v8_contract_drafts SET state=:state, reviewer=:reviewer, review_note=:note, reviewed_at=:now, updated_at=:now WHERE id=:id"), {"state": decision, "reviewer": reviewer, "note": note, "now": datetime.now(), "id": draft_id})
    return get(draft_id)


def reject_for_order(order_no: str, reviewer: str, reason: str = '') -> int:
    """订单被驳回时，把它尚未归档的合同附件一并驳回。

    只处理 submitted / preview_ready 两种状态的草稿：已归档（approved）是历史审批结果，
    已驳回（rejected）无需重复处理；返回值是被联动驳回的草稿数量。
    """
    ensure_table()
    cleaned_order_no = str(order_no or '').strip()
    if not cleaned_order_no:
        return 0
    with get_engine().begin() as conn:
        result = conn.execute(
            text(
                "UPDATE v8_contract_drafts SET state='rejected', reviewer=:reviewer, "
                "review_note=:note, reviewed_at=:now, updated_at=:now "
                "WHERE TRIM(source_order_no)=:order_no AND state IN ('submitted','preview_ready')"
            ),
            {"order_no": cleaned_order_no, "reviewer": reviewer, "note": reason, "now": datetime.now()},
        )
        return int(result.rowcount or 0)


def _iso(value: Any) -> str:
    if value is None:
        return ''
    return value.isoformat(sep=' ') if hasattr(value, 'isoformat') else str(value)


def list_latest_states(order_nos: list[str]) -> dict[str, dict[str, Any]]:
    """批量取每个经销商订单最新一版合同草稿的状态与审批留痕。

    审核列表用它展示「合同附件」列；只返回汇总信息，不带预览二进制和字段内容。
    """
    cleaned = [str(no or '').strip() for no in order_nos]
    cleaned = [no for no in cleaned if no]
    if not cleaned:
        return {}
    ensure_table()
    with get_engine().begin() as conn:
        rows = conn.execute(
            text(
                "SELECT source_order_no, state, reviewer, reviewed_at, created_at "
                "FROM v8_contract_drafts WHERE TRIM(source_order_no) IN :order_nos "
                "ORDER BY created_at DESC, updated_at DESC"
            ).bindparams(bindparam("order_nos", expanding=True)),
            {"order_nos": tuple(dict.fromkeys(cleaned))},
        ).mappings().all()
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = str(row["source_order_no"] or '').strip()
        if not key or key in latest:
            continue
        latest[key] = {
            "state": str(row["state"] or ''),
            "reviewer": str(row["reviewer"] or ''),
            "reviewed_at": _iso(row["reviewed_at"]),
        }
    return latest
