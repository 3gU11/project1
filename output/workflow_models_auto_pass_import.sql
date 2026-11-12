-- ============================================================
-- 流程模型导入脚本：把 14 个流程模型统一改成“自动通过 / 自动执行”
-- 生成时间：2026-11-12 15:14:06
-- 目标库：测试机 MySQL（表 workflow_models / workflow_model_versions / workflow_categories）
-- 执行方式：
--   mysql --default-character-set=utf8mb4 -h <主机> -P 3306 -u <用户> -p <库名> < workflow_models_auto_pass_import.sql
-- 说明：按 workflow_key 覆盖原模型（Key 不变），旧发布版本标记为历史，再写入新的已发布版本。
-- ============================================================
SET NAMES utf8mb4;
START TRANSACTION;

-- 1) 流程分类（不存在则补，存在则同步名称）
INSERT INTO workflow_categories (category_key,name,description) VALUES ('合同流程','合同流程','合同创建及后续动作') ON DUPLICATE KEY UPDATE name=VALUES(name);
INSERT INTO workflow_categories (category_key,name,description) VALUES ('订单流程','订单流程','销售订单创建及配货') ON DUPLICATE KEY UPDATE name=VALUES(name);
INSERT INTO workflow_categories (category_key,name,description) VALUES ('配货流程','配货流程','订单配货') ON DUPLICATE KEY UPDATE name=VALUES(name);
INSERT INTO workflow_categories (category_key,name,description) VALUES ('库存流程','库存流程','入库和库位转移') ON DUPLICATE KEY UPDATE name=VALUES(name);
INSERT INTO workflow_categories (category_key,name,description) VALUES ('发货流程','发货流程','发货确认') ON DUPLICATE KEY UPDATE name=VALUES(name);
INSERT INTO workflow_categories (category_key,name,description) VALUES ('客户成品流程','客户成品流程','客户成品及机台规划') ON DUPLICATE KEY UPDATE name=VALUES(name);
INSERT INTO workflow_categories (category_key,name,description) VALUES ('基础资料流程','基础资料流程','基础资料逆向操作') ON DUPLICATE KEY UPDATE name=VALUES(name);

-- 1. 创建合同（contract-create） 删除审批节点：无（原本已自动通过）
INSERT INTO workflow_models
  (workflow_key,name,category_key,direction,processing_type,business_object,execution_scope,
   status,is_required,current_version,created_by,updated_by,created_at,updated_at)
VALUES ('contract-create', '创建合同', '合同流程', '正向', '自动通过', '合同', '合同', '已发布', 1, 0, 'import-auto-pass', 'import-auto-pass', NOW(), NOW())
ON DUPLICATE KEY UPDATE
  name=VALUES(name), category_key=VALUES(category_key), direction=VALUES(direction),
  processing_type='自动通过', business_object=VALUES(business_object),
  execution_scope=VALUES(execution_scope), status='已发布', is_required=VALUES(is_required),
  updated_by='import-auto-pass', updated_at=NOW();
SET @model_id := (SELECT id FROM workflow_models WHERE workflow_key='contract-create');
SET @next_version := (SELECT COALESCE(MAX(version_no),0)+1 FROM workflow_model_versions WHERE model_id=@model_id);
UPDATE workflow_model_versions SET status='历史', runtime_enabled=0 WHERE model_id=@model_id AND status='已发布';
INSERT INTO workflow_model_versions
  (model_id,version_no,status,node_snapshot,runtime_enabled,published_by,published_at,created_at)
VALUES (@model_id,@next_version,'已发布','{"edges":[{"source":"start","target":"business-action-0"},{"source":"business-action-0","target":"end-1792462119345"}],"nodes":[{"x":60,"y":120,"id":"start","type":"start","label":"发起"},{"x":330,"y":120,"id":"business-action-0","type":"execute","label":"自动执行业务","action":"create_contract"},{"x":659.066650390625,"y":137.75,"id":"end-1792462119345","type":"end","label":"结束"}]}',1,'import-auto-pass',NOW(),NOW());
UPDATE workflow_models SET current_version=@next_version, updated_at=NOW() WHERE id=@model_id;

