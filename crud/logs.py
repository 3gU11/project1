from datetime import datetime, timedelta

import pandas as pd
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from database import get_engine


def append_log(action, sn_list, operator=None):
    current_time = datetime.now()
    operator = operator or "Unknown"
    new_logs = [{"时间": current_time, "操作类型": action, "流水号": sn, "操作员": operator} for sn in sn_list]
    if new_logs:
        try:
            pd.DataFrame(new_logs).to_sql('transaction_log', get_engine(), if_exists='append', index=False, method='multi')
        except (OperationalError, Exception) as e:
            print(f"append_log error: {e}")


def get_transaction_logs(page: int = 1, page_size: int = 50, days: int = 14):
    try:
        page = max(1, int(page))
        page_size = max(1, min(int(page_size), 200))
        days = max(1, int(days))
        offset = (page - 1) * page_size
        cutoff = datetime.now() - timedelta(days=days)
        with get_engine().connect() as conn:
            total = conn.execute(
                text("SELECT COUNT(*) FROM transaction_log WHERE 时间 >= :cutoff"),
                {"cutoff": cutoff},
            ).scalar() or 0
            df = pd.read_sql(
                text(
                    "SELECT DATE_FORMAT(时间, '%Y-%m-%d') AS 时间, 操作类型, 流水号, 操作员 "
                    "FROM transaction_log "
                    "WHERE 时间 >= :cutoff "
                    "ORDER BY transaction_log.时间 DESC "
                    "LIMIT :limit OFFSET :offset"
                ),
                conn,
                params={"cutoff": cutoff, "limit": page_size, "offset": offset},
            )
            return df, int(total)
    except (OperationalError, Exception):
        return pd.DataFrame(columns=["时间", "操作类型", "流水号", "操作员"]), 0
