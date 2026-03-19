import random
import time
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

from config import CUSTOM_MODEL_ORDER
from core.file_manager import save_contract_file
from core.navigation import go_home
from core.permissions import check_access
from crud.inventory import get_data
from crud.orders import get_orders
from crud.planning import get_factory_plan, save_factory_plan
from utils.formatters import get_model_rank
from views.components import render_archive_preview, render_file_manager, render_module_logs


def render_production():
    check_access('CONTRACT')
    if True:
        c_back, c_title = st.columns([2, 8])
        with c_back: st.button("⬅️ 返回", on_click=go_home, use_container_width=True)
        with c_title: st.header("🏭 合同管理")
        st.info("💡 在此录入未来合同。老板审批后，将流转至销售下单环节。")
        
        with st.expander("➕ 新增合同 (批量录入)", expanded=False):
            if 'contract_models' not in st.session_state: st.session_state.contract_models = []
            
            df_inv = get_data()
            
            # 使用全量机型 (0库存也要能选)
            all_known_models = set(CUSTOM_MODEL_ORDER)
            if not df_inv.empty:
                all_known_models.update(df_inv['机型'].unique())
            available_models_prod = sorted(list(all_known_models), key=get_model_rank)

            # 1. 基础信息
            c1, c2 = st.columns(2)
            with c1: 
                # f_contract = st.text_input("合同号 (Contract No)")
                st.markdown("##### 合同号将自动生成")
                st.caption("格式: HT + 日期 + 随机4位数")
            with c2: 
                # Auto-fill deadline
                def_date = datetime.now().date()
                if 'auto_deadline' in st.session_state:
                    try: def_date = pd.to_datetime(st.session_state['auto_deadline']).date()
                    except: pass
                f_deadline = st.date_input("要求交期", value=def_date)
            
            c3, c4 = st.columns(2)
            with c3: 
                # Auto-fill customer
                val_cust = st.session_state.get('auto_customer', "")
                f_customer = st.text_input("客户名 (Customer)", value=val_cust)
            with c4: 
                val_agent = st.session_state.get('auto_agent', "")
                f_agent = st.text_input("代理商 (Agent)", value=val_agent)
            
            # --- V7.5 Contract File Upload ---
            st.markdown("##### 📎 合同附件 (可选)")
            f_file = st.file_uploader("上传合同文件 (PDF/Word/JPG, Max 50MB)", type=['pdf', 'doc', 'docx', 'jpg', 'jpeg'])
            
            # --- V7.6 Intelligent Identification ---
            if f_file:
                if st.button("✨ 智能识别 (AI OCR)", type="primary"):
                    with st.spinner("正在分析合同内容..."):
                        processor = OCRProcessor()
                        res_data, full_text = processor.process_file(f_file)
                        
                        if res_data:
                            # 1. 基础信息自动填充
                            if res_data.get('customer'):
                                st.session_state['auto_customer'] = res_data['customer']
                            if res_data.get('agent'):
                                st.session_state['auto_agent'] = res_data['agent']
                            if res_data.get('global_note'):
                                st.session_state['auto_global_note'] = res_data['global_note']
                                
                            # 2. 日期解析
                            if res_data.get('deadline'):
                                try:
                                    # 尝试解析多种格式
                                    raw_date = res_data['deadline']
                                    d_str = raw_date.replace("年", "-").replace("月", "-").replace("日", "").replace("/", "-").strip()
                                    pd.to_datetime(d_str) # check validity
                                    st.session_state['auto_deadline'] = d_str
                                except: pass
                                
                            # 3. 机型列表解析 (适配新 JSON 结构)
                            new_entry_list = []
                            items = res_data.get('items', [])
                            
                            # 兼容旧格式 (如果 LLM 返回了旧结构)
                            if not items and res_data.get('机型及数量'):
                                # Fallback logic for old structure string "A:1 | B:2"
                                raw_str = res_data['机型及数量']
                                if raw_str != '未识别':
                                    parts = raw_str.split("|")
                                    for p in parts:
                                        m, q = p, "1"
                                        if ":" in p: m, q = p.split(":", 1)
                                        new_entry_list.append({
                                            "model": m.strip(), "qty": int(q) if q.isdigit() else 1, 
                                            "is_high": False, "note": "AI识别(旧格式)"
                                        })

                            # 处理新结构列表
                            elif isinstance(items, list):
                                for item in items:
                                    m_name = item.get('model', '')
                                    q_val = item.get('qty', 1)
                                    is_h = item.get('is_high', False)
                                    note_val = item.get('note', '')
                                    
                                    if not m_name: continue
                                    
                                    new_entry_list.append({
                                        "model": m_name, 
                                        "qty": int(q_val) if str(q_val).isdigit() else 1,
                                        "is_high": bool(is_h),
                                        "note": note_val
                                    })

                            # 4. 模糊匹配并填充表格
                            final_table_data = []
                            for entry in new_entry_list:
                                m = entry['model']
                                best_match = None
                                
                                # Fuzzy Match Logic
                                if available_models_prod:
                                    # 优先完全匹配
                                    if m in available_models_prod:
                                        best_match = m
                                    else:
                                        # 包含匹配
                                        for known in available_models_prod:
                                            if known in m or m in known:
                                                best_match = known
                                                break
                                
                                final_table_data.append({
                                    "机型": best_match if best_match else (m if m else available_models_prod[0]),
                                    "数量": entry['qty'],
                                    "加高?": entry['is_high'],
                                    "单行备注": entry['note'] if entry['note'] else "AI识别"
                                })
                            
                            if final_table_data:
                                st.session_state.contract_entry_df = pd.DataFrame(final_table_data)
                                st.success(f"已自动提取 {len(final_table_data)} 条机型数据！")
                            
                            st.success("识别完成！请检查下方填入的数据。")
                            st.expander("查看识别原文").write(full_text)
                        else:
                            st.error("识别失败或未提取到有效信息")
            
            st.divider()
            
            # 2. 机型选择与数据录入 (使用 data_editor 以支持多选重复机型)
            st.caption("请在下方表格中添加机型，支持同一机型添加多行（例如一行标准、一行加高）。")
            
            if 'contract_entry_df' not in st.session_state:
                st.session_state.contract_entry_df = pd.DataFrame(
                    [{"机型": available_models_prod[0] if available_models_prod else "", "数量": 1, "加高?": False, "备注": ""}]
                )

            edited_df = st.data_editor(
                st.session_state.contract_entry_df,
                num_rows="dynamic",
                use_container_width=True,
                column_config={
                    "机型": st.column_config.SelectboxColumn("机型", options=available_models_prod, required=True),
                    "数量": st.column_config.NumberColumn("数量", min_value=1, default=1, required=True),
                    "加高?": st.column_config.CheckboxColumn("加高?", default=False),
                    "备注": st.column_config.TextColumn("单行备注")
                },
                key="contract_editor"
            )
            
            # 3. 提交逻辑
            val_note = st.session_state.get('auto_global_note', "")
            f_note_global = st.text_input("合同总备注", value=val_note, placeholder="可选，应用于所有条目")
            
            if st.button("💾 保存所有合同条目", type="primary"):
                # 自动生成合同号
                f_contract = f"HT{datetime.now().strftime('%Y%m%d')}{random.randint(1000, 9999)}"
                
                if edited_df.empty:
                    st.warning("请至少添加一行机型数据")
                else:
                    df_plan = get_factory_plan()
                    new_rows = []
                    
                    # 遍历编辑后的 DataFrame
                    for _, row in edited_df.iterrows():
                        m = row.get('机型')
                        q = int(row.get('数量', 1))
                        is_h = row.get('加高?', False)
                        note_line = str(row.get('备注', ''))
                        
                        if not m: continue # 跳过空机型
                        
                        final_key = f"{m}(加高)" if is_h else m
                        
                        # 合并备注：总备注 + 行备注
                        final_note = f_note_global
                        if note_line:
                            if final_note: final_note += f" | {note_line}"
                            else: final_note = note_line
                        
                        new_rows.append({
                            "合同号": f_contract, "机型": final_key,
                            "排产数量": str(q), "要求交期": str(f_deadline),
                            "状态": "未下单", "备注": final_note,
                            "客户名": f_customer, "代理商": f_agent,
                            "指定批次/来源": ""
                        })
                    
                    if new_rows:
                        df_plan = pd.concat([df_plan, pd.DataFrame(new_rows)], ignore_index=True)
                        save_factory_plan(df_plan)
                        
                        # --- Save File if exists ---
                        if f_file:
                            if not f_customer: f_customer = "Unknown"
                            success, msg = save_contract_file(f_file, f_customer, f_contract, st.session_state.operator_name)
                            if success: st.success(f"📎 附件已上传！")
                            else: st.error(f"❌ 附件保存失败: {msg}")
                            
                        st.success(f"已添加 {len(new_rows)} 条合同记录！"); time.sleep(1); st.rerun()
                    else:
                        st.warning("有效数据为空")
        
        fp = get_factory_plan()
        # 确保新字段存在
        if "客户名" not in fp.columns: fp["客户名"] = ""
        if "代理商" not in fp.columns: fp["代理商"] = ""

        if not fp.empty:
            fp['temp_date'] = pd.to_datetime(fp['要求交期'], errors='coerce').dt.date
            today = datetime.now().date()
            
            tab1, tab2, tab3 = st.tabs(["🔥 紧急提醒 (2周内)", "📅 近期规划 (2月内)", "📋 全景视图"])
            
            def render_plan_table(df_view, key_prefix):
                if df_view.empty:
                    st.info("无相关数据")
                    return
                # 按机型排序
                df_view = df_view.copy()
                df_view['__rank'] = df_view['机型'].apply(get_model_rank)
                df_view = df_view.sort_values(by=['__rank', '要求交期'], ascending=[True, True])
                
                st.dataframe(df_view[["合同号", "客户名", "代理商", "机型", "排产数量", "要求交期", "状态", "备注"]], use_container_width=True, hide_index=True)
                
                c_op1, c_op2 = st.columns([3, 1])
                with c_op1:
                    op_contract = st.selectbox("选择合同号进行操作", df_view['合同号'].unique(), key=f"{key_prefix}_sel")
                with c_op2:
                    # --- [修改] 增加 "关联现有订单" 选项 ---
                    action_opts = ["标记已下单", "标记已完工", "取消计划", "🔗 关联现有订单(核销)"]
                    action = st.radio("动作", action_opts, horizontal=True, key=f"{key_prefix}_act", label_visibility="collapsed")
                    
                    # 如果选择了关联，需要输入订单号
                    link_oid = ""
                    if action == "🔗 关联现有订单(核销)":
                        link_oid = st.text_input("输入已存在的订单号", placeholder="例如: SO-2026...", key=f"{key_prefix}_oid_input")

                    if st.button("执行", key=f"{key_prefix}_btn"):
                        mask = fp['合同号'] == op_contract
                        
                        if action == "标记已下单": 
                            fp.loc[mask, '状态'] = "已下单"
                            st.success("状态已更新！")
                        elif action == "标记已完工": 
                            fp.loc[mask, '状态'] = "已完工"
                            st.success("状态已更新！")
                        elif action == "取消计划": 
                            fp.loc[mask, '状态'] = "已取消"
                            st.success("计划已取消！")
                        elif action == "🔗 关联现有订单(核销)":
                            if not link_oid:
                                st.error("请输入要关联的订单号")
                                st.stop()
                            else:
                                # 检查订单号是否存在
                                all_ords = get_orders()
                                if link_oid not in all_ords['订单号'].values:
                                    st.error(f"订单号 {link_oid} 不存在！请检查拼写。")
                                    st.stop()
                                else:
                                    fp.loc[mask, '状态'] = "已转订单"
                                    fp.loc[mask, '订单号'] = link_oid
                                    st.success(f"已成功将合同 {op_contract} 与订单 {link_oid} 关联！")
                        
                        save_factory_plan(fp)
                        time.sleep(1); st.rerun()

            with tab1:
                deadline_2w = today + timedelta(days=14)
                df_urgent = fp[(fp['temp_date'] <= deadline_2w) & (~fp['状态'].isin(['已完工', '已取消']))]
                render_plan_table(df_urgent, "tab1")
            with tab2:
                deadline_2m = today + timedelta(days=60)
                df_near = fp[(fp['temp_date'] <= deadline_2m) & (~fp['状态'].isin(['已完工', '已取消']))]
                render_plan_table(df_near, "tab2")
            with tab3:
                df_all = fp[~fp['状态'].isin(['已完工', '已取消'])]
                render_plan_table(df_all, "tab3")
        else: st.info("暂无排产计划数据")

    # --- ️ 机台信息编辑 ---
