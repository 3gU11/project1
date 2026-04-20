import pandas as pd
from sqlalchemy import text
from database import get_engine
from utils.cache import fetch_data_with_cache

def search_global_summary(keyword: str = ""):
    """
    Step 1: 广度筛选 - 返回追溯第一层级列表。
    """
    keyword = str(keyword or "").strip()
    if not keyword:
        return pd.DataFrame()

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
                MIN(fg.`预计入库时间`) AS `预计入库时间`,
                NULL AS `流水号`
            FROM factory_plan fp
            LEFT JOIN finished_goods_data fg
              ON fg.`占用订单号` = fp.`订单号`
             AND fg.`机型` = fp.`机型`
            WHERE fp.`客户名` LIKE :kw
               OR fp.`代理商` LIKE :kw
               OR fp.`合同号` LIKE :kw
               OR fp.`订单号` LIKE :kw
            GROUP BY
                fp.`机型`,
                fp.`状态`,
                fp.`合同号`,
                fp.`订单号`,
                fp.`客户名`,
                fp.`代理商`
                
            UNION ALL
            
            SELECT 
                fg.`机型` AS `机型`,
                '单台追溯' AS `状态`,
                fp.`合同号` AS `合同号`,
                fg.`占用订单号` AS `订单号`,
                COALESCE(fp.`客户名`, so.`客户名`) AS `客户`,
                COALESCE(fp.`代理商`, so.`代理商`) AS `代理商`,
                fg.`状态` AS `机台状态`,
                fg.`预计入库时间` AS `预计入库时间`,
                fg.`流水号` AS `流水号`
            FROM finished_goods_data fg
            LEFT JOIN factory_plan fp
              ON fg.`占用订单号` = fp.`订单号`
             AND fg.`机型` = fp.`机型`
            LEFT JOIN sales_orders so
              ON fg.`占用订单号` = so.`订单号`
            WHERE fg.`流水号` LIKE :kw
        ) AS combined
        ORDER BY `合同号` DESC, `订单号` DESC, `机型` ASC
    """
    df = fetch_data_with_cache(query, params={"kw": f"%{keyword}%"}, ttl=30)
    return df

def get_target_status_distribution(target_id: str, model: str = ""):
    """
    Step 2.1: 获取精确 ID 的实时状态切片。
    """
    query = """
        SELECT `状态`, COUNT(*) AS 数量
        FROM finished_goods_data
        WHERE (
            `流水号` = :target_id
           OR `占用订单号` = :target_id
           OR `占用订单号` IN (
                SELECT DISTINCT `订单号`
                FROM factory_plan
                WHERE `合同号` = :target_id
                  AND COALESCE(TRIM(`订单号`), '') <> ''
           )
           OR `订单备注` LIKE :kw
        )
    """
    params = {"target_id": target_id, "kw": f"%{target_id}%"}
    if str(model).strip():
        query += " AND `机型` = :model"
        params["model"] = str(model).strip()
    query += " GROUP BY `状态`"
    df = fetch_data_with_cache(query, params=params, ttl=30)
    return df

def get_target_timeline(target_id: str):
    """
    Step 2.2: 获取目标对象生命周期的完整流转历史。
    """
    query = """
        SELECT * FROM (
            SELECT 
                NULL AS id, 
                CAST(`操作类型` AS CHAR) AS action, 
                CAST(`流水号` AS CHAR) AS `流水号`, 
                CAST(`操作员` AS CHAR) AS operator, 
                `时间` AS created_at
            FROM transaction_log
            WHERE `流水号` = :target_id
               OR `流水号` LIKE :kw
               OR `流水号` IN (
                SELECT `流水号` FROM finished_goods_data 
                WHERE `占用订单号` = :target_id
                   OR `占用订单号` IN (
                        SELECT DISTINCT `订单号`
                        FROM factory_plan
                        WHERE `合同号` = :target_id
                          AND COALESCE(TRIM(`订单号`), '') <> ''
                   )
                   OR `订单备注` LIKE :kw
               )
               
            UNION ALL
            
            SELECT 
                `id`, 
                CAST(`action_type` AS CHAR) AS action, 
                CAST(`serial_no` AS CHAR) AS `流水号`, 
                CAST(`username` AS CHAR) AS operator, 
                `operate_time` AS created_at
            FROM sys_operation_log
            WHERE `serial_no` = :target_id 
               OR `serial_no` LIKE :kw
               OR `order_no` = :target_id 
               OR `contract_no` = :target_id
               OR `content` LIKE :kw
        ) AS combined
        ORDER BY created_at ASC
    """
    df = fetch_data_with_cache(query, params={"target_id": target_id, "kw": f"%{target_id}%"}, ttl=30)
    return df
