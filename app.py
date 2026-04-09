import streamlit as st

from core.bootstrap import initialize_app
from core.auth import try_auto_login
from core.permissions import get_role_permissions
from views.auth import login_form
from views.router import render_current_page
from views.sidebar import render_sidebar

initialize_app()

auto_logged_in = try_auto_login()
if auto_logged_in:
    st.session_state.permissions = get_role_permissions(st.session_state.role)

if st.session_state.current_user is None:
    login_form()
    st.stop()

render_sidebar()
render_current_page(st.session_state.page)
