import time
from datetime import datetime

import pandas as pd
import streamlit as st

from crud.inventory import (
    WAREHOUSE_MAX_CAPACITY,
    append_import_staging,
    get_data,
    get_import_staging,
    get_warehouse_layout,
    inbound_to_slot,
    reset_warehouse_layout,
    save_data,
    save_import_staging,
    save_warehouse_layout,
)
from crud.logs import append_log
from utils.formatters import get_model_rank
from utils.parsers import build_import_payload, diff_tracking_vs_inventory, execute_import_transaction_payload, parse_tracking_xls, should_reset_page_selection


def _on_plan_import_checkbox_change(sn, widget_key):
    now_ts = time.time()
    last_ts = float(st.session_state.get("plan_import_last_toggle_ts", 0.0))
    if now_ts - last_ts < 0.3:
        st.session_state[widget_key] = st.session_state.get("plan_import_selected_map", {}).get(sn, False)
        return
    selected_map = st.session_state.get("plan_import_selected_map", {})
    selected_map[str(sn)] = bool(st.session_state.get(widget_key, False))
    st.session_state["plan_import_selected_map"] = selected_map
    st.session_state["plan_import_last_toggle_ts"] = now_ts
    st.session_state["plan_import_select_event_count"] = int(st.session_state.get("plan_import_select_event_count", 0)) + 1


def check_prod_admin_permission():
    if st.session_state.role not in ['Admin', 'Prod', 'Inbound']:
        st.error("🚫 权限不足！仅限管理员 (Admin)、生产/仓管 (Prod) 或 入库员 (Inbound) 角色访问。")
        st.stop()

