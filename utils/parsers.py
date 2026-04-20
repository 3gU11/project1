import os
import json
import subprocess
import tempfile
from datetime import datetime

import pandas as pd
from config import MACHINE_ARCHIVE_ABS_DIR, OPENPYXL_AVAILABLE, openpyxl
from crud.inventory import (
    append_import_staging,
    append_import_staging_transactional,
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

def generate_auto_inbound(batch_input, model_input, qty_input, expected_inbound_date, machine_note=""):
    if qty_input <= 0: return -1, "数量必须大于0"
    if not batch_input or not model_input: return -1, "批次号和机型不能为空"
    
    if len(machine_note) > 500: return -1, "机台备注/配置内容过长（最大500字符）"
    machine_note = machine_note.replace("<script>", "").replace("</script>", "")

    month_part = ""
    if "-" in batch_input: month_part = batch_input.split("-")[0]
    else: month_part = batch_input 
    
    target_prefix = f"96-{month_part}-"
    existing_sns = set()
    db_df = get_data()
    if not db_df.empty: existing_sns.update(db_df['流水号'].dropna().tolist())
    
    # Check staging as well
    staging_df = get_import_staging()
    if '流水号' in staging_df.columns:
        existing_sns.update(staging_df['流水号'].dropna().tolist())

    max_seq = 0
    for sn in existing_sns:
        sn = str(sn).strip()
        if sn.startswith(target_prefix):
            try:
                suffix = sn.replace(target_prefix, "")
                seq = int(suffix)
                if seq > max_seq: max_seq = seq
            except: continue
    
    new_records = []
    start_seq = max_seq + 1
    if hasattr(expected_inbound_date, "strftime"):
        expected_inbound_text = expected_inbound_date.strftime("%Y-%m-%d")
    else:
        expected_inbound_text = str(expected_inbound_date) if expected_inbound_date else ""
    
    for i in range(qty_input):
        current_seq = start_seq + i
        new_sn = f"{target_prefix}{current_seq:02d}"
        new_records.append({
            "批次号": batch_input, "机型": model_input, "流水号": new_sn,
            "状态": "待入库", "预计入库时间": expected_inbound_text,
            "机台备注/配置": machine_note
        })
        
        # --- Auto Create Archive Folder ---
        sn_folder = os.path.join(MACHINE_ARCHIVE_ABS_DIR, new_sn)
        if not os.path.exists(sn_folder):
            try: os.makedirs(sn_folder, exist_ok=True)
            except: pass
        
    if new_records:
        df_new = pd.DataFrame(new_records)
        result = append_import_staging_transactional(df_new)
        if not result.get("ok"):
            return -2, f"{result.get('error_code', 'E_IMPORT_TXN_ROLLBACK')}: {result.get('message', '写入失败')}"
        return 1, f"已生成 {result.get('inserted', qty_input)} 条数据 ({new_records[0]['流水号']} ~ {new_records[-1]['流水号']})"
    else: return 0, "生成失败"

def parse_tracking_xls(uploaded_file) -> tuple[int, str, "pd.DataFrame"]: 
    """ 
    解析瑞钧跟踪单 .xls / .xlsx 文件。 
    返回 (code, message, df) 
      code=1  成功 
      code=-1 失败，df 为空 

    提取列： 
      col0 生产批次（前向填充） 
      col1 机型 
      col2 生产编号（流水号） 
      col3 发货日期 → 写入「机台备注/配置」 
    """ 
    if not OPENPYXL_AVAILABLE:
        return -1, "服务器未安装 openpyxl，无法解析 Excel 文件。", pd.DataFrame()

    suffix = os.path.splitext(uploaded_file.name)[-1].lower() 
    raw_bytes = uploaded_file.read() 

    # ── 统一转为 xlsx ────────────────────────────────────────────────────── 
    if suffix == ".xlsx": 
        tmp_xlsx = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) 
        tmp_xlsx.write(raw_bytes); tmp_xlsx.flush(); tmp_xlsx.close() 
        xlsx_path = tmp_xlsx.name 
    elif suffix == ".xls": 
        tmp_xls = tempfile.NamedTemporaryFile(suffix=".xls", delete=False) 
        tmp_xls.write(raw_bytes); tmp_xls.flush(); tmp_xls.close() 
        out_dir = tempfile.mkdtemp() 
        try: 
            # Check for LibreOffice (soffice) or libreoffice
            result = subprocess.run( 
                ["libreoffice", "--headless", "--convert-to", "xlsx", 
                 tmp_xls.name, "--outdir", out_dir], 
                capture_output=True, timeout=30 
            ) 
            if result.returncode != 0: 
                return -1, f"LibreOffice 转换失败: {result.stderr.decode()}", pd.DataFrame() 
        except FileNotFoundError: 
            return -1, "服务器未安装 LibreOffice，无法转换 .xls 文件。\n请将跟踪单另存为 .xlsx 后重新上传。", pd.DataFrame() 
        finally: 
            try: os.unlink(tmp_xls.name)
            except: pass
        converted = [f for f in os.listdir(out_dir) if f.endswith(".xlsx")] 
        if not converted: 
            return -1, "转换后未找到 xlsx 文件", pd.DataFrame() 
        xlsx_path = os.path.join(out_dir, converted[0]) 
    else: 
        return -1, f"不支持的文件格式: {suffix}，请上传 .xls 或 .xlsx", pd.DataFrame() 

    # ── 解析 xlsx ───────────────────────────────────────────────────────── 
    try: 
        wb = openpyxl.load_workbook(xlsx_path, data_only=True, read_only=True) 
        ws = wb.active 
        rows = [] 
        current_batch = "" 
        for r_idx, row in enumerate(ws.iter_rows(values_only=True)): 
            if r_idx == 0:          # 跳过表头行 
                continue 
            batch_val = row[0] if len(row) > 0 else None 
            model_val = row[1] if len(row) > 1 else None 
            sn_val    = row[2] if len(row) > 2 else None 
            note_val  = row[3] if len(row) > 3 else None   # 发货日期 

            if batch_val: 
                current_batch = str(batch_val).strip() 

            if not model_val or not sn_val: 
                continue 

            model = str(model_val).strip() 
            sn    = str(sn_val).strip() 
            note  = str(note_val).strip() if note_val else "" 

            if not sn or sn in ("nan", "None"): 
                continue 

            rows.append({ 
                "批次号":     current_batch, 
                "机型":       model, 
                "流水号":     sn, 
                "机台备注/配置": note, 
            }) 
        wb.close() 
    except Exception as e: 
        return -1, f"解析文件时出错: {e}", pd.DataFrame() 
    finally: 
        try: os.unlink(xlsx_path) 
        except: pass 

    if not rows: 
        return -1, "解析后无有效数据，请检查文件格式", pd.DataFrame() 

    df = pd.DataFrame(rows) 
    return 1, f"解析成功，共 {len(df)} 条记录", df 

