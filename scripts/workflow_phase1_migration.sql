-- 第一阶段工作流元数据迁移（MySQL 8+，可重复执行）
-- 业务表和工作流核心表由应用启动初始化；本脚本负责分类和运行状态收敛。
INSERT INTO workflow_categories (category_key, name, description) VALUES
('合同流程', '合同流程', '合同创建及后续动作'),
('订单流程', '订单流程', '销售订单创建及配货'),
('配货流程', '配货流程', '订单配货'),
('库存流程', '库存流程', '入库和库位转移'),
('发货流程', '发货流程', '发货确认'),
('客户成品流程', '客户成品流程', '客户成品及机台规划'),
('基础资料流程', '基础资料流程', '基础资料逆向操作')
ON DUPLICATE KEY UPDATE name=VALUES(name), description=VALUES(description);

UPDATE workflow_model_versions v
JOIN workflow_models m ON m.id=v.model_id
SET v.runtime_enabled=1
WHERE m.direction='正向' AND m.status='已发布' AND v.status='已发布'
  AND v.version_no=m.current_version;
