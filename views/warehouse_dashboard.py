import streamlit as st
import pandas as pd
from datetime import datetime

from core.permissions import check_access
from crud.inventory import get_data, get_warehouse_layout, save_warehouse_layout, reset_warehouse_layout, inbound_to_slot, WAREHOUSE_MAX_CAPACITY
from config import PLOTLY_AVAILABLE
import time

if PLOTLY_AVAILABLE:
    import plotly.graph_objects as go


@st.dialog("库位详情面板")
def show_slot_details(slot_code, slot_df):
    st.markdown(f"### 📍 库位: {slot_code}")
    if slot_df.empty:
        st.info("当前库位空闲")
        return
    
    st.write(f"**当前占用**: {len(slot_df)} / {WAREHOUSE_MAX_CAPACITY} 台")
    
    display_df = slot_df[["批次号", "机型", "流水号", "预计入库时间", "更新时间", "机台备注/配置"]].copy()
    st.dataframe(display_df, hide_index=True, use_container_width=True)


@st.dialog("库内调拨操作")
def render_transfer_dialog(sn, current_slot, all_slots):
    st.markdown(f"#### 移动机台: {sn}")
    st.write(f"**当前库位**: {current_slot}")
    
    # 过滤掉满载和异常的库位
    available_slots = []
    inventory_df = get_data()
    if "Location_Code" not in inventory_df.columns:
        inventory_df["Location_Code"] = ""
        
    for s in all_slots:
        code = str(s.get("code", "")).strip()
        status_cfg = str(s.get("status", "正常")).strip()
        if code == current_slot or status_cfg in ["锁定", "异常"]:
            continue
            
        slot_df = inventory_df[inventory_df["Location_Code"].astype(str).str.strip() == code]
        active_df = slot_df[slot_df["状态"].astype(str).str.contains("库存中", na=False)]
        if len(active_df) < WAREHOUSE_MAX_CAPACITY:
            available_slots.append(code)
            
    if not available_slots:
        st.warning("当前没有其他可用（未满载且正常）的库位。")
        if st.button("关闭"):
            st.session_state.transfer_dialog_done = True
            st.rerun()
        return

    target_slot = st.selectbox("选择目标库位", options=[""] + available_slots)
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🚀 确认调拨", type="primary", disabled=not target_slot, use_container_width=True):
            result = inbound_to_slot(sn, target_slot, is_transfer=True) # 复用入库逻辑来更新库位
            if result.get("ok"):
                st.success(f"成功将机台 {sn} 调拨至 {target_slot}！")
                st.session_state.transfer_dialog_done = True
                time.sleep(0.5)
                st.rerun()
            else:
                st.error(result.get("message", "调拨失败"))
    with col2:
        if st.button("❌ 取消", use_container_width=True):
            st.session_state.transfer_dialog_done = True
            st.rerun()