def diff_tracking_vs_inventory(tracking_df: "pd.DataFrame") -> "pd.DataFrame": 
    """ 
    比对跟踪单与成品库，返回流水号不在库中的新条目。 
    新条目默认状态 = '待入库'，预计入库时间为空。 
    """ 
    db_df = get_data()
    staging_df = get_import_staging()
    existing_sns = set(db_df["流水号"].astype(str).str.strip().tolist()) if not db_df.empty else set()
    if not staging_df.empty and "流水号" in staging_df.columns:
        existing_sns.update(staging_df["流水号"].astype(str).str.strip().tolist())

    mask = ~tracking_df["流水号"].astype(str).str.strip().isin(existing_sns) 
    new_df = tracking_df[mask].copy() 
    new_df["状态"] = "待入库" 
    new_df["预计入库时间"] = "" 
    # 将「型号」列名对齐为系统内字段「机型」 
    new_df = new_df.rename(columns={"型号": "机型"}) 
    new_df = new_df.reset_index(drop=True) 
    return new_df

def build_import_payload(selected_df, fallback_date=None):
    if selected_df is None or selected_df.empty:
        return [], "请至少选择 1 条数据"
    
    payload = []
    for _, row in selected_df.iterrows():
        sn = str(row.get("流水号", "")).strip()
        if sn:
            row_date = str(row.get("预计入库时间", "")).strip()
            date_str = row_date if row_date and row_date not in ("nan", "None") else ""
            if not date_str and fallback_date:
                date_str = fallback_date.strftime("%Y-%m-%d") if hasattr(fallback_date, "strftime") else str(fallback_date)
            payload.append({"trackNo": sn, "expectInDate": date_str})
    if not payload:
        return [], "所选数据缺少有效流水号"
    return payload, ""

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
            "客户": "",
            "代理商": "",
            "订单备注": "",
            "机台备注/配置": row.get("机台备注/配置", ""),
            "Location_Code": "",
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
