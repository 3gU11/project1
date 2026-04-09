import pandas as pd
import streamlit as st

from config import CUSTOM_MODEL_ORDER, PLOTLY_AVAILABLE, PRESET_RATIOS, px
from core.navigation import go_home
from crud.inventory import get_data
from utils.formatters import get_model_rank


def render_query():
    c_back, c_title = st.columns([2, 8])
    with c_back: st.button("⬅️ 返回", on_click=go_home, use_container_width=True)
    with c_title: st.header("📊 库存全景查询")

    # --- Dashboard Mode ---
    df = get_data()
    status_series = df['状态'].astype(str) if not df.empty and '状态' in df.columns else pd.Series(dtype=str)

    # 兼容状态写法：库存中、库存中（A01）等都视为“在库”；待入库保持原逻辑
    in_stock_mask = status_series.str.startswith('库存中', na=False)
    pending_mask = status_series.eq('待入库')

    # 始终包含 “库存中*” 和 “待入库”
    valid_df = df[in_stock_mask | pending_mask].copy()

    # --- 1. 机型筛选 (Optional) ---
    all_known_models = set(CUSTOM_MODEL_ORDER)
    if not df.empty: all_known_models.update(df['机型'].unique())
    unique_models = sorted(list(all_known_models), key=get_model_rank)

    # 顶部只留筛选
    c_q1, c_q2 = st.columns([3, 1])
    with c_q1:
        selected_models_query = st.multiselect("筛选机型", unique_models)
    with c_q2:
        st.write(""); st.write("")
        show_high_only = st.checkbox("仅显示加高 (High Only)")

    # 根据筛选过滤 valid_df 用于计算比例和图表
    if selected_models_query:
        display_df = valid_df[valid_df['机型'].isin(selected_models_query)]
        display_models = selected_models_query
    else:
        display_df = valid_df
        display_models = unique_models
        
    if show_high_only:
        display_df = display_df[
            display_df['机型'].str.contains("加高", na=False) |
            display_df['机台备注/配置'].str.contains("加高", na=False) |
            display_df['订单备注'].str.contains("加高", na=False)
        ]

    # --- 2. 库存比例看板 (直接显示) ---
    st.markdown("### 🧮 库存比例 (看板)")
    cols = st.columns(4)

    for idx, (label, (mA, mB)) in enumerate(PRESET_RATIOS.items()):
        with cols[idx % 4]:
            # 计算逻辑：使用 display_df (当前视图下的数据)
            cnt_a = len(display_df[display_df['机型'].isin(mA)])
            cnt_b = len(display_df[display_df['机型'].isin(mB)])
            pct = (cnt_a / cnt_b * 100) if cnt_b > 0 else 0.0
            
            # 使用 metric 直接显示
            st.metric(label=label, value=f"{pct:.1f}%", delta=f"{cnt_a} / {cnt_b}")

    st.divider()

    # --- 3. 三列库存列表 ---
    c_chart, c_table = st.columns([1, 1])

    with c_chart:
        total_all = len(display_df)
        
        # --- V7.4 Display Breakdown ---
        cnt_instock = len(display_df[display_df['状态'].astype(str).str.startswith('库存中', na=False)])
        cnt_pending = len(display_df[display_df['状态'] == '待入库'])
        
        st.metric("📦 当前总库存 (Total)", f"{total_all} 台")
        
        # Sub-metrics
        cm1, cm2 = st.columns(2)
        with cm1: st.metric("✅ 在库 (In Stock)", f"{cnt_instock}", help="已实际入库的现货")
        with cm2: st.metric("⏳ 待入库 (Pending)", f"{cnt_pending}", help="流水号已生成但未入库")
        
        if PLOTLY_AVAILABLE and not display_df.empty and px:
            fig = px.pie(display_df, names='机型', hole=0.4, title="机型分布")
            st.plotly_chart(fig, use_container_width=True)
        elif not PLOTLY_AVAILABLE:
            st.info("机型分布图未显示：当前环境未安装 `plotly`。安装后刷新页面即可恢复。")

    with c_table:
        # 计算三列数据
        # Group by Model and Status
        if not display_df.empty:
            stats_df = display_df.copy()
            stats_df['__状态归一'] = stats_df['状态'].astype(str).apply(lambda s: '库存中' if s.startswith('库存中') else s)
            stats = stats_df.groupby(['机型', '__状态归一']).size().unstack(fill_value=0)
            if '库存中' not in stats.columns: stats['库存中'] = 0
            if '待入库' not in stats.columns: stats['待入库'] = 0
        else:
            stats = pd.DataFrame(columns=['库存中', '待入库'])

        summary_data = []
        for m in display_models:
            in_stock = 0
            pending = 0
            
            if m in stats.index:
                in_stock = int(stats.loc[m, '库存中'])
                pending = int(stats.loc[m, '待入库'])
            
            total = in_stock + pending
            
            # 显示逻辑：有库存 OR 是重点机型
            is_key_model = m in CUSTOM_MODEL_ORDER
            if total > 0 or is_key_model or selected_models_query:
                summary_data.append({
                    "机型": m,
                    "库存中": in_stock,
                    "待入库": pending,
                    "全部": total
                })
        
        summary_df = pd.DataFrame(summary_data)
        if not summary_df.empty:
            summary_df['__rank'] = summary_df['机型'].apply(get_model_rank)
            summary_df = summary_df.sort_values(by=['__rank'], ascending=True)
            
            st.dataframe(
                summary_df.drop(columns=['__rank']), 
                use_container_width=True, 
                hide_index=True,
                column_config={
                    "库存中": st.column_config.NumberColumn(format="%d"),
                    "待入库": st.column_config.NumberColumn(format="%d"),
                    "全部": st.column_config.NumberColumn(format="%d"),
                }
            )
        else:
            st.info("无数据")
            
        with st.expander("详细清单 (Detailed List)"):
            # 防止SettingWithCopyWarning
            display_df = display_df.copy()
            display_df['__rank'] = display_df['机型'].apply(get_model_rank)
            display_df = display_df.sort_values(by=['__rank', '批次号'], ascending=[True, False])
            st.dataframe(display_df.drop(columns=['__rank'])[['批次号', '机型', '流水号', '状态', '机台备注/配置']], use_container_width=True)

    # --- 📜 日志 ---
