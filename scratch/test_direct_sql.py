import sys
import os
import pymysql

# Database config (based on database.py)
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '', # Assuming empty based on previous context or common local dev
    'db': 'v7std',
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor
}

def test_query(keyword):
    try:
        conn = pymysql.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        kw = f"%{keyword}%"
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
                    DATE_FORMAT(so.`发货时间`, '%Y-%m-%d') AS `发货时间`,
                    GROUP_CONCAT(DISTINCT CAST(fg.`流水号` AS CHAR) ORDER BY fg.`流水号` SEPARATOR ', ') AS `流水号`
                FROM factory_plan fp
                LEFT JOIN finished_goods_data fg
                  ON fg.`占用订单号` = fp.`订单号`
                 AND fg.`机型` = fp.`机型`
                LEFT JOIN sales_orders so
                  ON fp.`订单号` = so.`订单号`
                WHERE fp.`客户名` LIKE %s
                   OR fp.`代理商` LIKE %s
                   OR fp.`合同号` LIKE %s
                   OR fp.`订单号` LIKE %s
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
                    '单台追溯' AS `状态`,
                    fp.`合同号` AS `合同号`,
                    fg.`占用订单号` AS `订单号`,
                    COALESCE(fp.`客户名`, so.`客户名`) AS `客户`,
                    COALESCE(fp.`代理商`, so.`代理商`) AS `代理商`,
                    fg.`状态` AS `机台状态`,
                    fp.`要求交期` AS `要求交期`,
                    DATE_FORMAT(so.`发货时间`, '%Y-%m-%d') AS `发货时间`,
                    fg.`流水号` AS `流水号`
                FROM finished_goods_data fg
                LEFT JOIN factory_plan fp
                  ON fg.`占用订单号` = fp.`订单号`
                 AND fg.`机型` = fp.`机型`
                LEFT JOIN sales_orders so
                  ON fg.`占用订单号` = so.`订单号`
                WHERE fg.`流水号` LIKE %s
            ) AS combined
            ORDER BY `合同号` DESC, `订单号` DESC, `机型` ASC
        """
        cursor.execute(query, (kw, kw, kw, kw, kw))
        results = cursor.fetchall()
        print(f"Query found {len(results)} rows for '{keyword}'")
        for row in results:
            print(row)
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_query("187")
