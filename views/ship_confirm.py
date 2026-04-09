import time
from datetime import datetime

import pandas as pd
import streamlit as st

from core.navigation import go_home
from core.permissions import check_access
from crud.inventory import get_data, save_data, archive_shipped_data
from crud.orders import get_orders, revert_to_inbound
from crud.logs import append_log
from utils.formatters import get_model_rank
from views.components import render_archive_preview, render_module_logs


def render_ship_confirm():
    check_access('SHIP_CONFIRM')
    c_back, c_title = st.columns([2, 8])
    with c_back: st.button("⬅️ 返回", on_click=go_home, use_container_width=True)
    with c_title: st.header("🚛 发货复核")

    df = get_data()
    pending = df[df['状态'] == '待发货'].copy()

    st.metric("待发货总数", len(pending))

    if pending.empty: st.success("无任务")
    else:
        # 先标准化订单号，避免历史数据空格/None 导致显示和映射失败
        if '占用订单号' not in pending.columns:
            pending['占用订单号'] = ""
        pending['占用订单号'] = pending['占用订单号'].astype(str).str.strip()
        pending.loc[pending['占用订单号'].isin(['nan', 'None', 'NaT']), '占用订单号'] = ""

        # 关联最新的订单备注
        orders_df = get_orders()
        if not orders_df.empty:
            orders_df = orders_df.copy()
            orders_df['订单号'] = orders_df['订单号'].astype(str).str.strip()
            # map order note
            note_map = orders_df.set_index('订单号')['备注'].to_dict()
            # map delivery time
            date_map = orders_df.set_index('订单号')['发货时间'].to_dict()
            
            # 更新订单备注 (如果订单中有备注则使用订单的，否则保留原样)
            if '订单备注' not in pending.columns: pending['订单备注'] = ""
            mapped_notes = pending['占用订单号'].map(note_map)
            pending['订单备注'] = mapped_notes.fillna(pending['订单备注'])
            
            # 更新发货时间（统一转成字符串，避免日期列类型不一致导致空白显示）
            raw_dates = pending['占用订单号'].map(date_map)
            pending['发货时间'] = pd.to_datetime(raw_dates, errors='coerce').dt.strftime('%Y-%m-%d').fillna("")
        else:
            if '发货时间' not in pending.columns: pending['发货时间'] = ""

        # 按机型排序
        pending = pending.copy()
        pending['__rank'] = pending['机型'].apply(get_model_rank)
        pending = pending.sort_values(by=['__rank', '流水号'], ascending=[True, False])
        
        pending.insert(0, "✅", False)
        
        # 显示列包括 订单备注 和 机台备注/配置
        cols_to_show = ['✅', '发货时间', '占用订单号', '客户', '机型', '流水号', '订单备注', '机台备注/配置']
        # 确保列存在
        for c in cols_to_show:
            if c not in pending.columns: pending[c] = ""
            
        res = st.data_editor(
            pending[cols_to_show], 
            hide_index=True, 
            use_container_width=True,
            column_config={
                "发货时间": st.column_config.TextColumn("发货时间", width="small"),
                "订单备注": st.column_config.TextColumn("订单备注", width="medium"),
                "机台备注/配置": st.column_config.TextColumn("机台备注", width="medium")
            }
        )
        to_act = res[res['✅'] == True]
        
        if not to_act.empty:
            # --- 📸 选中机台照片预览 (Added) ---
            st.divider()
            st.markdown("### 📸 选中机台照片预览")
            for _, row in to_act.iterrows():
                sn = row['流水号']
                model = row['机型']
                with st.expander(f"📦 {sn} - {model}", expanded=True):
                    render_archive_preview(sn)
            st.divider()
            # -----------------------------------

            c_op1, c_op2 = st.columns([1, 1])
            with c_op1:
                if st.button(f"🚚 正式发货 {len(to_act)} 台", type="primary", use_container_width=True):
                    sns = to_act['流水号'].tolist()
                    df.loc[df['流水号'].isin(sns), '状态'] = '已出库'
                    df.loc[df['流水号'].isin(sns), '更新时间'] = datetime.now().strftime("%Y-%m-%d %H:%M")
                    save_data(df)
                    archive_shipped_data(df[df['流水号'].isin(sns)])
                    append_log("正式发货", sns)
                    st.success("发货完成"); time.sleep(1); st.rerun()
            
            with c_op2:
                # 发货撤回功能：撤回为待入库
                if st.button(f"🔄 撤回 {len(to_act)} 台 (退回待入库)", type="secondary", use_container_width=True):
                    revert_to_inbound(to_act['流水号'].tolist(), reason="正式发货撤回")
                    st.success("已撤回为待入库状态！"); time.sleep(1); st.rerun()

    st.divider()
    render_module_logs(["正式发货", "正式发货撤回", "已出库"])

    # --- 📥 入库 (V5.5) ---