-- 2. 创建销售订单（order-create） 删除审批节点：无（原本已自动通过）
INSERT INTO workflow_models
  (workflow_key,name,category_key,direction,processing_type,business_object,execution_scope,
   status,is_required,current_version,created_by,updated_by,created_at,updated_at)
VALUES ('order-create', '创建销售订单', '订单流程', '正向', '自动通过', '订单', '整单', '已发布', 1, 0, 'import-auto-pass', 'import-auto-pass', NOW(), NOW())
ON DUPLICATE KEY UPDATE
  name=VALUES(name), category_key=VALUES(category_key), direction=VALUES(direction),
  processing_type='自动通过', business_object=VALUES(business_object),
  execution_scope=VALUES(execution_scope), status='已发布', is_required=VALUES(is_required),
  updated_by='import-auto-pass', updated_at=NOW();
SET @model_id := (SELECT id FROM workflow_models WHERE workflow_key='order-create');
SET @next_version := (SELECT COALESCE(MAX(version_no),0)+1 FROM workflow_model_versions WHERE model_id=@model_id);
UPDATE workflow_model_versions SET status='历史', runtime_enabled=0 WHERE model_id=@model_id AND status='已发布';
INSERT INTO workflow_model_versions
  (model_id,version_no,status,node_snapshot,runtime_enabled,published_by,published_at,created_at)
VALUES (@model_id,@next_version,'已发布','{"edges":[{"source":"start","target":"business-action-0"},{"source":"business-action-0","target":"end"}],"nodes":[{"x":60,"y":120,"id":"start","type":"start","label":"发起"},{"x":640,"y":120,"id":"end","type":"end","label":"结束"},{"x":330,"y":120,"id":"business-action-0","type":"execute","label":"自动执行业务","action":"create_sales_order"}]}',1,'import-auto-pass',NOW(),NOW());
UPDATE workflow_models SET current_version=@next_version, updated_at=NOW() WHERE id=@model_id;

-- 3. 订单配货（allocation-create） 删除审批节点：无（原本已自动通过）
INSERT INTO workflow_models
  (workflow_key,name,category_key,direction,processing_type,business_object,execution_scope,
   status,is_required,current_version,created_by,updated_by,created_at,updated_at)
VALUES ('allocation-create', '订单配货', '配货流程', '正向', '自动通过', '订单', '整单', '已发布', 1, 0, 'import-auto-pass', 'import-auto-pass', NOW(), NOW())
ON DUPLICATE KEY UPDATE
  name=VALUES(name), category_key=VALUES(category_key), direction=VALUES(direction),
  processing_type='自动通过', business_object=VALUES(business_object),
  execution_scope=VALUES(execution_scope), status='已发布', is_required=VALUES(is_required),
  updated_by='import-auto-pass', updated_at=NOW();
SET @model_id := (SELECT id FROM workflow_models WHERE workflow_key='allocation-create');
SET @next_version := (SELECT COALESCE(MAX(version_no),0)+1 FROM workflow_model_versions WHERE model_id=@model_id);
UPDATE workflow_model_versions SET status='历史', runtime_enabled=0 WHERE model_id=@model_id AND status='已发布';
INSERT INTO workflow_model_versions
  (model_id,version_no,status,node_snapshot,runtime_enabled,published_by,published_at,created_at)
VALUES (@model_id,@next_version,'已发布','{"edges":[{"source":"start","target":"business-action-0"},{"source":"business-action-0","target":"end"}],"nodes":[{"x":60,"y":120,"id":"start","type":"start","label":"发起"},{"x":640,"y":120,"id":"end","type":"end","label":"结束"},{"x":330,"y":120,"id":"business-action-0","type":"execute","label":"自动执行业务","action":"allocate_order"}]}',1,'import-auto-pass',NOW(),NOW());
UPDATE workflow_models SET current_version=@next_version, updated_at=NOW() WHERE id=@model_id;

