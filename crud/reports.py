"""
CRUD operations for report generation
Provides data fetching and aggregation logic for all report types
"""
import pandas as pd
from sqlalchemy import text
from database import get_engine
from crud.inbound_history import ensure_inbound_history_table
from typing import Dict, Any


def get_inbound_report_data(
    start_date: str,
    end_date: str,
    model_type: str = "",
    customer: str = ""
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Fetch inbound report data with filters
    Returns (summary_df, detail_df)
    Uses immutable inbound history events rather than current inventory state.
    If inbound_history is empty, falls back to transaction_log.
    """
    with get_engine().begin() as conn:
        ensure_inbound_history_table(conn)

        # Check if inbound_history has data
        count_result = conn.execute(text("SELECT COUNT(*) FROM inbound_history")).fetchone()
        has_history = count_result and count_result[0] > 0

        if not has_history:
            # Fallback: query from transaction_log + finished_goods_data + shipping_history
            detail_sql = text("""
                SELECT
                    DATE_FORMAT(tl.`时间`, '%Y-%m-%d') AS `入库日期`,
                    tl.`流水号` AS `流水号`,
                    COALESCE(fg.`批次号`, sh.`批次号`, '') AS `批次号`,
                    COALESCE(fg.`机型`, sh.`机型`, '') AS `机型`,
                    COALESCE(fg.`状态`, sh.`状态`, '') AS `状态`,
                    COALESCE(fg.`客户`, sh.`客户`, '') AS `客户`,
                    COALESCE(fg.`代理商`, sh.`代理商`, '') AS `代理商`,
                    COALESCE(fg.`占用订单号`, sh.`占用订单号`, '') AS `订单号`,
                    COALESCE(fg.`Location_Code`, '') AS `库位`,
                    COALESCE(tl.`操作员`, '') AS `操作员`,
                    DATE_FORMAT(tl.`时间`, '%Y-%m-%d %H:%i') AS `入库时间`
                FROM transaction_log tl
                LEFT JOIN finished_goods_data fg
                    ON fg.`流水号` = tl.`流水号` COLLATE utf8mb4_general_ci
                LEFT JOIN shipping_history sh
                    ON sh.`流水号` = tl.`流水号` COLLATE utf8mb4_general_ci
                WHERE tl.`时间` BETWEEN :start_date AND :end_date
                    AND tl.`流水号` IS NOT NULL
                    AND TRIM(tl.`流水号`) <> ''
                    AND (
                        tl.`操作类型` = '直接配货-自动入库'
                        OR tl.`操作类型` = '配货自动入库'
                        OR (
                            tl.`操作类型` LIKE '%入库%'
                            AND tl.`操作类型` NOT LIKE '%退回%'
                            AND tl.`操作类型` NOT LIKE '%释放%'
                            AND tl.`操作类型` NOT LIKE '%撤回%'
                        )
                    )
                    AND COALESCE(fg.`状态`, sh.`状态`, '') COLLATE utf8mb4_general_ci <> '待入库'
                    AND COALESCE(fg.`状态`, sh.`状态`, '') COLLATE utf8mb4_general_ci <> ''
                    AND (:model_type = '' OR COALESCE(fg.`机型`, sh.`机型`, '') = :model_type)
                    AND (:customer = '' OR COALESCE(fg.`客户`, sh.`客户`, '') = :customer)
                ORDER BY tl.`时间` DESC, `批次号`, tl.`流水号`
            """)

            detail_df = pd.read_sql(
                detail_sql,
                conn,
                params={
                    "start_date": start_date,
                    "end_date": end_date,
                    "model_type": model_type,
                    "customer": customer
                }
            )

            # Summary query - grouped by model only (simple production statistics)
            # Use DISTINCT to avoid counting same serial_no multiple times
            # Join with model_dictionary to get sort_order
            # Use COLLATE to fix collation mismatch
            summary_sql = text("""
                SELECT
                    ur.`机型`,
                    COUNT(*) AS `数量`,
                    COALESCE(md.sort_order, 9999) AS sort_order
                FROM (
                    SELECT DISTINCT
                        tl.`流水号`,
                        COALESCE(fg.`机型`, sh.`机型`, '') AS `机型`
                    FROM transaction_log tl
                    LEFT JOIN finished_goods_data fg
                        ON fg.`流水号` = tl.`流水号` COLLATE utf8mb4_general_ci
                    LEFT JOIN shipping_history sh
                        ON sh.`流水号` = tl.`流水号` COLLATE utf8mb4_general_ci
                    WHERE tl.`时间` BETWEEN :start_date AND :end_date
                        AND tl.`流水号` IS NOT NULL
                        AND TRIM(tl.`流水号`) <> ''
                        AND (
                            tl.`操作类型` = '直接配货-自动入库'
                            OR tl.`操作类型` = '配货自动入库'
                            OR (
                                tl.`操作类型` LIKE '%入库%'
                                AND tl.`操作类型` NOT LIKE '%退回%'
                                AND tl.`操作类型` NOT LIKE '%释放%'
                                AND tl.`操作类型` NOT LIKE '%撤回%'
                            )
                        )
                        AND COALESCE(fg.`状态`, sh.`状态`, '') COLLATE utf8mb4_general_ci <> '待入库'
                        AND COALESCE(fg.`状态`, sh.`状态`, '') COLLATE utf8mb4_general_ci <> ''
                        AND (:model_type = '' OR COALESCE(fg.`机型`, sh.`机型`, '') = :model_type)
                        AND (:customer = '' OR COALESCE(fg.`客户`, sh.`客户`, '') = :customer)
                ) AS ur
                LEFT JOIN model_dictionary md
                    ON md.model_name = ur.`机型` COLLATE utf8mb4_general_ci
                WHERE ur.`机型` <> ''
                GROUP BY ur.`机型`, md.sort_order
                ORDER BY sort_order ASC, ur.`机型`
            """)

            summary_df = pd.read_sql(
                summary_sql,
                conn,
                params={
                    "start_date": start_date,
                    "end_date": end_date,
                    "model_type": model_type,
                    "customer": customer
                }
            )

            # Calculate percentage
            if not summary_df.empty:
                total = summary_df['数量'].sum()
                summary_df['占比'] = summary_df['数量'].apply(lambda x: f"{(x/total*100):.2f}%")
                # Remove sort_order column (used only for sorting)
                if 'sort_order' in summary_df.columns:
                    summary_df = summary_df.drop(columns=['sort_order'])

            return summary_df, detail_df

        # Original logic using inbound_history table
        # Detail query - all individual records
        detail_sql = text("""
            SELECT
                DATE_FORMAT(ih.inbound_time, '%Y-%m-%d') AS `入库日期`,
                ih.serial_no AS `流水号`,
                ih.batch_no AS `批次号`,
                ih.model AS `机型`,
                ih.status_after AS `状态`,
                ih.customer AS `客户`,
                ih.dealer AS `代理商`,
                ih.order_no AS `订单号`,
                ih.slot_code AS `库位`,
                ih.operator AS `操作员`,
                DATE_FORMAT(ih.inbound_time, '%Y-%m-%d %H:%i') AS `入库时间`
            FROM inbound_history ih
            WHERE ih.inbound_time BETWEEN :start_date AND :end_date
                AND COALESCE(ih.status_after, '') <> '待入库'
                AND COALESCE(ih.status_after, '') <> ''
                AND (:model_type = '' OR ih.model = :model_type)
                AND (:customer = '' OR ih.customer = :customer)
            ORDER BY ih.inbound_time DESC, ih.batch_no, ih.serial_no
        """)

        detail_df = pd.read_sql(
            detail_sql,
            conn,
            params={
                "start_date": start_date,
                "end_date": end_date,
                "model_type": model_type,
                "customer": customer
            }
        )

        # Summary query - grouped by model only (simple production statistics)
        # Join with model_dictionary to get sort_order
        # Use COLLATE to fix collation mismatch
        summary_sql = text("""
            SELECT
                ih.model AS `机型`,
                COUNT(*) AS `数量`,
                COALESCE(md.sort_order, 9999) AS sort_order
            FROM inbound_history ih
            LEFT JOIN model_dictionary md
                ON md.model_name = ih.model COLLATE utf8mb4_general_ci
            WHERE ih.inbound_time BETWEEN :start_date AND :end_date
                AND COALESCE(ih.status_after, '') <> '待入库'
                AND COALESCE(ih.status_after, '') <> ''
                AND (:model_type = '' OR ih.model = :model_type)
                AND (:customer = '' OR ih.customer = :customer)
            GROUP BY ih.model, md.sort_order
            ORDER BY sort_order ASC, ih.model
        """)

        summary_df = pd.read_sql(
            summary_sql,
            conn,
            params={
                "start_date": start_date,
                "end_date": end_date,
                "model_type": model_type,
                "customer": customer
            }
        )

        # Calculate percentage
        if not summary_df.empty:
            total = summary_df['数量'].sum()
            summary_df['占比'] = summary_df['数量'].apply(lambda x: f"{(x/total*100):.2f}%")
            # Remove sort_order column (used only for sorting)
            if 'sort_order' in summary_df.columns:
                summary_df = summary_df.drop(columns=['sort_order'])

    return summary_df, detail_df


def get_order_report_data(
    start_date: str,
    end_date: str,
    customer: str = "",
    dealer: str = "",
    status: str = ""
) -> pd.DataFrame:
    """
    Fetch order report data with filters
    Status options: 'active' (进行中), 'done' (已完结), 'deleted' (已删除)
    """
    with get_engine().connect() as conn:
        sql = text("""
            SELECT
                so.`订单号`,
                DATE_FORMAT(so.`下单时间`, '%Y-%m-%d') AS `下单日期`,
                so.`客户名`,
                so.`代理商`,
                so.`需求机型`,
                so.`需求数量`,
                so.`status` AS `订单状态`,
                DATE_FORMAT(so.`发货时间`, '%Y-%m-%d') AS `计划发货日期`,
                so.`备注`
            FROM sales_orders so
            WHERE so.`下单时间` BETWEEN :start_date AND :end_date
                AND (:customer = '' OR so.`客户名` = :customer)
                AND (:dealer = '' OR so.`代理商` = :dealer)
                AND (:status = '' OR so.`status` = :status)
            ORDER BY so.`下单时间` DESC
        """)

        df = pd.read_sql(
            sql,
            conn,
            params={
                "start_date": start_date,
                "end_date": end_date,
                "customer": customer,
                "dealer": dealer,
                "status": status
            }
        )

    return df


def get_shipment_report_data(
    start_date: str,
    end_date: str,
    customer: str = "",
    dealer: str = "",
    model_type: str = ""
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Fetch shipment report data from both shipping_history and finished_goods_data
    Returns (summary_df, detail_df)
    """
    with get_engine().connect() as conn:
        # Detail query - individual shipment records
        detail_sql = text("""
            SELECT
                DATE_FORMAT(sh.`更新时间`, '%Y-%m-%d') COLLATE utf8mb4_0900_ai_ci AS `出货日期`,
                sh.`流水号` COLLATE utf8mb4_0900_ai_ci AS `流水号`,
                sh.`客户` COLLATE utf8mb4_0900_ai_ci AS `客户`,
                sh.`代理商` COLLATE utf8mb4_0900_ai_ci AS `代理商`,
                sh.`机型` COLLATE utf8mb4_0900_ai_ci AS `机型`,
                sh.`占用订单号` COLLATE utf8mb4_0900_ai_ci AS `订单号`,
                COALESCE(NULLIF(sh.`合同号`, ''), fp.`合同号`) COLLATE utf8mb4_0900_ai_ci AS `合同号`,
                sh.`批次号` COLLATE utf8mb4_0900_ai_ci AS `批次号`
            FROM shipping_history sh
            LEFT JOIN (
                SELECT `订单号`, MAX(NULLIF(`合同号`, '')) AS `合同号`
                FROM factory_plan
                WHERE COALESCE(`订单号`, '') <> ''
                GROUP BY `订单号`
            ) fp ON fp.`订单号` COLLATE utf8mb4_0900_ai_ci = sh.`占用订单号` COLLATE utf8mb4_0900_ai_ci
            WHERE sh.`更新时间` BETWEEN :start_date AND :end_date
                AND sh.`状态` = '已出库'
                AND (:customer = '' OR sh.`客户` = :customer)
                AND (:dealer = '' OR sh.`代理商` = :dealer)
                AND (:model_type = '' OR sh.`机型` = :model_type)

            UNION ALL

            SELECT
                DATE_FORMAT(fg.`更新时间`, '%Y-%m-%d') COLLATE utf8mb4_0900_ai_ci AS `出货日期`,
                fg.`流水号` COLLATE utf8mb4_0900_ai_ci AS `流水号`,
                fg.`客户` COLLATE utf8mb4_0900_ai_ci AS `客户`,
                fg.`代理商` COLLATE utf8mb4_0900_ai_ci AS `代理商`,
                fg.`机型` COLLATE utf8mb4_0900_ai_ci AS `机型`,
                fg.`占用订单号` COLLATE utf8mb4_0900_ai_ci AS `订单号`,
                COALESCE(NULLIF(fg.`合同号`, ''), fp.`合同号`) COLLATE utf8mb4_0900_ai_ci AS `合同号`,
                fg.`批次号` COLLATE utf8mb4_0900_ai_ci AS `批次号`
            FROM finished_goods_data fg
            LEFT JOIN (
                SELECT `订单号`, MAX(NULLIF(`合同号`, '')) AS `合同号`
                FROM factory_plan
                WHERE COALESCE(`订单号`, '') <> ''
                GROUP BY `订单号`
            ) fp ON fp.`订单号` COLLATE utf8mb4_0900_ai_ci = fg.`占用订单号` COLLATE utf8mb4_0900_ai_ci
            WHERE fg.`更新时间` BETWEEN :start_date AND :end_date
                AND fg.`状态` = '已出库'
                AND (:customer = '' OR fg.`客户` = :customer)
                AND (:dealer = '' OR fg.`代理商` = :dealer)
                AND (:model_type = '' OR fg.`机型` = :model_type)

            ORDER BY `出货日期` DESC, `流水号`
        """)

        detail_df = pd.read_sql(
            detail_sql,
            conn,
            params={
                "start_date": start_date,
                "end_date": end_date,
                "customer": customer,
                "dealer": dealer,
                "model_type": model_type
            }
        )

        # Summary query - grouped by date, customer, dealer, model, order
        summary_sql = text("""
            SELECT
                `出货日期`,
                `客户`,
                `代理商`,
                `机型`,
                COUNT(*) AS `出货数量`,
                `订单号`,
                `合同号`,
                `批次号`
            FROM (
                SELECT
                    DATE_FORMAT(sh.`更新时间`, '%Y-%m-%d') COLLATE utf8mb4_0900_ai_ci AS `出货日期`,
                    sh.`客户` COLLATE utf8mb4_0900_ai_ci AS `客户`,
                    sh.`代理商` COLLATE utf8mb4_0900_ai_ci AS `代理商`,
                    sh.`机型` COLLATE utf8mb4_0900_ai_ci AS `机型`,
                    sh.`占用订单号` COLLATE utf8mb4_0900_ai_ci AS `订单号`,
                    COALESCE(NULLIF(sh.`合同号`, ''), fp.`合同号`) COLLATE utf8mb4_0900_ai_ci AS `合同号`,
                    sh.`批次号` COLLATE utf8mb4_0900_ai_ci AS `批次号`
                FROM shipping_history sh
                LEFT JOIN (
                    SELECT `订单号`, MAX(NULLIF(`合同号`, '')) AS `合同号`
                    FROM factory_plan
                    WHERE COALESCE(`订单号`, '') <> ''
                    GROUP BY `订单号`
                ) fp ON fp.`订单号` COLLATE utf8mb4_0900_ai_ci = sh.`占用订单号` COLLATE utf8mb4_0900_ai_ci
                WHERE sh.`更新时间` BETWEEN :start_date AND :end_date
                    AND sh.`状态` = '已出库'
                    AND (:customer = '' OR sh.`客户` = :customer)
                    AND (:dealer = '' OR sh.`代理商` = :dealer)
                    AND (:model_type = '' OR sh.`机型` = :model_type)

                UNION ALL

                SELECT
                    DATE_FORMAT(fg.`更新时间`, '%Y-%m-%d') COLLATE utf8mb4_0900_ai_ci AS `出货日期`,
                    fg.`客户` COLLATE utf8mb4_0900_ai_ci AS `客户`,
                    fg.`代理商` COLLATE utf8mb4_0900_ai_ci AS `代理商`,
                    fg.`机型` COLLATE utf8mb4_0900_ai_ci AS `机型`,
                    fg.`占用订单号` COLLATE utf8mb4_0900_ai_ci AS `订单号`,
                    COALESCE(NULLIF(fg.`合同号`, ''), fp.`合同号`) COLLATE utf8mb4_0900_ai_ci AS `合同号`,
                    fg.`批次号` COLLATE utf8mb4_0900_ai_ci AS `批次号`
                FROM finished_goods_data fg
                LEFT JOIN (
                    SELECT `订单号`, MAX(NULLIF(`合同号`, '')) AS `合同号`
                    FROM factory_plan
                    WHERE COALESCE(`订单号`, '') <> ''
                    GROUP BY `订单号`
                ) fp ON fp.`订单号` COLLATE utf8mb4_0900_ai_ci = fg.`占用订单号` COLLATE utf8mb4_0900_ai_ci
                WHERE fg.`更新时间` BETWEEN :start_date AND :end_date
                    AND fg.`状态` = '已出库'
                    AND (:customer = '' OR fg.`客户` = :customer)
                    AND (:dealer = '' OR fg.`代理商` = :dealer)
                    AND (:model_type = '' OR fg.`机型` = :model_type)
            ) AS combined
            GROUP BY `出货日期`, `客户`, `代理商`, `机型`, `订单号`, `合同号`, `批次号`
            ORDER BY `出货日期` DESC
        """)

        summary_df = pd.read_sql(
            summary_sql,
            conn,
            params={
                "start_date": start_date,
                "end_date": end_date,
                "customer": customer,
                "dealer": dealer,
                "model_type": model_type
            }
        )

    return summary_df, detail_df


def get_completion_report_data(
    start_date: str,
    end_date: str,
    model_type: str = "",
    customer: str = "",
    contract_no: str = ""
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Fetch completion report data from production_history_ledger
    Returns (summary_df, detail_df)
    """
    with get_engine().connect() as conn:
        # Detail query - individual units with production duration
        detail_sql = text("""
            SELECT
                phl.`unit_id` AS `机台ID`,
                phl.`batch_code` AS `批次号`,
                phl.`model_type` AS `机型`,
                phl.`contract_no` AS `合同号`,
                phl.`customer` AS `客户`,
                phl.`dealer_name` AS `经销商`,
                phl.`production_line_name` AS `产线`,
                DATE_FORMAT(phl.`scheduled_at`, '%Y-%m-%d %H:%i') AS `排产时间`,
                DATE_FORMAT(phl.`completed_at`, '%Y-%m-%d %H:%i') AS `完工时间`,
                TIMESTAMPDIFF(HOUR, phl.`scheduled_at`, phl.`completed_at`) AS `生产时长(小时)`,
                COALESCE(u.serial_no, u.forecast_serial_no) AS `流水号`
            FROM production_history_ledger phl
            LEFT JOIN units u ON u.unit_id = phl.unit_id COLLATE utf8mb4_general_ci
            WHERE phl.`completed_at` BETWEEN :start_date AND :end_date
                AND phl.`status` = 'Completed'
                AND (:model_type = '' OR phl.`model_type` = :model_type)
                AND (:customer = '' OR phl.`customer` = :customer)
                AND (:contract_no = '' OR phl.`contract_no` = :contract_no)
            ORDER BY phl.`completed_at` DESC
        """)

        detail_df = pd.read_sql(
            detail_sql,
            conn,
            params={
                "start_date": start_date,
                "end_date": end_date,
                "model_type": model_type,
                "customer": customer,
                "contract_no": contract_no
            }
        )

        # Summary query - grouped by date, contract, model
        summary_sql = text("""
            SELECT
                DATE_FORMAT(phl.`completed_at`, '%Y-%m-%d') AS `完工日期`,
                phl.`contract_no` AS `合同号`,
                phl.`model_type` AS `机型`,
                COUNT(*) AS `完工数量`,
                phl.`customer` AS `客户`,
                phl.`dealer_name` AS `经销商`,
                phl.`production_line_name` AS `产线`,
                phl.`batch_code` AS `批次号`,
                ROUND(AVG(TIMESTAMPDIFF(HOUR, phl.`scheduled_at`, phl.`completed_at`)), 1) AS `平均生产时长(小时)`
            FROM production_history_ledger phl
            WHERE phl.`completed_at` BETWEEN :start_date AND :end_date
                AND phl.`status` = 'Completed'
                AND (:model_type = '' OR phl.`model_type` = :model_type)
                AND (:customer = '' OR phl.`customer` = :customer)
                AND (:contract_no = '' OR phl.`contract_no` = :contract_no)
            GROUP BY DATE_FORMAT(phl.`completed_at`, '%Y-%m-%d'), phl.`contract_no`,
                     phl.`model_type`, phl.`customer`, phl.`dealer_name`,
                     phl.`production_line_name`, phl.`batch_code`
            ORDER BY DATE_FORMAT(phl.`completed_at`, '%Y-%m-%d') DESC
        """)

        summary_df = pd.read_sql(
            summary_sql,
            conn,
            params={
                "start_date": start_date,
                "end_date": end_date,
                "model_type": model_type,
                "customer": customer,
                "contract_no": contract_no
            }
        )

    return summary_df, detail_df


def get_available_filters() -> Dict[str, Any]:
    """
    Get available filter options (customers, dealers, models) for dropdowns
    """
    with get_engine().connect() as conn:
        customers_df = pd.read_sql(
            text("SELECT DISTINCT `客户` FROM finished_goods_data WHERE `客户` != '' AND `客户` IS NOT NULL ORDER BY `客户`"),
            conn
        )
        dealers_df = pd.read_sql(
            text("SELECT DISTINCT `代理商` FROM finished_goods_data WHERE `代理商` != '' AND `代理商` IS NOT NULL ORDER BY `代理商`"),
            conn
        )
        models_df = pd.read_sql(
            text("SELECT DISTINCT `机型` FROM finished_goods_data WHERE `机型` != '' AND `机型` IS NOT NULL ORDER BY `机型`"),
            conn
        )

    return {
        "customers": customers_df["客户"].tolist() if not customers_df.empty else [],
        "dealers": dealers_df["代理商"].tolist() if not dealers_df.empty else [],
        "models": models_df["机型"].tolist() if not models_df.empty else []
    }
