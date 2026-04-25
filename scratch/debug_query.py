from database import get_engine
from sqlalchemy import text
import pandas as pd
engine = get_engine()

query = """
    SELECT * FROM (
        SELECT
            fp.`机型` AS `机型`,
            fp.`状态` AS `状态`,
            fp.`合同号` AS `合同号`,
            fp.`订单号` AS `订单号`,
            fp.`客户名` AS `客户`,
            fp.`代理商` AS `代理商`,
            GROUP_CONCAT(DISTINCT fg.`状态` ORDER BY fg.`状态` SEPARATOR ' / ') AS `机台状态`,
            fp.`要求交期` AS `要求交期`,
            CAST(so.`发货时间` AS CHAR) AS `发货时间`,
            GROUP_CONCAT(DISTINCT CAST(fg.`流水号` AS CHAR) ORDER BY fg.`流水号` SEPARATOR ', ') AS `流水号`
        FROM factory_plan fp
        LEFT JOIN finished_goods_data fg
          ON fg.`占用订单号` = fp.`订单号`
         AND fg.`机型` = fp.`机型`
        LEFT JOIN sales_orders so
          ON fp.`订单号` = so.`订单号`
        WHERE fp.`客户名` LIKE :kw1
           OR fp.`代理商` LIKE :kw2
           OR fp.`合同号` LIKE :kw3
           OR fp.`订单号` LIKE :kw4
        GROUP BY
            fp.`机型`,
            fp.`状态`,
            fp.`合同号`,
            fp.`订单号`,
            fp.`客户名`,
            fp.`代理商`,
            fp.`要求交期`,
            so.`发货时间`
            
        UNION ALL
        
        SELECT 
            fg.`机型` AS `机型`,
            '单台追溯' COLLATE utf8mb4_general_ci AS `状态`,
            fp.`合同号` AS `合同号`,
            fg.`占用订单号` AS `订单号`,
            COALESCE(fp.`客户名`, so.`客户名`) COLLATE utf8mb4_general_ci AS `客户`,
            COALESCE(fp.`代理商`, so.`代理商`) COLLATE utf8mb4_general_ci AS `代理商`,
            fg.`状态` AS `机台状态`,
            fp.`要求交期` AS `要求交期`,
            CAST(so.`发货时间` AS CHAR) AS `发货时间`,
            fg.`流水号` AS `流水号`
        FROM finished_goods_data fg
        LEFT JOIN factory_plan fp
          ON fg.`占用订单号` = fp.`订单号`
         AND fg.`机型` = fp.`机型`
        LEFT JOIN sales_orders so
          ON fg.`占用订单号` = so.`订单号`
        WHERE fg.`流水号` LIKE :kw5
    ) AS combined
    ORDER BY `合同号` DESC, `订单号` DESC, `机型` ASC
"""

keyword = 'HT202602053037'
pattern = f"%{keyword}%"
params = {f"kw{i}": pattern for i in range(1, 6)}

try:
    with engine.connect() as conn:
        df = pd.read_sql(text(query), conn, params=params)
        print(f"Success! Found {len(df)} rows")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