-- 4. 成品入库（stock-inbound） 删除审批节点：无（原本已自动通过）
INSERT INTO workflow_models
  (workflow_key,name,category_key,direction,processing_type,business_object,execution_scope,
   status,is_required,current_version,created_by,updated_by,created_at,updated_at)
VALUES ('stock-inbound', '成品入库', '库存流程', '正向', '自动通过', '机台', '单机台', '已发布', 1, 0, 'import-auto-pass', 'import-auto-pass', NOW(), NOW())
ON DUPLICATE KEY UPDATE
  name=VALUES(name), category_key=VALUES(category_key), direction=VALUES(direction),
  processing_type='自动通过', business_object=VALUES(business_object),
  execution_scope=VALUES(execution_scope), status='已发布', is_required=VALUES(is_required),
  updated_by='import-auto-pass', updated_at=NOW();
SET @model_id := (SELECT id FROM workflow_models WHERE workflow_key='stock-inbound');
SET @next_version := (SELECT COALESCE(MAX(version_no),0)+1 FROM workflow_model_versions WHERE model_id=@model_id);
UPDATE workflow_model_versions SET status='历史', runtime_enabled=0 WHERE model_id=@model_id AND status='已发布';
INSERT INTO workflow_model_versions
  (model_id,version_no,status,node_snapshot,runtime_enabled,published_by,published_at,created_at)
VALUES (@model_id,@next_version,'已发布','{"edges":[{"source":"start","target":"business-action-0"},{"source":"business-action-0","target":"end"}],"nodes":[{"x":60,"y":120,"id":"start","type":"start","label":"发起"},{"x":640,"y":120,"id":"end","type":"end","label":"结束"},{"x":330,"y":120,"id":"business-action-0","type":"execute","label":"自动执行业务","action":"inbound_machine"}]}',1,'import-auto-pass',NOW(),NOW());
UPDATE workflow_models SET current_version=@next_version, updated_at=NOW() WHERE id=@model_id;

-- 5. 库位转移（stock-transfer） 删除审批节点：无（原本已自动通过）
INSERT INTO workflow_models
  (workflow_key,name,category_key,direction,processing_type,business_object,execution_scope,
   status,is_required,current_version,created_by,updated_by,created_at,updated_at)
VALUES ('stock-transfer', '库位转移', '库存流程', '正向', '自动通过', '机台', '单机台', '已发布', 1, 0, 'import-auto-pass', 'import-auto-pass', NOW(), NOW())
ON DUPLICATE KEY UPDATE
  name=VALUES(name), category_key=VALUES(category_key), direction=VALUES(direction),
  processing_type='自动通过', business_object=VALUES(business_object),
  execution_scope=VALUES(execution_scope), status='已发布', is_required=VALUES(is_required),
  updated_by='import-auto-pass', updated_at=NOW();
SET @model_id := (SELECT id FROM workflow_models WHERE workflow_key='stock-transfer');
SET @next_version := (SELECT COALESCE(MAX(version_no),0)+1 FROM workflow_model_versions WHERE model_id=@model_id);
UPDATE workflow_model_versions SET status='历史', runtime_enabled=0 WHERE model_id=@model_id AND status='已发布';
INSERT INTO workflow_model_versions
  (model_id,version_no,status,node_snapshot,runtime_enabled,published_by,published_at,created_at)
VALUES (@model_id,@next_version,'已发布','{"edges":[{"source":"start","target":"business-action-0"},{"source":"business-action-0","target":"end"}],"nodes":[{"x":60,"y":120,"id":"start","type":"start","label":"发起"},{"x":640,"y":120,"id":"end","type":"end","label":"结束"},{"x":330,"y":120,"id":"business-action-0","type":"execute","label":"自动执行业务","action":"transfer_machine"}]}',1,'import-auto-pass',NOW(),NOW());
UPDATE workflow_models SET current_version=@next_version, updated_at=NOW() WHERE id=@model_id;

-- 6. 发货确认（shipment-confirm） 删除审批节点：无（原本已自动通过）
INSERT INTO workflow_models
  (workflow_key,name,category_key,direction,processing_type,business_object,execution_scope,
   status,is_required,current_version,created_by,updated_by,created_at,updated_at)
