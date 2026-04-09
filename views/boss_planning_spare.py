import time

import pandas as pd
import streamlit as st

from core.navigation import go_home
from core.permissions import check_access
from crud.inventory import get_data
from crud.orders import create_sales_order, get_orders, save_orders
from crud.planning import get_factory_plan, save_factory_plan
from utils.parsers import parse_alloc_dict, to_json_text


"""
应急版 boss_planning（防卡死精简版）
用途：当主版本 boss_planning.py 出现卡顿/假死时，
可以用本文件内容直接覆盖 views/boss_planning.py 进行快速恢复。
"""


def _parse_simple_alloc_text(raw_text: str) -> dict:
    """将 '现货(Spot):2, B2401:3' 解析为 dict。"""
    txt = str(raw_text or "").strip()
    if not txt:
        return {}
    out = {}
    for part in txt.split(","):
        seg = str(part).strip()
        if not seg or ":" not in seg:
            continue
        k, v = seg.split(":", 1)
        key = str(k).strip()
        if not key:
            continue
        try:
            qty = int(float(str(v).strip()))
        except Exception:
            qty = 0
        if qty > 0:
            out[key] = qty
    return out


def _alloc_to_text(alloc: dict) -> str:
    if not alloc:
        return ""
    return ", ".join([f"{k}:{v}" for k, v in alloc.items()])


