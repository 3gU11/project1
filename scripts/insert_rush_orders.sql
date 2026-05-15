INSERT INTO rush_order_queue (
    contract_no,
    customer,
    dealer_name,
    model_type,
    due_date,
    remark,
    source,
    status,
    created_by,
    updated_by,
    created_at,
    updated_at
)
SELECT 
    f.`合同号`,
    f.`客户名`,
    f.`代理商`,
    f.`机型`,
    f.`要求交期`,
    f.`备注`,
    'contract',
    'pending',
    'system',
    'system',
    NOW(),
    NOW()
FROM factory_plan f
JOIN (
    SELECT 1 AS n UNION ALL SELECT 2 UNION ALL SELECT 3 UNION ALL SELECT 4 UNION ALL SELECT 5 
    UNION ALL SELECT 6 UNION ALL SELECT 7 UNION ALL SELECT 8 UNION ALL SELECT 9 UNION ALL SELECT 10
    UNION ALL SELECT 11 UNION ALL SELECT 12 UNION ALL SELECT 13 UNION ALL SELECT 14 UNION ALL SELECT 15
) n ON n.n <= CAST(f.`排产数量` AS UNSIGNED)
WHERE f.`要求交期` LIKE '2026-05%'
  AND f.`状态` IN ('待规划', '未下单');