VALUES ('shipment-confirm', '发货确认', '发货流程', '正向', '自动通过', '发货单', '整单', '已发布', 1, 0, 'import-auto-pass', 'import-auto-pass', NOW(), NOW())
ON DUPLICATE KEY UPDATE
  name=VALUES(name), category_key=VALUES(category_key), direction=VALUES(direction),
  processing_type='自动通过', business_object=VALUES(business_object),
  execution_scope=VALUES(execution_scope), status='已发布', is_required=VALUES(is_required),
  updated_by='import-auto-pass', updated_at=NOW();
SET @model_id := (SELECT id FROM workflow_models WHERE workflow_key='shipment-confirm');
SET @next_version := (SELECT COALESCE(MAX(version_no),0)+1 FROM workflow_model_versions WHERE model_id=@model_id);
UPDATE workflow_model_versions SET status='历史', runtime_enabled=0 WHERE model_id=@model_id AND status='已发布';
INSERT INTO workflow_model_versions
  (model_id,version_no,status,node_snapshot,runtime_enabled,published_by,published_at,created_at)
VALUES (@model_id,@next_version,'已发布','{"edges":[{"source":"start","target":"business-action-0"},{"source":"business-action-0","target":"end"}],"nodes":[{"x":60,"y":120,"id":"start","type":"start","label":"发起"},{"x":640,"y":120,"id":"end","type":"end","label":"结束"},{"x":330,"y":120,"id":"business-action-0","type":"execute","label":"自动执行业务","action":"confirm_shipment"}]}',1,'import-auto-pass',NOW(),NOW());
UPDATE workflow_models SET current_version=@next_version, updated_at=NOW() WHERE id=@model_id;

-- 7. 客户机台规划（customer-machine-plan） 删除审批节点：无（原本已自动通过）
INSERT INTO workflow_models
  (workflow_key,name,category_key,direction,processing_type,business_object,execution_scope,
   status,is_required,current_version,created_by,updated_by,created_at,updated_at)
VALUES ('customer-machine-plan', '客户机台规划', '客户成品流程', '正向', '自动通过', '机台', '单机台', '已发布', 0, 0, 'import-auto-pass', 'import-auto-pass', NOW(), NOW())
ON DUPLICATE KEY UPDATE
  name=VALUES(name), category_key=VALUES(category_key), direction=VALUES(direction),
  processing_type='自动通过', business_object=VALUES(business_object),
  execution_scope=VALUES(execution_scope), status='已发布', is_required=VALUES(is_required),
  updated_by='import-auto-pass', updated_at=NOW();
SET @model_id := (SELECT id FROM workflow_models WHERE workflow_key='customer-machine-plan');
SET @next_version := (SELECT COALESCE(MAX(version_no),0)+1 FROM workflow_model_versions WHERE model_id=@model_id);
UPDATE workflow_model_versions SET status='历史', runtime_enabled=0 WHERE model_id=@model_id AND status='已发布';
INSERT INTO workflow_model_versions
  (model_id,version_no,status,node_snapshot,runtime_enabled,published_by,published_at,created_at)
VALUES (@model_id,@next_version,'已发布','{"edges":[{"source":"start","target":"execute"},{"source":"execute","target":"end"}],"nodes":[{"x":35,"y":120,"id":"start","type":"start","label":"发起"},{"x":300,"y":120,"id":"execute","type":"execute","label":"保存客户机台规划","action":"save_customer_machine_plan"},{"x":600,"y":120,"id":"end","type":"end","label":"结束"}]}',1,'import-auto-pass',NOW(),NOW());
UPDATE workflow_models SET current_version=@next_version, updated_at=NOW() WHERE id=@model_id;

-- 8. 取消合同（contract-cancel） 删除审批节点：上一级审批
INSERT INTO workflow_models
  (workflow_key,name,category_key,direction,processing_type,business_object,execution_scope,
   status,is_required,current_version,created_by,updated_by,created_at,updated_at)
