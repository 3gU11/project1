import hashlib
import json
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from sqlalchemy import bindparam, text
from database import get_engine
from contract_bridge.renderer import render_order_form

# 「瑞钧科技办事处订货单」必填项：这四项都能从订单直接推导，缺了说明订单数据本身有问题
REQUIRED = ("supplier_name", "dealer_name", "signed_date", "buyer_name")
DEFAULT_SUPPLIER = "苏州瑞钧智能科技有限公司"
DEFAULT_PRODUCT = "瑞钧中走丝线切割"
DEFAULT_TAX = "含税"      # 税票默认含税：云端没单独采集时也按含税出单
ITEM_FIELDS = ("product", "spec", "qty", "tax")
BASE_ITEM_ROWS = 4      # 模板自带 4 行明细，少了留空、多了渲染时自动加行
MAX_ITEM_ROWS = 30      # 防止异常数据把表格撑爆

# 订货单栏位 → 云端订单里可能出现的键名，按纸质表单从上到下、分区块排列。
# 小程序/云端表单是中文的，接口也可能直接传驼峰或下划线字段，所以三种写法一并认；
# 新增云端字段时只在这个表里补别名即可，映射、渲染、旧草稿升级都不用改。
FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    # —— 订单头 ——
    "supplier_name": ("supplierName", "supplier_name", "供方", "供方名称", "供应商"),
    "dealer_name": ("dealerName", "dealer_name", "agentName", "agent_name", "经销商", "需方", "代理商"),
    "office_name": ("officeName", "office_name", "belongOffice", "belong_office",
                    "regionalOffice", "regional_office", "salesOffice", "sales_office",
                    "所属办事处", "region"),
    "signed_date": ("signedDate", "signed_date", "submitTime", "submit_time",
                    "createdAt", "created_at", "签订时间", "下单时间", "提交时间"),
    # —— 备注与交货条款 ——
    "remark": ("remark", "remarks", "备注"),
    # 云端表单上叫「期望交期」，落地字段是 expectedDeliveryDate / deliveryDate
    "delivery_date": ("expectedDeliveryDate", "expected_delivery_date", "expectDeliveryDate",
                      "expect_delivery_date", "deliveryDate", "delivery_date",
                      "交货时间", "期望交期", "交期", "要求交期"),
    # 云端表单上叫「结算方式及期限」
    "settlement_terms": ("settlementTerms", "settlement_terms", "settlement", "settlementMethod",
                         "settlement_method", "paymentTerms", "payment_terms", "paymentMethod",
                         "payMethod", "结算方式", "结算方式及期限", "付款方式"),
    # —— 购货方信息（对应云端订单的「客户信息/地址」区块）——
    "buyer_name": ("customerName", "customer_name", "buyerName", "buyer_name",
                   "购货单位", "客户名称", "客户"),
    # 云端把「客户信息/地址」拆成「客户 + 地址」两栏后，地址取 customerAddress
    "buyer_address": ("customerAddress", "customer_address", "buyerAddress", "buyer_address",
                      "deliveryAddress", "delivery_address", "address", "客户地址", "地址",
                      "收货地址", "交货地址"),
    "contact_name": ("contactName", "contact_name", "联系人"),
    "contact_phone": ("contactPhone", "contact_phone", "phone", "联系电话", "联系方式"),
    # —— 办事处信息（非必填：云端没采集就留空，审批人可在编辑字段里补）——
    "office_branch": ("officeBranch", "office_branch", "serviceOffice", "service_office",
                      "deliveryOffice", "delivery_office", "办事处"),
    "office_contact": ("officeContact", "office_contact", "办事处联系人"),
    "office_phone": ("officePhone", "office_phone", "办事处电话", "办事处联系方式"),
    # —— 其他特殊要求 ——
    "special_requirements": ("specialRequirements", "special_requirements",
                             "extraRemark", "extra_remark", "其他特殊要求", "特殊要求"),
}

