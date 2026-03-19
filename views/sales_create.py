import ast
import time

import pandas as pd
import streamlit as st

from config import CUSTOM_MODEL_ORDER
from core.navigation import go_home
from core.permissions import check_access
from crud.inventory import get_data
from crud.orders import create_sales_order, get_orders, save_orders
from crud.planning import get_factory_plan, save_factory_plan
from utils.formatters import get_model_rank
from utils.parsers import parse_requirements


def render_sales_create():
    check_access('SALES_CREATE')
    c_back, c_title = st.columns([2, 8])
    with c_back: st.button("⬅️ 返回", on_click=go_home, use_container_width=True)
    with c_title: st.header("📝 销售订单管理")

    # --- 辅助函数：获取全量机型列表 (含0库存) ---
    def get_all_models(df_source):
        all_models = set(CUSTOM_MODEL_ORDER)
        if not df_source.empty:
            all_models.update(df_source['机型'].unique())
        return sorted(list(all_models), key=get_model_rank)

    df_inv = get_data()
    active_inv = df_inv[df_inv['状态'] != '已出库']

    # 使用全量模型列表
    available_models = get_all_models(df_inv)

    tab_new, tab_import, tab_manage = st.tabs(["➕ 手动下单", "导入已规划合同 ", "订单查询与管理"])

    with tab_new:
        # --- Reset Logic ---
        if st.session_state.get("reset_manual_order_flag", False):
            for key in ["mo_cust", "mo_agent", "mo_note", "mo_source", "mo_date", "mo_pack"]:
                if key in st.session_state: del st.session_state[key]
            
            if "manual_order_editor" in st.session_state: del st.session_state["manual_order_editor"]
            st.session_state.manual_order_df = pd.DataFrame(
                [{"机型": available_models[0] if available_models else "", "数量": 1, "加高?": False, "备注": ""}]
            )
            st.session_state["reset_manual_order_flag"] = False

        # --- V7.1 Update: 使用 Data Editor 表格录入 (支持多行/加高) ---
        st.markdown("##### 1. 填写订单详情")
        c_cust, c_agent = st.columns(2)
        with c_cust: inp_customer = st.text_input("客户信息 (Customer)", key="mo_cust")
        with c_agent: inp_agent = st.text_input("代理商 (Agent)", key="mo_agent")

        st.markdown("##### 2. 录入机型")
        st.caption("请在下方表格中添加机型。支持重复添加同一机型（例如一行标准、一行加高）。")

        if 'manual_order_df' not in st.session_state:
            st.session_state.manual_order_df = pd.DataFrame(
                [{"机型": available_models[0] if available_models else "", "数量": 1, "加高?": False, "备注": ""}]
            )

        edited_df = st.data_editor(
            st.session_state.manual_order_df,
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "机型": st.column_config.SelectboxColumn("机型", options=available_models, required=True),
                "数量": st.column_config.NumberColumn("数量", min_value=1, default=1, required=True),
                "加高?": st.column_config.CheckboxColumn("加高?", default=False),
                "备注": st.column_config.TextColumn("单行备注")
            },
            key="manual_order_editor"
        )
        
        # --- [新增] 深度撞单检测 (Deep Conflict Check) ---
        conflict_found = False
        if inp_customer and not edited_df.empty:
             # 1. 准备用户输入的数据摘要
             user_items = []
             has_user_input = False
             for _, row in edited_df.iterrows():
                 m = row.get('机型')
                 if not m: continue
                 has_user_input = True
                 q = int(row.get('数量', 1))
                 is_h = row.get('加高?', False)
                 final_m = f"{m}(加高)" if is_h else m
                 note = str(row.get('备注', '')).strip()
                 user_items.append({'model': final_m, 'qty': q, 'note': note})
             
             if has_user_input:
                 risk_details = []
                 fp_check = get_factory_plan()
                 # 筛选潜在合同 (状态符合 + 客户名包含)
                 # 修复 re.error: 使用 regex=False 进行纯文本匹配
                 potential_contracts = fp_check[
                     (fp_check['状态'].isin(['已规划', '已审批', '未下单'])) &
                     (fp_check['客户名'].str.contains(inp_customer, na=False, regex=False))
                 ]
                 
                 if not potential_contracts.empty:
                     # 按合同号分组比对
                     for cid, grp in potential_contracts.groupby('合同号'):
                         contract_score = 0
                         match_reasons = []
                         
                         # 构建合同的机型清单
                         c_items = []
                         for _, c_row in grp.iterrows():
                             try: c_q = int(float(c_row['排产数量']))
                             except: c_q = 0
                             c_items.append({'model': c_row['机型'], 'qty': c_q, 'note': str(c_row.get('备注', ''))})
                         
                         # 比对逻辑: 机型匹配+2分, 数量匹配+3分, 备注相似+2分. 阈值>3
                         for u_item in user_items:
                             for c_item in c_items:
                                 if u_item['model'].upper() == c_item['model'].upper():
                                     # 机型匹配
                                     item_score = 2
                                     reason_part = f"{u_item['model']}"
                                     
                                     if u_item['qty'] == c_item['qty']:
                                         item_score += 3
                                         reason_part += f" x{u_item['qty']}(数量一致)"
                                     else:
                                         reason_part += f" (用户:{u_item['qty']} vs 合同:{c_item['qty']})"
                                     
                                     if u_item['note'] and c_item['note'] and (u_item['note'] in c_item['note'] or c_item['note'] in u_item['note']):
                                          item_score += 2
                                          reason_part += " [备注相似]"
                                     
                                     if item_score > 3: # 仅当匹配度较高时才计入风险
                                         contract_score += item_score
                                         match_reasons.append(reason_part)
                         
                         if contract_score >= 5: # 整体风险阈值
                             risk_details.append(f"📄 **合同 {cid}**: 包含 {', '.join(set(match_reasons))}")

                 # 2. 检测现有订单 (Sales Orders)
                 existing_orders = get_orders()
                 if not existing_orders.empty:
                    # 查找同客户名的订单
                    # 修复 re.error: 使用 regex=False 进行纯文本匹配
                    potential_orders = existing_orders[
                         existing_orders['客户名'].str.contains(inp_customer, na=False, regex=False) | 
                         existing_orders['客户名'].apply(lambda x: inp_customer in str(x))
                    ]
                    
                    if not potential_orders.empty:
                         # user_items 转为 dict: {model_key: qty}
                         user_reqs_check = {}
                         for u in user_items:
                             user_reqs_check[u['model']] = user_reqs_check.get(u['model'], 0) + u['qty']
                         
                         for _, ord_row in potential_orders.iterrows():
                             # 解析订单需求
                             ord_reqs = parse_requirements(ord_row['需求机型'], ord_row['需求数量'])
                             
                             if user_reqs_check == ord_reqs:
                                 o_time = ord_row.get('下单时间', '未知时间')
                                 risk_details.append(f"📦 **现有订单 {ord_row['订单号']}**: 内容完全一致！(下单时间: {o_time})")

                 if risk_details:
                     st.error(
                         f"🚨 **深度撞单预警**：检测到以下合同/订单与当前录入高度雷同！\n\n" + 
                         "\n".join(risk_details) + 
                         "\n\n👉 请务必检查！如需强制下单，请勾选下方的【确认】框。"
                     )
                     conflict_found = True

        st.markdown("---")
        c2_1, c2_2 = st.columns([3, 1])
        with c2_1:
            inp_note_global = st.text_input("订单总备注", key="mo_note")
            inp_delivery_date = st.date_input("发货时间 (选填)", value=None, key="mo_date")
        with c2_2:
            st.write(""); st.write("")
            need_pack = st.checkbox("需要包装", key="mo_pack")
        
        inp_source = st.text_input("指定批次/来源 (初始备注)", placeholder="如：优先现货", key="mo_source")
        
        confirm_force = False
        if conflict_found:
             confirm_force = st.checkbox("⚠️ 我确认这不是重复下单 (I confirm this is NOT a duplicate)", key="force_submit_duplicate")

        if st.button("✅ 生成订单", type="primary", use_container_width=True):
            if conflict_found and not confirm_force:
                 st.error("❌ 操作已拦截：检测到重复下单风险。请勾选上方的确认框以继续。")
                 st.stop()
            
            if not inp_customer: 
                st.error("请输入客户信息")
            elif edited_df.empty:
                st.warning("请至少添加一行机型数据")
            else:
                model_qty_map = {}
                combined_notes = []
                if inp_note_global: combined_notes.append(inp_note_global)
                
                has_valid_row = False
                for _, row in edited_df.iterrows():
                    m = row.get('机型')
                    q = int(row.get('数量', 1))
                    is_h = row.get('加高?', False)
                    r_note = str(row.get('备注', '')).strip()
                    
                    if not m: continue
                    has_valid_row = True
                    
                    final_key = f"{m}(加高)" if is_h else m
                    model_qty_map[final_key] = model_qty_map.get(final_key, 0) + q
                    
                    if r_note:
                        combined_notes.append(f"[{final_key}: {r_note}]")
                
                if not has_valid_row:
                    st.error("有效机型数据为空")
                else:
                    final_note_str = " ".join(combined_notes)
                    pack_opt = "需要包装" if need_pack else "不包装"
                    delivery_str = inp_delivery_date.strftime("%Y-%m-%d") if inp_delivery_date else ""
                    
                    oid = create_sales_order(inp_customer, inp_agent, model_qty_map, final_note_str, pack_opt, delivery_str, inp_source)
                    
                    # Set flag to reset on next run
                    st.session_state["reset_manual_order_flag"] = True
                    
                    st.success(f"订单已生成: {oid}"); time.sleep(1); st.rerun()

    with tab_import:
        st.subheader("📥 导入已规划合同 (Import Planned Contracts)")
        fp_df = get_factory_plan()
        if "客户名" not in fp_df.columns: fp_df["客户名"] = ""
        
        # 筛选 '已规划' 的合同
        planned_contracts = fp_df[fp_df['状态'] == '已规划'].copy()
        
        if planned_contracts.empty:
            st.info("暂无已规划的合同")
        else:
            # 显示列表
            st.dataframe(planned_contracts[["合同号", "客户名", "机型", "排产数量", "要求交期", "备注"]], use_container_width=True, hide_index=True)
            
            st.divider()
            
            # --- 新逻辑：按合同号聚合 ---
            # 1. 获取唯一合同号
            unique_contracts = planned_contracts['合同号'].unique()
            
            # 2. 构建选项
            contract_opts = []
            contract_map = {} # label -> contract_id
            
            for cid in unique_contracts:
                c_rows = planned_contracts[planned_contracts['合同号'] == cid]
                cust = c_rows.iloc[0]['客户名']
                # 汇总机型
                models_list = c_rows['机型'].unique()
                total_qty = c_rows['排产数量'].astype(float).sum()
                
                label = f"{cid} | {cust} | 共 {int(total_qty)} 台 ({len(models_list)} 款机型)"
                contract_opts.append(label)
                contract_map[label] = cid

            # --- V7.3 Update: 支持多选合并 ---
            sel_strs = st.multiselect("选择要转换/合并的合同 (支持多选)", contract_opts)
            
            if sel_strs:
                sel_cids = [contract_map[s] for s in sel_strs]
                
                # 获取所有选中合同的行
                all_target_rows = planned_contracts[planned_contracts['合同号'].isin(sel_cids)]
                
                # 基础信息取第一个合同的作为默认值
                first_row = all_target_rows.iloc[0]
                
                # 检查客户是否一致
                unique_customers = all_target_rows['客户名'].unique()
                if len(unique_customers) > 1:
                    st.warning(f"⚠️ 注意：您选择了不同客户的合同进行合并 ({', '.join(unique_customers)})，请确认是否正确。")
                
                st.markdown("#### 📝 确认合并订单信息 (可修改)")
                with st.form("confirm_planned_order"):
                    c1, c2 = st.columns(2)
                    with c1: 
                        new_cust = st.text_input("客户名", value=first_row.get('客户名', ''))
                        new_agent = st.text_input("代理商", value=first_row.get('代理商', ''))
                    with c2:
                        new_delivery = st.text_input("发货时间/交期", value=first_row.get('要求交期', ''))
                        new_pack = st.checkbox("需要包装", value=False)
                    
                    st.write("**包含机型及数量 (合并汇总):**")
                    
                    # --- 准备合并数据 ---
                    model_lines = []
                    # 这里的 target_rows 包含所有选中的合同行
                    for idx, row in all_target_rows.iterrows():
                        raw_model = row['机型']
                        is_h = "(加高)" in raw_model
                        base_m = raw_model.replace("(加高)", "")
                        
                        # 查找是否已存在该机型 (为了UI合并显示，避免列表太长，但为了保留原始备注，最好还是列出来?)
                        # 用户需求是合并出货。
                        # 如果我们把相同机型合并成一行，备注怎么处理？
                        # 方案：不合并行，罗列所有行，用户确认总数。或者：按机型合并，备注拼接。
                        # 这里选择：不合并行，让用户看到每一笔来源，这样更清晰。
                        # 但为了方便，可以在表格里加一列 "来源合同"
                        
                        model_lines.append({
                            "来源合同": row['合同号'],
                            "机型": base_m,
                            "加高?": is_h,
                            "数量": int(float(row['排产数量'])),
                            "原备注": row.get('备注', ''),
                            "__idx": idx
                        })
                    
                    # 使用 data_editor
                    df_models_confirm = pd.DataFrame(model_lines)
                    edited_models = st.data_editor(
                        df_models_confirm[['来源合同', '机型', '加高?', '数量', '原备注']],
                        key="editor_contract_models",
                        use_container_width=True,
                        disabled=["来源合同", "机型", "原备注"],
                        column_config={
                            "加高?": st.column_config.CheckboxColumn(
                                "加高?",
                                help="勾选后将自动添加 (加高) 后缀",
                                default=False,
                            ),
                            "数量": st.column_config.NumberColumn("数量", min_value=1)
                        }
                    )
                    
                    # 构建默认备注（包含各机型的备注）
                    default_note = ""
                    # 简单的去重合并备注
                    seen_notes = set()
                    for idx, row in all_target_rows.iterrows():
                         r_note = str(row.get('备注', '')).strip()
                         if r_note and r_note not in seen_notes:
                             cid_prefix = f"[{row['合同号']}] " if len(sel_cids) > 1 else ""
                             default_note += f"{cid_prefix}{r_note} "
                             seen_notes.add(r_note)

                    new_note = st.text_area("订单总备注", value=default_note.strip())
                    
                    if st.form_submit_button("🚀 确认生成合并订单 (Confirm Merge)", type="primary"):
                        pack_opt = "需要包装" if new_pack else "不包装"
                        
                        # 1. 收集机型数据 (合并同类项)
                        final_model_data = {}
                        
                        for _, m_row in edited_models.iterrows():
                            m_name = m_row['机型']
                            is_h = m_row['加高?']
                            final_name = f"{m_name}(加高)" if is_h else m_name
                            
                            m_qty = int(m_row['数量'])
                            final_model_data[final_name] = final_model_data.get(final_name, 0) + m_qty
                        
                        # 2. 合并 Source Batch (Plan String)
                        # 必须解析 -> 合并 -> 序列化，防止覆盖
                        merged_plan_map = {} # {Model: {Batch: Qty}}
                        
                        for idx, row in all_target_rows.iterrows():
                            p_str = str(row.get('指定批次/来源', ''))
                            if not p_str: continue
                            
                            # 解析单个 plan string (e.g. "ModelA:{...}; ModelB:{...}")
                            parts = p_str.split(";")
                            for part in parts:
                                if ":" in part:
                                    try:
                                        m_key, content = part.split(":", 1)
                                        m_key = m_key.strip()
                                        alloc_dict = ast.literal_eval(content.strip())
                                        
                                        if m_key not in merged_plan_map:
                                            merged_plan_map[m_key] = {}
                                        
                                        # Merge alloc_dict
                                        for batch, qty in alloc_dict.items():
                                            merged_plan_map[m_key][batch] = merged_plan_map[m_key].get(batch, 0) + int(qty)
                                    except: pass
                        
                        # 序列化
                        all_plans_final = []
                        for m_key, alloc_data in merged_plan_map.items():
                            all_plans_final.append(f"{m_key}:{str(alloc_data)}")
                            
                        combined_plan_str = "; ".join(all_plans_final)
                        
                        # 3. 创建订单
                        new_oid = create_sales_order(
                            customer=new_cust,
                            agent=new_agent,
                            model_data=final_model_data,
                            note=new_note,
                            pack_option=pack_opt,
                            delivery_time=new_delivery,
                            source_batch=combined_plan_str
                        )
                        
                        # 4. 更新所有合同状态
                        fp_df.loc[fp_df['合同号'].isin(sel_cids), '状态'] = '已转订单'
                        fp_df.loc[fp_df['合同号'].isin(sel_cids), '订单号'] = new_oid
                        save_factory_plan(fp_df)
                        
                        st.success(f"已生成合并订单: {new_oid}！包含 {len(sel_cids)} 份合同。"); time.sleep(1); st.rerun()

    with tab_manage:
        # 1. 获取数据
        q_orders = get_orders()
        df_inv = get_data()
        
        # 2. 计算订单完成度
        if not df_inv.empty:
            shipped_stats = df_inv[df_inv['状态'] == '已出库'].groupby('占用订单号').size().to_dict()
        else: shipped_stats = {}
        
        def check_order_status(oid, req_qty_str, db_status):
            # 优先判断数据库标记的状态
            if str(db_status) == 'deleted': return 'deleted'
            
            if not oid: return "unknown"
            s_qty = shipped_stats.get(oid, 0)
            try: r_qty = int(float(req_qty_str))
            except: r_qty = 999999
            
            if s_qty >= r_qty and r_qty > 0: return "completed"
            return "active"

        # 3. 筛选器
        st.markdown("#### 🔍 订单查询与管理")
        
        # 4. 过滤数据
        if not q_orders.empty:
            # 添加状态列辅助筛选
            q_orders['__status'] = q_orders.apply(lambda r: check_order_status(r['订单号'], r['需求数量'], r.get('status', '')), axis=1)
            
            # --- V7.2 新增：按月份筛选 ---
            # 确保下单时间为 datetime
            q_orders['下单时间_dt'] = pd.to_datetime(q_orders['下单时间'], errors='coerce')
            q_orders['month_str'] = q_orders['下单时间_dt'].dt.strftime('%Y-%m')
            
            available_months = sorted(q_orders['month_str'].dropna().unique().tolist(), reverse=True)
            month_opts = ["全部"] + available_months
            
            c_f1, c_f2 = st.columns([3, 1])
            with c_f1:
                filter_status = st.radio("订单状态筛选", ["进行中 (Active)", "往期/已完结 (Completed)", "已删除 (Deleted)"], horizontal=True)
            with c_f2:
                sel_month = st.selectbox("📅 按下单月份筛选", month_opts)
            
            target_status = "active"
            if "已完结" in filter_status: target_status = "completed"
            elif "已删除" in filter_status: target_status = "deleted"
            
            # 构建过滤掩码
            mask = (q_orders['__status'] == target_status)
            if sel_month != "全部":
                mask = mask & (q_orders['month_str'] == sel_month)
            
            view_df = q_orders[mask].copy()
            
            # 搜索框
            search_txt = st.text_input("搜索订单 (订单号/客户/代理)", key="manage_search")
            if search_txt:
                s = search_txt.lower()
                view_df = view_df[
                    view_df['订单号'].str.lower().str.contains(s, na=False) |
                    view_df['客户名'].str.lower().str.contains(s, na=False) |
                    view_df['代理商'].str.lower().str.contains(s, na=False)
                ]
            
            # 5. 显示与编辑
            if view_df.empty:
                st.info("无相关订单数据")
            else:
                # 倒序显示
                view_df = view_df.iloc[::-1]
                
                # 如果是“进行中”订单，允许编辑
                if target_status == "active":
                    st.caption(f"共找到 {len(view_df)} 个进行中订单。支持直接编辑【备注】和【发货时间】，勾选后可删除。")
                elif target_status == "deleted":
                    st.caption(f"共找到 {len(view_df)} 个已删除订单。")
                else:
                    st.caption(f"共找到 {len(view_df)} 个已完结订单。")
                    
                # 预处理：确保 '发货时间' 是 datetime 类型
                view_df['发货时间'] = pd.to_datetime(view_df['发货时间'], errors='coerce').dt.date
                
                # 需要显示的列
                disp_cols = ["订单号", "客户名", "代理商", "需求机型", "需求数量", "发货时间", "备注", "下单时间"]
                
                # 如果是已删除，显示删除原因
                if target_status == "deleted":
                    if "delete_reason" not in view_df.columns: view_df['delete_reason'] = ""
                    disp_cols.append("delete_reason")
                
                # 允许删除的操作列 (仅 Active/Completed)
                if target_status != "deleted":
                    view_df.insert(0, "✅", False)
                    final_cols = ["✅"] + disp_cols
                else:
                    final_cols = disp_cols
                
                # 配置 column config
                column_config = {
                    "订单号": st.column_config.TextColumn(disabled=True),
                    "客户名": st.column_config.TextColumn(disabled=True),
                    "代理商": st.column_config.TextColumn(disabled=True),
                    "需求机型": st.column_config.TextColumn(disabled=True),
                    "需求数量": st.column_config.TextColumn(disabled=True),
                    "下单时间": st.column_config.TextColumn(disabled=True),
                    "发货时间": st.column_config.DateColumn("发货时间", format="YYYY-MM-DD"),
                    "备注": st.column_config.TextColumn("备注 (可编辑)"),
                    "delete_reason": st.column_config.TextColumn("删除原因", disabled=True),
                    "✅": st.column_config.CheckboxColumn("选择", default=False)
                }
                
                # data_editor
                edited_df = st.data_editor(
                    view_df[final_cols],
                    hide_index=True,
                    use_container_width=True,
                    column_config=column_config,
                    key="order_manage_editor"
                )
                
                # --- 保存修改逻辑 (仅针对备注/时间) ---
                if target_status == "active": # 只有 Active 状态通常允许改这些，Completed 也可以但这里限制一下？原逻辑是 Active 允许
                    if st.button("💾 保存信息修改", type="primary"):
                        changed_count = 0
                        for idx, row in edited_df.iterrows():
                            oid = row['订单号']
                            new_note = row['备注']
                            new_date = row['发货时间'].strftime("%Y-%m-%d") if row['发货时间'] else ""
                            
                            mask = q_orders['订单号'] == oid
                            if not q_orders[mask].empty:
                                org_row = q_orders[mask].iloc[0]
                                org_note = org_row['备注']
                                org_date = org_row['发货时间']
                                
                                if str(new_note) != str(org_note) or str(new_date) != str(org_date):
                                    q_orders.loc[mask, '备注'] = new_note
                                    q_orders.loc[mask, '发货时间'] = new_date
                                    changed_count += 1
                        
                        if changed_count > 0:
                            # 清理临时列
                            for c in ['__status', 'month_str', '下单时间_dt']: 
                                if c in q_orders.columns: del q_orders[c]
                            save_orders(q_orders)
                            st.success(f"已更新 {changed_count} 条订单信息！"); time.sleep(1); st.rerun()
                        else:
                            st.info("未检测到修改")

                # --- 删除逻辑 ---
                if target_status != "deleted":
                    to_delete = edited_df[edited_df['✅'] == True]
                    if not to_delete.empty:
                        st.divider()
                        st.markdown(f"#### 🗑️ 删除订单操作 (选中 {len(to_delete)} 个)")
                        with st.form("delete_order_form"):
                            del_reason = st.text_input("请输入删除原因 (必填):", placeholder="例如：客户取消、重复下单等")
                            if st.form_submit_button("⚠️ 确认删除", type="secondary"):
                                if not del_reason.strip():
                                    st.error("❌ 必须填写删除原因才能删除！")
                                else:
                                    oids_to_del = to_delete['订单号'].tolist()
                                    # Update Status
                                    q_orders.loc[q_orders['订单号'].isin(oids_to_del), 'status'] = 'deleted'
                                    q_orders.loc[q_orders['订单号'].isin(oids_to_del), 'delete_reason'] = del_reason
                                    
                                    # Cleanup and Save
                                    for c in ['__status', 'month_str', '下单时间_dt']: 
                                        if c in q_orders.columns: del q_orders[c]
                                    save_orders(q_orders)
                                    st.success(f"已删除 {len(oids_to_del)} 个订单！"); time.sleep(1); st.rerun()

        else:
            st.info("暂无订单记录")

    # --- 📦 订单配货 (升级版：显示老板指示) ---