VALUES ('contract-cancel', '取消合同', '合同流程', '逆向', '自动通过', '合同', '整单', '已发布', 0, 0, 'import-auto-pass', 'import-auto-pass', NOW(), NOW())
ON DUPLICATE KEY UPDATE
  name=VALUES(name), category_key=VALUES(category_key), direction=VALUES(direction),
  processing_type='自动通过', business_object=VALUES(business_object),
  execution_scope=VALUES(execution_scope), status='已发布', is_required=VALUES(is_required),
  updated_by='import-auto-pass', updated_at=NOW();
SET @model_id := (SELECT id FROM workflow_models WHERE workflow_key='contract-cancel');
SET @next_version := (SELECT COALESCE(MAX(version_no),0)+1 FROM workflow_model_versions WHERE model_id=@model_id);
UPDATE workflow_model_versions SET status='历史', runtime_enabled=0 WHERE model_id=@model_id AND status='已发布';
INSERT INTO workflow_model_versions
  (model_id,version_no,status,node_snapshot,runtime_enabled,published_by,published_at,created_at)
VALUES (@model_id,@next_version,'已发布','{"edges":[{"branch":"false","source":"condition","target":"cancel-unbound","sourceType":"condition"},{"branch":"true","source":"condition","target":"cancel-bound","sourceType":"condition"},{"source":"cancel-unbound","target":"end-unbound"},{"source":"cancel-bound","target":"notify-inbound"},{"source":"notify-inbound","target":"end-bound"},{"source":"start","target":"condition"}],"nodes":[{"x":30,"y":190,"id":"start","type":"start","label":"发起取消"},{"x":350,"y":190,"id":"condition","type":"condition","label":"是否绑定机台","branches":{"true":"cancel-bound","false":"cancel-unbound"},"conditionField":"bound_machine_count","conditionValue":0,"conditionOperator":"gt"},{"x":530,"y":90,"id":"cancel-unbound","type":"execute","label":"直接取消合同","action":"cancel_contract"},{"x":710,"y":390,"id":"cancel-bound","type":"execute","label":"取消并释放机台","action":"cancel_contract_reinbound"},{"x":710,"y":290,"id":"notify-inbound","type":"notify","label":"通知入库员","notifyRoles":["Inbound"]},{"x":890,"y":90,"id":"end-unbound","type":"end","label":"结束"},{"x":890,"y":290,"id":"end-bound","type":"end","label":"结束"}]}',1,'import-auto-pass',NOW(),NOW());
UPDATE workflow_models SET current_version=@next_version, updated_at=NOW() WHERE id=@model_id;

-- 9. 删除机型字典（model-dict-delete） 删除审批节点：审批
INSERT INTO workflow_models
  (workflow_key,name,category_key,direction,processing_type,business_object,execution_scope,
   status,is_required,current_version,created_by,updated_by,created_at,updated_at)
VALUES ('model-dict-delete', '删除机型字典', '基础资料流程', '逆向', '自动通过', '机型字典', '基础资料对象', '已发布', 0, 0, 'import-auto-pass', 'import-auto-pass', NOW(), NOW())
ON DUPLICATE KEY UPDATE
  name=VALUES(name), category_key=VALUES(category_key), direction=VALUES(direction),
  processing_type='自动通过', business_object=VALUES(business_object),
  execution_scope=VALUES(execution_scope), status='已发布', is_required=VALUES(is_required),
  updated_by='import-auto-pass', updated_at=NOW();
SET @model_id := (SELECT id FROM workflow_models WHERE workflow_key='model-dict-delete');
SET @next_version := (SELECT COALESCE(MAX(version_no),0)+1 FROM workflow_model_versions WHERE model_id=@model_id);
UPDATE workflow_model_versions SET status='历史', runtime_enabled=0 WHERE model_id=@model_id AND status='已发布';
INSERT INTO workflow_model_versions
  (model_id,version_no,status,node_snapshot,runtime_enabled,published_by,published_at,created_at)
