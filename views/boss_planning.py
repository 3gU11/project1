import time
from datetime import datetime

import pandas as pd
import streamlit as st

from config import CUSTOM_MODEL_ORDER
from core.navigation import go_home
from core.permissions import check_access
from crud.contracts import get_unlinked_contract_folders
from crud.inventory import get_data
from crud.orders import create_sales_order, get_orders, save_orders
from crud.planning import get_factory_plan, save_factory_plan, save_planning_record
from utils.formatters import get_model_rank
from utils.parsers import parse_alloc_dict, parse_plan_map, parse_requirements, to_json_text
from views.components import render_file_manager


def render_boss_planning():
    check_access('PLANNING')

    if True:
        c_back, c_title = st.columns([1, 9])
        with c_back: st.button("⬅️ 返回", on_click=go_home, use_container_width=True)
        with c_title: st.header("👑 生产统筹 & 订单资源分配")

        # 恢复左右分栏布局
        col_list, col_detail = st.columns([1, 2], gap="large")

        fp_df = get_factory_plan()
        orders_df = get_orders()
        inventory_df = get_data()

        if 'boss_selected_id' not in st.session_state: st.session_state.boss_selected_id = None
        if 'boss_selected_type' not in st.session_state: st.session_state.boss_selected_type = 'contract' # contract | order

        # ==================== 左侧列表 (导航) ====================
        with col_list:
            with st.container(height=750, border=True):
                tab_pending, tab_planning, tab_orders = st.tabs(["📄 待审合同", "🎯 待规划", "📦 现有订单"])
                
                # --- 1. 待审合同 (Pending Review) ---
                with tab_pending:
                    # 搜索框
                    search_txt = st.text_input("🔍 搜索待审合同 (合同号/客户)", key="search_pending")
                    
                    # 按合同号聚合
                    pending_df = fp_df[fp_df['状态'] == '未下单'].copy()
                    
                    if search_txt:
                        s_term = search_txt.lower()
                        pending_df = pending_df[
                            pending_df['合同号'].str.lower().str.contains(s_term, na=False) |
                            pending_df['客户名'].str.lower().str.contains(s_term, na=False)
                        ]
                    
                    if pending_df.empty:
                        st.info("无待审合同")
                    else:
                        pending_df['temp_date'] = pd.to_datetime(pending_df['要求交期'], errors='coerce')
                        pending_df = pending_df.sort_values('temp_date')
                        pending_df['month_key'] = pending_df['temp_date'].apply(lambda x: x.strftime('%Y-%m') if pd.notnull(x) else 'Unknown')
                        months = sorted([m for m in pending_df['month_key'].unique() if m != 'Unknown'], reverse=False)
                        if 'Unknown' in pending_df['month_key'].unique():
                            months.append('Unknown')

                        for m_key in months:
                            m_rows = pending_df[pending_df['month_key'] == m_key]
                            unique_contracts = m_rows['合同号'].unique()
                            count = len(unique_contracts)
                            is_expanded = st.session_state.get('boss_pending_month', months[0]) == m_key

                            with st.expander(f"📅 {m_key} ({count} 单)", expanded=is_expanded):
                                for cid in unique_contracts:
                                    c_rows = m_rows[m_rows['合同号'] == cid]
                                    cust = c_rows.iloc[0]['客户名']
                                    model_counts = c_rows.groupby('机型')['排产数量'].apply(lambda x: sum(int(float(i)) for i in x))
                                    models_display = []
                                    for m, q in model_counts.items():
                                        models_display.append(f"{m} x{q}")
                                    models_str = "\n".join(models_display)

                                    label = f"🏢 {cust}\n{models_str}"
                                    btn_type = "primary" if (st.session_state.boss_selected_id == cid and st.session_state.boss_selected_type == 'contract') else "secondary"

                                    if st.button(label, key=f"btn_con_{cid}_{m_key}", type=btn_type, use_container_width=True):
                                        st.session_state.boss_selected_id = cid
                                        st.session_state.boss_selected_type = 'contract'
                                        st.session_state.boss_pending_month = m_key
                                        st.rerun()

                # --- 2. 待规划 (Pending Planning) ---
                with tab_planning:
                    search_plan = st.text_input("🔍 搜索待规划 (合同/客户)", key="search_planning")
                    # 状态为 '待规划'
                    planning_df = fp_df[fp_df['状态'] == '待规划'].copy()

                    if search_plan:
                        s_term = search_plan.lower()
                        planning_df = planning_df[
                            planning_df['合同号'].str.lower().str.contains(s_term, na=False) |
                            planning_df['客户名'].str.lower().str.contains(s_term, na=False)
                        ]

                    if planning_df.empty:
                        st.info("无待规划项")
                    else:
                        # 1. 预处理数据和排序
                        planning_df['temp_date'] = pd.to_datetime(planning_df['要求交期'], errors='coerce')
                        planning_df = planning_df.sort_values('temp_date')
                        
                        # 2. 增加月份分组键
                        planning_df['month_key'] = planning_df['temp_date'].apply(lambda x: x.strftime('%Y-%m') if pd.notnull(x) else 'Unknown')
                        
                        # 3. 获取所有月份并排序
                        months = sorted([m for m in planning_df['month_key'].unique() if m != 'Unknown'], reverse=True)
                        if 'Unknown' in planning_df['month_key'].unique():
                            months.append('Unknown')
                        
                        # 4. 按月份渲染折叠面板
                        for m_key in months:
                            m_rows = planning_df[planning_df['month_key'] == m_key]
                            unique_plans = m_rows['合同号'].unique()
                            count = len(unique_plans)
                            
                            # 默认展开最近一个月
                            is_expanded = (m_key == months[0])
                            
                            with st.expander(f"📅 {m_key} ({count} 单)", expanded=is_expanded):
                                for cid in unique_plans:
                                    c_rows = m_rows[m_rows['合同号'] == cid]
                                    cust = c_rows.iloc[0]['客户名']
                                    models_summary = ", ".join(c_rows['机型'].unique())
                                    if len(models_summary) > 15: models_summary = models_summary[:15] + "..."
                                    
                                    label = f"🎯 {cid}\n{cust} | {models_summary}"
                                    btn_type = "primary" if (st.session_state.boss_selected_id == cid and st.session_state.boss_selected_type == 'planning') else "secondary"
                                    
                                    if st.button(label, key=f"btn_plan_{cid}_{m_key}", type=btn_type, use_container_width=True):
                                        st.session_state.boss_selected_id = cid
                                        st.session_state.boss_selected_type = 'planning'
                                        st.rerun()

                # --- 3. 现有订单 (Existing Orders / Planned) ---
                with tab_orders:
                    # 辅助函数：判断订单是否已完结 (Shipping >= Request)
                    # 计算所有占用 (Allocated + Shipped + Pending)
                    if not inventory_df.empty:
                        shipped_stats = inventory_df[inventory_df['状态'] == '已出库'].groupby('占用订单号').size().to_dict()
                        all_allocated_stats = inventory_df[inventory_df['占用订单号'] != ""].groupby('占用订单号').size().to_dict()
                    else: 
                        shipped_stats = {}
                        all_allocated_stats = {}

                    def is_order_completed(oid, req_qty_str):
                        if not oid: return False
                        s_qty = shipped_stats.get(oid, 0)
                        try: r_qty = int(float(req_qty_str))
                        except: r_qty = 999999
                        return s_qty >= r_qty and r_qty > 0
                    
                    # 辅助：判断是否已配齐 (Allocated >= Request)
                    def is_fully_allocated(oid, req_qty_str):
                        if not oid: return False
                        alloc_qty = all_allocated_stats.get(oid, 0)
                        try: r_qty = int(float(req_qty_str))
                        except: r_qty = 999999
                        return alloc_qty >= r_qty and r_qty > 0

                    # 1. 准备合同数据 (Contracts)
                    done_df = fp_df[fp_df['状态'].isin(['已规划', '已转订单', '已下单', '已配货'])].copy()
                    
                    # 过滤掉已完结的合同 (如果关联了订单且订单已完结)
                    completed_oids = set()
                    if not orders_df.empty and not done_df.empty:
                        linked_oids = done_df['订单号'].dropna().unique()
                        for oid in linked_oids:
                            if not oid: continue
                            ord_row = orders_df[orders_df['订单号'] == oid]
                            if not ord_row.empty:
                                req = ord_row.iloc[0]['需求数量']
                                if is_order_completed(oid, req):
                                    completed_oids.add(oid)
                    
                    if completed_oids:
                        done_df = done_df[~done_df['订单号'].isin(completed_oids)]

                    # 2. 准备手动订单数据 (Manual Orders - No Contract)
                    # 找出所有在 fp_df 中出现的订单号
                    all_contract_oids = set(fp_df['订单号'].dropna().unique())
                    
                    manual_orders = []
                    if not orders_df.empty:
                        for idx, row in orders_df.iterrows():
                            oid = row['订单号']
                            if not oid: continue
                            # 排除已关联合同的
                            if oid in all_contract_oids: continue
                            # 排除已完结的
                            if is_order_completed(oid, row['需求数量']): continue
                            
                            manual_orders.append(row)
                    
                    manual_df = pd.DataFrame(manual_orders)

                    search_q = st.text_input("🔍 搜索", placeholder="合同/订单/客户")
                    
                    # 搜索过滤
                    if search_q:
                        s = search_q.lower()
                        if not done_df.empty:
                            done_df = done_df[
                                done_df['合同号'].str.lower().str.contains(s, na=False) |
                                done_df['客户名'].str.lower().str.contains(s, na=False) |
                                done_df['订单号'].str.lower().str.contains(s, na=False)
                            ]
                        if not manual_df.empty:
                            manual_df = manual_df[
                                manual_df['订单号'].str.lower().str.contains(s, na=False) |
                                manual_df['客户名'].str.lower().str.contains(s, na=False) |
                                manual_df['代理商'].str.lower().str.contains(s, na=False)
                            ]

                    # 显示列表
                    has_data = False
                    
                    # A. 合同列表 (按月份折叠)
                    if not done_df.empty:
                        has_data = True
                        st.caption("📑 合同订单 (按月分组)")
                        
                        # 1. 增加月份辅助列 (基于 '要求交期')
                        done_df['month_key'] = pd.to_datetime(done_df['要求交期'], errors='coerce').dt.strftime('%Y-%m')
                        done_df['month_key'] = done_df['month_key'].fillna('Unknown')
                        
                        # 2. 获取所有月份并降序排列
                        all_months = sorted(done_df['month_key'].unique(), reverse=True)
                        
                        for m_key in all_months:
                            # 3. 统计该月合同数
                            m_rows = done_df[done_df['month_key'] == m_key]
                            m_count = m_rows['合同号'].nunique()
                            
                            # 4. 默认展开最近一个月，其他折叠
                            is_expanded = (m_key == all_months[0])
                            
                            with st.expander(f"📅 {m_key} ({m_count} 单)", expanded=is_expanded):
                                unique_done = m_rows['合同号'].unique()[::-1]
                                for cid in unique_done:
                                    c_rows = m_rows[m_rows['合同号'] == cid]
                                    cust = c_rows.iloc[0]['客户名']
                                    oid = c_rows.iloc[0].get('订单号', '')
                                    status = c_rows.iloc[0]['状态']
                                    label = f"📦 {cid} ({status})\n{cust}" + (f" | {oid}" if oid else "")
                                    btn_type = "primary" if (st.session_state.boss_selected_id == cid and st.session_state.boss_selected_type == 'done') else "secondary"
                                    if st.button(label, key=f"btn_done_{cid}_{m_key}", type=btn_type, use_container_width=True):
                                        st.session_state.boss_selected_id = cid
                                        st.session_state.boss_selected_type = 'done'
                                        st.rerun()
                    
                    # B. 手动订单列表
                    if not manual_df.empty:
                        has_data = True
                        st.caption("📝 独立订单 (无合同)")
                        
                        # 分组：进行中 vs 已配齐
                        m_ongoing = []
                        m_allocated = []
                        
                        for idx, row in manual_df.iloc[::-1].iterrows():
                            if is_fully_allocated(row['订单号'], row['需求数量']):
                                m_allocated.append(row)
                            else:
                                m_ongoing.append(row)
                        
                        # 渲染函数
                        def render_manual_btn(row):
                            oid = row['订单号']
                            cust = row['客户名']
                            s_qty = shipped_stats.get(oid, 0)
                            req_qty = row['需求数量']
                            label = f"📝 {oid}\n{cust} | 进度: {s_qty}/{req_qty}"
                            btn_type = "primary" if (st.session_state.boss_selected_id == oid and st.session_state.boss_selected_type == 'manual_order') else "secondary"
                            if st.button(label, key=f"btn_manual_{oid}", type=btn_type, use_container_width=True):
                                st.session_state.boss_selected_id = oid
                                st.session_state.boss_selected_type = 'manual_order'
                                st.rerun()

                        # 1. 显示进行中
                        for row in m_ongoing: render_manual_btn(row)
                        
                        # 2. 显示已配齐 (折叠)
                        if m_allocated:
                            with st.expander(f"✅ 已配齐待发 ({len(m_allocated)})", expanded=False):
                                for row in m_allocated: render_manual_btn(row)

                    if not has_data:
                        st.info("无相关未完结订单")

        # ==================== 右侧详情 (Review / Plan / Edit) ====================
        with col_detail:
            with st.container(height=750, border=True):
                sel_id = st.session_state.boss_selected_id
                sel_type = st.session_state.boss_selected_type
                
                if not sel_id:
                     # 用户要求：右边配置区域也是默认空白
                     # 原来是: st.info("👈 请从左侧选择一个项目")
                     st.info("👈 请从左侧选择一个项目以查看详情")
                
                # --- 场景1: 待审合同 (Review) ---
                elif sel_type == 'contract':
                    target_rows = fp_df[(fp_df['合同号'] == sel_id) & (fp_df['状态'] == '未下单')]
                    if target_rows.empty:
                        st.warning("该合同状态已变更，请刷新")
                    else:
                        first_row = target_rows.iloc[0]
                        
                        # --- 编辑模式开关 ---
                        c_h1, c_h2 = st.columns([8, 2])
                        with c_h1: st.markdown(f"### 📄 合同详情: {sel_id}")
                        with c_h2: 
                            is_edit_mode = st.toggle("✏️ 编辑模式", key=f"edit_mode_{sel_id}")
                        
                        if is_edit_mode:
                            st.info("正在编辑合同内容...")
                            with st.form(f"edit_contract_{sel_id}"):
                                c_e1, c_e2 = st.columns(2)
                                with c_e1:
                                    new_cust = st.text_input("客户名", value=first_row['客户名'])
                                    new_deadline = st.date_input("要求交期", value=pd.to_datetime(first_row['要求交期']).date() if pd.notna(first_row['要求交期']) else datetime.now().date())
                                with c_e2:
                                    new_agent = st.text_input("代理商", value=first_row['代理商'])
                                    # 备注通常存在第一行或者每行都有，这里取第一行作为总备注的近似，或者允许批量修改
                                    # 实际上 factory_plan 里的备注是行备注。但通常合同有个总备注？
                                    # 我们的数据结构里没有独立的合同总备注，通常存在每行的备注里，或者只是UI上的概念
                                    # 这里我们提供一个 "批量修改备注" 的功能，或者只展示行编辑
                                    pass

                                st.markdown("#### 🛠️ 机型明细 (可增删改)")
                                # 准备编辑用的数据
                                # 必须包含: 机型, 排产数量, 备注
                                edit_data = target_rows[['机型', '排产数量', '备注']].copy()
                                # 转换数量为数字
                                edit_data['排产数量'] = edit_data['排产数量'].astype(float).astype(int)
                                
                                # 获取全量机型选项
                                df_inv_tmp = get_data()
                                all_models = set(CUSTOM_MODEL_ORDER)
                                if not df_inv_tmp.empty: all_models.update(df_inv_tmp['机型'].unique())
                                model_options = sorted(list(all_models), key=get_model_rank)

                                edited_items = st.data_editor(
                                    edit_data,
                                    num_rows="dynamic",
                                    use_container_width=True,
                                    column_config={
                                        "机型": st.column_config.SelectboxColumn("机型", options=model_options, required=True),
                                        "排产数量": st.column_config.NumberColumn("数量", min_value=1, required=True),
                                        "备注": st.column_config.TextColumn("备注")
                                    }
                                )
                                
                                if st.form_submit_button("💾 保存修改"):
                                    if edited_items.empty:
                                        st.error("至少需要一行机型数据")
                                    else:
                                        # 1. 删除旧数据
                                        fp_df = fp_df[fp_df['合同号'] != sel_id]
                                        
                                        # 2. 构建新数据
                                        new_rows = []
                                        for _, r_item in edited_items.iterrows():
                                            new_row = {
                                                "合同号": sel_id,
                                                "机型": r_item['机型'],
                                                "排产数量": int(r_item['排产数量']),
                                                "要求交期": str(new_deadline),
                                                "状态": "未下单",
                                                "备注": r_item.get('备注', ''),
                                                "客户名": new_cust,
                                                "代理商": new_agent,
                                                "指定批次/来源": "", # 重置规划
                                                "订单号": ""
                                            }
                                            new_rows.append(new_row)
                                        
                                        fp_df = pd.concat([fp_df, pd.DataFrame(new_rows)], ignore_index=True)
                                        save_factory_plan(fp_df)
                                        st.success("合同修改已保存！")
                                        # 关闭编辑模式
                                        # st.session_state[f"edit_mode_{sel_id}"] = False # toggle 无法直接通过代码关闭，只能 rerun
                                        time.sleep(1); st.rerun()

                            st.divider()
                            c_act1, c_act2 = st.columns(2)
                            with c_act1:
                                if st.button("🚀 前往规划", type="primary", use_container_width=True, key=f"to_planning_edit_{sel_id}"):
                                    # 将该合同下所有条目状态改为 '待规划'
                                    fp_df.loc[fp_df['合同号'] == sel_id, '状态'] = '待规划'
                                    save_factory_plan(fp_df)
                                    st.session_state.boss_selected_type = 'planning'
                                    st.success("已批准！进入规划阶段。")
                                    st.rerun()
                            with c_act2:
                                if st.button("❌ 驳回/取消", use_container_width=True, key=f"reject_contract_edit_{sel_id}"):
                                    fp_df.loc[fp_df['合同号'] == sel_id, '状态'] = '已取消'
                                    save_factory_plan(fp_df)
                                    st.warning("合同已取消")
                                    st.session_state.boss_selected_id = None
                                    st.rerun()

                        else:
                            # --- 阅读模式 (原显示逻辑) ---
                            st.markdown(f"""
                            <div class="boss-plan-card">
                                <p><b>客户:</b> {first_row['客户名']} | <b>代理:</b> {first_row['代理商']}</p>
                                <p><b>交期:</b> {first_row['要求交期']}</p>
                                <p><b>备注:</b> {first_row['备注']}</p>
                            </div>
                            """, unsafe_allow_html=True)
                            
                            st.write("**包含机型:**")
                            st.dataframe(target_rows[['机型', '排产数量', '要求交期', '备注']], use_container_width=True, hide_index=True)
                        
                        st.divider()
                        c_act1, c_act2 = st.columns(2)
                        with c_act1:
                            if st.button("🚀 前往规划", type="primary", use_container_width=True):
                                # 将该合同下所有条目状态改为 '待规划'
                                fp_df.loc[fp_df['合同号'] == sel_id, '状态'] = '待规划'
                                save_factory_plan(fp_df)
                                st.session_state.boss_selected_type = 'planning'
                                st.success("已批准！进入规划阶段。")
                                st.rerun()
                        with c_act2:
                            if st.button("❌ 驳回/取消", use_container_width=True):
                                fp_df.loc[fp_df['合同号'] == sel_id, '状态'] = '已取消'
                                save_factory_plan(fp_df)
                                st.warning("合同已取消")
                                st.session_state.boss_selected_id = None
                                st.rerun()

                        # --- V7.5 File Preview & Download (Enhanced UI) ---
                        render_file_manager(sel_id, first_row['客户名'], default_expanded=True)

                elif sel_type == 'orphan_contract':
                    orphan_id = str(sel_id)
                    orphan_customer = orphan_id.split("_")[0] if "_" in orphan_id else orphan_id
                    st.markdown(f"### 📎 附件详情: {orphan_id}")
                    st.caption("该条目来自 data 目录附件，尚未在合同计划中建档。")
                    render_file_manager(orphan_id, orphan_customer, default_expanded=True, key_suffix="_orphan")

                # --- 场景2: 待规划 & 已规划 (Planning / Editing) ---
                elif sel_type in ['planning', 'done']:
                    # 获取该合同所有行
                    target_rows = fp_df[fp_df['合同号'] == sel_id]
                    if target_rows.empty:
                        st.error("数据未找到")
                    else:
                        first_row = target_rows.iloc[0]
                        status_now = first_row['状态']
                        oid_now = first_row.get('订单号', '')
                        
                        st.markdown(f"""
                        <div class="boss-plan-card">
                            <h3>🎯 规划详情: {sel_id}</h3>
                            <p><b>状态:</b> {status_now} {f'| <b>关联订单:</b> {oid_now}' if oid_now else ''}</p>
                            <p><b>客户:</b> {first_row['客户名']} | <b>交期:</b> {first_row['要求交期']}</p>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        # --- V7.7 Add File Preview (Collapsed) ---
                        render_file_manager(sel_id, first_row['客户名'], default_expanded=False, key_suffix="_plan")

                        changes_map = {}
                        
                        for idx, row in target_rows.iterrows():
                            model = row['机型']
                            qty_needed = int(float(row['排产数量']))
                            remark = row.get('备注', '')
                            
                            # --- 解析机型是否为加高 ---
                            is_high_req = "(加高)" in model
                            real_model = model.replace("(加高)", "")
                            req_label = f"🏗️ {real_model} [加高定制]" if is_high_req else f"⚙️ {real_model} [标准]"

                            st.markdown(f"#### {req_label} (需 {qty_needed} 台)")
                            if remark:
                                st.info(f"📝 **备注:** {remark}")
                            
                            # 解析旧配置
                            prev_alloc = parse_alloc_dict(row.get('指定批次/来源', {}))
                            
                            # --- 新增：显示实际配货进度 (Actual Allocation) ---
                            actual_alloc_info = ""
                            has_actual = False
                            if oid_now:
                                # 查找 inventory 中被此订单占用的
                                act_mask = (inventory_df['占用订单号'] == oid_now) & (inventory_df['机型'] == real_model)
                                if is_high_req:
                                    act_mask = act_mask & (inventory_df['机台备注/配置'].str.contains("加高", na=False))
                                else:
                                    act_mask = act_mask & (~inventory_df['机台备注/配置'].str.contains("加高", na=False))
                                
                                act_df = inventory_df[act_mask]
                                
                                if not act_df.empty:
                                    has_actual = True
                                    act_counts = act_df.groupby('批次号').size().to_dict()
                                    info_parts = []
                                    for b, c in act_counts.items():
                                        info_parts.append(f"{b}: {c}台")
                                    actual_alloc_info = f"✅ **实际已配:** {', '.join(info_parts)} (共 {len(act_df)} 台)"
                                else:
                                    actual_alloc_info = "ℹ️ 实际未配货"
                            
                            if has_actual:
                                # 恢复直观展示
                                st.write(actual_alloc_info)
                                # 同步按钮
                                if st.button("📥 载入实际配货到规划", key=f"sync_{idx}_{model}", help="将当前实际配货数量填入下方规划框"):
                                    # 构造新的配货字典
                                    new_alloc = {}
                                    for b, c in act_counts.items():
                                        if b == "无批次" or not b: new_alloc['现货(Spot)'] = c
                                        else: new_alloc[b] = c
                                    
                                    # 1. 更新当前行的 '指定批次/来源'
                                    fp_df.at[idx, '指定批次/来源'] = to_json_text(new_alloc)
                                    save_factory_plan(fp_df)
                                    
                                    # 2. 如果关联了订单，同步更新 Sales Order
                                    if oid_now:
                                        # 重新获取整个合同的 plan
                                        # 注意：这里只更新了当前 model 的 plan，其他 model 保持原样
                                        # 为了确保完整性，我们从 fp_df 重新构建整个合同的 plan string
                                        # 但 fp_df 在内存中可能还没包含其他 model 的最新改动（如果用户没点保存）
                                        # 这里是一个单点操作，我们假设只修改这一条
                                        
                                        # 获取该合同所有相关行（最新状态）
                                        related_rows = fp_df[fp_df['合同号'] == sel_id]
                                        all_plans_sync = {}
                                        for _, r_sync in related_rows.iterrows():
                                            model_sync = str(r_sync.get('机型', '')).strip()
                                            alloc_sync = parse_alloc_dict(r_sync.get('指定批次/来源', {}))
                                            if model_sync and alloc_sync:
                                                all_plans_sync[model_sync] = alloc_sync
                                        
                                        if oid_now in orders_df['订单号'].values:
                                            orders_df.loc[orders_df['订单号'] == oid_now, '指定批次/来源'] = [all_plans_sync]
                                            save_orders(orders_df)
                                    
                                    st.success("已同步实际配货数据！"); time.sleep(0.5); st.rerun()
                            else:
                                 st.caption(actual_alloc_info)

                            # 库存查询
                            # 1. Spot (Left): 仅包含 '库存中'
                            mask_spot = (
                                (inventory_df['机型'] == real_model) & 
                                (inventory_df['状态'] == '库存中') & 
                                (inventory_df['占用订单号'] == "")
                            )
                            if is_high_req:
                                mask_spot = mask_spot & (inventory_df['机台备注/配置'].str.contains("加高", na=False))
                            else:
                                mask_spot = mask_spot & (~inventory_df['机台备注/配置'].str.contains("加高", na=False))
                            
                            spot_df = inventory_df[mask_spot]
                            spot_count = len(spot_df)

                            # 2. Batch (Right): 仅包含 '待入库'
                            mask_batch = (
                                (inventory_df['机型'] == real_model) & 
                                (inventory_df['状态'] == '待入库') & 
                                (inventory_df['占用订单号'] == "")
                            )
                            if is_high_req:
                                mask_batch = mask_batch & (inventory_df['机台备注/配置'].str.contains("加高", na=False))
                            else:
                                mask_batch = mask_batch & (~inventory_df['机台备注/配置'].str.contains("加高", na=False))
                                
                            batch_df = inventory_df[mask_batch]
                            batch_stats = batch_df.groupby('批次号').size().to_dict()
                            
                            # --- 获取批次预计入库时间 ---
                            batch_dates = {}
                            if '预计入库时间' in batch_df.columns:
                                temp_dates = batch_df[['批次号', '预计入库时间']].drop_duplicates()
                                for _, r_d in temp_dates.iterrows():
                                    b_name = r_d['批次号']
                                    d_val = str(r_d['预计入库时间']).strip()
                                    if b_name not in batch_dates and d_val:
                                        batch_dates[b_name] = d_val
                            
                            c_r1, c_r2 = st.columns(2)
                            with c_r1:
                                val_spot = prev_alloc.get('现货(Spot)', 0)
                                alloc_spot = st.number_input(f"现货 (余{spot_count})", min_value=0, value=int(val_spot), key=f"plan_spot_{idx}")
                            
                            current_batch_alloc = {}
                            with c_r2:
                                all_batches = set(batch_stats.keys()) | set(k for k in prev_alloc.keys() if k != '现货(Spot)')
                                if not all_batches: st.caption("无批次库存")
                                else:
                                    for b in sorted(list(all_batches)):
                                        can_use = batch_stats.get(b, 0)
                                        
                                        # 构建显示标签
                                        label_text = f"批次 {b} (余{can_use})"
                                        arr_time = batch_dates.get(b, "")
                                        if arr_time:
                                            label_text += f" [📅 {arr_time}]"
                                        
                                        prev_val = prev_alloc.get(b, 0)
                                        val_b = st.number_input(label_text, min_value=0, value=int(prev_val), key=f"plan_b_{idx}_{b}")
                                        if val_b > 0: current_batch_alloc[b] = val_b
                            
                            total_alloc = alloc_spot + sum(current_batch_alloc.values())
                            st.progress(min(total_alloc / qty_needed, 1.0) if qty_needed > 0 else 0)
                            st.caption(f"已规划: {total_alloc} / {qty_needed}")
                            
                            # 构建保存串
                            this_plan = {}
                            if alloc_spot > 0: this_plan['现货(Spot)'] = alloc_spot
                            this_plan.update(current_batch_alloc)
                            
                            changes_map[idx] = this_plan
                            st.divider()

                        if st.button("💾 保存规划 (Save Plan)", type="primary"):
                            for idx, plan_obj in changes_map.items():
                                fp_df.at[idx, '指定批次/来源'] = to_json_text(plan_obj)
                                
                                if oid_now:
                                    try:
                                        model_name = fp_df.loc[idx, '机型']
                                        save_planning_record(oid_now, model_name, to_json_text(plan_obj))
                                    except Exception as e:
                                        print(f"Error saving to CSV: {e}")

                                if fp_df.loc[idx, '状态'] == '待规划':
                                    fp_df.loc[idx, '状态'] = '已规划'
                            
                            save_factory_plan(fp_df)
                            
                            if oid_now:
                                all_plans = {}
                                contract_rows = fp_df[fp_df['合同号'] == sel_id]
                                for _, r_plan in contract_rows.iterrows():
                                    model_name = str(r_plan.get('机型', '')).strip()
                                    alloc_data = parse_alloc_dict(r_plan.get('指定批次/来源', {}))
                                    if model_name and alloc_data:
                                        all_plans[model_name] = alloc_data
                                if oid_now in orders_df['订单号'].values:
                                    orders_df.loc[orders_df['订单号'] == oid_now, '指定批次/来源'] = [all_plans]
                                    save_orders(orders_df)
                                    st.success(f"已同步更新销售订单 {oid_now}！")
                                else:
                                    st.warning(f"关联订单 {oid_now} 在销售表中未找到，仅更新了规划表。")
                            else:
                                st.success("规划已保存！(等待销售下单引用)")
                            
                            time.sleep(1); st.rerun()
                        
                        if status_now == '已规划' and not oid_now:
                            if st.button("🚀 直通配货 (自动生成销售订单)", help="跳过销售确认，直接生成订单并进入配货"):
                                model_data = {}
                                all_plans = {}
                                note_combined = ""
                                for idx, row in target_rows.iterrows():
                                    m = row['机型']; q = int(float(row['排产数量']))
                                    model_data[m] = q
                                    if row.get('备注'): note_combined += f" {m}:{row['备注']}"
                                    alloc_data = parse_alloc_dict(row.get('指定批次/来源', {}))
                                    if alloc_data:
                                        all_plans[m] = alloc_data
                                new_oid = create_sales_order(
                                    customer=first_row['客户名'], agent=first_row['代理商'], model_data=model_data,
                                    note=note_combined, pack_option="未指定", delivery_time=first_row['要求交期'],
                                    source_batch=all_plans
                                )
                                fp_df.loc[fp_df['合同号'] == sel_id, '订单号'] = new_oid
                                fp_df.loc[fp_df['合同号'] == sel_id, '状态'] = '已转订单'
                                save_factory_plan(fp_df)
                                st.success(f"已自动生成订单 {new_oid}！")
                                time.sleep(1)
                                st.session_state.page = 'sales_alloc'
                                st.rerun()

                # --- 场景3: 独立手动订单 (Manual Orders) ---
                elif sel_type == 'manual_order':
                    target_order = orders_df[orders_df['订单号'] == sel_id]
                    if target_order.empty:
                        st.error("订单未找到")
                    else:
                        row = target_order.iloc[0]
                        cust = row['客户名']; agent = row['代理商']
                        
                        st.markdown(f"""
                        <div class="boss-plan-card">
                            <h3>📝 独立订单规划: {sel_id}</h3>
                            <p><b>客户:</b> {cust} | <b>代理:</b> {agent}</p>
                            <p><b>发货时间:</b> {row['发货时间']} | <b>备注:</b> {row['备注']}</p>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        # 解析需求机型
                        reqs = parse_requirements(row['需求机型'], row['需求数量'])
                        
                        # 解析已有的 source plan
                        existing_plan_map = parse_plan_map(row.get('指定批次/来源', {}))

                        new_plans = {}
                        
                        for model_key, qty in reqs.items():
                            # --- V7.1 核心解析逻辑 ---
                            is_high_req = "(加高)" in model_key
                            real_model = model_key.replace("(加高)", "")
                            req_label = f"🏗️ {real_model} [加高定制]" if is_high_req else f"⚙️ {real_model} [标准]"
                            
                            st.markdown(f"#### {req_label} (需 {qty} 台)")
                            
                            prev_alloc = existing_plan_map.get(model_key, {})
                            
                            # --- 新增：显示实际配货进度 (Actual Allocation) for Manual Orders ---
                            actual_alloc_info = ""
                            has_actual = False
                            
                            # 查找 inventory 中被此订单占用的
                            # V7.1: 使用 real_model 并结合备注过滤
                            act_mask = (inventory_df['占用订单号'] == sel_id) & (inventory_df['机型'] == real_model)
                            if is_high_req:
                                act_mask = act_mask & (inventory_df['机台备注/配置'].str.contains("加高", na=False))
                            else:
                                act_mask = act_mask & (~inventory_df['机台备注/配置'].str.contains("加高", na=False))
                                
                            act_df = inventory_df[act_mask]
                            
                            if not act_df.empty:
                                has_actual = True
                                act_counts = act_df.groupby('批次号').size().to_dict()
                                info_parts = []
                                for b, c in act_counts.items():
                                    info_parts.append(f"{b}: {c}台")
                                actual_alloc_info = f"✅ **实际已配:** {', '.join(info_parts)} (共 {len(act_df)} 台)"
                            else:
                                actual_alloc_info = "ℹ️ 实际未配货"
                            
                            if has_actual:
                                # 恢复直观展示
                                st.write(actual_alloc_info)
                                # 同步按钮
                                if st.button("📥 载入实际配货到规划", key=f"sync_m_{sel_id}_{model_key}", help="将当前实际配货数量填入下方规划框"):
                                    # 构造新的配货字典
                                    new_alloc = {}
                                    for b, c in act_counts.items():
                                        if b == "无批次" or not b: new_alloc['现货(Spot)'] = c
                                        else: new_alloc[b] = c
                                    
                                    # 更新 Manual Order 的指定批次/来源
                                    # 1. 更新内存 map
                                    existing_plan_map[model_key] = new_alloc
                                    
                                    # 2. 重新构建整个订单的 plan string
                                    # Manual Order 的格式是 "ModelA:{...}; ModelB:{...}"
                                    all_plans_sync = {}
                                    for m_key in reqs.keys():
                                        alloc_data = existing_plan_map.get(m_key, {})
                                        if alloc_data:
                                            all_plans_sync[m_key] = alloc_data
                                    
                                    orders_df.loc[orders_df['订单号'] == sel_id, '指定批次/来源'] = [all_plans_sync]
                                    save_orders(orders_df)
                                    st.success("已同步实际配货数据！"); time.sleep(0.5); st.rerun()
                            else:
                                 st.caption(actual_alloc_info)

                            # 库存查询
                            # 1. Spot (Left): 仅包含 '库存中'
                            mask_spot = (
                                (inventory_df['机型'] == real_model) & 
                                (inventory_df['状态'] == '库存中') & 
                                (inventory_df['占用订单号'] == "")
                            )
                            if is_high_req:
                                mask_spot = mask_spot & (inventory_df['机台备注/配置'].str.contains("加高", na=False))
                            else:
                                mask_spot = mask_spot & (~inventory_df['机台备注/配置'].str.contains("加高", na=False))
                            
                            spot_df = inventory_df[mask_spot]
                            spot_count = len(spot_df)

                            # 2. Batch (Right): 仅包含 '待入库'
                            mask_batch = (
                                (inventory_df['机型'] == real_model) & 
                                (inventory_df['状态'] == '待入库') & 
                                (inventory_df['占用订单号'] == "")
                            )
                            if is_high_req:
                                mask_batch = mask_batch & (inventory_df['机台备注/配置'].str.contains("加高", na=False))
                            else:
                                mask_batch = mask_batch & (~inventory_df['机台备注/配置'].str.contains("加高", na=False))
                                
                            batch_df = inventory_df[mask_batch]
                            batch_stats = batch_df.groupby('批次号').size().to_dict()
                            
                            # --- 获取批次预计入库时间 ---
                            batch_dates = {}
                            if '预计入库时间' in batch_df.columns:
                                temp_dates = batch_df[['批次号', '预计入库时间']].drop_duplicates()
                                for _, r_d in temp_dates.iterrows():
                                    b_name = r_d['批次号']
                                    d_val = str(r_d['预计入库时间']).strip()
                                    if b_name not in batch_dates and d_val:
                                        batch_dates[b_name] = d_val
                            
                            c_r1, c_r2 = st.columns(2)
                            with c_r1:
                                val_spot = prev_alloc.get('现货(Spot)', 0)
                                alloc_spot = st.number_input(f"现货 (余{spot_count})", min_value=0, value=int(val_spot), key=f"m_spot_{model_key}")
                            
                            current_batch_alloc = {}
                            with c_r2:
                                all_batches = set(batch_stats.keys()) | set(k for k in prev_alloc.keys() if k != '现货(Spot)')
                                if not all_batches: st.caption("无批次库存")
                                else:
                                    for b in sorted(list(all_batches)):
                                        can_use = batch_stats.get(b, 0)
                                        
                                        # 构建显示标签
                                        label_text = f"批次 {b} (余{can_use})"
                                        arr_time = batch_dates.get(b, "")
                                        if arr_time:
                                            label_text += f" [📅 {arr_time}]"
                                        
                                        prev_val = prev_alloc.get(b, 0)
                                        val_b = st.number_input(label_text, min_value=0, value=int(prev_val), key=f"m_b_{model_key}_{b}")
                                        if val_b > 0: current_batch_alloc[b] = val_b
                            
                            total_alloc = alloc_spot + sum(current_batch_alloc.values())
                            st.progress(min(total_alloc / qty, 1.0) if qty > 0 else 0)
                            st.caption(f"已规划: {total_alloc} / {qty}")
                            
                            this_plan = {}
                            if alloc_spot > 0: this_plan['现货(Spot)'] = alloc_spot
                            this_plan.update(current_batch_alloc)
                            new_plans[model_key] = this_plan
                            st.divider()
                            
                        if st.button("💾 保存订单规划", type="primary"):
                            orders_df.loc[orders_df['订单号'] == sel_id, '指定批次/来源'] = [new_plans]
                            save_orders(orders_df)

                            try:
                                for m, c in new_plans.items():
                                    save_planning_record(sel_id, m, to_json_text(c))
                            except Exception as e:
                                print(f"Error saving manual plan to CSV: {e}")

                            st.success("订单规划已保存！"); time.sleep(1); st.rerun()

    # --- 🏭 合同管理 (Contract Management) ---
