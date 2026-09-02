"""
CRUD operations for report generation
Provides data fetching and aggregation logic for all report types
"""
import re

import pandas as pd
from sqlalchemy import text
from database import get_engine
from crud.inbound_history import ensure_inbound_history_table
from typing import Dict, Any


REPORT_FAMILY_ORDER = [
    "中小型XS",
    "中小型AUTO",
    "中小型G",
    "中大型AUTO",
    "中大型XS",
    "特殊",
    "未匹配",
]
SCREW_REFERENCE_FAMILIES = {
    "XS": {"中小型XS", "中大型XS"},
    "AUTO": {"中小型AUTO", "中大型AUTO"},
    "G": {"中小型G"},
}


def _format_ratio(value: float, total: int | float) -> str:
    return f"{(value / total * 100):.2f}%" if total else "0.00%"


def _normalize_report_model(value: object) -> str:
    """Normalize the order token format to the model dictionary key."""
    return str(value or "").strip().replace("(加高)", "").replace("（加高）", "").strip()


def _get_model_dictionary_frame() -> pd.DataFrame:
    with get_engine().connect() as conn:
        return pd.read_sql(
            text(
                "SELECT model_name, model_family, sort_order "
                "FROM model_dictionary "
                "ORDER BY sort_order ASC, id ASC"
            ),
            conn,
        )


def get_order_model_quantities(order_df: pd.DataFrame) -> pd.DataFrame:
    """Expand one or more `机型 x 数量` tokens from each sales order."""
    rows: list[dict[str, object]] = []
    for _, order in order_df.iterrows():
        raw = str(order.get("需求机型", "") or "")
        parsed = False
        for token_raw in raw.split(";"):
            token = token_raw.strip()
            if not token:
                continue
            match = re.search(r"(?:[x×:：]\s*)(\d+)\s*$", token, flags=re.IGNORECASE)
            if not match:
                continue
            model = _normalize_report_model(re.sub(r"(?:[x×:：]\s*)\d+\s*$", "", token, flags=re.IGNORECASE))
            quantity = int(match.group(1))
            if model and quantity > 0:
                rows.append({"机型": model, "数量": quantity})
                parsed = True

        # Compatibility with legacy single-model orders that did not store x quantity.
        if not parsed:
            model = _normalize_report_model(raw)
            quantity = pd.to_numeric(pd.Series([order.get("需求数量", 0)]), errors="coerce").fillna(0).iloc[0]
            if model and quantity > 0:
                rows.append({"机型": model, "数量": int(quantity)})

    return pd.DataFrame(rows, columns=["机型", "数量"])