VALUES (@model_id,@next_version,'已发布','{"edges":[{"source":"execute","target":"end"},{"source":"start","target":"execute"}],"nodes":[{"x":35,"y":120,"id":"start","type":"start","label":"发起"},{"x":405,"y":120,"id":"execute","type":"execute","label":"自动执行","action":"disable_model","targetState":"按业务执行器处理"},{"x":775,"y":120,"id":"end","type":"end","label":"结束"}]}',1,'import-auto-pass',NOW(),NOW());
UPDATE workflow_models SET current_version=@next_version, updated_at=NOW() WHERE id=@model_id;

-- 10. 删除订单（order-delete） 删除审批节点：上一级审批
INSERT INTO workflow_models
  (workflow_key,name,category_key,direction,processing_type,business_object,execution_scope,
   status,is_required,current_version,created_by,updated_by,created_at,updated_at)
VALUES ('order-delete', '删除订单', '订单流程', '逆向', '自动通过', '订单', '整单', '已发布', 0, 0, 'import-auto-pass', 'import-auto-pass', NOW(), NOW())
ON DUPLICATE KEY UPDATE
  name=VALUES(name), category_key=VALUES(category_key), direction=VALUES(direction),
  processing_type='自动通过', business_object=VALUES(business_object),
  execution_scope=VALUES(execution_scope), status='已发布', is_required=VALUES(is_required),
  updated_by='import-auto-pass', updated_at=NOW();
SET @model_id := (SELECT id FROM workflow_models WHERE workflow_key='order-delete');
SET @next_version := (SELECT COALESCE(MAX(version_no),0)+1 FROM workflow_model_versions WHERE model_id=@model_id);
UPDATE workflow_model_versions SET status='历史', runtime_enabled=0 WHERE model_id=@model_id AND status='已发布';
INSERT INTO workflow_model_versions
  (model_id,version_no,status,node_snapshot,runtime_enabled,published_by,published_at,created_at)
VALUES (@model_id,@next_version,'已发布','{"edges":[{"branch":"false","source":"condition","target":"delete-unbound","sourceType":"condition"},{"branch":"true","source":"condition","target":"delete-bound","sourceType":"condition"},{"source":"delete-unbound","target":"end-unbound"},{"source":"delete-bound","target":"notify-inbound"},{"source":"notify-inbound","target":"end-bound"},{"source":"start","target":"condition"}],"nodes":[{"x":30,"y":190,"id":"start","type":"start","label":"发起删除"},{"x":350,"y":190,"id":"condition","type":"condition","label":"是否已绑定机台","branches":{"true":"delete-bound","false":"delete-unbound"},"conditionField":"bound_machine_count","conditionValue":0,"conditionOperator":"gt"},{"x":530,"y":90,"id":"delete-unbound","type":"execute","label":"直接删除订单","action":"delete_order"},{"x":530,"y":290,"id":"delete-bound","type":"execute","label":"删除并发起重入库","action":"delete_order_reinbound"},{"x":890,"y":390,"id":"notify-inbound","type":"notify","label":"通知入库员","notifyRoles":["Inbound"]},{"x":890,"y":90,"id":"end-unbound","type":"end","label":"结束"},{"x":1070,"y":390,"id":"end-bound","type":"end","label":"结束"}]}',1,'import-auto-pass',NOW(),NOW());
UPDATE workflow_models SET current_version=@next_version, updated_at=NOW() WHERE id=@model_id;

-- 11. 撤回配货（allocation-recall） 删除审批节点：无（原本已自动通过）
INSERT INTO workflow_models
  (workflow_key,name,category_key,direction,processing_type,business_object,execution_scope,
   status,is_required,current_version,created_by,updated_by,created_at,updated_at)
VALUES ('allocation-recall', '撤回配货', '配货流程', '逆向', '自动通过', '配货单', '整单', '已发布', 0, 0, 'import-auto-pass', 'import-auto-pass', NOW(), NOW())
ON DUPLICATE KEY UPDATE
  name=VALUES(name), category_key=VALUES(category_key), direction=VALUES(direction),
  processing_type='自动通过', business_object=VALUES(business_object),
  execution_scope=VALUES(execution_scope), status='已发布', is_required=VALUES(is_required),
  updated_by='import-auto-pass', updated_at=NOW();
