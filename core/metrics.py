from datetime import datetime, timedelta

from crud.planning import get_factory_plan


def get_urgent_production_count():
    fp = get_factory_plan()
    if fp.empty:
        return 0
    today = datetime.now().date()
    target_date = today + timedelta(days=14)
    count = 0
    for _, row in fp.iterrows():
        status = str(row['状态']).strip()
        deadline_str = str(row['要求交期']).strip()
        if status == "待规划" and deadline_str:
            try:
                d_date = datetime.strptime(deadline_str, "%Y-%m-%d").date()
                if d_date <= target_date:
                    count += 1
            except Exception:
                pass
    return count
