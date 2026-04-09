import time
from datetime import datetime

import streamlit as st

from core.navigation import go_home
from crud.users import get_all_users, save_all_users


def render_user_management():
    # Strict Admin Check - ONLY Admin role can access this, ignoring permissions
    if st.session_state.role != "Admin":
        st.error("🚫 权限不足！此页面仅限系统管理员访问。")
        st.button("⬅️ 返回首页", on_click=go_home)
        st.stop()

    c_back, c_title = st.columns([2, 8])
    with c_back: st.button("⬅️ 返回", on_click=go_home, use_container_width=True)
    with c_title: st.header("👥 用户注册审核与管理")

    users_df = get_all_users()

    # Metrics
    total = len(users_df)
    pending = len(users_df[users_df['status'] == 'pending'])
    active = len(users_df[users_df['status'] == 'active'])

    c1, c2, c3 = st.columns(3)
    c1.metric("总用户数", total)
    c2.metric("🟢 活跃用户", active)
    c3.metric("🟠 待审核", pending)

    st.divider()

    tab_audit, tab_all = st.tabs(["🟠 待审核申请", "📋 所有用户列表"])

    with tab_audit:
        pending_df = users_df[users_df['status'] == 'pending'].copy()
        if pending_df.empty:
            st.info("暂无待审核的注册申请")
        else:
            for idx, row in pending_df.iterrows():
                with st.container(border=True):
                    c_info, c_act = st.columns([3, 1])
                    with c_info:
                        role_map_audit = {"Sales": "销售员", "Prod": "生产/仓管", "Boss": "老板/管理", "Admin": "管理员", "Inbound": "入库员"}
                        role_cn = role_map_audit.get(row['role'], row['role'])
                        st.markdown(f"**申请人:** {row['name']} (`{row['username']}`)")
                        st.caption(f"申请角色: **{role_cn}** | 申请时间: {row['register_time']}")
                    
                    with c_act:
                        c_a1, c_a2 = st.columns(2)
                        with c_a1:
                            if st.button("✅ 通过", key=f"app_{row['username']}"):
                                users_df.loc[users_df['username'] == row['username'], 'status'] = 'active'
                                users_df.loc[users_df['username'] == row['username'], 'auditor'] = st.session_state.operator_name
                                users_df.loc[users_df['username'] == row['username'], 'audit_time'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                save_all_users(users_df)
                                st.success(f"已批准 {row['name']}")
                                time.sleep(0.5); st.rerun()
                        with c_a2:
                            if st.button("❌ 拒绝", key=f"rej_{row['username']}"):
                                users_df.loc[users_df['username'] == row['username'], 'status'] = 'rejected'
                                users_df.loc[users_df['username'] == row['username'], 'auditor'] = st.session_state.operator_name
                                users_df.loc[users_df['username'] == row['username'], 'audit_time'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                save_all_users(users_df)
                                st.warning(f"已拒绝 {row['name']}")
                                time.sleep(0.5); st.rerun()

    with tab_all:
        # Show all users
        st.dataframe(
            users_df[['username', 'name', 'role', 'status', 'register_time', 'audit_time', 'auditor']],
            use_container_width=True,
            hide_index=True
        )

    # --- 👑 生产统筹/订单规划 (老板核心功能) ---