SET @model_id := (SELECT id FROM workflow_models WHERE workflow_key='allocation-recall');
SET @next_version := (SELECT COALESCE(MAX(version_no),0)+1 FROM workflow_model_versions WHERE model_id=@model_id);
UPDATE workflow_model_versions SET status='历史', runtime_enabled=0 WHERE model_id=@model_id AND status='已发布';
INSERT INTO workflow_model_versions
  (model_id,version_no,status,node_snapshot,runtime_enabled,published_by,published_at,created_at)
VALUES (@model_id,@next_version,'已发布','{"edges":[{"source":"start","target":"execute"},{"source":"execute","target":"notify"},{"source":"notify","target":"end"}],"nodes":[{"x":35,"y":120,"id":"start","type":"start","label":"发起"},{"x":220,"y":120,"id":"execute","type":"execute","label":"自动执行","action":"recall_allocation","targetState":"按业务执行器处理"},{"x":405,"y":120,"id":"notify","type":"notify","label":"通知","notifyRoles":["Inbound"]},{"x":590,"y":120,"id":"end","type":"end","label":"结束"}]}',1,'import-auto-pass',NOW(),NOW());
UPDATE workflow_models SET current_version=@next_version, updated_at=NOW() WHERE id=@model_id;

-- 12. 发货撤回（shipment-recall） 删除审批节点：审批
INSERT INTO workflow_models
  (workflow_key,name,category_key,direction,processing_type,business_object,execution_scope,
   status,is_required,current_version,created_by,updated_by,created_at,updated_at)
VALUES ('shipment-recall', '发货撤回', '发货流程', '逆向', '自动通过', '发货单', '整单', '已发布', 0, 0, 'import-auto-pass', 'import-auto-pass', NOW(), NOW())
ON DUPLICATE KEY UPDATE
  name=VALUES(name), category_key=VALUES(category_key), direction=VALUES(direction),
  processing_type='自动通过', business_object=VALUES(business_object),
  execution_scope=VALUES(execution_scope), status='已发布', is_required=VALUES(is_required),
  updated_by='import-auto-pass', updated_at=NOW();
SET @model_id := (SELECT id FROM workflow_models WHERE workflow_key='shipment-recall');
SET @next_version := (SELECT COALESCE(MAX(version_no),0)+1 FROM workflow_model_versions WHERE model_id=@model_id);
UPDATE workflow_model_versions SET status='历史', runtime_enabled=0 WHERE model_id=@model_id AND status='已发布';
INSERT INTO workflow_model_versions
  (model_id,version_no,status,node_snapshot,runtime_enabled,published_by,published_at,created_at)
VALUES (@model_id,@next_version,'已发布','{"edges":[{"source":"execute","target":"notify"},{"source":"notify","target":"end"},{"source":"start","target":"execute"}],"nodes":[{"x":35,"y":120,"id":"start","type":"start","label":"发起"},{"x":220,"y":120,"id":"execute","type":"execute","label":"自动执行","action":"recall_shipment","targetState":"按业务执行器处理"},{"x":405,"y":120,"id":"notify","type":"notify","label":"通知","notifyRoles":["Inbound"]},{"x":590,"y":120,"id":"end","type":"end","label":"结束"}]}',1,'import-auto-pass',NOW(),NOW());
UPDATE workflow_models SET current_version=@next_version, updated_at=NOW() WHERE id=@model_id;

-- 13. 客户成品核销发货撤回（customer-finished-recall） 删除审批节点：审批
INSERT INTO workflow_models
  (workflow_key,name,category_key,direction,processing_type,business_object,execution_scope,
   status,is_required,current_version,created_by,updated_by,created_at,updated_at)
VALUES ('customer-finished-recall', '客户成品核销发货撤回', '客户成品流程', '逆向', '自动通过', '客户成品', '整单', '已发布', 0, 0, 'import-auto-pass', 'import-auto-pass', NOW(), NOW())
ON DUPLICATE KEY UPDATE
  name=VALUES(name), category_key=VALUES(category_key), direction=VALUES(direction),
  processing_type='自动通过', business_object=VALUES(business_object),
  execution_scope=VALUES(execution_scope), status='已发布', is_required=VALUES(is_required),
  updated_by='import-auto-pass', updated_at=NOW();
