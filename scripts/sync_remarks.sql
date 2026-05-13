UPDATE units u
JOIN finished_goods_data fg 
  ON CONVERT(u.serial_no USING utf8mb4) COLLATE utf8mb4_general_ci = 
     CONVERT(fg.`流水号` USING utf8mb4) COLLATE utf8mb4_general_ci
SET 
  u.contract_no = fg.`合同号`,
  u.customer = fg.`客户`,
  u.dealer_name = fg.`代理商`,
  u.order_remark = CONCAT_WS(' | ', 
      NULLIF(TRIM(fg.`订单备注`), ''), 
      NULLIF(TRIM(fg.`机台备注/配置`), '')
  )
WHERE u.batch_id LIKE 'BATCH-SYNC-%';
