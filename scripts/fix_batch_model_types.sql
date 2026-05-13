UPDATE batches b SET model_type = COALESCE((
    SELECT CASE 
        WHEN UPPER(fg.机型) LIKE '%AUTO%' THEN 'AUTO' 
        WHEN UPPER(fg.机型) LIKE '%SPECIAL%' THEN 'SPECIAL' 
        WHEN UPPER(fg.机型) LIKE 'FR-1080%' THEN 'SPECIAL' 
        WHEN UPPER(fg.机型) LIKE 'FL-%' THEN 'SPECIAL' 
        WHEN UPPER(fg.机型) LIKE 'FR-8060%' THEN 'SPECIAL' 
        WHEN UPPER(fg.机型) LIKE 'FR-8080%' THEN 'SPECIAL' 
        WHEN UPPER(fg.机型) LIKE 'FR-1100%' THEN 'SPECIAL' 
        WHEN UPPER(fg.机型) LIKE '%XS%' THEN 'XS' 
        ELSE 'G' END 
    FROM finished_goods_data fg 
    WHERE CONVERT(fg.批次号 USING utf8mb4) COLLATE utf8mb4_general_ci = CONVERT(b.batch_code USING utf8mb4) COLLATE utf8mb4_general_ci
    LIMIT 1
), 'G') 
WHERE batch_id LIKE 'BATCH-SYNC-%';