ITEM_ALIASES: dict[str, tuple[str, ...]] = {
    "product": ("productName", "product_name", "产品名称", "产品"),
    "spec": ("productCode", "product_code", "spec", "model", "规格型号", "机型"),
    "qty": ("quantity", "qty", "数量"),
    "tax": ("taxIncluded", "tax_included", "tax", "invoiceType", "taxType", "税票", "含税"),
}

# 字段在订货单里的出现顺序（与模板从上到下一致，前端「编辑字段」按这个顺序展示）。
# 明细行 item*_* 插在订单头之后，由 ITEM_FIELDS 展开。
HEAD_FIELDS = ("supplier_name", "dealer_name", "office_name", "signed_date")
TERMS_FIELDS = ("remark", "delivery_date", "settlement_terms")
BUYER_FIELDS = ("buyer_name", "buyer_address", "contact_name", "contact_phone")
OFFICE_FIELDS = ("office_branch", "office_contact", "office_phone")
EXTRA_FIELDS = ("special_requirements",)

# 只出现在「订货合同」旧字段集里的键，用来识别换模板之前生成的草稿
LEGACY_FIELD_KEYS = frozenset({
    "contract_no", "signing_place", "total_upper", "accessories",
    "item1_price", "item1_brand",
})

# 云端把数量传成 Decimal 时会变成 "5.000"，只去掉纯整数的小数尾零
_INTEGER_DECIMAL = re.compile(r'^(-?\d+)\.0+$')
# 签订时间可能是 "2026-10-24" 或 "2026-10-24 14:22:34"，纸质单上统一写成中文日期
_ISO_DATE = re.compile(r'^(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T].*)?$')
# 加高机型：云端在 inventory_type 上标 heightened，也可能直接拼在机型后面
_HEIGHTENED_TYPES = frozenset({"heightened", "heighten", "high", "tall"})
_HEIGHTENED_MARK = re.compile(r'[\(（]\s*加高\s*[\)）]|加高')


def _clean_text(value: Any) -> str:
    """统一取值格式：去空白，纯整数的 Decimal 去掉小数尾零（5.000 → 5）。"""
    text_value = str(value).strip()
    integer = _INTEGER_DECIMAL.match(text_value)
    return integer.group(1) if integer else text_value


def _format_signed_date(value: str) -> str:
    """签订时间按纸质单惯例写成「2026 年 10 月 24 日」。

    已经是中文或自由文本（如「2026 年 10 月 23 日」）的值原样保留，只规整 ISO 日期。
    """
    match = _ISO_DATE.match(value or "")
    if not match:
        return value
    year, month, day = (int(part) for part in match.groups())
    return f"{year} 年 {month} 月 {day} 日"


def _lookup(obj: dict[str, Any], aliases: tuple[str, ...]) -> str:
    for name in aliases:
        if name in obj:
            value = obj.get(name)
            if value is not None and str(value).strip():
                return _clean_text(value)
    return ""


def _value(obj: dict[str, Any], *names: str) -> str:
    return _lookup(obj, tuple(names))


def _item_is_heightened(item: dict[str, Any]) -> bool:
    """判断一条明细是不是加高机型。

    云端订单用 inventory_type = heightened 标记加高（与本地 dealer_orders.inventory_type 同口径），
    有的渠道会把「(加高)」「（加高）」直接拼在机型后面，两种都认。
    只看明细自己的字段，不看订单备注：云端会把订单备注复制到每一行，用它判断会把整单误标成加高。
    """
    if _lookup(item, ("inventoryType", "inventory_type")).lower() in _HEIGHTENED_TYPES:
        return True
    return "加高" in _lookup(item, ITEM_ALIASES["spec"])


def _display_spec(spec: str, heightened: bool) -> str:
    """加高机型统一在规格型号后标「（加高）」，与同型号普通机区分。"""
    if not heightened:
        return spec
    base = _HEIGHTENED_MARK.sub(" ", spec).strip()
    return f"{base}（加高）" if base else ""


