import time
from datetime import datetime
import json

import streamlit as st

from config import CUSTOM_MODEL_ORDER
from core.navigation import go_home
from core.permissions import check_access
from crud.inventory import get_data
from utils.formatters import get_model_rank
from utils.parsers import generate_auto_inbound
from views.inbound_modules import (
    check_prod_admin_permission,
    render_machine_inbound_module,
    render_tracking_import_module,
)


def render_inbound():
    check_access('INBOUND')
    c_back, c_title = st.columns([2, 8])
    with c_back: st.button("⬅️ 返回", on_click=go_home, use_container_width=True)
    with c_title: st.header("📥 入库作业")

    # 权限检查
    check_prod_admin_permission()

    is_inbound_only = st.session_state.get('role') == 'Inbound'

    if is_inbound_only:
        render_machine_inbound_module()
    else:
        tab_machine, tab_import = st.tabs(["🏭 机台入库 (Machine Inbound)", "📋 跟踪单导入 (Tracking Import)"])

        # --- 模块一：机台入库 ---
        with tab_machine:
            render_machine_inbound_module()
            
        # --- 模块二：跟踪单导入 ---
        with tab_import:
            render_tracking_import_module()
            
            st.divider()
            with st.expander("⚡ 辅助功能：自动生成流水号 (Auto Generate)", expanded=False):
                st.caption("用于生成测试数据或无跟踪单的情况，生成后将写入 PLAN_IMPORT。")
                c1, c2, c3, c4 = st.columns(4)
                with c1: inp_batch = st.text_input("批次号", key="auto_batch")
                with c2:
                    df_for_model = get_data()
                    all_known_models = set(CUSTOM_MODEL_ORDER)
                    if not df_for_model.empty:
                        all_known_models.update(df_for_model['机型'].unique())
                    models = sorted(list(all_known_models), key=get_model_rank)
                    
                    inp_model = st.selectbox("机型", options=models + ["其它(手输)"] if models else ["其它(手输)"], key="auto_model_sel")
                    if inp_model == "其它(手输)":
                        final_model = st.text_input("请输入机型名称", key="auto_model_txt")
                    else: final_model = inp_model
                with c3: inp_qty = st.number_input("数量", min_value=1, value=1, key="auto_qty")
                with c4: inp_date = st.date_input("预计入库", value=datetime.now().date(), key="auto_date")
                inp_note = st.text_area("机台备注", key="auto_note")
                
                confirm_gen = st.checkbox("我确认上述信息无误", key="auto_confirm")
                request_signature = json.dumps(
                    {
                        "batch": str(inp_batch or "").strip(),
                        "model": str(final_model or "").strip(),
                        "qty": int(inp_qty),
                        "date": str(inp_date),
                        "note": str(inp_note or "").strip(),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
                if st.button("✅ 生成并保存到 PLAN_IMPORT", type="primary", disabled=not confirm_gen, key="auto_btn"):
                    last_failed_signature = st.session_state.get("auto_last_failed_signature", "")
                    if last_failed_signature == request_signature:
                        st.error("E_DUPLICATE_SUBMIT: 上一次相同请求已失败，请修改参数后重试")
                        return
                    code, msg = generate_auto_inbound(inp_batch, final_model, inp_qty, inp_date, inp_note)
                    if code == 1:
                        st.session_state["auto_last_failed_signature"] = ""
                        st.success(msg)
                        time.sleep(1); st.rerun()
                    else:
                        st.session_state["auto_last_failed_signature"] = request_signature
                        st.error(msg)

    # --- 🔍 查询 (保持原版逻辑) ---
