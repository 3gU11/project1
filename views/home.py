import streamlit as st

from config import FUNC_MAP
from core.navigation import go_page


def render_home():
    st.title("🏭 成品整机管理系统 V7.0")
    st.caption(f"当前用户: {st.session_state.operator_name} | 角色: {st.session_state.role}")
    st.write("")

    user_perms = st.session_state.get('permissions', [])

    # 1. 顶部：管理与统筹
    # 动态组装
    top_buttons = []
    if "PLANNING" in user_perms: top_buttons.append(FUNC_MAP["PLANNING"])
    if "CONTRACT" in user_perms: top_buttons.append(FUNC_MAP["CONTRACT"])

    if top_buttons:
        st.markdown("#### 👑 管理与统筹")
        c_adm = st.columns(len(top_buttons))
        for idx, btn in enumerate(top_buttons):
            with c_adm[idx]:
                st.markdown(f'<div class="{btn["class"]}">', unsafe_allow_html=True)
                if st.button(btn["label"], key=f"home_top_{btn['page']}", use_container_width=True): 
                    go_page(btn["page"]); st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)
        st.divider()

    # 2. 核心业务按钮
    # 按照业务流顺序: INBOUND -> SALES_CREATE -> SALES_ALLOC -> SHIP_CONFIRM -> QUERY -> MACHINE_EDIT
    flow_order = ["INBOUND", "SALES_CREATE", "SALES_ALLOC", "SHIP_CONFIRM", "QUERY", "MACHINE_EDIT", "ARCHIVE"]

    core_buttons = []
    for code in flow_order:
        if code in user_perms and code not in ["PLANNING", "CONTRACT"]: # Avoid duplicates if any overlap
             core_buttons.append(FUNC_MAP[code])
        
    # 动态渲染按钮 (每行3个)
    if core_buttons:
        for i in range(0, len(core_buttons), 3):
            cols = st.columns(3, gap="medium")
            batch = core_buttons[i:i+3]
            for idx, btn in enumerate(batch):
                with cols[idx]:
                    st.markdown(f'<div class="big-btn {btn["class"]}">', unsafe_allow_html=True)
                    if st.button(btn["label"], key=f"home_btn_{btn['page']}"): 
                        go_page(btn["page"]); st.rerun()
                    st.markdown('</div>', unsafe_allow_html=True)

    # --- 👥 用户管理 (Admin) ---