def _sum_quantity(left: str, right: str) -> str:
    """合并明细行时数量相加。

    任一侧为空或不是数字时保留原值（都为空就仍然是空），不把缺失的数量当 0 参与计算。
    """
    if not left or not right:
        return left or right
    try:
        total = Decimal(left) + Decimal(right)
    except (InvalidOperation, TypeError, ValueError):
        return left or right
    return _clean_text(format(total.normalize(), "f"))


def _merge_item_rows(items: list[dict[str, Any]]) -> list[dict[str, str]]:
    """把同型号明细合并成一行、数量相加，并标出加高机型。

    云端订单明细是按批次行下发的：同一型号可能拆成多行、每行 1 台，但订货单是合同附件，
    同一型号应当合成一行按数量叠加；加高机与普通机必须分开，所以合并键是「规格型号 + 是否加高」。
    没有规格型号的行不参与合并，原样保留，避免把不同设备误并成一行。
    """
    merged: list[dict[str, str]] = []
    positions: dict[tuple[str, bool], int] = {}
    for item in items:
        heightened = _item_is_heightened(item)
        spec = _display_spec(_lookup(item, ITEM_ALIASES["spec"]), heightened)
        row = {
            "product": _lookup(item, ITEM_ALIASES["product"]),
            "spec": spec,
            "qty": _lookup(item, ITEM_ALIASES["qty"]),
            "tax": _lookup(item, ITEM_ALIASES["tax"]),
        }
        key = (spec, heightened)
        if spec and key in positions:
            existing = merged[positions[key]]
            existing["qty"] = _sum_quantity(existing["qty"], row["qty"])
            existing["product"] = existing["product"] or row["product"]
            existing["tax"] = existing["tax"] or row["tax"]
            continue
        if spec:
            positions[key] = len(merged)
        merged.append(row)
    return merged


_ITEM_KEY = re.compile(r'item\d+_[A-Za-z]+')


def _stored_item_rows(fields: dict[str, Any]) -> list[tuple[str, ...]]:
    """按明细行号取出非空行（product/spec/qty/tax 四元组）。"""
    rows: list[tuple[str, ...]] = []
    for index in range(1, MAX_ITEM_ROWS + 1):
        values = tuple(str(fields.get(f"item{index}_{suffix}") or "").strip() for suffix in ITEM_FIELDS)
        if any(values):
            rows.append(values)
    return rows


def _spec_quantity_totals(rows: list[tuple[str, ...]]) -> dict[str, Decimal]:
    """按「基础型号」汇总数量，用来判断旧草稿的明细数量有没有被人工改过。"""
    totals: dict[str, Decimal] = {}
    for product, spec, qty, _tax in rows:
        key = _HEIGHTENED_MARK.sub("", spec).strip() or product
        try:
            amount = Decimal(qty)
        except (InvalidOperation, TypeError, ValueError):
            amount = Decimal(0)
        totals[key] = totals.get(key, Decimal(0)) + amount
    return totals


def _canonical_fields(fields: dict[str, Any]) -> dict[str, Any]:
    """按订货单栏位顺序重排字段；旧字段集里多出来的键原样跟在后面。"""
    ordered: dict[str, Any] = {}
    for name in HEAD_FIELDS:
        ordered[name] = fields.get(name, "")
    for index in range(1, MAX_ITEM_ROWS + 1):
        keys = [f"item{index}_{suffix}" for suffix in ITEM_FIELDS]
        if not any(key in fields for key in keys):
            break
        for key in keys:
            ordered[key] = fields.get(key, "")
    for name in TERMS_FIELDS + BUYER_FIELDS + OFFICE_FIELDS + EXTRA_FIELDS:
        ordered[name] = fields.get(name, "")
    for key, value in fields.items():
        if key not in ordered:
            ordered[key] = value
    return ordered