def get_dealer_sales_summary(order_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate the filtered order report by dealer without dropping blank dealers."""
    if order_df.empty:
        return pd.DataFrame(columns=["代理商", "所售数量", "总销售占比"])

    work = order_df.copy()
    work["代理商"] = work["代理商"].fillna("").astype(str).str.strip().replace("", "未填写")
    work["需求数量"] = pd.to_numeric(work["需求数量"], errors="coerce").fillna(0).astype(int)
    result = work.groupby("代理商", as_index=False)["需求数量"].sum()
    result.columns = ["代理商", "所售数量"]
    result = result.sort_values(["所售数量", "代理商"], ascending=[False, True], kind="stable")
    total = int(result["所售数量"].sum())
    result["总销售占比"] = result["所售数量"].map(lambda qty: _format_ratio(int(qty), total))
    result.loc[len(result)] = ["合计", total, "100.00%"]
    return result


def build_model_report_appendices(
    model_quantities: pd.DataFrame,
    model_dictionary: pd.DataFrame | None = None,
) -> dict[str, pd.DataFrame]:
    """Build the family, screw-reference, and all-model appendices for Excel exports."""
    empty = pd.DataFrame(columns=["机型", "数量"])
    source = model_quantities.copy() if model_quantities is not None else empty
    if source.empty or "机型" not in source or "数量" not in source:
        return {
            "总族类比例": pd.DataFrame(columns=["总族类", "累计出货", "总族类比例", "机型数"]),
            "丝杆订货需求比例": pd.DataFrame(),
            "机型累计占比": pd.DataFrame(columns=["排名", "机型", "总族类", "累计出货", "累计占比", "字典状态"]),
        }

    source["机型"] = source["机型"].map(_normalize_report_model)
    source["数量"] = pd.to_numeric(source["数量"], errors="coerce").fillna(0).astype(int)
    source = source[(source["机型"] != "") & (source["数量"] > 0)]
    if source.empty:
        return build_model_report_appendices(empty, model_dictionary)

    dictionary = model_dictionary.copy() if model_dictionary is not None else _get_model_dictionary_frame()
    if dictionary.empty:
        dictionary = pd.DataFrame(columns=["model_name", "model_family", "sort_order"])
    for column, default in (("model_name", ""), ("model_family", ""), ("sort_order", 9999)):
        if column not in dictionary:
            dictionary[column] = default
    dictionary["model_key"] = dictionary["model_name"].map(_normalize_report_model).str.casefold()
    dictionary["sort_order"] = pd.to_numeric(dictionary["sort_order"], errors="coerce").fillna(9999)
    dictionary = dictionary.drop_duplicates("model_key", keep="first")
    family_map = dictionary.set_index("model_key")["model_family"].fillna("").to_dict()
    sort_map = dictionary.set_index("model_key")["sort_order"].to_dict()

    model_summary = source.groupby("机型", as_index=False)["数量"].sum()
    model_summary["_key"] = model_summary["机型"].str.casefold()
    model_summary["总族类"] = model_summary["_key"].map(family_map).fillna("").astype(str).str.strip()
    model_summary.loc[~model_summary["总族类"].isin(REPORT_FAMILY_ORDER[:-1]), "总族类"] = "未匹配"
    model_summary["字典状态"] = model_summary["总族类"].map(lambda family: "待维护" if family == "未匹配" else "已匹配")
    model_summary["_sort_order"] = model_summary["_key"].map(sort_map).fillna(9999)

    total_quantity = int(model_summary["数量"].sum())
    family_rows: list[dict[str, object]] = []
    for family in REPORT_FAMILY_ORDER:
        group = model_summary[model_summary["总族类"] == family]
        if group.empty:
            continue
        quantity = int(group["数量"].sum())
        family_rows.append(
            {
                "总族类": family,
                "累计出货": quantity,
                "总族类比例": _format_ratio(quantity, total_quantity),
                "机型数": int(group["机型"].nunique()),
            }
        )
    family_rows.append({"总族类": "全部总族类", "累计出货": total_quantity, "总族类比例": "100.00%", "机型数": int(model_summary["机型"].nunique())})
    family_summary = pd.DataFrame(family_rows)

    all_models = model_summary.sort_values(["数量", "_sort_order", "机型"], ascending=[False, True, True], kind="stable").reset_index(drop=True)
    all_models.insert(0, "排名", all_models.index + 1)
    all_models["累计出货"] = all_models["数量"]
    all_models["累计占比"] = all_models["累计出货"].map(lambda qty: _format_ratio(int(qty), total_quantity))
    all_models = all_models[["排名", "机型", "总族类", "累计出货", "累计占比", "字典状态"]]
    all_models.loc[len(all_models)] = ["全部机型", "", "", total_quantity, "100.00%", ""]

    reference_columns = [
        "XS 名称", "数量", "订货参考占比",
        "AUTO 名称", "数量", "订货参考占比",
        "G 名称", "数量", "订货参考占比",
    ]
    reference_groups: dict[str, pd.DataFrame] = {}
    for label, families in SCREW_REFERENCE_FAMILIES.items():
        group = model_summary[model_summary["总族类"].isin(families)].sort_values(
            ["_sort_order", "机型"], ascending=[True, True], kind="stable"
        )
        reference_groups[label] = group

    max_rows = max((len(group) for group in reference_groups.values()), default=0)
    reference_rows: list[list[object]] = []
    for index in range(max_rows):
        row: list[object] = []
        for label in ("XS", "AUTO", "G"):
            group = reference_groups[label]
            if index < len(group):
                item = group.iloc[index]
                group_total = int(group["数量"].sum())
                row.extend([item["机型"], int(item["数量"]), _format_ratio(int(item["数量"]), group_total)])
            else:
                row.extend(["", "", ""])
        reference_rows.append(row)

    total_row: list[object] = []
    for label in ("XS", "AUTO", "G"):
        group = reference_groups[label]
        total_row.extend([f"{label} 合计", int(group["数量"].sum()), "100.00%" if not group.empty else "0.00%"])
    reference_rows.append(total_row)
    screw_reference = pd.DataFrame(reference_rows, columns=reference_columns)

    return {
        "总族类比例": family_summary,
        "丝杆订货需求比例": screw_reference,
        "机型累计占比": all_models,
    }


def serialize_model_report_appendices(appendices: dict[str, pd.DataFrame]) -> dict[str, list[dict[str, object]]]:
    """Serialize appendices for JSON while retaining all three repeated screw columns."""
    screw = appendices.get("丝杆订货需求比例", pd.DataFrame())
    screw_records: list[dict[str, object]] = []
    for _, row in screw.iterrows():
        screw_records.append(
            {
                "xs_name": row.iloc[0] if len(row) > 0 else "",
                "xs_quantity": row.iloc[1] if len(row) > 1 else "",
                "xs_ratio": row.iloc[2] if len(row) > 2 else "",
                "auto_name": row.iloc[3] if len(row) > 3 else "",
                "auto_quantity": row.iloc[4] if len(row) > 4 else "",
                "auto_ratio": row.iloc[5] if len(row) > 5 else "",
                "g_name": row.iloc[6] if len(row) > 6 else "",
                "g_quantity": row.iloc[7] if len(row) > 7 else "",
                "g_ratio": row.iloc[8] if len(row) > 8 else "",
            }
        )
    return {
        "总族类比例": appendices.get("总族类比例", pd.DataFrame()).to_dict("records"),
        "丝杆订货需求比例": screw_records,
        "机型累计占比": appendices.get("机型累计占比", pd.DataFrame()).to_dict("records"),
    }


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
                WHERE tl.`时间` >= :start_date
                    AND tl.`时间` < DATE_ADD(:end_date, INTERVAL 1 DAY)
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
                    WHERE tl.`时间` >= :start_date
                        AND tl.`时间` < DATE_ADD(:end_date, INTERVAL 1 DAY)
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
            WHERE ih.inbound_time >= :start_date
                AND ih.inbound_time < DATE_ADD(:end_date, INTERVAL 1 DAY)
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
            WHERE ih.inbound_time >= :start_date
                AND ih.inbound_time < DATE_ADD(:end_date, INTERVAL 1 DAY)
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


def get_completion_output_report_data(
    start_date: str,
    end_date: str,
    model_type: str = "",
    customer: str = ""
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Fetch completion/output report data with filters.
    Uses finished_goods_data + shipping_history so historical shipped machines
    that lack inbound_history events are still counted once by serial number.
    """
    with get_engine().connect() as conn:
        base_sql = """
            WITH combined AS (
                SELECT
                    0 AS source_rank,
                    '成品库' COLLATE utf8mb4_0900_ai_ci AS source_table,
                    fg.`批次号` COLLATE utf8mb4_0900_ai_ci AS batch_no,
                    fg.`机型` COLLATE utf8mb4_0900_ai_ci AS model,
                    fg.`流水号` COLLATE utf8mb4_0900_ai_ci AS serial_no,
                    fg.`状态` COLLATE utf8mb4_0900_ai_ci AS status,
                    fg.`预计入库时间` AS completed_at,
                    fg.`更新时间` AS updated_at,
                    COALESCE(fg.`占用订单号`, '') COLLATE utf8mb4_0900_ai_ci AS order_no,
                    COALESCE(fg.`客户`, '') COLLATE utf8mb4_0900_ai_ci AS customer,
                    COALESCE(fg.`代理商`, '') COLLATE utf8mb4_0900_ai_ci AS dealer,
                    COALESCE(fg.`合同号`, '') COLLATE utf8mb4_0900_ai_ci AS contract_no,
                    COALESCE(fg.`合同备注`, '') COLLATE utf8mb4_0900_ai_ci AS remark,
                    COALESCE(fg.`Location_Code`, '') COLLATE utf8mb4_0900_ai_ci AS slot_code
                FROM finished_goods_data fg
                WHERE fg.`预计入库时间` >= :start_date
                    AND fg.`预计入库时间` < DATE_ADD(:end_date, INTERVAL 1 DAY)
                    AND COALESCE(fg.`状态`, '') <> '待入库'
                    AND COALESCE(fg.`状态`, '') <> ''
                    AND (:model_type = '' OR fg.`机型` = :model_type)
                    AND (:customer = '' OR fg.`客户` = :customer)

                UNION ALL

                SELECT
                    1 AS source_rank,
                    '出库历史' COLLATE utf8mb4_0900_ai_ci AS source_table,
                    sh.`批次号` COLLATE utf8mb4_0900_ai_ci AS batch_no,
                    sh.`机型` COLLATE utf8mb4_0900_ai_ci AS model,
                    sh.`流水号` COLLATE utf8mb4_0900_ai_ci AS serial_no,
                    sh.`状态` COLLATE utf8mb4_0900_ai_ci AS status,
                    sh.`预计入库时间` AS completed_at,
                    sh.`更新时间` AS updated_at,
                    COALESCE(sh.`占用订单号`, '') COLLATE utf8mb4_0900_ai_ci AS order_no,
                    COALESCE(sh.`客户`, '') COLLATE utf8mb4_0900_ai_ci AS customer,
                    COALESCE(sh.`代理商`, '') COLLATE utf8mb4_0900_ai_ci AS dealer,
                    COALESCE(sh.`合同号`, '') COLLATE utf8mb4_0900_ai_ci AS contract_no,
                    COALESCE(sh.`合同备注`, '') COLLATE utf8mb4_0900_ai_ci AS remark,
                    '' COLLATE utf8mb4_0900_ai_ci AS slot_code
                FROM shipping_history sh
                WHERE sh.`预计入库时间` >= :start_date
                    AND sh.`预计入库时间` < DATE_ADD(:end_date, INTERVAL 1 DAY)
                    AND COALESCE(sh.`状态`, '') <> '待入库'
                    AND COALESCE(sh.`状态`, '') <> ''
                    AND (:model_type = '' OR sh.`机型` = :model_type)
                    AND (:customer = '' OR sh.`客户` = :customer)
            ),
            dedup AS (
                SELECT
                    combined.*,
                    ROW_NUMBER() OVER (
                        PARTITION BY serial_no
                        ORDER BY source_rank ASC, COALESCE(updated_at, completed_at) DESC
                    ) AS rn
                FROM combined
                WHERE COALESCE(TRIM(serial_no), '') <> ''
            )
        """

        detail_sql = text(base_sql + """
            SELECT
                DATE_FORMAT(completed_at, '%Y-%m-%d') AS `完工日期`,
                serial_no AS `流水号`,
                batch_no AS `批次号`,
                model AS `机型`,
                status AS `状态`,
                customer AS `客户`,
                dealer AS `代理商`,
                order_no AS `订单号`,
                contract_no AS `合同号`,
                slot_code AS `库位`,
                remark AS `合同备注`,
                source_table AS `数据来源`,
                DATE_FORMAT(completed_at, '%Y-%m-%d %H:%i') AS `完工时间`,
                DATE_FORMAT(updated_at, '%Y-%m-%d %H:%i') AS `更新时间`
            FROM dedup
            WHERE rn = 1
            ORDER BY completed_at ASC, batch_no ASC, serial_no ASC
        """)

        params = {
            "start_date": start_date,
            "end_date": end_date,
            "model_type": model_type,
            "customer": customer
        }
        detail_df = pd.read_sql(detail_sql, conn, params=params)

        summary_sql = text(base_sql + """
            SELECT
                d.model AS `机型`,
                COUNT(*) AS `数量`,
                COALESCE(md.sort_order, 9999) AS sort_order
            FROM dedup d
            LEFT JOIN model_dictionary md
                ON md.model_name = d.model COLLATE utf8mb4_general_ci
            WHERE d.rn = 1
                AND COALESCE(d.model, '') <> ''
            GROUP BY d.model, md.sort_order
            ORDER BY sort_order ASC, d.model
        """)

        summary_df = pd.read_sql(summary_sql, conn, params=params)
        if not summary_df.empty:
            total = summary_df['数量'].sum()
            summary_df['占比'] = summary_df['数量'].apply(lambda x: f"{(x/total*100):.2f}%")
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
            WHERE so.`下单时间` >= :start_date
                AND so.`下单时间` < DATE_ADD(:end_date, INTERVAL 1 DAY)
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
            WHERE sh.`更新时间` >= :start_date
                AND sh.`更新时间` < DATE_ADD(:end_date, INTERVAL 1 DAY)
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
            WHERE fg.`更新时间` >= :start_date
                AND fg.`更新时间` < DATE_ADD(:end_date, INTERVAL 1 DAY)
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
                WHERE sh.`更新时间` >= :start_date
                    AND sh.`更新时间` < DATE_ADD(:end_date, INTERVAL 1 DAY)
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
                WHERE fg.`更新时间` >= :start_date
                    AND fg.`更新时间` < DATE_ADD(:end_date, INTERVAL 1 DAY)
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
            WHERE phl.`completed_at` >= :start_date
                AND phl.`completed_at` < DATE_ADD(:end_date, INTERVAL 1 DAY)
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
            WHERE phl.`completed_at` >= :start_date
                AND phl.`completed_at` < DATE_ADD(:end_date, INTERVAL 1 DAY)
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
