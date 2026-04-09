from views.boss_planning import render_boss_planning
from views.home import render_home
from views.inbound import render_inbound
from views.log_viewer import render_log_viewer
from views.machine_archive import render_machine_archive
from views.machine_edit import render_machine_edit
from views.production import render_production
from views.query import render_query
from views.sales_alloc import render_sales_alloc
from views.sales_create import render_sales_create
from views.ship_confirm import render_ship_confirm
from views.user_management import render_user_management
from views.warehouse_dashboard import render_warehouse_dashboard

ROUTES = {
    'home': render_home,
    'boss_planning': render_boss_planning,
    'production': render_production,
    'query': render_query,
    'machine_archive': render_machine_archive,
    'sales_create': render_sales_create,
    'inbound': render_inbound,
    'sales_alloc': render_sales_alloc,
    'ship_confirm': render_ship_confirm,
    'machine_edit': render_machine_edit,
    'log_viewer': render_log_viewer,
    'user_management': render_user_management,
    'warehouse_dashboard': render_warehouse_dashboard,
}


def render_current_page(page_name: str | None = None) -> None:
    current_page = page_name or 'home'
    render = ROUTES.get(current_page, render_home)
    render()
