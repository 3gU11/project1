import hashlib
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta

import pandas as pd
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError

from config import BASE_DIR
from database import get_engine


def audit_log(action, details, user="System"):
    ip = "Local"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    new_row = {
        "timestamp": timestamp,
        "user": user,
        "ip": ip,
        "action": action,
        "details": details,
    }
    try:
        pd.DataFrame([new_row]).to_sql('audit_log', get_engine(), if_exists='append', index=False, method='multi')
    except (OperationalError, Exception):
        pass


def save_contract_file(uploaded_file, customer_name, contract_id, uploader_name, convert_to_docx=True):
    max_size = 50 * 1024 * 1024
    fname = getattr(uploaded_file, "name", None) or getattr(uploaded_file, "filename", None) or "upload.bin"
    ext = os.path.splitext(fname)[1].lower()
    if ext not in ['.pdf', '.doc', '.docx', '.jpg', '.jpeg']:
        return False, "不支持的文件格式 (仅限 PDF, Word, JPG)"

    safe_cust = re.sub(r'[\/*?:"<>|]', "", str(customer_name)).strip() or "Unknown"
    if contract_id:
        folder_name = re.sub(r'[\/*?:"<>|]', "", str(contract_id)).strip()
    else:
        timestamp_str = datetime.now().strftime("%Y%m%d%H%M%S")
        folder_name = f"{safe_cust}_{timestamp_str}"

    rel_dir = os.path.join("data", folder_name)
    abs_dir = os.path.join(BASE_DIR, rel_dir)
    os.makedirs(abs_dir, exist_ok=True)

    save_path = os.path.join(abs_dir, fname)
    rel_save_path = os.path.join(rel_dir, fname)
    try:
        file_hash_obj = hashlib.sha256()
        source_size = getattr(uploaded_file, "size", None)

        if hasattr(uploaded_file, "file"):
            src = uploaded_file.file
            src.seek(0)
            written = 0
            with open(save_path, "wb") as f:
                while True:
                    chunk = src.read(1024 * 1024)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > max_size:
                        try:
                            os.remove(save_path)
                        except Exception:
                            pass
                        return False, "文件超过 50MB 限制"
                    file_hash_obj.update(chunk)
                    f.write(chunk)
            if source_size is None:
                source_size = written
        elif hasattr(uploaded_file, "getvalue"):
            file_bytes = uploaded_file.getvalue()
            source_size = len(file_bytes)
            if source_size > max_size:
                return False, "文件超过 50MB 限制"
            file_hash_obj.update(file_bytes)
            with open(save_path, "wb") as f:
                f.write(file_bytes)
        else:
            return False, "上传对象不支持读取"

        if source_size is not None and source_size > max_size:
            try:
                os.remove(save_path)
            except Exception:
                pass
            return False, "文件超过 50MB 限制"
        file_hash = file_hash_obj.hexdigest()
    except Exception as e:
        return False, f"保存文件失败: {e}"

    final_fname = fname
    final_rel_path = rel_save_path
    conversion_note = ""

    if ext == '.doc' and convert_to_docx:
        script_path = os.path.join(BASE_DIR, "合同", "合同", "convert_doc_to_docx.py")
        if os.path.exists(script_path):
            try:
                cmd = [sys.executable, script_path, save_path]
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    abs_docx_path = os.path.splitext(save_path)[0] + ".docx"
                    if os.path.exists(abs_docx_path):
                        final_fname = os.path.splitext(fname)[0] + ".docx"
                        final_rel_path = os.path.splitext(rel_save_path)[0] + ".docx"
                        with open(abs_docx_path, "rb") as f:
                            file_hash = hashlib.sha256(f.read()).hexdigest()
                        conversion_note = "（.doc 已自动转换为 .docx）"
                    else:
                        conversion_note = f"（转换脚本执行成功，但未找到生成的 .docx 文件）"
                else:
                    conversion_note = f"（.doc 转换失败: {result.stderr.strip()}）"
            except Exception as e:
                conversion_note = f"（执行转换脚本异常: {e}）"
        else:
            conversion_note = f"（未找到转换脚本: {script_path}）"

    new_record = {
        "contract_id": str(contract_id) if contract_id else "",
        "customer": str(customer_name),
        "file_name": final_fname,
        "file_path": final_rel_path,
        "file_hash": file_hash,
        "uploader": uploader_name,
        "upload_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    try:
        pd.DataFrame([new_record]).to_sql('contract_records', get_engine(), if_exists='append', index=False, method='multi')
        audit_log("Upload Contract", f"Uploaded {final_fname} for {customer_name} (ID: {contract_id})", user=uploader_name)
        return True, f"上传成功{conversion_note}"
    except (IntegrityError, OperationalError, Exception) as e:
        return False, f"记录保存失败: {e}"


def delete_contract_file(contract_id, file_name, operator="System"):
    try:
        with get_engine().connect() as conn:
            result = conn.execute(
                text("SELECT file_path FROM contract_records WHERE contract_id=:cid AND file_name=:fn"),
                {"cid": str(contract_id), "fn": str(file_name)}
            )
            row = result.fetchone()

        if not row:
            return False, "文件记录未找到"

        rel_path = row[0]
        abs_path = os.path.join(BASE_DIR, rel_path)
        if os.path.exists(abs_path):
            try:
                os.remove(abs_path)
            except Exception as e:
                return False, f"物理文件删除失败: {e}"

        with get_engine().begin() as conn:
            conn.execute(
                text("DELETE FROM contract_records WHERE contract_id=:cid AND file_name=:fn"),
                {"cid": str(contract_id), "fn": str(file_name)}
            )

        audit_log("Delete Contract File", f"Deleted {file_name} from {contract_id}", user=operator)
        return True, "文件已删除"
    except (IntegrityError, OperationalError, Exception) as e:
        return False, f"删除操作出错: {e}"


def clean_expired_contracts():
    retention_days = 365 * 3
    cutoff_date = datetime.now() - timedelta(days=retention_days)
    cutoff_str = cutoff_date.strftime("%Y-%m-%d %H:%M:%S")

    try:
        with get_engine().connect() as conn:
            df = pd.read_sql(text("SELECT file_path FROM contract_records WHERE upload_time < :cut"), conn, params={"cut": cutoff_str})
        if df.empty:
            return 0

        count = 0
        for _, row in df.iterrows():
            f_path = row['file_path']
            abs_path = os.path.join(BASE_DIR, f_path)
            if os.path.exists(abs_path):
                try:
                    os.remove(abs_path)
                    count += 1
                except Exception:
                    pass

        with get_engine().begin() as conn:
            conn.execute(text("DELETE FROM contract_records WHERE upload_time < :cut"), {"cut": cutoff_str})

        if count > 0:
            audit_log("System Cleanup", f"Deleted {count} expired files older than {retention_days} days")
        return count
    except (OperationalError, Exception) as e:
        print(f"Cleanup error: {e}")
        return 0
