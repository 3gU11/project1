import logging
from sqlalchemy.exc import IntegrityError, OperationalError

from crud.users import create_pending_user, get_user_for_login, normalize_username, user_exists


logger = logging.getLogger(__name__)


def register_user(username, password, role, name):
    try:
        if user_exists(username):
            return False, "用户名已存在"
    except (OperationalError, Exception) as e:
        return False, f"系统错误: {e}"

    try:
        create_pending_user(username, password, role, name)
        return True, "注册成功，请等待管理员审核"
    except (IntegrityError, OperationalError, Exception) as e:
        return False, f"系统错误，保存失败: {e}"


def verify_login(username, password):
    raw_username = str(username)
    username_norm = normalize_username(raw_username)
    logger.info("login_verify_start username_raw='%s' username_norm='%s'", raw_username, username_norm)
    try:
        user_row = get_user_for_login(raw_username)
    except (OperationalError, Exception) as e:
        logger.exception("login_verify_db_error username_norm='%s'", username_norm)
        return False, f"系统错误: {e}", None

    if not user_row:
        logger.warning("login_verify_user_not_found username_norm='%s'", username_norm)
        return False, "用户不存在", None

    if str(user_row.get('password', '')) != str(password):
        logger.warning("login_verify_password_mismatch username_norm='%s'", username_norm)
        return False, "密码错误", None

    status = str(user_row.get('status', '')).strip().lower()
    if status == 'active':
        logger.info("login_verify_success username_norm='%s' role='%s'", username_norm, user_row.get("role", ""))
        return True, "登录成功", user_row
    if status == 'pending':
        return False, "账户待审核，请联系管理员", None
    if status == 'rejected':
        return False, "账户审核未通过", None
    return False, f"账户状态异常: {status}", None
