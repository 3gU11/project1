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
                DATE_FORMAT(`时间`, '%Y-%m-%d %H:%i:%s') AS created_at,
                NULL AS contract_no,
                NULL AS order_no,
                NULL AS content
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
                DATE_FORMAT(`operate_time`, '%Y-%m-%d %H:%i:%s') AS created_at,
                CAST(`contract_no` AS CHAR) AS contract_no,
                CAST(`order_no` AS CHAR) AS order_no,
                CAST(`content` AS CHAR) AS content
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
