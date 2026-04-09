import re
import time
from datetime import datetime

import streamlit as st

from config import CUSTOM_MODEL_ORDER
from core.navigation import go_home
from core.permissions import check_access
from crud.inventory import get_data, save_data
from utils.formatters import get_model_rank


def _norm_cell(v) -> str:
    t = str(v).strip()
    if t.lower() in ("", "nan", "none"):
        return ""
    return t


def _hyphen_segment_match(series, kw: str):
    """
    关键字须作为完整的一段出现在「用 - 或 / 分隔」的片段中。
    避免 naive 子串匹配：如搜 03-11 时误命中订单号 03-1155（03-11 是其中子串）。
    例：96-03 仍匹配 96-03-238；03-11 不匹配 03-05。
    """
    if not kw:
        return series.map(lambda _: True)
    pat = r"(?:^|[/-])" + re.escape(kw) + r"(?:[/-]|$)"
    return series.astype(str).str.contains(pat, case=False, na=False, regex=True)


def render_machine_edit():
    check_access('MACHINE_EDIT')
    user_perms = st.session_state.get('permissions', [])
    can_edit_model = (st.session_state.role == "Admin") or ("MACHINE_EDIT_MODEL" in user_perms)
    c_back, c_title = st.columns([2, 8])
    with c_back: st.button("⬅️ 返回", on_click=go_home, use_container_width=True)
    with c_title: st.header("🛠️ 机台信息编辑")

    with st.expander("🔎 筛选条件", expanded=True):
        c_f1, c_f2 = st.columns(2)
        with c_f1:
            f_keyword = st.text_input(
                "搜索 (流水号 / 订单号 / 批次号)",
                placeholder="流水号/订单号：按「- /」分段匹配；批次号：整段须完全一致",
            )
        with c_f2:
            f_date_range = st.date_input("更新时间范围", value=[])

    df = get_data()
    edit_df = df[df['状态'] != '已出库'].copy()
    all_models = sorted(list(set(CUSTOM_MODEL_ORDER).union(set(df['机型'].dropna().astype(str).tolist()))), key=get_model_rank)

    kw = (f_keyword or "").strip()
    if kw:
        kw_l = kw.lower()
        # 流水号 / 订单号：分段边界匹配（re.escape 处理特殊字符）
        sn_mask = _hyphen_segment_match(edit_df["流水号"], kw)
        ord_mask = _hyphen_segment_match(edit_df["占用订单号"], kw)
        batch_mask = edit_df["批次号"].map(lambda v: _norm_cell(v).lower() == kw_l)
        mask = sn_mask | ord_mask | batch_mask
        edit_df = edit_df[mask].copy()

    if not edit_df.empty:
        # 按机型排序
        edit_df['__rank'] = edit_df['机型'].apply(get_model_rank)
        edit_df = edit_df.sort_values(by=['__rank', '批次号'], ascending=[True, False])
        
        edit_df.insert(0, "✅ 选择", False)
        
        edited_res = st.data_editor(
            edit_df[['✅ 选择', '批次号', '流水号', '机型', '状态', 'Location_Code', '占用订单号', '机台备注/配置', '更新时间']],
            hide_index=True,
            use_container_width=True,
            key="machine_edit_editor",
            column_config={
                "机型": st.column_config.SelectboxColumn("机型", options=all_models, required=True),
            },
            disabled=["状态", "Location_Code"] if can_edit_model else ["机型", "状态", "Location_Code"],
        )
        selected_rows = edited_res[edited_res['✅ 选择'] == True]

        # 检测 data_editor 中行内修改的机型/状态/库位，若有变化则立即保存
        if can_edit_model:
            inline_changed_sns = []
            for _, row in edited_res.iterrows():
                sn = row['流水号']
                orig_row = df[df['流水号'] == sn]
                if orig_row.empty:
                    continue
                orig_model = str(orig_row.iloc[0]['机型'])
                new_model_val = str(row['机型'])
                if orig_model != new_model_val:
                    df.loc[df['流水号'] == sn, '机型'] = new_model_val
                    df.loc[df['流水号'] == sn, '更新时间'] = datetime.now().strftime("%Y-%m-%d %H:%M")
                    inline_changed_sns.append(sn)
            if inline_changed_sns:
                save_data(df)
                st.success(f"已自动保存 {len(inline_changed_sns)} 台机型修改！")
                time.sleep(0.8)
                st.rerun()
        
        if not selected_rows.empty:
            st.divider()
            with st.form("batch_edit_form"):
                if can_edit_model:
                    new_model = st.selectbox("新的机型 (可选)", ["(不修改)"] + all_models)
                    
                new_note = st.text_area("新的机台备注/配置 (Max 500字)", max_chars=500)
                c_q1, c_q2 = st.columns(2)
                with c_q1:
                    opt_xs_auto = st.checkbox("XS改X手自一体")
                with c_q2:
                    opt_back_cond = st.checkbox("后导电")
                if st.form_submit_button("💾 批量保存修改", type="primary"):
                    sns_val = selected_rows['流水号'].tolist()
                    # 先将 data_editor 中行内修改的机型同步回 df
                    if can_edit_model:
                        for _, row in edited_res.iterrows():
                            sn = row['流水号']
                            new_model_inline = row['机型']
                            orig = df.loc[df['流水号'] == sn, '机型']
                            if not orig.empty and str(orig.iloc[0]) != str(new_model_inline):
                                df.loc[df['流水号'] == sn, '机型'] = new_model_inline
                    if can_edit_model and new_model != "(不修改)":
                        df.loc[df['流水号'].isin(sns_val), '机型'] = new_model
                    note_parts = [new_note.strip()] if str(new_note).strip() else []
                    if opt_xs_auto:
                        note_parts.append("XS改X手自一体")
                    if opt_back_cond:
                        note_parts.append("后导电")
                    df.loc[df['流水号'].isin(sns_val), '机台备注/配置'] = "；".join(note_parts)
                    df.loc[df['流水号'].isin(sns_val), '更新时间'] = datetime.now().strftime("%Y-%m-%d %H:%M")
                    save_data(df)
                    st.success(f"已更新 {len(sns_val)} 台机器！"); time.sleep(1); st.rerun()
    else: st.info("无数据")

    # --- 📂 机台档案 (Machine Archive) ---
