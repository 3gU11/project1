import streamlit as st
import pymysql
import pandas as pd
import datetime

# --- 数据库连接配置 ---
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "030705",
    "database": "rjfinshed",
    "charset": "utf8mb4"
}

def get_db_connection():
    return pymysql.connect(**DB_CONFIG)


def _normalize_model_family(model_type: str) -> str:
    """将原始机型名归一化为批次族代码 G/XS/AUTO/SPECIAL。"""
    v = model_type.strip().upper()
    if "XS" in v or "XS)" in v:
        return "XS"
    if "AUTO" in v:
        return "AUTO"
    if v.endswith("G") or v.startswith("FH-"):
        return "G"
    return "SPECIAL"


# --- 页面配置 ---
st.set_page_config(page_title="生产批次同步工具", page_icon="⚙️", layout="centered")

st.title("⚙️ 生产批次同步工具")
st.markdown("""
通过此工具，你可以快速将 ERP 的**成品数据**导入到**生产看板**的指定产线上。
""")

# --- 数据获取 ---
@st.cache_data(ttl=60)
def fetch_metadata():
    conn = get_db_connection()
    try:
        # 获取产线列表
        lines_df = pd.read_sql("SELECT line_id, line_name FROM production_lines ORDER BY display_order", conn)
        # 获取最近有数据的批次号
        recent_batches = pd.read_sql("SELECT `批次号` FROM finished_goods_data WHERE `批次号` IS NOT NULL AND `批次号` != '' GROUP BY `批次号` ORDER BY MAX(`更新时间`) DESC LIMIT 20", conn)
        return lines_df, recent_batches['批次号'].tolist()
    finally:
        conn.close()

try:
    lines_df, batch_options = fetch_metadata()
except Exception as e:
    st.error(f"无法连接数据库: {e}")
    st.stop()

# --- UI 交互 ---
with st.form("sync_form"):
    st.subheader("同步配置")
    
    # 批次号输入
    selected_batch = st.selectbox("1. 选择或输入批次号", options=["手动输入"] + batch_options)
    if selected_batch == "手动输入":
        batch_code = st.text_input("请输入批次号 (例如: 03-16附加)", "").strip()
    else:
        batch_code = selected_batch

    # 产线选择
    line_labels = {row['line_id']: f"{row['line_name']} ({row['line_id']})" for _, row in lines_df.iterrows()}
    target_line_id = st.selectbox("2. 选择目标产线", options=list(line_labels.keys()), format_func=lambda x: line_labels[x])

    # 确认按钮
    submit_button = st.form_submit_button("🚀 开始同步到看板", use_container_width=True)

