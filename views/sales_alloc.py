import re
import time

import pandas as pd
import streamlit as st

from core.navigation import go_home
from core.permissions import check_access
from crud.inventory import get_data
from crud.orders import allocate_inventory, get_orders, revert_to_inbound
from crud.planning import get_planning_records
from utils.parsers import parse_requirements


def render_sales_alloc():
    check_access('SALES_ALLOC')
    c_back, c_title = st.columns([2, 8])
    with c_back: st.button("⬅️ 返回", on_click=go_home, use_container_width=True)
    with c_title: st.header("📦 订单智能配货")

    orders = get_orders()
    inventory = get_data()

    if not inventory.empty:
        shipped_total_stats = inventory[inventory['状态'] == '已出库'].groupby('占用订单号').size().to_dict()
    else: shipped_total_stats = {}

    active_orders = orders.iloc[::-1]

    # 过滤掉已删除的订单
    if 'status' in active_orders.columns:
        active_orders = active_orders[active_orders['status'] != 'deleted']

    if active_orders.empty: st.info("暂无订单。")
    else:
        # 增加筛选：仅显示有老板指示的订单
        filter_has_plan = st.checkbox("🔍 仅显示有老板指示的订单", value=False)

        for idx, row in active_orders.iterrows():
            oid = row['订单号']
            customer = row['客户名']; agent = row['代理商']; note = str(row['备注'])
            
            # 获取发货时间
            raw_date = row.get('发货时间', '')
            delivery_date = str(raw_date) if pd.notna(raw_date) and str(raw_date).strip() != '' else "未指定"
            
            # --- 显示老板的规划指示 ---
            # V7.2: 优先从 CSV 读取规划记录，解决覆盖更新问题
            source_plan = ""
            try:
                plan_records = get_planning_records()
                order_plans = plan_records[plan_records['order_id'] == oid]
                
                if not order_plans.empty:
                    combined_plans = []
                    for _, pr in order_plans.iterrows():
                        p_info = str(pr['plan_info'])
                        p_model = str(pr['model'])
                        combined_plans.append(f"{p_model}:{p_info}")
                    source_plan = "; ".join(combined_plans)
                else:
                    source_plan = row.get('指定批次/来源', '')
            except Exception as e:
                print(f"Error loading plan from CSV: {e}")
                source_plan = row.get('指定批次/来源', '')

            plan_html = ""
            has_valid_plan = False
            
            if source_plan:
                # 智能过滤：去除空指示 (例如 "Model: {}")
                raw_items = str(source_plan).split(";")
                valid_items = []
                for item in raw_items:
                    s_item = item.strip()
                    if not s_item: continue
                    
                    # 检查是否实质为空 (以 {} 或 [] 结尾)
                    # 去除所有空格后检查
                    clean_check = s_item.replace(" ", "")
                    if clean_check.endswith("{}") or clean_check.endswith("[]"):
                        continue
                    # 简单的 Key: 格式也忽略
                    if clean_check.endswith(":"):
                        continue
                        
                    valid_items.append(s_item)
                
                if valid_items:
                    has_valid_plan = True
                    # 重新组合并美化
                    cleaned_source = "; ".join(valid_items)
                    display_plan = cleaned_source.replace(";", "<br>").replace("{", " [").replace("}", "] ").replace("'", "")
                    plan_html = f"<div style='background:#FFF8DC; color:#8B4500; padding:5px; border-radius:4px; font-size:14px;'><b>👑 老板指示:</b><br>{display_plan}</div>"
            
            # 筛选逻辑
            if filter_has_plan and not has_valid_plan:
                continue

            requirements = parse_requirements(row['需求机型'], row['需求数量'])
            total_req_qty = sum(requirements.values())
            
            current_alloc_df = inventory[inventory['占用订单号'] == oid]
            current_total_filled = len(current_alloc_df)
            shipped_count = shipped_total_stats.get(oid, 0)
            
            if shipped_count >= total_req_qty and total_req_qty > 0: continue
            
            # 使用单行 HTML 避免 Markdown 解析缩进问题
            st.markdown(f"""<div class="order-card" style="border:1px solid #ddd; padding:10px; border-radius:5px; margin-bottom:10px;"><h4>📜 {oid} | {customer} (代理: {agent})</h4><p><b>📅 发货时间: {delivery_date}</b></p>{plan_html}<p><b>进度: {current_total_filled} / {total_req_qty}</b> (已发: {shipped_count})</p><p style="color:gray; font-size:14px;">📝 {note}</p></div>""", unsafe_allow_html=True)
            
            for model_key, target_qty in requirements.items():
                # --- V7.1 核心解析 ---
                is_high_req = "(加高)" in model_key
                real_model = model_key.replace("(加高)", "")
                
                # 显示给用户的标题
                display_name = f"{real_model} (加高)" if is_high_req else real_model
                
                # 获取该特定需求已分配的数量
                alloc_mask = (current_alloc_df['机型'] == real_model)
                if is_high_req:
                    alloc_mask = alloc_mask & (current_alloc_df['机台备注/配置'].str.contains("加高", na=False))
                else:
                    alloc_mask = alloc_mask & (~current_alloc_df['机台备注/配置'].str.contains("加高", na=False))
                
                allocated_for_model = len(current_alloc_df[alloc_mask])
                
                remaining = target_qty - allocated_for_model
                status_icon = "✅" if remaining <= 0 else "⏳"
                
                with st.expander(f"{status_icon} 机型: {display_name} | 缺: {max(0, remaining)}", expanded=(remaining > 0)):
                    # --- 显示机型备注 ---
                    model_remark = ""
                    try:
                        # 尝试从订单备注中提取 "Model:Remark"
                        # 优先匹配 model_key (原始键), 然后尝试 display_name
                        keys_to_try = [model_key, display_name]
                        for k in keys_to_try:
                            if not k: continue
                            safe_k = re.escape(k)
                            # 匹配: (开头或空格)Key:(内容)(直到 空格+Word+: 或 结尾)
                            pattern = rf"(?:^|\s){safe_k}:(.*?)(?=\s[\w\(\)\-]+\:|{'$'})"
                            match = re.search(pattern, note)
                            if match:
                                model_remark = match.group(1).strip()
                                break
                    except: pass
                    
                    if model_remark:
                        st.info(f"📝 **备注:** {model_remark}")
                    
                    # --- V7.2 Update: 扩展加高定义 ---
                    # 如果订单备注/机台备注中包含 "加高"，也视为加高需求
                    if "加高" in model_remark:
                        is_high_req = True
                        st.caption("ℹ️ 检测到备注包含“加高”，自动匹配加高库存。")

                    if remaining > 0:
                        # --- V7.1 库存过滤核心 ---
                        mask = (
                            (inventory['机型'] == real_model) & 
                            (inventory['状态'].isin(['待入库', '库存中'])) & 
                            (inventory['占用订单号'] == "")
                        )
                        # --- V7.3 统一加高判断逻辑 ---
                        # 定义：任何字段包含 "加高" 即视为加高库存
                        is_stock_high = (
                            inventory['机型'].str.contains("加高", na=False) |
                            inventory['机台备注/配置'].str.contains("加高", na=False) |
                            inventory['订单备注'].str.contains("加高", na=False)
                        )

                        if is_high_req:
                            mask = mask & is_stock_high
                            st.info("🎯 已自动过滤为：【加高】机器")
                        else:
                            # 需求是标准：排除所有“加高”特征的
                            mask = mask & (~is_stock_high)
                        
                        available_stock = inventory[mask]
                        
                        if available_stock.empty:
                            st.warning(f"⚠️ {display_name} 暂无可用库存")
                        else:
                            # 增加批次筛选功能，方便员工按老板指示找货
                            batches_avail = available_stock['批次号'].unique()
                            c_filter1, c_filter2 = st.columns([1, 2])
                            with c_filter1:
                                filter_b = st.selectbox("按批次筛选 (参考老板指示)", ["全部"] + list(batches_avail), key=f"filter_b_{oid}_{model_key}")
                            
                            filtered_stock = available_stock
                            if filter_b != "全部":
                                filtered_stock = available_stock[available_stock['批次号'] == filter_b]

                            st.markdown(f"**勾选配货 (需 {remaining} 台):**")
                            select_pool = filtered_stock[['批次号', '流水号', '状态', '机台备注/配置', '订单备注']].reset_index(drop=True)
                            # 虽然是单机型，但也按批次排序
                            select_pool = select_pool.sort_values(by=['批次号'], ascending=False)
                            
                            select_pool.insert(0, "✅ 选择", False)
                            
                            key_alloc = f"alloc_{oid}_{model_key}"
                            edited_pool = st.data_editor(select_pool, key=key_alloc, hide_index=True, use_container_width=True, height=200)
                            
                            selected_rows = edited_pool[edited_pool['✅ 选择'] == True]
                            if not selected_rows.empty:
                                if st.button(f"🚀 确认分配 {len(selected_rows)} 台", key=f"btn_go_{key_alloc}", type="primary"):
                                    allocate_inventory(oid, customer, agent, selected_rows['流水号'].tolist())
                                    st.success("成功！"); time.sleep(0.5); st.rerun()

            # 撤回逻辑 (保持原样)
            if current_total_filled > 0:
                with st.expander(f"🔄 配货撤回 ({current_total_filled})", expanded=False):
                    revertable = inventory[(inventory['占用订单号'] == oid) & (inventory['状态'] != '已出库')].copy()
                    if not revertable.empty:
                        revertable.insert(0, "❌", False)
                        res_rev = st.data_editor(revertable[['❌', '批次号', '流水号', '机型']], key=f"rev_{oid}", hide_index=True)
                        to_rev = res_rev[res_rev['❌'] == True]
                        if not to_rev.empty and st.button("确认撤回", key=f"btn_rev_{oid}"):
                            revert_to_inbound(to_rev['流水号'].tolist()); st.rerun()

    st.divider()
    render_module_logs(["配货锁定", "自动入库", "撤回"])



    # --- 🚛 发货复核 ---