def map_order_to_contract(order: dict[str, Any]) -> dict[str, str]:
    """把云端经销商订单映射成「订货单」字段。

    表单是纯表格：值单元格一个字段，标签是固定文字，所以这里只产出值，不拼标签。
    值一律按订货单栏位顺序输出（订单头 → 明细行 → 备注条款 → 购货方信息 → 办事处信息 →
    其他特殊要求），前端「编辑字段」按这个顺序展示。
    明细按「规格型号 + 是否加高」合并同型号的批次行，数量相加；加高机型在规格型号后标「（加高）」。
    两个默认值：供方固定为苏州瑞钧；税票按业务惯例默认「含税」。
    办事处信息是非必填项，云端没采集时留空，不阻断审批；其余字段缺值也留空，
    由审批人补齐，不编造商业条款。
    """
    raw_items = order.get("items") if isinstance(order.get("items"), list) else [order]
    items = _merge_item_rows([item for item in raw_items if isinstance(item, dict)] or [order])
    fields: dict[str, str] = {}
    for name in HEAD_FIELDS:
        fields[name] = _lookup(order, FIELD_ALIASES[name])
    fields["supplier_name"] = fields["supplier_name"] or DEFAULT_SUPPLIER
    fields["signed_date"] = _format_signed_date(fields["signed_date"])
    item_rows = min(max(len(items), BASE_ITEM_ROWS), MAX_ITEM_ROWS)
    for index in range(1, item_rows + 1):
        fields.update({f"item{index}_{suffix}": "" for suffix in ITEM_FIELDS})
    for index, item in enumerate(items[:MAX_ITEM_ROWS], 1):
        fields.update({
            # 产品名称优先用订单传的；没传但这一行有机型时补默认名，没机型就留空
            f"item{index}_product": item["product"] or (DEFAULT_PRODUCT if item["spec"] else ""),
            f"item{index}_spec": item["spec"],
            f"item{index}_qty": item["qty"],
            # 税票默认含税；云端传了「不含税」等值才覆盖
            f"item{index}_tax": item["tax"] or DEFAULT_TAX,
        })
    for name in TERMS_FIELDS + BUYER_FIELDS + OFFICE_FIELDS + EXTRA_FIELDS:
        fields[name] = _lookup(order, FIELD_ALIASES[name])
    if not fields["office_contact"]:
        # 办事处信息非必填：订单没有单独的办事处联系人时，用所属大区经理兜底
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