# --- 同步逻辑 ---
if submit_button:
    if not batch_code:
        st.warning("请填写批次号！")
    else:
        with st.spinner(f"正在同步批次 {batch_code} 到产线 {target_line_id}..."):
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                
                batch_id = f"BATCH-SYNC-{batch_code}"
                
                # 0. 获取批次的机型信息，并归一化为族代码（G/XS/AUTO/SPECIAL）
                cursor.execute("SELECT `机型` FROM finished_goods_data WHERE `批次号` = %s LIMIT 1", (batch_code,))
                row = cursor.fetchone()
                raw_model = row[0] if row else "Unknown"

                # 通过 model_dictionary 获取 model_family
                cursor.execute(
                    "SELECT model_family FROM model_dictionary WHERE enabled=1 AND UPPER(TRIM(model_name))=UPPER(%s) LIMIT 1",
                    (raw_model.strip(),)
                )
                family_row = cursor.fetchone()
                if family_row and family_row[0]:
                    family = family_row[0].strip().upper()
                    model_type = "SPECIAL" if family in ("SPECIAL", "特殊") else family if family in ("G", "XS", "AUTO") else _normalize_model_family(raw_model)
                else:
                    model_type = _normalize_model_family(raw_model)

                # 1. 更新批次表 (补齐缺失的必填字段 batch_no, model_type)
                cursor.execute("""
                    INSERT INTO batches (batch_id, batch_code, batch_no, model_type, production_line_id, status, capacity, source, created_at, updated_at)
                    VALUES (%s, %s, 1, %s, %s, 'In_Production', 20, 'manual_sync', NOW(), NOW())
                    ON DUPLICATE KEY UPDATE 
                        production_line_id = %s,
                        status = 'In_Production',
                        updated_at = NOW()
                """, (batch_id, batch_code, model_type, target_line_id, target_line_id))

                # 1.1 更新产线状态为 Busy
                cursor.execute("UPDATE production_lines SET status = 'Busy' WHERE line_id = %s", (target_line_id,))

                # 2. 清理旧数据
                cursor.execute("DELETE FROM units WHERE batch_id = %s", (batch_id,))

                # 3. 导入数据
                import_sql = """
                INSERT INTO units (
                    unit_id, serial_no, batch_id, production_line_id, slot_index, model_type, 
                    contract_no, customer, dealer_name, order_remark, due_date, status, created_at, updated_at
                )
                SELECT 
                    CONCAT(b.batch_id, '_', ROW_NUMBER() OVER (PARTITION BY b.batch_id ORDER BY fg.`流水号` COLLATE utf8mb4_general_ci)),
                    fg.`流水号`,
                    b.batch_id,
                    b.production_line_id,
                    ROW_NUMBER() OVER (PARTITION BY b.batch_id ORDER BY fg.`流水号` COLLATE utf8mb4_general_ci),
                    fg.`机型`,
                    COALESCE(
                        NULLIF(TRIM(fg.`合同号`), ''), 
                        fp.`合同号`,
                        REGEXP_SUBSTR(fg.`合同备注`, 'HT[0-9]{10,}'),
                        REGEXP_SUBSTR(fg.`订单备注`, 'HT[0-9]{10,}'),
                        REGEXP_SUBSTR(so.`备注`, 'HT[0-9]{10,}')
                    ),
                    COALESCE(NULLIF(TRIM(fg.`客户`), ''), so.`客户名`, fp.`客户名`),
                    COALESCE(NULLIF(TRIM(fg.`代理商`), ''), so.`代理商`, fp.`代理商`),
                    COALESCE(NULLIF(TRIM(fg.`合同备注`), ''), NULLIF(TRIM(fg.`订单备注`), '')),
                    COALESCE(DATE(so.`发货时间`), 
                             STR_TO_DATE(NULLIF(TRIM(fp.`要求交期`), ''), '%%Y-%%m-%%d'),
                             DATE(fp.`要求交期`)
            ),
            'In_Production',
            NOW(),
            NOW()
        FROM finished_goods_data fg
        JOIN batches b ON b.batch_code = fg.`批次号` COLLATE utf8mb4_general_ci
        LEFT JOIN sales_orders so ON (so.`订单号` = fg.`占用订单号` COLLATE utf8mb4_general_ci AND NULLIF(TRIM(fg.`占用订单号`), '') IS NOT NULL)
        LEFT JOIN factory_plan fp ON (
            -- 注意：两个分支都必须加机型限制，否则同一订单多机型时会产生笛卡尔积
            (fp.`订单号` = fg.`占用订单号` COLLATE utf8mb4_general_ci AND NULLIF(TRIM(fg.`占用订单号`), '') IS NOT NULL AND fp.`机型` = fg.`机型` COLLATE utf8mb4_general_ci)
            OR 
            (fp.`合同号` = fg.`合同号` COLLATE utf8mb4_general_ci AND NULLIF(TRIM(fg.`合同号`), '') IS NOT NULL AND fp.`机型` = fg.`机型` COLLATE utf8mb4_general_ci)
        )
        WHERE b.batch_id = %s
        """
                cursor.execute(import_sql, (batch_id,))
                
                inserted_count = cursor.rowcount
                conn.commit()
                
                if inserted_count > 0:
                    st.success(f"✅ 同步成功！已导入 {inserted_count} 条数据到 {line_labels[target_line_id]}。")
                    st.balloons()
                else:
                    st.warning(f"⚠️ 同步完成，但在 ERP 成品库中未找到批次 '{batch_code}' 的任何机台。")
                    
            except Exception as e:
                st.error(f"❌ 同步过程中出错: {e}")
            finally:
                conn.close()

st.sidebar.markdown("### 使用说明")
st.sidebar.info("""
1. 从下拉框选择或手动输入**批次号**。
2. 选择该批次目前所在的**产线**。
3. 点击开始同步。
4. 刷新生产看板页面即可查看结果。
""")
