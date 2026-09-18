"""Classify pending inventory without changing its physical lifecycle status."""


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
