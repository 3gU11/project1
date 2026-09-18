"""Classify pending inventory without changing its physical lifecycle status."""


def inventory_relationship_join_sql():
    # One row per normalized serial avoids multiplying inventory when legacy units overlap.
    active = "u.status='In_Production' AND b.status='In_Production' AND p.status='Busy'"
    return f"""LEFT JOIN (
      SELECT COALESCE(NULLIF(TRIM(u.serial_no), ''), TRIM(u.forecast_serial_no))
               COLLATE utf8mb4_general_ci AS serial_key,
        MAX(CASE WHEN {active} THEN 1 ELSE 0 END) AS in_production,
        MAX(CASE WHEN b.status='Confirmed' AND u.status IN ('Pending','Confirmed')
          AND NULLIF(TRIM(u.production_line_id),'') IS NULL THEN 1 ELSE 0 END) AS queued,
        MAX(CASE WHEN {active} AND (NULLIF(TRIM(u.sales_id),'') IS NOT NULL
          OR NULLIF(TRIM(u.contract_no),'') IS NOT NULL) THEN 1 ELSE 0 END) AS bound
      FROM units u JOIN batches b ON b.batch_id=u.batch_id
      LEFT JOIN production_lines p ON p.line_id=u.production_line_id
      GROUP BY serial_key
    ) rel ON rel.serial_key=TRIM(fg.`流水号`) COLLATE utf8mb4_general_ci"""


def joined_pending_scope_sql():
    return """CASE WHEN TRIM(COALESCE(fg.`状态`,'')) <> '待入库' THEN ''
      WHEN rel.in_production=1 THEN 'production'
      WHEN rel.queued=1 THEN 'queued' ELSE 'review' END"""


def production_bound_sql(alias="fg"):
    return f"""EXISTS (
      SELECT 1 FROM units u JOIN batches b ON b.batch_id=u.batch_id
      JOIN production_lines p ON p.line_id=u.production_line_id
      WHERE COALESCE(NULLIF(TRIM(u.serial_no), ''), TRIM(u.forecast_serial_no))
        = TRIM({alias}.`流水号`) COLLATE utf8mb4_general_ci
        AND u.status='In_Production' AND b.status='In_Production' AND p.status='Busy'
        AND (NULLIF(TRIM(u.sales_id),'') IS NOT NULL OR NULLIF(TRIM(u.contract_no),'') IS NOT NULL)
    )"""


def pending_inbound_scope_sql(alias="fg"):
    serial = f"TRIM({alias}.`流水号`) COLLATE utf8mb4_general_ci"
    return f"""CASE
      WHEN TRIM(COALESCE({alias}.`状态`, '')) <> '待入库' THEN ''
      WHEN EXISTS (
        SELECT 1 FROM units u
        JOIN batches b ON b.batch_id=u.batch_id
        JOIN production_lines p ON p.line_id=u.production_line_id
        WHERE COALESCE(NULLIF(TRIM(u.serial_no), ''), TRIM(u.forecast_serial_no)) = {serial}
          AND u.status='In_Production' AND b.status='In_Production' AND p.status='Busy'
      ) THEN 'production'
      WHEN EXISTS (
        SELECT 1 FROM units u JOIN batches b ON b.batch_id=u.batch_id
        WHERE COALESCE(NULLIF(TRIM(u.serial_no), ''), TRIM(u.forecast_serial_no)) = {serial}
          AND b.status='Confirmed' AND u.status IN ('Pending', 'Confirmed')
          AND NULLIF(TRIM(u.production_line_id), '') IS NULL
      ) THEN 'queued'
      ELSE 'review' END"""