def render_layout_config():
    with st.sidebar.expander("⚙️ 库位布局与自动生成", expanded=False):
        layout_id = "default"
        layout_resp = get_warehouse_layout(layout_id)
        existing_slots = layout_resp.get("layout_json", {}).get("slots", [])
        if not isinstance(existing_slots, list):
            existing_slots = []

        st.markdown("**自动生成布局**")
        gen_mode = st.radio("生成模式", ["按行生成 (Z字形)", "按列生成 (N字形)"])

        col1, col2 = st.columns(2)
        rows = col1.number_input("行数", min_value=1, value=3, step=1)
        cols = col2.number_input("列数", min_value=1, value=4, step=1)

        prefix = st.text_input("区域前缀 (如: A, B)", value="A")
        allowed_models = st.text_input("允许存放机型 (逗号分隔，留空不限)", value="")

        append_mode = st.checkbox("追加到现有布局", value=False)
        area_gap = 20

        if st.button("✨ 生成布局", key="btn_generate_layout"):
            width, height = 300, 160
            gap_x, gap_y = 40, 40

            prefix = prefix.strip()
            if not prefix:
                st.warning("请先填写区域前缀")
                return

            prefix_slots = []
            other_slots = []
            for s in existing_slots:
                code = str(s.get("code", "")).strip()
                if code.startswith(prefix):
                    prefix_slots.append(s)
                else:
                    other_slots.append(s)

            # 1) 覆盖生成：清空全部，从左上角生成
            # 2) 追加 + 同前缀存在：替换该区域（按新行列重建）
            # 3) 追加 + 同前缀不存在：作为新区域追加到最右侧
            if not append_mode:
                final_slots = []
                base_x, base_y = 20, 20
            elif prefix_slots:
                final_slots = other_slots.copy()
                base_x = min(int(float(s.get("x", 0))) for s in prefix_slots)
                base_y = min(int(float(s.get("y", 0))) for s in prefix_slots)
            else:
                final_slots = existing_slots.copy()
                if final_slots:
                    max_bottom = max(int(float(s.get("y", 0))) + int(float(s.get("h", 160))) for s in final_slots)
                    base_x = 20
                    base_y = max_bottom + int(area_gap)
                else:
                    base_x = 20
                    base_y = 20

            max_id_num = 0
            for s in final_slots:
                sid = str(s.get("id", "")).strip()
                try:
                    max_id_num = max(max_id_num, int(sid.split("-")[-1]))
                except:
                    pass

            generated = []
            if "按行" in gen_mode:
                for r in range(int(rows)):
                    for c in range(int(cols)):
                        seq = len(generated) + 1
                        code = f"{prefix}{seq:02d}"
                        channel_gap = (c // 2) * 40
                        x = base_x + c * (width + gap_x) + channel_gap
                        y = base_y + r * (height + gap_y)
                        max_id_num += 1
                        generated.append({
                            "id": f"slot-{max_id_num}",
                            "code": code,
                            "x": x,
                            "y": y,
                            "w": width,
                            "h": height,
                            "status": "正常",
                            "allowed_models": allowed_models.strip()
                        })
            else:
                for c in range(int(cols)):
                    for r in range(int(rows)):
                        seq = len(generated) + 1
                        code = f"{prefix}{seq:02d}"
                        channel_gap = (c // 2) * 40
                        x = base_x + c * (width + gap_x) + channel_gap
                        y = base_y + r * (height + gap_y)
                        max_id_num += 1
                        generated.append({
                            "id": f"slot-{max_id_num}",
                            "code": code,
                            "x": x,
                            "y": y,
                            "w": width,
                            "h": height,
                            "status": "正常",
                            "allowed_models": allowed_models.strip()
                        })

            save_warehouse_layout(layout_id, {"slots": final_slots + generated})
            st.success("布局已生成！")
            time.sleep(0.5)
            st.rerun()

        st.divider()
        st.markdown("**手动微调配置**")
        layout_id = "default"
        layout_resp = get_warehouse_layout(layout_id)
        slots = layout_resp.get("layout_json", {}).get("slots", [])
        if not isinstance(slots, list):
            slots = []
        slots_df = pd.DataFrame(slots)
        for c in ["id", "code", "x", "y", "w", "h", "status", "allowed_models"]:
            if c not in slots_df.columns:
                if c == "status":
                    slots_df[c] = "正常"
                else:
                    slots_df[c] = ""
        if not slots_df.empty:
            slots_df = slots_df[["id", "code", "x", "y", "w", "h", "status", "allowed_models"]]
            
            slots_editor = st.data_editor(
                slots_df,
                hide_index=True,
                use_container_width=True,
                column_config={
                    "status": st.column_config.SelectboxColumn(
                        "状态",
                        options=["正常", "锁定", "异常"],
                        required=True,
                    ),
                    "allowed_models": st.column_config.TextColumn(
                        "允许存放机型"
                    )
                },
                key="warehouse_slots_editor",
            )
            
            if st.button("💾 保存微调", key="warehouse_slots_save"):
                save_rows = slots_editor.fillna("").to_dict(orient="records")
                normalized = []
                for idx, row in enumerate(save_rows):
                    code = str(row.get("code", "")).strip()
                    if not code:
                        continue
                    normalized.append({
                        "id": str(row.get("id", "")).strip() or f"slot-{idx + 1}",
                        "code": code,
                        "x": int(float(row.get("x") or 0)),
                        "y": int(float(row.get("y") or 0)),
                        "w": int(float(row.get("w") or 300)),
                        "h": int(float(row.get("h") or 160)),
                        "status": str(row.get("status", "正常")),
                        "allowed_models": str(row.get("allowed_models", "")),
                    })
                save_warehouse_layout(layout_id, {"slots": normalized})
                st.success("微调已保存")
                time.sleep(0.4)
                st.rerun()
                
            if st.button("♻️ 清空布局", key="warehouse_slots_reset"):
                reset_warehouse_layout(layout_id)
                st.success("库位布局已清空")
                time.sleep(0.4)
                st.rerun()

@st.dialog("选择要调拨的机台")
def select_machine_to_transfer(active_df, current_slot, all_slots):
    st.write(f"请选择库位 **{current_slot}** 中要移动的机台：")
    
    options = active_df['流水号'].tolist()
    selected_sn = st.selectbox("流水号", options=[""] + options)
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("➡️ 下一步", type="primary", disabled=not selected_sn, use_container_width=True):
            st.session_state.pending_transfer_sn = selected_sn
            st.session_state.show_transfer_select_dialog = False
            st.session_state.show_transfer_action_dialog = True
            st.rerun()
    with col2:
        if st.button("取消", use_container_width=True):
            st.session_state.show_transfer_select_dialog = False
            st.rerun()

@st.dialog("直接入库操作")
def show_direct_inbound_dialog(slot_code):
    st.markdown(f"#### 📦 录入机台至库位: {slot_code}")
    st.info("该库位当前为空闲状态。请输入要入库的机台流水号：")
    
    sn_input = st.text_input("机台流水号", key=f"direct_inbound_sn_{slot_code}").strip()
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🚀 确认入库", type="primary", disabled=not sn_input, use_container_width=True):
            # 实时检查流水号是否存在且状态为待入库
            inventory_df = get_data()
            if not inventory_df.empty and "流水号" in inventory_df.columns:
                target_machine = inventory_df[inventory_df["流水号"].astype(str).str.strip() == sn_input]
                if target_machine.empty:
                    st.error("系统中未找到该流水号！请检查输入是否正确。")
                    return
                
                status = str(target_machine.iloc[0].get("状态", ""))
                if "待入库" not in status:
                    st.error(f"该机台当前状态为【{status}】，只有【待入库】状态的机台才允许上架！")
                    return
            
            result = inbound_to_slot(sn_input, slot_code, is_transfer=False)
            if result.get("ok"):
                st.success(f"成功将机台 {sn_input} 入库至 {slot_code}！")
                st.session_state.direct_inbound_dialog_done = True
                time.sleep(0.5)
                st.rerun()
            else:
                st.error(result.get("message", "入库失败"))
    with col2:
        if st.button("❌ 取消", use_container_width=True):
            st.session_state.direct_inbound_dialog_done = True
            st.rerun()

@st.dialog("库位操作")
def show_mixed_action_dialog(slot_code, active_df, all_slots):
    st.markdown(f"#### 📍 库位操作: {slot_code}")
    
    tab1, tab2, tab3 = st.tabs(["� 在库明细", "� 存入机台 (入库)", "📤 移出机台 (调拨)"])
    
    with tab1:
        if active_df.empty:
            st.info("当前库位无机台数据。")
        else:
            st.write(f"**当前占用**: {len(active_df)} / {WAREHOUSE_MAX_CAPACITY} 台")
            display_df = active_df[["流水号", "机型", "预计入库时间", "更新时间", "机台备注/配置"]].copy()
            st.dataframe(display_df, hide_index=True, use_container_width=True)
            
    with tab2:
        st.info("输入待入库的机台流水号：")
        sn_input = st.text_input("机台流水号", key=f"mixed_inbound_sn_{slot_code}").strip()
        
        if st.button("🚀 确认入库", type="primary", disabled=not sn_input, use_container_width=True, key=f"btn_mixed_in_{slot_code}"):
            inventory_df = get_data()
            if not inventory_df.empty and "流水号" in inventory_df.columns:
                target_machine = inventory_df[inventory_df["流水号"].astype(str).str.strip() == sn_input]
                if target_machine.empty:
                    st.error("系统中未找到该流水号！")
                else:
                    status = str(target_machine.iloc[0].get("状态", ""))
                    if "待入库" not in status:
                        st.error(f"该机台状态为【{status}】，只允许【待入库】机台！")
                    else:
                        result = inbound_to_slot(sn_input, slot_code, is_transfer=False)
                        if result.get("ok"):
                            st.success(f"成功将 {sn_input} 入库！")
                            st.session_state.mixed_action_dialog_done = True
                            time.sleep(0.5)
                            st.rerun()
                        else:
                            st.error(result.get("message", "入库失败"))
                            
    with tab3:
        st.write("选择当前库位中要移出的机台：")
        options = active_df['流水号'].tolist()
        selected_sn = st.selectbox("流水号", options=[""] + options, key=f"mixed_transfer_sn_{slot_code}")
        
        if st.button("➡️ 下一步 (选择目标库位)", type="primary", disabled=not selected_sn, use_container_width=True, key=f"btn_mixed_out_{slot_code}"):
            st.session_state.pending_transfer_sn = selected_sn
            st.session_state.pending_transfer_slot = slot_code
            st.session_state.show_mixed_action_dialog = False
            st.session_state.show_transfer_select_dialog = False # 确保如果是从满载状态进来的也被清理
            st.session_state.show_transfer_action_dialog = True
            st.rerun()

    st.markdown("---")
    if st.button("❌ 取消操作", use_container_width=True, key=f"btn_mixed_cancel_{slot_code}"):
        st.session_state.mixed_action_dialog_done = True
        st.rerun()

import streamlit.components.v1 as components
import os

_warehouse_map = components.declare_component(
    "warehouse_map_v2_clickfix",
    path=os.path.abspath(os.path.join(os.path.dirname(__file__), "warehouse_map_frontend_v2"))
)

def render_warehouse_map(mode="dashboard", pending_sn=None, fullscreen=False):
    """
    渲染可视化库位图
    mode: "dashboard" (大屏展示) 或 "inbound" (入库作业交互)
    """
    layout_resp = get_warehouse_layout("default")
    slots = layout_resp.get("layout_json", {}).get("slots", [])
    if not slots:
        st.info("当前尚未配置任何库位，请先在入库作业中配置库位布局。")
        return None

    inventory_df = get_data().copy()
    if "Location_Code" not in inventory_df.columns:
        inventory_df["Location_Code"] = ""
        
    slots_data = []
    
    for s in slots:
        code = str(s.get("code", "")).strip()
        x = int(float(s.get("x", 0)))
        y = int(float(s.get("y", 0)))
        w = int(float(s.get("w", 300)))
        h = int(float(s.get("h", 160)))
        slot_status_cfg = str(s.get("status", "正常")).strip()
        
        slot_df = inventory_df[inventory_df["Location_Code"].astype(str).str.strip() == code]
        active_df = slot_df[slot_df["状态"].astype(str).str.contains("库存中", na=False)]
        count = len(active_df)
        
        if slot_status_cfg in ["锁定", "异常"]:
            status = "锁定异常"
        elif count == 0:
            status = "空闲"
        elif count >= WAREHOUSE_MAX_CAPACITY:
            status = "满载"
        else:
            status = "占用"
            
        machines = []
        for _, row in active_df.iterrows():
            sn = str(row.get('流水号', ''))
            model = str(row.get('机型', ''))
            in_time = str(row.get('预计入库时间', ''))
            if in_time and in_time != 'NaT':
                try:
                    in_time = str(pd.to_datetime(in_time).date())
                except:
                    pass
            else:
                in_time = str(row.get('更新时间', '')).split(' ')[0]
            
            machines.append({
                "sn": sn,
                "model": model,
                "in_time": in_time
            })

        slots_data.append({
            "code": code,
            "x": x,
            "y": y,
            "w": w,
            "h": h,
            "status": status,
            "count": count,
            "max_capacity": WAREHOUSE_MAX_CAPACITY,
            "machines": machines
        })

    # Render custom component
    clicked_value = _warehouse_map(slots=slots_data, fullscreen=fullscreen, key=f"warehouse_map_comp_{mode}")
    st.session_state._warehouse_click_raw = clicked_value

    selected_code = None
    click_token = None
    if isinstance(clicked_value, dict):
        selected_code = str(clicked_value.get("code", "")).strip()
        click_token = clicked_value.get("ts")
    elif clicked_value:
        raw_value = str(clicked_value).strip()
        if "||" in raw_value:
            selected_code, click_token = raw_value.split("||", 1)
            selected_code = selected_code.strip()
        else:
            selected_code = raw_value

    selected_event_id = f"{selected_code}|{click_token}" if (selected_code and click_token is not None) else selected_code

    if selected_code and selected_event_id != st.session_state.get('last_selected_code'):
        if selected_code == "EXIT_FULLSCREEN":
            st.session_state.fullscreen = False
            st.session_state.last_selected_code = "EXIT_FULLSCREEN"
            st.rerun()
        else:
            # 实时获取该库位状态
            slot_status = "空闲"
            for s_data in slots_data:
                if s_data['code'] == selected_code:
                    slot_status = s_data['status']
                    break
            
            st.session_state.last_selected_code = selected_event_id
            
            # 清理所有可能残留的对话框状态，确保唯一打开
            st.session_state.show_direct_inbound_dialog = False
            st.session_state.show_mixed_action_dialog = False
            st.session_state.show_transfer_select_dialog = False
            st.session_state.show_transfer_action_dialog = False
            
            if slot_status == '空闲':
                st.session_state.pending_direct_inbound_slot = selected_code
                st.session_state.show_direct_inbound_dialog = True
            elif slot_status == '占用':
                st.session_state.pending_mixed_action_slot = selected_code
                st.session_state.show_mixed_action_dialog = True
            else:
                # 满载或异常锁定状态
                st.session_state.pending_transfer_slot = selected_code
                st.session_state.show_transfer_select_dialog = True
            st.rerun()
            
    # 大屏综合操作对话框 (针对"占用"状态，支持入库和移出)
    if st.session_state.get('show_mixed_action_dialog', False):
        slot_code = st.session_state.get('pending_mixed_action_slot')
        if slot_code:
            slot_df = inventory_df[inventory_df["Location_Code"].astype(str).str.strip() == slot_code]
            active_df = slot_df[slot_df["状态"].astype(str).str.contains("库存中", na=False)]
            show_mixed_action_dialog(slot_code, active_df, slots)
            
        if st.session_state.get('mixed_action_dialog_done', False):
            st.session_state.show_mixed_action_dialog = False
            st.session_state.mixed_action_dialog_done = False
            st.session_state.pending_mixed_action_slot = None
            st.session_state.last_selected_code = "__cleared__"
            st.rerun()
            
    # 大屏直接入库对话框 (针对"空闲"状态)
    elif st.session_state.get('show_direct_inbound_dialog', False):
        slot_code = st.session_state.get('pending_direct_inbound_slot')
        if slot_code:
            show_direct_inbound_dialog(slot_code)
            
        if st.session_state.get('direct_inbound_dialog_done', False):
            st.session_state.show_direct_inbound_dialog = False
            st.session_state.direct_inbound_dialog_done = False
            st.session_state.pending_direct_inbound_slot = None
            st.session_state.last_selected_code = "__cleared__"
            st.rerun()

    # 调拨选择对话框 (针对满载或异常状态)
    elif st.session_state.get('show_transfer_select_dialog', False):
        slot_code = st.session_state.get('pending_transfer_slot')
        if slot_code:
            slot_df = inventory_df[inventory_df["Location_Code"].astype(str).str.strip() == slot_code]
            active_df = slot_df[slot_df["状态"].astype(str).str.contains("库存中", na=False)]
            
            if active_df.empty:
                st.toast(f"库位 {slot_code} 是空的，无可调拨机台")
                st.session_state.show_transfer_select_dialog = False
                st.session_state.last_selected_code = st.session_state.get('_warehouse_click_raw')
            else:
                # 复用综合操作对话框，但对于满载库位，默认打开"在库明细"或"移出机台"选项卡也是好的体验
                # 这里为了保持一致性，统一使用 show_mixed_action_dialog
                show_mixed_action_dialog(slot_code, active_df, slots)
                
        if st.session_state.get('mixed_action_dialog_done', False):
            st.session_state.show_transfer_select_dialog = False
            st.session_state.mixed_action_dialog_done = False
            st.session_state.pending_transfer_slot = None
            st.session_state.last_selected_code = "__cleared__"
            st.rerun()

    # 实际调拨操作对话框
    elif st.session_state.get('show_transfer_action_dialog', False):
        sn = st.session_state.get('pending_transfer_sn')
        current_slot = st.session_state.get('pending_transfer_slot')
        if sn and current_slot:
            render_transfer_dialog(sn, current_slot, slots)
            
        if st.session_state.get('transfer_dialog_done', False):
            st.session_state.show_transfer_action_dialog = False
            st.session_state.transfer_dialog_done = False
            st.session_state.pending_transfer_sn = None
            st.session_state.pending_transfer_slot = None
            st.session_state.last_selected_code = "__cleared__"
            st.rerun()
            st.rerun()

    return None


def render_warehouse_dashboard():
    """独立部署的大屏库位可视化模块"""
    check_access('WAREHOUSE_MAP')
    
    if st.session_state.get('fullscreen', False):
        st.markdown(
            """
            <style>
            /* 隐藏无关导航与控件 */
            [data-testid="stSidebar"] { display: none !important; }
            [data-testid="stHeader"] { display: none !important; }
            footer { display: none !important; }
            /* 页面填满 */
            .block-container { 
                padding: 0 !important; 
                max-width: 100% !important; 
                margin: 0 !important; 
            }
            .stApp {
                background-color: #111111 !important;
                overflow: hidden !important; /* 隐藏全局滚动条 */
            }
            /* 强制全屏 iframe 铺满且不滚动 */
            iframe {
                height: 100vh !important;
                width: 100vw !important;
                border: none !important;
            }
            /* 悬浮退出按钮容器 */
            .exit-fs-container {
                position: fixed;
                top: 20px;
                left: 20px;
                z-index: 999999;
            }
            </style>
            """, unsafe_allow_html=True
        )
        # 1秒实时刷新
        try:
            from streamlit_autorefresh import st_autorefresh
            st_autorefresh(interval=1000, key="fs_refresh")
        except ImportError:
            pass
            
        st.markdown('<div class="exit-fs-container">', unsafe_allow_html=True)
        if st.button("🏠 返回主页", key="back_home_fs_btn"):
            st.session_state.fullscreen = False
            st.session_state.page = "home"
            st.rerun()
        if st.button("❌ 退出全屏 (ESC)", key="exit_fs_btn"):
            st.session_state.fullscreen = False
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
        
        render_warehouse_map(mode="dashboard", fullscreen=True)
        return
        
    render_layout_config()
    
    st.markdown(
        """
        <style>
        /* 苹果风格响应式背景与卡片圆角 */
        .block-container {
            max-width: 95% !important;
            padding-top: 1rem !important;
            background-color: #F5F5F7; /* 苹果浅灰背景 */
        }
        .stApp {
            background-color: #F5F5F7 !important;
        }
        .dashboard-header {
            text-align: center;
            padding-bottom: 20px;
            color: #1D1D1F; /* 苹果深灰标题 */
            font-size: 2.5rem;
            font-weight: 600; /* 苹果惯用粗细 */
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            margin-top: 10px;
        }
        .legend-container {
            display: flex;
            justify-content: center;
            gap: 20px;
            margin-bottom: 20px;
            flex-wrap: wrap; /* 移动端自动换行 */
        }
        .legend-item {
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 1.1rem;
            font-weight: 500;
            color: #8E8E93; /* 苹果次级文字颜色 */
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        }
        .legend-color {
            width: 20px;
            height: 20px;
            border-radius: 6px; /* 苹果圆角 */
            border: 1px solid rgba(0,0,0,0.1); /* 柔和边框 */
            box-shadow: 0 2px 4px rgba(0,0,0,0.05); /* 柔和阴影 */
        }
        /* 移动端响应式字体 */
        @media (max-width: 768px) {
            .dashboard-header { font-size: 1.8rem; }
            .legend-item { font-size: 0.9rem; }
            .block-container { max-width: 100% !important; padding: 0.5rem !important; }
        }
        </style>
        """,
        unsafe_allow_html=True
    )

    col1, col2, col3 = st.columns([1.2, 7.8, 1])
    with col1:
        st.write("")
        if st.button("🏠 返回主页", use_container_width=True, key="back_home_btn"):
            st.session_state.page = "home"
            st.rerun()
    with col2:
        st.markdown('<div class="dashboard-header">🏢 数字化智能化大屏库位可视化</div>', unsafe_allow_html=True)
    with col3:
        st.write("") # spacer
        st.write("") # spacer
        if st.button("🔲 全屏显示", use_container_width=True):
            st.session_state.fullscreen = True
            st.rerun()
    
    st.markdown(
        """
        <div class="legend-container">
            <div class="legend-item"><div class="legend-color" style="background:#FFFFFF; border-color:#34C759;"></div> 空闲</div>
            <div class="legend-item"><div class="legend-color" style="background:#F2F2F7; border-color:#007AFF;"></div> 占用</div>
            <div class="legend-item"><div class="legend-color" style="background:#FFEBEE; border-color:#FF3B30;"></div> 满载</div>
            <div class="legend-item"><div class="legend-color" style="background:#E5E5EA; border-color:#8E8E93;"></div> 锁定/异常</div>
        </div>
        """,
        unsafe_allow_html=True
    )
    
    render_warehouse_map(mode="dashboard")