def render_boss_planning():
    check_access("PLANNING")

    c_back, c_title = st.columns([1, 9])
    with c_back:
        st.button("⬅️ 返回", on_click=go_home, use_container_width=True)
    with c_title:
        st.header("👑 生产统筹 & 订单资源分配（应急版）")

    fp_df = get_factory_plan()
    orders_df = get_orders()
    inventory_df = get_data()

    if "boss_selected_id" not in st.session_state:
        st.session_state.boss_selected_id = None
    if "boss_selected_type" not in st.session_state:
        st.session_state.boss_selected_type = "contract"

    col_left, col_right = st.columns([1, 2], gap="large")

    with col_left:
        with st.container(height=750, border=True):
            tab_pending, tab_planning, tab_orders = st.tabs(["📄 待审合同", "🎯 待规划", "📦 现有订单"])

            with tab_pending:
                pending_df = fp_df[fp_df["状态"] == "未下单"].copy()
                if pending_df.empty:
                    st.info("无待审合同")
                else:
                    for cid in pending_df["合同号"].dropna().astype(str).unique():
                        c_rows = pending_df[pending_df["合同号"].astype(str) == cid]
                        cust = c_rows.iloc[0].get("客户名", "")
                        if st.button(f"📄 {cid} | {cust}", key=f"safe_p_{cid}", use_container_width=True):
                            st.session_state.boss_selected_id = cid
                            st.session_state.boss_selected_type = "contract"
                            st.rerun()

            with tab_planning:
                planning_df = fp_df[fp_df["状态"].isin(["待规划", "已规划", "已转订单", "已下单", "已配货"])].copy()
                if planning_df.empty:
                    st.info("无待规划/已规划项")
                else:
                    for cid in planning_df["合同号"].dropna().astype(str).unique():
                        c_rows = planning_df[planning_df["合同号"].astype(str) == cid]
                        status = c_rows.iloc[0].get("状态", "")
                        cust = c_rows.iloc[0].get("客户名", "")
                        if st.button(f"🎯 {cid} ({status}) | {cust}", key=f"safe_pl_{cid}", use_container_width=True):
                            st.session_state.boss_selected_id = cid
                            st.session_state.boss_selected_type = "planning"
                            st.rerun()

            with tab_orders:
                if orders_df.empty:
                    st.info("无订单")
                else:
                    for oid in orders_df["订单号"].dropna().astype(str).unique()[::-1]:
                        o_rows = orders_df[orders_df["订单号"].astype(str) == oid]
                        cust = o_rows.iloc[0].get("客户名", "")
                        if st.button(f"📦 {oid} | {cust}", key=f"safe_o_{oid}", use_container_width=True):
                            st.session_state.boss_selected_id = oid
                            st.session_state.boss_selected_type = "order"
                            st.rerun()

    with col_right:
        with st.container(height=750, border=True):
            sel_id = st.session_state.boss_selected_id
            sel_type = st.session_state.boss_selected_type

            if not sel_id:
                st.info("👈 请从左侧选择项目")
                return

            if sel_type == "contract":
                target = fp_df[(fp_df["合同号"].astype(str) == str(sel_id)) & (fp_df["状态"] == "未下单")]
                if target.empty:
                    st.warning("合同不存在或状态已变化")
                    return

                first_row = target.iloc[0]
                st.markdown(f"### 📄 合同详情: {sel_id}")
                st.write(f"客户: {first_row.get('客户名', '')} | 代理: {first_row.get('代理商', '')}")
                st.write(f"交期: {first_row.get('要求交期', '')}")
                st.dataframe(target[["机型", "排产数量", "备注"]], use_container_width=True, hide_index=True)

                c1, c2 = st.columns(2)
                with c1:
                    if st.button("🚀 批准并进入规划", type="primary", use_container_width=True, key=f"safe_approve_{sel_id}"):
                        fp_df.loc[fp_df["合同号"].astype(str) == str(sel_id), "状态"] = "待规划"
                        save_factory_plan(fp_df)
                        st.session_state.boss_selected_type = "planning"
                        st.success("已批准")
                        time.sleep(0.3)
                        st.rerun()
                with c2:
                    if st.button("❌ 驳回/取消", use_container_width=True, key=f"safe_reject_{sel_id}"):
                        fp_df.loc[fp_df["合同号"].astype(str) == str(sel_id), "状态"] = "已取消"
                        save_factory_plan(fp_df)
                        st.session_state.boss_selected_id = None
                        st.warning("已取消")
                        st.rerun()

            elif sel_type == "planning":
                target = fp_df[fp_df["合同号"].astype(str) == str(sel_id)].copy()
                if target.empty:
                    st.warning("未找到该合同")
                    return

                first_row = target.iloc[0]
                st.markdown(f"### 🎯 规划详情: {sel_id}")
                st.write(f"状态: {first_row.get('状态', '')} | 客户: {first_row.get('客户名', '')}")

                edit_text_map = {}
                for idx, row in target.iterrows():
                    model = str(row.get("机型", "")).strip()
                    need_qty = int(float(row.get("排产数量", 0) or 0))
                    prev_alloc = parse_alloc_dict(row.get("指定批次/来源", {}))
                    default_text = _alloc_to_text(prev_alloc)
                    st.markdown(f"**{model}**（需 {need_qty} 台）")
                    edit_text_map[idx] = st.text_input(
                        f"{model} 配货计划（格式: 现货(Spot):2, B2401:3）",
                        value=default_text,
                        key=f"safe_alloc_{idx}",
                    )

                if st.button("💾 保存规划", type="primary"):
                    for idx, raw in edit_text_map.items():
                        plan_obj = _parse_simple_alloc_text(raw)
                        fp_df.at[idx, "指定批次/来源"] = to_json_text(plan_obj)
                        if fp_df.at[idx, "状态"] == "待规划":
                            fp_df.at[idx, "状态"] = "已规划"
                    save_factory_plan(fp_df)
                    st.success("规划已保存")
                    time.sleep(0.3)
                    st.rerun()

                if first_row.get("状态", "") == "已规划" and not str(first_row.get("订单号", "") or "").strip():
                    if st.button("🚀 自动生成订单并跳转配货"):
                        model_data = {}
                        all_plans = {}
                        note_combined = ""
                        for _, row in target.iterrows():
                            m = str(row.get("机型", "")).strip()
                            q = int(float(row.get("排产数量", 0) or 0))
                            if m:
                                model_data[m] = q
                                alloc_data = parse_alloc_dict(row.get("指定批次/来源", {}))
                                if alloc_data:
                                    all_plans[m] = alloc_data
                                if row.get("备注"):
                                    note_combined += f" {m}:{row.get('备注')}"

                        new_oid = create_sales_order(
                            customer=first_row.get("客户名", ""),
                            agent=first_row.get("代理商", ""),
                            model_data=model_data,
                            note=note_combined,
                            pack_option="未指定",
                            delivery_time=first_row.get("要求交期", ""),
                            source_batch=all_plans,
                        )
                        fp_df.loc[fp_df["合同号"].astype(str) == str(sel_id), "订单号"] = new_oid
                        fp_df.loc[fp_df["合同号"].astype(str) == str(sel_id), "状态"] = "已转订单"
                        save_factory_plan(fp_df)
                        st.success(f"已生成订单 {new_oid}")
                        st.session_state.page = "sales_alloc"
                        time.sleep(0.3)
                        st.rerun()

            elif sel_type == "order":
                target = orders_df[orders_df["订单号"].astype(str) == str(sel_id)]
                if target.empty:
                    st.warning("订单未找到")
                    return
                row = target.iloc[0]
                st.markdown(f"### 📦 订单信息: {sel_id}")
                st.write(f"客户: {row.get('客户名', '')} | 代理: {row.get('代理商', '')}")
                st.write(f"需求机型: {row.get('需求机型', '')}")
                st.write(f"需求数量: {row.get('需求数量', '')}")
                alloc_n = len(inventory_df[inventory_df["占用订单号"].astype(str) == str(sel_id)]) if not inventory_df.empty else 0
                st.info(f"当前已占用库存: {alloc_n} 台")
                if st.button("➡️ 跳转订单配货", type="primary"):
                    st.session_state.page = "sales_alloc"
                    st.rerun()
