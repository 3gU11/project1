import streamlit as st

from core.navigation import go_page


def render_sidebar():
    with st.sidebar:
        st.title("🏭 管理系统 V7.0")

        # 显示当前用户信息
        role_display_map = {
            "Sales": "销售员",
            "Prod": "生产/仓管",
            "Boss": "老板/管理",
            "Admin": "管理员",
            "Inbound": "入库员",
        }
        current_role_display = role_display_map.get(st.session_state.role, st.session_state.role)

        st.success(f"👤 {st.session_state.operator_name}")
        st.caption(f"角色: {current_role_display}")

        if st.button("🚪 退出登录", use_container_width=True):
            from core.auth import logout_user
            logout_user()
            st.rerun()

        st.divider()

        # 根据角色显示侧边栏功能
        user_perms = st.session_state.get('permissions', [])

        # 1. Management
        if "PLANNING" in user_perms:
            st.subheader("👑 管理功能")
            if st.button("👑 生产统筹/订单规划", use_container_width=True):
                go_page('boss_planning')
                st.rerun()

        # Admin User Management
        if st.session_state.role == "Admin":
            if st.button("👥 用户管理 (管理员)", use_container_width=True):
                go_page('user_management')
                st.rerun()

        # 2. Contract
        if "CONTRACT" in user_perms:
            if st.button("🏭 合同管理", use_container_width=True):
                go_page('production')
                st.rerun()

        st.divider()
        if "WAREHOUSE_MAP" in user_perms:
            if st.button("🗺️ 库位大屏"):
                go_page('warehouse_dashboard')
        if "QUERY" in user_perms:
            if st.button("📁 交易日志"):
                go_page('log_viewer')
        if "ARCHIVE" in user_perms:
            if st.button("📂 机台档案"):
                go_page('machine_archive')
