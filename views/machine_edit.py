import time
from datetime import datetime

import streamlit as st

from core.navigation import go_home
from core.permissions import check_access
from crud.inventory import get_data, save_data
from utils.formatters import get_model_rank


def render_machine_edit():
    check_access('MACHINE_EDIT')
    c_back, c_title = st.columns([2, 8])
    with c_back: st.button("⬅️ 返回", on_click=go_home, use_container_width=True)
    with c_title: st.header("🛠️ 机台信息编辑")

    with st.expander("🔎 筛选条件", expanded=True):
        c_f1, c_f2, c_f3 = st.columns(3)
        with c_f1: f_sn = st.text_input("流水号 (包含)")
        with c_f2: f_order = st.text_input("订单号 (包含)")
        with c_f3: f_date_range = st.date_input("更新时间范围", value=[])

    df = get_data()
    edit_df = df[df['状态'] != '已出库'].copy()

    if f_sn: edit_df = edit_df[edit_df['流水号'].str.contains(f_sn, case=False, na=False)]
    if f_order: edit_df = edit_df[edit_df['占用订单号'].str.contains(f_order, case=False, na=False)]

    if not edit_df.empty:
        # 按机型排序
        edit_df['__rank'] = edit_df['机型'].apply(get_model_rank)
        edit_df = edit_df.sort_values(by=['__rank', '批次号'], ascending=[True, False])
        
        edit_df.insert(0, "✅ 选择", False)
        edited_res = st.data_editor(edit_df[['✅ 选择', '流水号', '机型', '状态', '占用订单号', '机台备注/配置', '更新时间']], hide_index=True, use_container_width=True, key="machine_edit_editor")
        selected_rows = edited_res[edited_res['✅ 选择'] == True]
        
        if not selected_rows.empty:
            st.divider()
            with st.form("batch_edit_form"):
                new_note = st.text_area("新的机台备注/配置 (Max 500字)", max_chars=500)
                if st.form_submit_button("💾 批量修改备注", type="primary"):
                    sns_val = selected_rows['流水号'].tolist()
                    df.loc[df['流水号'].isin(sns_val), '机台备注/配置'] = new_note
                    df.loc[df['流水号'].isin(sns_val), '更新时间'] = datetime.now().strftime("%Y-%m-%d %H:%M")
                    save_data(df)
                    st.success(f"已更新 {len(sns_val)} 台机器！"); time.sleep(1); st.rerun()
    else: st.info("无数据")

    # --- 📂 机台档案 (Machine Archive) ---