SET @model_id := (SELECT id FROM workflow_models WHERE workflow_key='customer-finished-recall');
SET @next_version := (SELECT COALESCE(MAX(version_no),0)+1 FROM workflow_model_versions WHERE model_id=@model_id);
UPDATE workflow_model_versions SET status='历史', runtime_enabled=0 WHERE model_id=@model_id AND status='已发布';
INSERT INTO workflow_model_versions
  (model_id,version_no,status,node_snapshot,runtime_enabled,published_by,published_at,created_at)
VALUES (@model_id,@next_version,'已发布','{"edges":[{"source":"execute","target":"notify"},{"source":"notify","target":"end"},{"source":"start","target":"execute"}],"nodes":[{"x":35,"y":120,"id":"start","type":"start","label":"发起"},{"x":405,"y":120,"id":"execute","type":"execute","label":"自动执行","action":"recall_customer_finished","targetState":"按业务执行器处理"},{"x":590,"y":120,"id":"notify","type":"notify","label":"通知","notifyRoles":["Inbound"]},{"x":775,"y":120,"id":"end","type":"end","label":"结束"}]}',1,'import-auto-pass',NOW(),NOW());
UPDATE workflow_models SET current_version=@next_version, updated_at=NOW() WHERE id=@model_id;

-- 14. 客户成品订单已发货（customer-order-shipped） 删除审批节点：无（原本已自动通过）
INSERT INTO workflow_models
  (workflow_key,name,category_key,direction,processing_type,business_object,execution_scope,
   status,is_required,current_version,created_by,updated_by,created_at,updated_at)
VALUES ('customer-order-shipped', '客户成品订单已发货', '客户成品流程', '正向', '自动通过', '客户成品订单', '整单', '已发布', 0, 0, 'import-auto-pass', 'import-auto-pass', NOW(), NOW())
ON DUPLICATE KEY UPDATE
  name=VALUES(name), category_key=VALUES(category_key), direction=VALUES(direction),
  processing_type='自动通过', business_object=VALUES(business_object),
  execution_scope=VALUES(execution_scope), status='已发布', is_required=VALUES(is_required),
  updated_by='import-auto-pass', updated_at=NOW();
SET @model_id := (SELECT id FROM workflow_models WHERE workflow_key='customer-order-shipped');
SET @next_version := (SELECT COALESCE(MAX(version_no),0)+1 FROM workflow_model_versions WHERE model_id=@model_id);
UPDATE workflow_model_versions SET status='历史', runtime_enabled=0 WHERE model_id=@model_id AND status='已发布';
INSERT INTO workflow_model_versions
  (model_id,version_no,status,node_snapshot,runtime_enabled,published_by,published_at,created_at)
VALUES (@model_id,@next_version,'已发布','{"edges":[{"source":"start","target":"execute"},{"source":"execute","target":"end"}],"nodes":[{"x":35,"y":120,"id":"start","type":"start","label":"发起"},{"x":300,"y":120,"id":"execute","type":"execute","label":"客户成品发货","action":"ship_customer_order"},{"x":600,"y":120,"id":"end","type":"end","label":"结束"}]}',1,'import-auto-pass',NOW(),NOW());
UPDATE workflow_models SET current_version=@next_version, updated_at=NOW() WHERE id=@model_id;

COMMIT;

-- ============================================================
-- 导入后自查（可单独执行）
-- SELECT workflow_key, name, processing_type, status, current_version
--   FROM workflow_models ORDER BY category_key, name;
-- SELECT m.workflow_key, v.version_no, v.status, v.runtime_enabled
--   FROM workflow_models m JOIN workflow_model_versions v
--     ON v.model_id=m.id AND v.version_no=m.current_version
--  WHERE v.runtime_enabled=1 ORDER BY m.workflow_key;
-- ============================================================
