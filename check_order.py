import sys
sys.path.insert(0, r'd:\CURSORpj\V7STD1.0')

from database import get_engine
from sqlalchemy import text
from datetime import datetime

ORDER_ID = 'SO-20260509-5536'
engine = get_engine()

with engine.begin() as conn:
    result = conn.execute(
        text("""
            UPDATE finished_goods_data
            SET 状态 = '待发货', 更新时间 = :now
            WHERE 占用订单号 = :oid AND 状态 != '已出库'
        """),
        {"oid": ORDER_ID, "now": datetime.now().strftime("%Y-%m-%d %H:%M")}
    )
    print(f"已更新 {result.rowcount} 台机台状态为 [待发货]")
