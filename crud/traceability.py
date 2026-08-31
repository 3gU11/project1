import pandas as pd
from sqlalchemy import text
from database import get_engine
from utils.cache import fetch_data_with_cache


def _table_exists(conn, table_name: str) -> bool:
    try:
        return conn.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.TABLES "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :table_name"
            ),
            {"table_name": table_name},
        ).scalar() > 0
    except Exception:
        return False

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
                CAST(fp.`机型` AS CHAR) COLLATE utf8mb4_general_ci AS `机型`,
                CAST(fp.`状态` AS CHAR) COLLATE utf8mb4_general_ci AS `状态`,
                CAST(fp.`合同号` AS CHAR) COLLATE utf8mb4_general_ci AS `合同号`,
                CAST(fp.`订单号` AS CHAR) COLLATE utf8mb4_general_ci AS `订单号`,
                CAST(fp.`客户名` AS CHAR) COLLATE utf8mb4_general_ci AS `客户`,
                CAST(fp.`代理商` AS CHAR) COLLATE utf8mb4_general_ci AS `代理商`,
                GROUP_CONCAT(DISTINCT fg.`状态` ORDER BY fg.`状态` SEPARATOR ' / ') COLLATE utf8mb4_general_ci AS `机台状态`,
                CAST(fp.`要求交期` AS CHAR) COLLATE utf8mb4_general_ci AS `要求交期`,
                LEFT(CAST(so.`发货时间` AS CHAR), 10) COLLATE utf8mb4_general_ci AS `发货时间`,
                GROUP_CONCAT(DISTINCT CAST(fg.`流水号` AS CHAR) ORDER BY fg.`流水号` SEPARATOR ', ') COLLATE utf8mb4_general_ci AS `流水号`
            FROM factory_plan fp
            LEFT JOIN finished_goods_data fg
              ON (
                   fg.`合同号` = fp.`合同号`
                   OR (fg.`占用订单号` = fp.`订单号` AND COALESCE(TRIM(fp.`订单号`), '') <> '')
                 )
             AND fg.`机型` = fp.`机型`
            LEFT JOIN sales_orders so
              ON fp.`订单号` = so.`订单号`
            WHERE fp.`客户名` LIKE :kw1
               OR fp.`代理商` LIKE :kw2
               OR fp.`合同号` LIKE :kw3
               OR fp.`订单号` LIKE :kw4
               OR fp.`机型` LIKE :kw5
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
                CAST(fg.`机型` AS CHAR) COLLATE utf8mb4_general_ci AS `机型`,
                '单台追溯' COLLATE utf8mb4_general_ci AS `状态`,
                CAST(fp.`合同号` AS CHAR) COLLATE utf8mb4_general_ci AS `合同号`,
                CAST(fg.`占用订单号` AS CHAR) COLLATE utf8mb4_general_ci AS `订单号`,
                COALESCE(fp.`客户名`, so.`客户名`) COLLATE utf8mb4_general_ci AS `客户`,
                COALESCE(fp.`代理商`, so.`代理商`) COLLATE utf8mb4_general_ci AS `代理商`,
                CAST(fg.`状态` AS CHAR) COLLATE utf8mb4_general_ci AS `机台状态`,
                CAST(fp.`要求交期` AS CHAR) COLLATE utf8mb4_general_ci AS `要求交期`,
                LEFT(CAST(so.`发货时间` AS CHAR), 10) COLLATE utf8mb4_general_ci AS `发货时间`,
                CAST(fg.`流水号` AS CHAR) COLLATE utf8mb4_general_ci AS `流水号`
            FROM finished_goods_data fg
            LEFT JOIN factory_plan fp
              ON (
                   fg.`合同号` = fp.`合同号`
                   OR (fg.`占用订单号` = fp.`订单号` AND COALESCE(TRIM(fp.`订单号`), '') <> '')
                 )
             AND fg.`机型` = fp.`机型`
            LEFT JOIN sales_orders so
              ON fg.`占用订单号` = so.`订单号`
            WHERE fg.`流水号` LIKE :kw6
               OR fg.`机型` LIKE :kw7
               OR fg.`状态` LIKE :kw8
               OR fg.`合同号` LIKE :kw9
               OR fg.`占用订单号` LIKE :kw10

            UNION ALL

            SELECT
                CAST(pi.`机型` AS CHAR) COLLATE utf8mb4_general_ci AS `机型`,
                '待入库追溯' COLLATE utf8mb4_general_ci AS `状态`,
                CAST(pi.`合同号` AS CHAR) COLLATE utf8mb4_general_ci AS `合同号`,
                '' COLLATE utf8mb4_general_ci AS `订单号`,
                CAST(pi.`客户` AS CHAR) COLLATE utf8mb4_general_ci AS `客户`,
                CAST(pi.`代理商` AS CHAR) COLLATE utf8mb4_general_ci AS `代理商`,
                CAST(pi.`状态` AS CHAR) COLLATE utf8mb4_general_ci AS `机台状态`,
                LEFT(CAST(pi.`预计入库时间` AS CHAR), 10) COLLATE utf8mb4_general_ci AS `要求交期`,
                NULL AS `发货时间`,
                CAST(pi.`流水号` AS CHAR) COLLATE utf8mb4_general_ci AS `流水号`
            FROM plan_import pi
            WHERE pi.`流水号` LIKE :kw11
               OR pi.`批次号` LIKE :kw12
               OR pi.`合同号` LIKE :kw13
               OR pi.`机型` LIKE :kw14

            UNION ALL

            SELECT
                CAST(u.`model_type` AS CHAR) COLLATE utf8mb4_general_ci AS `机型`,
                '沙盘卡片追溯' COLLATE utf8mb4_general_ci AS `状态`,
                CAST(u.`contract_no` AS CHAR) COLLATE utf8mb4_general_ci AS `合同号`,
                '' COLLATE utf8mb4_general_ci AS `订单号`,
                CAST(u.`customer` AS CHAR) COLLATE utf8mb4_general_ci AS `客户`,
                CAST(u.`dealer_name` AS CHAR) COLLATE utf8mb4_general_ci AS `代理商`,
                CAST(u.`status` AS CHAR) COLLATE utf8mb4_general_ci AS `机台状态`,
                LEFT(CAST(u.`due_date` AS CHAR), 10) COLLATE utf8mb4_general_ci AS `要求交期`,
                NULL AS `发货时间`,
                CAST(COALESCE(NULLIF(u.`serial_no`, ''), NULLIF(u.`forecast_serial_no`, ''), u.`unit_id`) AS CHAR) COLLATE utf8mb4_general_ci AS `流水号`
            FROM units u
            LEFT JOIN batches b ON b.`batch_id` = u.`batch_id`
            WHERE COALESCE(u.`serial_no`, u.`forecast_serial_no`, u.`unit_id`) LIKE :kw15
               OR u.`contract_no` LIKE :kw16
               OR b.`batch_code` LIKE :kw17
               OR u.`model_type` LIKE :kw18
        ) AS combined
        ORDER BY `合同号` DESC, `订单号` DESC, `机型` ASC
    """
    pattern = f"%{keyword}%"
    params = {f"kw{i}": pattern for i in range(1, 19)}
    df = fetch_data_with_cache(query, params=params, ttl=30)
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
           OR `合同号` = :target_id
           OR `合同备注` LIKE :kw
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
    target_id = str(target_id or "").strip()
    if not target_id:
        return pd.DataFrame(columns=["id", "action", "流水号", "operator", "created_at", "contract_no", "order_no", "content"])

    params = {"target_id": target_id, "kw": f"%{target_id}%"}
    base_parts = [
        """
        SELECT
            NULL AS id,
            CAST(`操作类型` AS CHAR) COLLATE utf8mb4_general_ci AS action,
            CAST(`流水号` AS CHAR) COLLATE utf8mb4_general_ci AS `流水号`,
            CAST(`操作员` AS CHAR) COLLATE utf8mb4_general_ci AS operator,
            CAST(`时间` AS CHAR) COLLATE utf8mb4_general_ci AS created_at,
            CAST(NULL AS CHAR) COLLATE utf8mb4_general_ci AS contract_no,
            CAST(NULL AS CHAR) COLLATE utf8mb4_general_ci AS order_no,
            CAST(NULL AS CHAR) COLLATE utf8mb4_general_ci AS content
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
               OR `合同号` = :target_id
               OR `合同备注` LIKE :kw
           )
        """,
        """
        SELECT
            `id`,
            CAST(`action_type` AS CHAR) COLLATE utf8mb4_general_ci AS action,
            CAST(`serial_no` AS CHAR) COLLATE utf8mb4_general_ci AS `流水号`,
            CAST(`username` AS CHAR) COLLATE utf8mb4_general_ci AS operator,
            CAST(`operate_time` AS CHAR) COLLATE utf8mb4_general_ci AS created_at,
            CAST(`contract_no` AS CHAR) COLLATE utf8mb4_general_ci AS contract_no,
            CAST(`order_no` AS CHAR) COLLATE utf8mb4_general_ci AS order_no,
            CAST(`content` AS CHAR) COLLATE utf8mb4_general_ci AS content
        FROM sys_operation_log
        WHERE `serial_no` = :target_id
           OR `serial_no` LIKE :kw
           OR `order_no` = :target_id
           OR `contract_no` = :target_id
           OR `content` LIKE :kw
        """,
    ]

    optional_parts = []
    with get_engine().connect() as conn:
        if _table_exists(conn, "operation_log"):
            optional_parts.append(
                """
                SELECT
                    `log_id` AS id,
                    CAST(`action` AS CHAR) AS action,
                    CAST(`target_id` AS CHAR) COLLATE utf8mb4_general_ci AS `流水号`,
                    CAST(`actor` AS CHAR) COLLATE utf8mb4_general_ci AS operator,
                    CAST(`created_at` AS CHAR) COLLATE utf8mb4_general_ci AS created_at,
                    NULL AS contract_no,
                    NULL AS order_no,
                    CONCAT(
                        '对象：', COALESCE(CAST(`target_type` AS CHAR), ''),
                        ' / ', COALESCE(CAST(`target_id` AS CHAR), ''),
                        '；详情：', COALESCE(CAST(`detail` AS CHAR), '')
                    ) COLLATE utf8mb4_general_ci AS content
                FROM operation_log
                WHERE `target_id` = :target_id
                   OR `target_id` LIKE :kw
                   OR CAST(`detail` AS CHAR) LIKE :kw
                """
            )
        if _table_exists(conn, "production_history_ledger"):
            optional_parts.append(
                """
                SELECT
                    phl.`id` AS id,
                    CONCAT('生产看板-', COALESCE(CAST(phl.`status` AS CHAR), '')) AS action,
                    CAST(COALESCE(NULLIF(u.`serial_no`, ''), NULLIF(u.`forecast_serial_no`, ''), phl.`unit_id`) AS CHAR) COLLATE utf8mb4_general_ci AS `流水号`,
                    '生产看板' AS operator,
                    CAST(COALESCE(phl.`completed_at`, phl.`updated_at`, phl.`scheduled_at`) AS CHAR) COLLATE utf8mb4_general_ci AS created_at,
                    CAST(phl.`contract_no` AS CHAR) COLLATE utf8mb4_general_ci AS contract_no,
                    NULL AS order_no,
                    CONCAT(
                        '产线：', COALESCE(phl.`production_line_name`, ''),
                        '；批次：', COALESCE(phl.`batch_code`, ''),
                        '；机型：', COALESCE(phl.`model_type`, ''),
                        '；客户：', COALESCE(phl.`customer`, ''),
                        '；备注：', COALESCE(phl.`order_remark`, '')
                    ) COLLATE utf8mb4_general_ci AS content
                FROM production_history_ledger phl
                LEFT JOIN units u ON u.`unit_id` = phl.`unit_id`
                WHERE phl.`unit_id` = :target_id
                   OR phl.`unit_id` LIKE :kw
                   OR phl.`contract_no` = :target_id
                   OR phl.`batch_code` = :target_id
                   OR COALESCE(u.`serial_no`, u.`forecast_serial_no`, '') = :target_id
                   OR COALESCE(u.`serial_no`, u.`forecast_serial_no`, '') LIKE :kw
                """
            )

    query = f"""
        SELECT * FROM (
            {' UNION ALL '.join(base_parts + optional_parts)}
        ) AS combined
        WHERE created_at IS NOT NULL AND created_at <> ''
        ORDER BY created_at ASC
    """
    with get_engine().connect() as conn:
        df = pd.read_sql(text(query), conn, params=params)
    return df