def _normalize_stored_fields(fields: dict[str, Any],
                             snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
    """把存量草稿的字段规整成当前映射的取值约定。

    - 税票默认含税、签订时间转中文日期：这两项只存在于映射逻辑里，云端订单快照不会因此
      变化、也就不会生成新版本草稿；不补的话，改动之前生成、还在待审的草稿会一直空着。
    - 明细合并：旧草稿按云端批次行逐行存（同型号拆成多行、每行 1 台），数量口径没被人工
      改过时按当前「型号 + 加高」合并规则重排，加高机型顺带补上「（加高）」标记；
      一旦人工改过数量/型号（按型号汇总的数量对不上快照）就保持原样，不覆盖审批人的修改。
    - 最后按订货单栏位顺序重排，前端「编辑字段」直接按这个顺序展示。
    """
    signed_date = str(fields.get("signed_date") or "").strip()
    if signed_date:
        fields["signed_date"] = _format_signed_date(signed_date)
    for index in range(1, MAX_ITEM_ROWS + 1):
        has_content = (str(fields.get(f"item{index}_product") or "").strip()
                       or str(fields.get(f"item{index}_spec") or "").strip())
        if has_content and not str(fields.get(f"item{index}_tax") or "").strip():
            fields[f"item{index}_tax"] = DEFAULT_TAX
    if isinstance(snapshot, dict) and snapshot:
        stored_rows = _stored_item_rows(fields)
        derived = map_order_to_contract(snapshot)
        derived_rows = _stored_item_rows(derived)
        if (stored_rows and len(derived_rows) < len(stored_rows)
                and _spec_quantity_totals(stored_rows) == _spec_quantity_totals(derived_rows)):
            # 数量口径和快照一致，说明审批人没改过明细，可以按新规则合并
            for key in [name for name in fields if _ITEM_KEY.fullmatch(name)]:
                fields.pop(key)
            for key, value in derived.items():
                if _ITEM_KEY.fullmatch(key):
                    fields[key] = value
    return _canonical_fields(fields)


def get(draft_id: str) -> dict[str, Any] | None:
    ensure_table()
    with get_engine().begin() as conn:
        row = conn.execute(text("SELECT * FROM v8_contract_drafts WHERE id=:id"), {"id": draft_id}).mappings().first()
    if not row: return None
    result = dict(row)
    result.pop("preview", None)
    for key in ("fields_json", "source_snapshot"):
        result[key[:-5] if key == "fields_json" else "source_order_snapshot"] = json.loads(result.pop(key) or "{}")
    snapshot = result.get("source_order_snapshot") or {}
    stored_fields = result["fields"]
    if result.get("state") == 'approved':
        # 已归档合同是历史结果：字段按归档时的口径展示，不按新规则重排，避免字段与附件内容对不上
        result["fields"] = _upgrade_legacy_fields(stored_fields, snapshot)
    else:
        fields = _normalize_stored_fields(
            dict(_upgrade_legacy_fields(stored_fields, snapshot)), snapshot
        )
        if fields != stored_fields and result.get("state") == 'preview_ready':
            # 映射规则升级后（税票默认值/加高标记/明细合并）旧预览已经过期：回到「待生成预览」，
            # 下次打开会按新字段重新渲染，避免审批人对着旧版附件审批归档。
            result["state"] = 'submitted'
            result["preview_hash"] = None
        result["fields"] = fields
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
        # 字段可能是按当前映射规整过的（税票默认值/加高标记/明细合并），顺手落库，
        # 免得每次读取都判定为过期、反复把预览打回「待生成」。
        conn.execute(text("UPDATE v8_contract_drafts SET fields_json=:fields, state='preview_ready', preview=:preview, preview_hash=:hash, template_hash=:template, updated_at=:now WHERE id=:id"), {"fields": json.dumps(row['fields'], ensure_ascii=False), "preview": content, "hash": digest, "template": template_hash, "now": datetime.now(), "id": draft_id})
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


def latest_document(order_no: str) -> tuple[bytes, str] | None:
    """返回经销商订单最新一版可归档的订货单（docx 字节, 建议文件名）。

    转合同时用它把"系统生成的订货单"一起挂到合同附件里，避免合同只剩人工上传的文件。
    优先复用已生成并可能已审批的预览；没有预览时按当前字段重新渲染（旧草稿字段已在 get() 里升级）。
    找不到任何草稿时返回 None，由调用方决定是否跳过。
    """
    cleaned_order_no = str(order_no or '').strip()
    if not cleaned_order_no:
        return None
    ensure_table()
    with get_engine().begin() as conn:
        row = conn.execute(
            text(
                "SELECT id FROM v8_contract_drafts WHERE TRIM(source_order_no)=:order_no "
                "ORDER BY CASE state WHEN 'approved' THEN 0 WHEN 'preview_ready' THEN 1 ELSE 2 END, "
                "created_at DESC LIMIT 1"
            ),
            {"order_no": cleaned_order_no},
        ).mappings().first()
        if not row:
            return None
        preview = conn.execute(
            text("SELECT preview FROM v8_contract_drafts WHERE id=:id"),
            {"id": str(row["id"])},
        ).scalar()
    if preview:
        content = bytes(preview)
    else:
        draft = get(str(row["id"]))
        if not draft:
            return None
        content, _ = render_order_form(draft['fields'])
    return content, f"{cleaned_order_no}-订货单.docx"
