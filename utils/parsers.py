import json
from datetime import datetime

import pandas as pd
from crud.inventory import (
    append_import_staging,
    get_data,
    get_import_staging,
    save_data,
    save_import_staging,
)


def _to_int_qty(value):
    try:
        return int(float(value))
    except Exception:
        return 0


def parse_alloc_dict(value):
    if isinstance(value, dict):
        return {str(k): _to_int_qty(v) for k, v in value.items() if _to_int_qty(v) > 0}
    if value is None:
        return {}
    raw = str(value).strip()
    if not raw:
        return {}
    payload = raw
    if ":" in raw and not raw.startswith("{"):
        payload = raw.split(":", 1)[1].strip()
    for candidate in (payload, payload.replace("'", '"')):
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return {str(k): _to_int_qty(v) for k, v in parsed.items() if _to_int_qty(v) > 0}
        except Exception:
            continue
    return {}


def parse_plan_map(value):
    if isinstance(value, dict):
        normalized = {}
        for k, v in value.items():
            alloc = parse_alloc_dict(v)
            if alloc:
                normalized[str(k)] = alloc
        return normalized
    if value is None:
        return {}
    raw = str(value).strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            normalized = {}
            for k, v in parsed.items():
                alloc = parse_alloc_dict(v)
                if alloc:
                    normalized[str(k)] = alloc
            return normalized
    except Exception:
        pass
    merged = {}
    for part in raw.split(";"):
        if ":" not in part:
            continue
        model, content = part.split(":", 1)
        model = model.strip()
        alloc = parse_alloc_dict(content.strip())
        if not model or not alloc:
            continue
        if model not in merged:
            merged[model] = {}
        for batch, qty in alloc.items():
            merged[model][batch] = merged[model].get(batch, 0) + _to_int_qty(qty)
    return merged


def to_json_text(data):
    if data is None:
        return "{}"
    try:
        return json.dumps(data, ensure_ascii=False)
    except Exception:
        return "{}"

def parse_requirements(model_str, total_qty_str):
    reqs = {}
    m_str = str(model_str)
    if ":" in m_str: 
        try:
            items = m_str.split(";")
            for item in items:
                if ":" in item:
                    k, v = item.split(":")
                    reqs[k.strip()] = int(v)
        except: 
            reqs = {m_str: int(float(total_qty_str)) if total_qty_str else 0}
    else:
        try: q = int(float(total_qty_str))
        except: q = 0
        reqs[m_str] = q
    return reqs

def process_paste_data(raw_text):
    if not raw_text.strip(): return -1, "内容为空"
    try:
        cleaned_text = raw_text.replace("，", ",")
        lines = cleaned_text.strip().split('\n')
        new_records = []
        for line in lines:
            parts = line.replace('\t', ',').split(',')
            parts = [p.strip() for p in parts if p.strip()]
            if len(parts) >= 3:
                b_id = parts[0] if parts[0] not in ['nan', '', 'NaN'] else "无批次"
                record = { "批次号": b_id, "机型": parts[1], "流水号": parts[2] }
                if len(parts) >= 4: record["状态"] = parts[3]
                if len(parts) >= 5: record["预计入库时间"] = parts[4]
                new_records.append(record)
        
        if not new_records: return -1, "未解析出有效数据"
        df_new = pd.DataFrame(new_records)
        if '状态' not in df_new.columns: df_new['状态'] = '待入库'
        
        save_cols = ["批次号", "机型", "流水号", "状态"]
        if "预计入库时间" in df_new.columns: save_cols.append("预计入库时间")
        
        append_import_staging(df_new[save_cols])
        return 1, f"已解析并添加 {len(new_records)} 条数据到计划表"
    except Exception as e: return -1, f"解析错误: {str(e)}"

def execute_import_transaction_payload(payload, retry_times=1):
    result = {"success": [], "failed": []}
    if not payload:
        return result

    plan_df = get_import_staging().copy()
    if plan_df.empty:
        result["failed"] = [{"trackNo": str(item.get("trackNo", "")), "reason": "待入库清单为空"} for item in payload]
        return result

    plan_df["流水号"] = plan_df["流水号"].astype(str).str.strip()
    staged_map = {row["流水号"]: row for _, row in plan_df.iterrows()}
    payload_map = {}
    for item in payload:
        track_no = str(item.get("trackNo", "")).strip()
        expect_date = str(item.get("expectInDate", "")).strip()
        if not track_no or not expect_date:
            result["failed"].append({"trackNo": track_no, "reason": "参数无效"})
            continue
        payload_map[track_no] = expect_date
        if track_no in staged_map:
            plan_df.loc[plan_df["流水号"] == track_no, "预计入库时间"] = expect_date

    db_df = get_data().copy()
    existing_sns = set(db_df["流水号"].astype(str).str.strip().tolist()) if not db_df.empty else set()
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
    rows_to_add = []
    add_track_nos = []
    for track_no, expect_date in payload_map.items():
        if track_no not in staged_map:
            result["failed"].append({"trackNo": track_no, "reason": "待入库清单不存在该流水号"})
            continue
        if track_no in existing_sns:
            result["failed"].append({"trackNo": track_no, "reason": "流水号已在库存中"})
            continue
        row = staged_map[track_no]
        rows_to_add.append({
            "批次号": row.get("批次号", ""),
            "机型": row.get("机型", ""),
            "流水号": track_no,
            "状态": "待入库",
            "预计入库时间": expect_date,
            "更新时间": current_time,
            "占用订单号": "",
            "客户": row.get("客户", ""),
            "代理商": row.get("代理商", ""),
            "订单备注": "",
            "机台备注/配置": row.get("合同备注", ""),
            "Location_Code": "",
            "合同号": row.get("合同号", ""),
        })
        add_track_nos.append(track_no)

    if rows_to_add:
        df_add = pd.DataFrame(rows_to_add)
        merged_df = pd.concat([db_df, df_add], ignore_index=True)
        merged_df = merged_df.drop_duplicates(subset=['流水号'], keep='first')
        last_error = None
        for _ in range(retry_times + 1):
            try:
                save_data(merged_df)
                last_error = None
                break
            except Exception as e:
                last_error = str(e)
        if last_error is not None:
            for track_no in add_track_nos:
                result["failed"].append({"trackNo": track_no, "reason": f"写入库存失败: {last_error}"})
        else:
            result["success"] = [{"trackNo": track_no} for track_no in add_track_nos]

    success_sns = {item["trackNo"] for item in result["success"]}
    remaining_plan_df = plan_df[~plan_df["流水号"].isin(success_sns)].copy()
    save_import_staging(remaining_plan_df)
    return result

def should_reset_page_selection(prev_page, current_page):
    return prev_page != current_page