def render_tracking_import_module():
    """
    模块二：跟踪单流水号导入
    - 权限控制：仅 Prod/Admin
    - 功能：上传 -> PLAN_IMPORT -> 编辑 -> 确认 -> 写入库存
    """
    check_prod_admin_permission()
    
    st.markdown("### 📋 跟踪单流水号导入模块")
    
    # --- 1. 上传与解析 ---
    with st.expander("📤 上传新跟踪单 (Upload)", expanded=False):
        uploaded = st.file_uploader("选择跟踪单文件 (.xls / .xlsx)", type=["xls", "xlsx"], key="tracking_mod_uploader")
        if uploaded:
            if st.button("🔍 解析并追加到待入库清单", type="primary"):
                with st.spinner("正在解析..."):
                    code, msg, parsed_df = parse_tracking_xls(uploaded)
                    if code == 1:
                        # Diff check logic
                        diff_df = diff_tracking_vs_inventory(parsed_df)
                        
                        if not diff_df.empty:
                            # Append to DB Staging
                            try:
                                append_import_staging(diff_df)
                                st.success(f"✅ 解析成功！已追加 {len(diff_df)} 条记录到待入库清单。")
                                time.sleep(1); st.rerun()
                            except Exception as e:
                                st.error(f"写入待入库清单失败: {e}")
                        else:
                            st.warning("所有解析到的流水号均已在库存中，无需导入。")
                    else:
                        st.error(msg)

    # --- 2. 待入库数据表格展示与编辑 ---
    st.markdown("#### 📝 待入库数据审核 (DB Staging)")
    
    plan_df = get_import_staging().copy()
    
    if plan_df.empty:
        st.info("待入库清单为空，请先上传跟踪单或手动添加。")
    else:
        st.markdown(
            """
            <style>
            div[data-testid="stDataEditor"] table thead tr th:first-child,
            div[data-testid="stDataEditor"] table tbody tr td:first-child {
                width: 40px !important;
                min-width: 40px !important;
                max-width: 40px !important;
                text-align: center !important;
            }
            </style>
            """,
            unsafe_allow_html=True
        )
        plan_df["流水号"] = plan_df["流水号"].astype(str).str.strip()
        filter_col1, filter_col2, filter_col3, filter_col4 = st.columns([2, 1, 1, 2])
        with filter_col1:
            filter_keyword = st.text_input("筛选关键字", value="", key="plan_import_filter_keyword")
        with filter_col2:
            sort_col = st.selectbox("排序字段", ["流水号", "批次号", "机型", "预计入库时间"], index=0, key="plan_import_sort_col")
        with filter_col3:
            sort_asc = st.checkbox("升序", value=True, key="plan_import_sort_asc")
        with filter_col4:
            page_size = st.selectbox("每页条数", [10, 20, 50, 100], index=1, key="plan_import_page_size")

        work_df = plan_df.copy()
        if filter_keyword:
            mask = (
                work_df["流水号"].astype(str).str.contains(filter_keyword, case=False, na=False) |
                work_df["批次号"].astype(str).str.contains(filter_keyword, case=False, na=False) |
                work_df["机型"].astype(str).str.contains(filter_keyword, case=False, na=False)
            )
            work_df = work_df[mask].copy()

        if not work_df.empty:
            work_df = work_df.sort_values(by=sort_col, ascending=sort_asc, kind="stable")

        total_rows = len(work_df)
        total_pages = max(1, (total_rows + page_size - 1) // page_size)
        page_col1, page_col2, page_col3 = st.columns([1, 1, 4])
        with page_col1:
            page_no = st.number_input("页码", min_value=1, max_value=total_pages, value=1, step=1, key="plan_import_page_no")
        with page_col2:
            st.markdown(f"共 {total_pages} 页")
        page_idx = int(page_no) - 1
        start = page_idx * page_size
        end = start + page_size
        page_df = work_df.iloc[start:end].copy()
        editable_cols = ["流水号", "批次号", "机型", "状态", "预计入库时间", "机台备注/配置"]
        editor_df = page_df[editable_cols].copy()
        editor_df.insert(0, "原流水号", page_df["流水号"].astype(str).tolist())
        edited_page_df = st.data_editor(
            editor_df,
            hide_index=True,
            use_container_width=True,
            key=f"plan_import_editor_{page_idx}",
            disabled=["原流水号"],
        )
        save_col1, save_col2 = st.columns([1.5, 5.5])
        with save_col1:
            if st.button("💾 保存本页编辑", key=f"plan_import_save_page_{page_idx}"):
                edited_apply_df = edited_page_df.copy()
                edited_apply_df["原流水号"] = edited_apply_df["原流水号"].astype(str).str.strip()
                edited_apply_df["流水号"] = edited_apply_df["流水号"].astype(str).str.strip()
                if (edited_apply_df["流水号"] == "").any():
                    st.error("流水号不能为空")
                    st.stop()
                full_df = plan_df.copy()
                full_df["流水号"] = full_df["流水号"].astype(str).str.strip()
                source_sns = edited_apply_df["原流水号"].tolist()
                remaining_df = full_df[~full_df["流水号"].isin(source_sns)].copy()
                updated_rows_df = edited_apply_df.drop(columns=["原流水号"])
                merged_df = pd.concat([remaining_df, updated_rows_df], ignore_index=True)
                duplicated_sns = merged_df["流水号"][merged_df["流水号"].duplicated()].astype(str).tolist()
                if duplicated_sns:
                    st.error(f"保存失败，存在重复流水号: {duplicated_sns[:5]}")
                    st.stop()
                save_import_staging(merged_df)
                st.session_state["plan_import_selected_map"] = {}
                st.success("已保存本页编辑")
                time.sleep(0.5)
                st.rerun()
        page_df = edited_page_df.drop(columns=["原流水号"]).copy()
        page_df["流水号"] = page_df["流水号"].astype(str).str.strip()

        if should_reset_page_selection(st.session_state.get("plan_import_prev_page"), page_idx):
            st.session_state["plan_import_selected_map"] = {}
            st.session_state["plan_import_prev_page"] = page_idx

        selected_map = st.session_state.get("plan_import_selected_map", {})
        page_sns = page_df["流水号"].astype(str).tolist()
        for sn in page_sns:
            selected_map.setdefault(sn, False)
        selected_map = {sn: selected_map.get(sn, False) for sn in page_sns}
        st.session_state["plan_import_selected_map"] = selected_map

        top_left, top_mid, top_right = st.columns([5, 2, 2])
        with top_right:
            all_selected = (len(page_sns) > 0 and sum(1 for v in selected_map.values() if v) == len(page_sns))
            select_all_key = f"plan_import_select_all_{page_idx}"
            select_all = st.checkbox("全选/取消全选", value=all_selected, key=select_all_key)
            if select_all != all_selected:
                selected_map = {sn: select_all for sn in page_sns}
                st.session_state["plan_import_selected_map"] = selected_map

        # 构建带勾选列的展示表格
        display_df = page_df[["流水号", "批次号", "机型", "预计入库时间", "机台备注/配置"]].copy()
        display_df.insert(0, "选择", display_df["流水号"].astype(str).map(
            lambda sn: bool(st.session_state.get("plan_import_selected_map", {}).get(sn, False))
        ))
        sel_editor_key = f"plan_import_sel_editor_{page_idx}"
        sel_result = st.data_editor(
            display_df,
            hide_index=True,
            use_container_width=True,
            key=sel_editor_key,
            disabled=["流水号", "批次号", "机型", "预计入库时间", "机台备注/配置"],
            column_config={
                "选择": st.column_config.CheckboxColumn("选择", width="small"),
                "流水号": st.column_config.TextColumn("流水号", width="medium"),
                "批次号": st.column_config.TextColumn("批次号", width="medium"),
                "机型": st.column_config.TextColumn("机型", width="medium"),
                "预计入库时间": st.column_config.TextColumn("预计入库时间", width="medium"),
                "机台备注/配置": st.column_config.TextColumn("机台备注", width="large"),
            }
        )
        # 同步勾选状态到 session_state（必须在显示计数之前完成）
        new_map = {}
        for i, row_s in sel_result.iterrows():
            sn = str(row_s["流水号"]).strip()
            new_map[sn] = bool(row_s["选择"])
        st.session_state["plan_import_selected_map"] = new_map

        # 已选数量在 sel_result 同步后计算，确保实时准确
        selected_count = sum(1 for v in new_map.values() if v)
        with top_mid:
            st.markdown(f"**已选 {selected_count} 条**")

        selected_map = st.session_state.get("plan_import_selected_map", {})
        selected_rows = page_df[page_df["流水号"].astype(str).isin(
            [sn for sn, v in new_map.items() if v]
        )].copy()
        payload_date_col, confirm_btn_col, msg_col = st.columns([2, 1.5, 3])
        with payload_date_col:
            selected_date = st.date_input(
                "预计入库日期",
                value=None,
                min_value=datetime.now().date(),
                format="YYYY-MM-DD",
                key=f"plan_import_date_{page_idx}",
            )
        can_import = (not selected_rows.empty) and (selected_date is not None)
        with msg_col:
            if selected_rows.empty:
                st.warning("请先勾选至少 1 条数据")
            elif selected_date is None:
                st.warning("请选择预计入库日期")
            else:
                st.success(f"已选 {len(selected_rows)} 条，可执行导入")

        with confirm_btn_col:
            if st.button("🚀 确认导入 (Confirm)", type="primary", disabled=not can_import):
                payload, err = build_import_payload(selected_rows, selected_date)
                if err:
                    st.error(err)
                else:
                    import_result = execute_import_transaction_payload(payload, retry_times=1)
                    success_n = len(import_result["success"])
                    failed_n = len(import_result["failed"])
                    if hasattr(st, "toast"):
                        st.toast(f"成功 {success_n} 条，失败 {failed_n} 条")
                    else:
                        st.success(f"成功 {success_n} 条，失败 {failed_n} 条")
                    if failed_n > 0:
                        st.dataframe(pd.DataFrame(import_result["failed"]), use_container_width=True, hide_index=True)
                    time.sleep(0.5)
                    st.rerun()

@st.dialog("确认入库")
def confirm_inbound_dialog(sns, target_code):
    st.warning(f"确定要将以下 {len(sns)} 台机台入库到库位 **{target_code}** 吗？")
    st.write(sns)
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("✅ 确认", type="primary", use_container_width=True):
            success_count = 0
            errors = []
            
            # Use individual inbound_to_slot to properly handle concurrency/capacity
            for sn in sns:
                result = inbound_to_slot(sn, target_code)
                if result.get("ok"):
                    success_count += 1
                    append_log("扫描入库", [sn])
                else:
                    errors.append(f"{sn}: {result.get('message')}")
            
            if success_count > 0:
                st.success(f"成功将 {success_count} 台机台入库到 {target_code}！")
            if errors:
                for err in errors:
                    st.error(err)
            
            st.session_state.inbound_dialog_done = True
            st.rerun()
            
    with col2:
        if st.button("❌ 取消", use_container_width=True):
            st.session_state.show_inbound_dialog = False
            st.session_state.inbound_dialog_done = False
            st.rerun()

def render_machine_inbound_module():
    """
    模块一：机台入库 (保留原有逻辑)
    - 权限控制：仅 Prod/Admin
    """
    check_prod_admin_permission()
    
    st.markdown("### 🏭 机台入库模块 (扫描入库)")
    
    # Original logic from line 4290
    c_s1, c_s2 = st.columns([3, 1])
    with c_s1:
        scan_keyword = st.text_input("扫描批次号/流水号", value=st.session_state.current_batch, key="machine_scan_batch")
    with c_s2:
        show_all = st.checkbox("显示全部待入库", value=True, key="machine_show_all")

    if scan_keyword:
        st.session_state.current_batch = scan_keyword
    
    df = get_data()
    # Filter '待入库'
    data = df[df['状态'] == '待入库'].copy()
    
    if not show_all:
        if scan_keyword:
            keyword = str(scan_keyword).strip()
            data = data[
                data['批次号'].astype(str).str.contains(keyword, na=False)
                | data['流水号'].astype(str).str.contains(keyword, na=False)
            ]
        else:
            data = pd.DataFrame(columns=data.columns)
        
    if not data.empty:
        st.info(f"待入库清单 ({len(data)} 台)")
        # 按机型排序
        data['__rank'] = data['机型'].apply(get_model_rank)
        data = data.sort_values(by=['__rank', '批次号'], ascending=[True, False])
        
        data.insert(0, "✅", False)
        # Use a key to avoid conflict
        res = st.data_editor(
            data[['✅', '批次号', '机型', '流水号', '机台备注/配置']], 
            hide_index=True, 
            use_container_width=True,
            key="machine_inbound_editor"
        )
        
        sel = res[res['✅'] == True]
        
        if not sel.empty:
            st.markdown("---")
            with st.expander("🎯 请选择目标库位进行入库 (点击库位按钮确认)", expanded=True):
                layout_resp = get_warehouse_layout("default")
                slots = layout_resp.get("layout_json", {}).get("slots", [])
                
                if not slots:
                    st.warning("尚未配置库位，请先到大屏看板配置库位！")
                else:
                    inventory_df = df.copy()
                    if "Location_Code" not in inventory_df.columns:
                        inventory_df["Location_Code"] = ""
                    
                    # 快速定位目标库位
                    slot_query = st.text_input("🔎 快速定位库位", value="", placeholder="输入库位编号，如 A03 / B12", key="inbound_slot_search").strip().lower()
                    display_slots = []
                    for s in slots:
                        code = str(s.get("code", "")).strip()
                        if slot_query and slot_query not in code.lower():
                            continue
                        display_slots.append(s)

                    if slot_query and not display_slots:
                        st.warning("未找到匹配库位，请检查输入。")

                    # 响应式布局：根据屏幕宽度自适应列数，避免移动端显示挤压
                    cols = st.columns([1, 1, 1, 1, 1, 1]) 
                    
                    # Gather all selected models
                    selected_models = set(sel['机型'].astype(str).str.strip().tolist())
                    
                    for idx, s in enumerate(display_slots):
                        code = str(s.get("code", "")).strip()
                        status_cfg = str(s.get("status", "正常")).strip()
                        allowed_models_str = str(s.get("allowed_models", "")).strip()
                        
                        slot_df = inventory_df[inventory_df["Location_Code"].astype(str).str.strip() == code]
                        active_df = slot_df[slot_df["状态"].astype(str).str.contains("库存中", na=False)]
                        count = len(active_df)
                        
                        btn_disabled = False
                        display_text = ""
                        
                        if status_cfg in ["锁定", "异常"]:
                            display_text = f"🚫 {code}\n( {status_cfg} )"
                            btn_disabled = True
                            btn_type = "secondary"
                        elif count >= WAREHOUSE_MAX_CAPACITY:
                            display_text = f"🔴 {code}\n({count}/{WAREHOUSE_MAX_CAPACITY} 满载)"
                            btn_disabled = True
                            btn_type = "secondary"
                        else:
                            # Check constraint
                            model_allowed = True
                            if allowed_models_str:
                                allowed_list = [m.strip() for m in allowed_models_str.split(",") if m.strip()]
                                if allowed_list:
                                    for m in selected_models:
                                        if m not in allowed_list:
                                            model_allowed = False
                                            break
                            if not model_allowed:
                                display_text = f"⛔ {code}\n(机型不符)"
                                btn_disabled = True
                                btn_type = "secondary"
                            else:
                                if count == 0:
                                    display_text = f"🟩 {code}\n(空闲)"
                                    btn_type = "primary"
                                else:
                                    display_text = f"🟨 {code}\n({count}/{WAREHOUSE_MAX_CAPACITY} 占用)"
                                    btn_type = "primary"
                        
                        col = cols[idx % 6]
                        if col.button(display_text, key=f"btn_slot_{code}", type=btn_type, disabled=btn_disabled, use_container_width=True):
                            st.session_state.pending_inbound_sns = sel['流水号'].tolist()
                            st.session_state.pending_target_code = code
                            st.session_state.show_inbound_dialog = True
                            st.rerun()

            if st.session_state.get('show_inbound_dialog', False):
                sns = st.session_state.get('pending_inbound_sns', [])
                target_code = st.session_state.get('pending_target_code', '')
                if sns and target_code:
                    confirm_inbound_dialog(sns, target_code)
                # 无论 dialog 结果如何，只要 rerun 后 done 未被置位，则清除弹窗状态
                if st.session_state.get('inbound_dialog_done', False):
                    st.session_state.show_inbound_dialog = False
                    st.session_state.inbound_dialog_done = False
                elif not sns or not target_code:
                    # sns/code 为空时也重置，防止空状态循环弹出
                    st.session_state.show_inbound_dialog = False
    else:
            st.info("当前无待入库数据 (或未扫描到对应批次)")
