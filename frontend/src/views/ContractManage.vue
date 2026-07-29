<template>
  <div class="contract-page">
    <PageHeader title="🏢 销售合同管理" />

    <div class="notice">💡 提示：录入的新合同在审批通过后，将自动流转至老板计划/沙盘与下单环节。</div>

    <div class="new-row">
      <button type="button" class="new-row-toggle" @click="batchPanelOpen = !batchPanelOpen">
        {{ batchPanelOpen ? '▾' : '▸' }} ➕ 录入新合同 (批量)
      </button>
    </div>

    <div class="batch-slide" :class="{ open: batchPanelOpen }">
      <div class="batch-slide-inner">
        <div class="batch-panel">
          <div class="batch-grid">
            <div>
              <div class="ops-label">合同号</div>
              <el-input
                v-model="batchForm.contractId"
                class="auto-id-input"
                maxlength="128"
                placeholder="请输入合同号"
                clearable
              />
              <div class="tip">默认自动生成，可按需手动修改</div>
            </div>
            <div>
              <div class="ops-label">期望交付日期</div>
              <el-date-picker v-model="batchForm.deadline" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
            </div>
            <div>
              <div class="ops-label">客户名称</div>
              <el-input v-model="batchForm.customer" />
            </div>
            <div>
              <div class="ops-label">代理商名称</div>
              <el-input v-model="batchForm.agent" />
            </div>
            <div>
              <div class="ops-label">急单</div>
              <el-switch v-model="batchForm.isRush" active-text="是" inactive-text="否" />
            </div>
          </div>

          <el-divider />
          <div class="ops-label">📎 附加合同文件 (可选)</div>
          <el-upload
            v-model:file-list="batchUploadFiles"
            class="contract-drop-upload"
            drag
            :auto-upload="false"
            :show-file-list="true"
            multiple
            :accept="contractFileAccept"
            :on-change="onBatchFileChange"
            :on-remove="onBatchFileRemove"
            @drop.capture="onBatchUploadDrop"
          >
            <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
            <div class="el-upload__text">拖入合同文件到这里，或 <em>点击选择</em></div>
            <template #tip>
              <div class="el-upload__tip">支持 PDF、Word、JPG/JPEG，单个文件不超过 50MB；不支持拖入文件夹。</div>
            </template>
          </el-upload>

          <el-divider />
          <div class="tip">请在下方清单中添加设备机型。支持同一机型添加多条记录（例如：标准版与加高版分开录入）。</div>
          <el-table :data="batchItems" border stripe class="form-table">
            <el-table-column label="#" width="60">
              <template #default="scope">{{ scope.$index + 1 }}</template>
            </el-table-column>
            <el-table-column label="机型">
              <template #default="scope">
                <el-select v-model="scope.row.model" filterable placeholder="请选择机型" style="width: 100%">
                  <el-option v-for="m in modelOptions" :key="m" :label="m" :value="m" />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="数量" width="100">
              <template #default="scope">
                <el-input-number v-model="scope.row.qty" :min="1" :controls="false" placeholder="数量" style="width: 100%" />
              </template>
            </el-table-column>
            <el-table-column label="加高?" width="90">
              <template #default="scope">
                <el-checkbox v-model="scope.row.high" />
              </template>
            </el-table-column>
            <el-table-column label="单行备注">
              <template #default="scope">
                <el-input v-model="scope.row.rowNote" />
              </template>
            </el-table-column>
          </el-table>
          <div class="batch-row-actions">
            <el-button link type="primary" @click="addBatchItem">+ 添加机型行</el-button>
          </div>

          <div class="ops-label">合同总备注</div>
          <el-input v-model="batchForm.contractNote" placeholder="可选，应用于所有条目" />

          <div class="batch-save">
            <el-button type="danger" :loading="batchSaving" @click="submitBatchContracts">💾 保存所有合同条目</el-button>
          </div>
        </div>
      </div>
    </div>

    <section class="contract-workspace">
      <div class="tabs-row">
        <button
          v-for="tab in statusTabs"
          :key="tab"
          type="button"
          class="status-tab"
          :class="{ active: activeTab === tab }"
          @click="activeTab = tab"
        >
          <span>{{ tab }}</span>
          <strong>{{ tabCounts[tab] }}</strong>
        </button>
      </div>

      <div class="workspace-grid">
        <aside class="contract-list-panel">
          <div class="list-tools">
            <el-input
              v-model="contractSearchKeyword"
              clearable
              placeholder="搜索合同号 / 客户 / 代理商"
              @clear="contractSearchKeyword = ''"
            />
            <el-select
              v-model="contractModelFilter"
              class="list-filter-control"
              clearable
              filterable
              placeholder="按机台筛选"
            >
              <el-option v-for="model in contractModelOptions" :key="model" :label="model" :value="model" />
            </el-select>
          </div>

          <div v-loading="loading" class="month-list">
            <el-empty v-if="groupedContracts.length === 0" description="当前状态暂无合同" :image-size="96" />
            <el-collapse v-else v-model="openMonths">
              <el-collapse-item v-for="group in groupedContracts" :key="group.month" :name="group.month">
                <template #title>
                  <div class="month-title">
                    <span>{{ group.month }}</span>
                    <em>{{ group.contracts.length }} 单</em>
                  </div>
                </template>
                <button
                  v-for="contract in group.contracts"
                  :key="contract.id"
                  type="button"
                  class="contract-card"
                  :class="{ active: selectedContractId === contract.id }"
                  @click="selectContract(contract.id)"
                >
                  <div class="contract-card-head">
                    <strong>{{ contract.id }}</strong>
                    <el-tag size="small" :type="statusTagType(contract.status)">{{ contract.status }}</el-tag>
                  </div>
                  <div class="contract-customer">{{ contract.customer || '未填写客户' }}</div>
                  <div class="contract-meta">
                    <span>{{ contract.modelSummary }}</span>
                    <span>{{ contract.dueDate || '未定交期' }}</span>
                  </div>
                </button>
              </el-collapse-item>
            </el-collapse>
          </div>
        </aside>

        <main ref="detailPanelRef" class="contract-detail-panel">
          <el-empty v-if="!selectedContract" description="请选择左侧合同" :image-size="112" />
          <template v-else>
            <div class="detail-head">
              <div>
                <div class="detail-kicker">{{ activeTab }}</div>
                <h2>{{ selectedContract.id }}</h2>
              </div>
              <el-tag size="large" :type="statusTagType(selectedContract.status)">{{ selectedContract.status }}</el-tag>
            </div>

            <div class="info-grid">
              <div>
                <span>客户名</span>
                <strong>{{ selectedContract.customer || '-' }}</strong>
              </div>
              <div>
                <span>代理商</span>
                <strong>{{ selectedContract.agent || '-' }}</strong>
              </div>
              <div>
                <span>要求交期</span>
                <strong>{{ selectedContract.dueDate || '-' }}</strong>
              </div>
              <div>
                <span>合计数量</span>
                <strong>{{ selectedContract.totalQty }}</strong>
              </div>
              <div v-if="showOrderNo">
                <span>订单号</span>
                <strong>{{ selectedContract.orderNo || '-' }}</strong>
              </div>
              <div>
                <span>机型摘要</span>
                <strong>{{ selectedContract.modelSummary }}</strong>
              </div>
            </div>

            <div class="detail-section">
              <div class="section-title">机型明细</div>
              <el-table :data="selectedContract.rows" border stripe size="small">
                <el-table-column prop="机型" label="机型" min-width="180" />
                <el-table-column prop="排产数量" label="数量" width="90" />
                <el-table-column prop="要求交期" label="交期" width="120" />
                <el-table-column prop="状态" label="状态" width="110" />
                <el-table-column prop="备注" label="备注" min-width="180" show-overflow-tooltip />
              </el-table>
            </div>

            <div class="detail-section">
              <div class="section-title">附件</div>
              <div class="attachment-header">
                <span class="attachment-title">合同附件</span>
                <el-button link type="primary" :loading="attachmentLoading" @click="fetchAttachments(selectedContract.id)">
                  刷新
                </el-button>
              </div>

              <div v-if="attachmentLoading" class="attachment-loading">
                <el-icon class="is-loading"><Loading /></el-icon> 加载中...
              </div>
              <div v-else-if="attachmentFiles.length === 0" class="attachment-empty">该合同暂无附件</div>
              <div v-else class="attachment-list">
                <div v-for="file in attachmentFiles" :key="file.file_name" class="attachment-item">
                  <div class="attachment-info">
                    <el-icon><Document /></el-icon>
                    <span class="attachment-name">{{ file.file_name }}</span>
                    <span class="attachment-meta">{{ file.uploader }} · {{ file.upload_time }}</span>
                  </div>
                  <div class="attachment-actions">
                    <el-button type="success" link :loading="previewingFile === file.file_name" @click="previewAttachment(selectedContract.id, file.file_name)">
                      预览
                    </el-button>
                    <el-button type="primary" link :loading="downloadingFile === file.file_name" @click="downloadAttachment(selectedContract.id, file.file_name)">
                      下载
                    </el-button>
                    <el-button type="danger" link @click="deleteAttachment(selectedContract.id, file.file_name)">
                      删除
                    </el-button>
                  </div>
                </div>
              </div>

              <div class="attachment-upload-row">
                <el-upload
                  v-model:file-list="existingAttachmentUploadFiles"
                  class="contract-drop-upload compact"
                  drag
                  :auto-upload="false"
                  :show-file-list="false"
                  multiple
                  :accept="contractFileAccept"
                  :on-change="onExistingContractFileChange"
                  @drop.capture="onBatchUploadDrop"
                >
                  <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
                  <div class="el-upload__text">拖入附件，或 <em>点击追加</em></div>
                  <template #tip>
                    <div class="el-upload__tip">PDF、Word、JPG/JPEG，单个不超过 50MB；不支持文件夹。</div>
                  </template>
                </el-upload>
              </div>
            </div>

            <div class="detail-section actions-section">
              <div>
                <div class="section-title">可用操作</div>
                <div class="ops-hint">待规划合同可转为已规划并同步沙盘；取消后会清理预测沙盒占用、排产队列和急单队列，并触发重算。</div>
              </div>
              <div class="action-buttons">
                <el-button
                  v-if="canEditSelected"
                  type="warning"
                  :loading="contractEditSaving"
                  @click="openContractEditDialog"
                >
                  修改合同
                </el-button>
                <el-button
                  v-if="canMarkPlannedSelected"
                  type="primary"
                  :loading="executing"
                  @click="markSelectedContractPlanned"
                >
                  转为已规划
                </el-button>
                <el-button
                  v-if="canCancelSelected"
                  type="danger"
                  :loading="executing"
                  @click="cancelSelectedContract"
                >
                  取消合同
                </el-button>
                <el-tag v-if="!hasAvailableAction" type="info">当前状态无可用操作</el-tag>
              </div>
            </div>
          </template>
        </main>
      </div>
    </section>

    <el-dialog
      v-model="contractEditDialogVisible"
      title="修改合同"
      width="920px"
      destroy-on-close
    >
      <div class="contract-edit-form">
        <div class="edit-grid">
          <div>
            <div class="ops-label">合同号</div>
            <el-input v-model="contractEditForm.contractNo" disabled />
          </div>
          <div>
            <div class="ops-label">客户名</div>
            <el-input v-model="contractEditForm.customer" />
          </div>
          <div>
            <div class="ops-label">代理商</div>
            <el-input v-model="contractEditForm.agent" />
          </div>
          <div>
            <div class="ops-label">要求交期</div>
            <el-date-picker v-model="contractEditForm.dueDate" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
          </div>
        </div>

        <el-divider />
        <div class="section-title">机型明细</div>
        <el-table :data="contractEditForm.items" border stripe class="form-table">
          <el-table-column label="#" width="56">
            <template #default="scope">{{ scope.$index + 1 }}</template>
          </el-table-column>
          <el-table-column label="机型" min-width="210">
            <template #default="scope">
              <el-select v-model="scope.row.model" filterable placeholder="请选择机型" style="width: 100%">
                <el-option v-for="m in modelOptions" :key="m" :label="m" :value="m" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="数量" width="110">
            <template #default="scope">
              <el-input-number v-model="scope.row.qty" :min="1" :controls="false" style="width: 100%" />
            </template>
          </el-table-column>
          <el-table-column label="备注" min-width="220">
            <template #default="scope">
              <el-input v-model="scope.row.remark" />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="90">
            <template #default="scope">
              <el-button link type="danger" :disabled="contractEditForm.items.length <= 1" @click="removeContractEditItem(scope.$index)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <div class="batch-row-actions">
          <el-button link type="primary" @click="addContractEditItem">+ 添加机型行</el-button>
        </div>
      </div>
      <template #footer>
        <el-button @click="contractEditDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="contractEditSaving" @click="precheckContractEdit">保存并预检影响</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="contractImpactDialogVisible"
      title="确认合同修改影响"
      width="980px"
      destroy-on-close
    >
      <div v-if="contractEditPreview" class="impact-dialog-body">
        <el-alert
          type="warning"
          :closable="false"
          show-icon
          :title="`该合同已绑定 ${contractEditPreview.impact?.bound_units || 0} 张沙盘/产线卡片，确认后会按下面方案同步。`"
        />
        <div class="impact-stats">
          <span v-for="(qty, status) in contractEditPreview.impact?.by_status || {}" :key="status">{{ status }}：{{ qty }}</span>
        </div>

        <div class="section-title">卡片处理</div>
        <el-table :data="contractUnitDecisions" border stripe max-height="360" size="small">
          <el-table-column prop="unit_id" label="卡片" min-width="190" show-overflow-tooltip />
          <el-table-column prop="from_model" label="原机型" min-width="150" />
          <el-table-column prop="model_family" label="机型族" min-width="120" />
          <el-table-column label="批次" min-width="150">
            <template #default="scope">
              {{ scope.row.batch_status || '-' }} / {{ scope.row.batch_id || '-' }} / {{ scope.row.slot_index || '-' }}
            </template>
          </el-table-column>
          <el-table-column label="处理" width="150">
            <template #default="scope">
              <el-radio-group v-model="scope.row.action" size="small">
                <el-radio-button label="keep">保留</el-radio-button>
                <el-radio-button label="release">释放</el-radio-button>
              </el-radio-group>
            </template>
          </el-table-column>
          <el-table-column label="目标机型" min-width="190">
            <template #default="scope">
              <el-select
                v-model="scope.row.to_model"
                filterable
                :disabled="scope.row.action === 'release'"
                placeholder="选择目标机型"
                style="width: 100%"
              >
                <el-option
                  v-for="m in targetModelsForFamily(scope.row.model_family)"
                  :key="m"
                  :label="m"
                  :value="m"
                />
              </el-select>
            </template>
          </el-table-column>
        </el-table>

        <div class="section-title supplement-title">补排调整</div>
        <el-table v-if="contractDecisionSupplements.length > 0" :data="contractDecisionSupplements" border stripe size="small">
          <el-table-column prop="model" label="机型" min-width="180" />
          <el-table-column prop="model_family" label="机型族" min-width="140" />
          <el-table-column label="补排数量" width="140">
            <template #default="scope">
              <el-input-number v-model="scope.row.qty" :min="0" :controls="false" style="width: 100%" />
            </template>
          </el-table-column>
          <el-table-column prop="reason" label="原因" min-width="220" />
        </el-table>
        <div v-else class="impact-empty">无需新增补排。</div>
        <el-alert v-if="contractImpactError" class="impact-error" type="error" :closable="false" show-icon :title="contractImpactError" />
      </div>
      <template #footer>
        <el-button @click="contractImpactDialogVisible = false">返回修改</el-button>
        <el-button type="primary" :disabled="Boolean(contractImpactError)" :loading="contractEditSaving" @click="confirmContractEditImpact">确认并同步</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="previewDialogVisible"
      :title="previewTitle"
      width="82vw"
      class="attachment-preview-dialog"
      destroy-on-close
    >
      <div v-if="previewLoading" class="preview-loading">
        <el-icon class="is-loading"><Loading /></el-icon> 正在加载预览...
      </div>
      <iframe
        v-else-if="previewType === 'pdf' && previewUrl"
        class="preview-frame"
        :src="previewUrl"
        title="PDF 预览"
      />
      <iframe
        v-else-if="previewType === 'html'"
        class="preview-frame"
        :srcdoc="previewHtml"
        sandbox=""
        title="文档预览"
      />
      <div v-else class="preview-empty">
        <div class="preview-empty-title">暂不支持直接在线渲染</div>
        <div class="preview-empty-text">{{ previewMessage || '该文件类型暂不支持在线预览。' }}</div>
        <el-button v-if="selectedContract" type="primary" @click="downloadAttachment(selectedContract.id, previewTitle)">
          下载查看
        </el-button>
      </div>
    </el-dialog>

    <el-dialog
      v-model="saveModeDialogVisible"
      title="保存方式"
      width="460px"
      :close-on-click-modal="false"
      :close-on-press-escape="false"
      @closed="onSaveModeDialogClosed"
    >
      <div class="save-mode-body">
        <div>请选择保存方式：</div>
        <div class="save-mode-sub">
          {{ isRushOrderActive ? '进入生产看板（参与急单排产）' : '进入沙盘（参与老板计划排产）' }}或使用现货（直接置为已规划）。
        </div>
        <div v-if="!canUseSpotMode" class="save-mode-hint">
          当前“使用现货”不可用：{{ spotModeBlockReason }}
        </div>
      </div>
      <template #footer>
        <el-button @click="closeSaveModeDialog">取消</el-button>
        <el-button type="warning" :disabled="!canUseSpotMode" @click="chooseSaveMode('spot')">使用现货</el-button>
        <el-button type="primary" @click="chooseSaveMode('sandbox')">
          {{ isRushOrderActive ? '进入生产看板' : '进入沙盘' }}
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="dealerOrderDialogVisible" title="选择经销商订单转合同" width="860px">
      <div class="dealer-import-toolbar">
        <el-input
          v-model="dealerOrderKeyword"
          clearable
          placeholder="搜索订单号 / 客户 / 联系人 / 机型"
          @keyup.enter="loadDealerOrders"
          @clear="loadDealerOrders"
        />
        <el-tag type="success" size="large">待审核/已通过可转合同</el-tag>
        <el-button :loading="dealerOrderLoading" @click="loadDealerOrders">查询</el-button>
      </div>
      <el-table
        v-loading="dealerOrderLoading"
        :data="dealerOrders"
        border
        stripe
        size="small"
        height="420"
        @row-dblclick="openDealerOrderConvertDialog"
      >
        <el-table-column prop="order_no" label="订单号" min-width="160" show-overflow-tooltip />
        <el-table-column prop="customer_name" label="客户名称" min-width="150" show-overflow-tooltip />
        <el-table-column prop="contact_name" label="代理商/联系人" width="130" show-overflow-tooltip />
        <el-table-column prop="model" label="机型明细" min-width="220" show-overflow-tooltip />
        <el-table-column prop="quantity" label="数量" width="80" align="right" />
        <el-table-column label="状态" width="120">
          <template #default="{ row }">{{ dealerOrderStatusText(row) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="110" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" :disabled="!canConvertDealerOrder(row)" @click="openDealerOrderConvertDialog(row)">转合同</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="dealer-import-tip">选择订单后会打开完整转合同表单，可检查合同号、交期、明细和保存方式后生成合同。</div>
    </el-dialog>

    <el-dialog
      v-model="dealerConvertDialogVisible"
      title="从经销商订单转为合同"
      width="860px"
      :close-on-click-modal="false"
      :close-on-press-escape="false"
    >
      <div class="convert-grid">
        <div>
          <div class="ops-label">合同号</div>
          <el-input v-model="dealerConvertForm.contractNo" placeholder="自动生成" />
        </div>
        <div>
          <div class="ops-label">期望交付日期</div>
          <el-date-picker v-model="dealerConvertForm.deliveryDate" type="date" value-format="YYYY-MM-DD" style="width:100%" />
        </div>
        <div>
          <div class="ops-label">客户名称</div>
          <el-input v-model="dealerConvertForm.customer" />
        </div>
        <div>
          <div class="ops-label">代理商</div>
          <el-input v-model="dealerConvertForm.agent" />
        </div>
        <div>
          <div class="ops-label">急单</div>
          <el-switch v-model="dealerConvertForm.isRush" active-text="是" inactive-text="否" />
        </div>
      </div>

      <el-divider />
      <div class="ops-label">机型明细</div>
      <el-table :data="dealerConvertForm.items" border size="small" class="form-table">
        <el-table-column label="#" width="50">
          <template #default="scope">{{ scope.$index + 1 }}</template>
        </el-table-column>
        <el-table-column label="机型" min-width="160">
          <template #default="scope">
            <el-select v-model="scope.row.model" filterable placeholder="机型" style="width:100%">
              <el-option v-for="m in modelOptions" :key="m" :label="m" :value="m" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="数量" width="90">
          <template #default="scope">
            <el-input-number v-model="scope.row.qty" :min="1" :controls="false" style="width:100%" />
          </template>
        </el-table-column>
        <el-table-column label="加高" width="70">
          <template #default="scope">
            <el-checkbox v-model="scope.row.high" />
          </template>
        </el-table-column>
        <el-table-column label="原备注" min-width="120">
          <template #default="scope">
            <el-input v-model="scope.row.remark" placeholder="原备注" />
          </template>
        </el-table-column>
        <el-table-column label="附加备注" min-width="120">
          <template #default="scope">
            <el-input v-model="scope.row.extraRemark" placeholder="附加备注" />
          </template>
        </el-table-column>
        <el-table-column label="需要修改数量" width="110">
          <template #default="scope">
            <el-input-number v-model="scope.row.ermq" :min="0" :controls="false" style="width:100%" />
          </template>
        </el-table-column>
      </el-table>

      <el-divider />
      <div class="ops-label">合同总备注</div>
      <el-input v-model="dealerConvertForm.contractNote" placeholder="可选" />

      <div class="save-mode-section">
        <div class="ops-label">保存方式</div>
        <div class="save-mode-sub">
          {{ isDealerRushActive ? '进入生产看板（参与急单排产）' : '进入沙盘（参与老板计划排产）' }}或使用现货（直接置为已规划）。
        </div>
        <div v-if="!dealerConvertCanUseSpot" class="save-mode-blocked">当前“使用现货”不可用：{{ dealerConvertSpotBlockReason }}</div>
      </div>

      <template #footer>
        <el-button @click="dealerConvertDialogVisible = false">取消</el-button>
        <el-button type="warning" :disabled="!dealerConvertCanUseSpot" :loading="dealerConvertSaving" @click="submitDealerConvert('spot')">使用现货</el-button>
        <el-button type="primary" :loading="dealerConvertSaving" @click="submitDealerConvert('sandbox')">
          {{ isDealerRushActive ? '进入生产看板' : '进入沙盘' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Loading, Document, UploadFilled } from '@element-plus/icons-vue'
import { apiGet, apiGetAll, apiPost, apiPut, apiDelete, apiDownloadBlob, getApiErrorMessage } from '../utils/request'
import { useFormSubmit } from '../composables/useFormSubmit'
import { useContractsStore } from '../store/contracts'
import { useRefFormDraft } from '../composables/useFormDraft'
import { hasText, isPositiveInteger } from '../utils/formRules'
import { compareModels, getModelOrderList, isModelInDictionary } from '../utils/modelOrder'
import PageHeader from '../components/PageHeader.vue'

const router = useRouter()

type StatusTab = '待规划' | '已规划' | '已完成'
type MessageResponse = {
  message?: string
  rush_created?: number
  rush_auto_inserted?: number
  save_mode?: 'sandbox' | 'spot'
}
type ContractSummary = {
  id: string
  customer: string
  agent: string
  dueDate: string
  status: string
  orderNo: string
  rows: any[]
  totalQty: number
  modelSummary: string
}
type DealerOrderLine = {
  model?: string
  quantity?: number
  remark?: string
  extra_remark?: string
  factory_remark?: string
  ERMQ?: number
  factory_pending?: number
  batch_no?: string
  eta?: string
  inventory_type?: string
}
type DealerOrder = {
  order_no: string
  customer_name?: string
  contact_name?: string
  delivery_date?: string
  model?: string
  quantity?: number
  status?: string
  remark?: string
  extra_remark?: string
  factory_remark?: string
  ERMQ?: number
  factory_pending?: number
  review_note?: string
  items?: DealerOrderLine[]
}
type DealerOrderListResponse = {
  data: DealerOrder[]
  total: number
}
type ContractEditItem = { model: string; qty: number; remark: string }
type ContractUnitDecision = {
  unit_id: string
  from_model: string
  to_model: string
  model_family: string
  batch_status: string
  batch_id: string
  slot_index: number | string
  action: 'keep' | 'release'
}
type ContractSupplementDecision = {
  model: string
  model_family: string
  qty: number
  reason?: string
}
type ContractEditPreview = {
  blocked?: boolean
  blocked_reason?: string
  requires_mapping?: boolean
  preview_token?: string
  diff?: any
  impact?: { bound_units?: number; by_status?: Record<string, number> }
  unit_plan?: {
    assignments?: any[]
    releases?: any[]
    supplements?: ContractSupplementDecision[]
  }
  families?: Record<string, string>
}

const statusTabs: StatusTab[] = ['待规划', '已规划', '已完成']
const completedStatuses = new Set(['已转订单', '已下单', '已完工'])
const cancellableStatuses = new Set(['待规划', '已规划'])

const loading = ref(false)
const executing = ref(false)
const batchSaving = ref(false)
const batchPanelOpen = ref(false)
const allRows = ref<any[]>([])
const activeTab = ref<StatusTab>('待规划')
const selectedContractId = ref('')
const contractSearchKeyword = ref('')
const contractModelFilter = ref('')
const batchPickedFiles = ref<File[]>([])
const batchUploadFiles = ref<any[]>([])
const existingAttachmentUploadFiles = ref<any[]>([])
const dealerOrderDialogVisible = ref(false)
const dealerOrderLoading = ref(false)
const dealerOrderKeyword = ref('')
const dealerOrders = ref<DealerOrder[]>([])
const dealerOrderSource = ref('')
const dealerConvertDialogVisible = ref(false)
const dealerConvertSaving = ref(false)
const dealerConvertCanUseSpot = ref(true)
const dealerConvertSpotBlockReason = ref('')
const openMonths = ref<string[]>([])
const detailPanelRef = ref<HTMLElement | null>(null)
const contractEditDialogVisible = ref(false)
const contractImpactDialogVisible = ref(false)
const contractEditSaving = ref(false)
const contractEditPreview = ref<ContractEditPreview | null>(null)
const contractUnitDecisions = ref<ContractUnitDecision[]>([])
const contractDecisionSupplements = ref<ContractSupplementDecision[]>([])
const { submitWithLock } = useFormSubmit()
const contractsStore = useContractsStore()
const contractEditForm = reactive({
  contractNo: '',
  customer: '',
  agent: '',
  dueDate: '',
  items: [] as ContractEditItem[],
})
const batchForm = ref({
  contractId: '',
  deadline: '',
  customer: '',
  agent: '',
  contractNote: '',
  isRush: false,
})
const batchItems = ref<Array<{ model: string; qty: number; high: boolean; rowNote: string }>>([
  { model: '', qty: 1, high: false, rowNote: '' },
])
const modelOptions = computed(() => getModelOrderList())
type DealerConvertItem = { model: string; qty: number; high: boolean; rowNote: string; remark: string; extraRemark: string; ermq: number }
const dealerConvertForm = reactive({
  contractNo: '',
  deliveryDate: '',
  customer: '',
  agent: '',
  isRush: false,
  items: [] as DealerConvertItem[],
  contractNote: '',
  sourceOrderNo: '',
})
const isRushOrderActive = computed(() => batchForm.value.isRush)
const isDealerRushActive = computed(() => dealerConvertForm.isRush)
const saveModeDialogVisible = ref(false)
const canUseSpotMode = ref(true)
const spotModeBlockReason = ref('')
let saveModeDialogResolver: ((mode: 'sandbox' | 'spot' | null) => void) | null = null

const todayYmd = () => new Date().toISOString().slice(0, 10)
const fetchNextContractId = async () => {
  const res = await apiGet<{ contract_no: string }>('/planning/contracts/next-id')
  return String(res.contract_no || '').trim()
}

const resetBatchForm = async () => {
  batchForm.value = {
    contractId: '',
    deadline: todayYmd(),
    customer: '',
    agent: '',
    contractNote: '',
    isRush: false,
  }
  batchItems.value = [{ model: '', qty: 1, high: false, rowNote: '' }]
  batchPickedFiles.value = []
  batchUploadFiles.value = []
  dealerOrderSource.value = ''
  try {
    batchForm.value.contractId = await fetchNextContractId()
  } catch (err) {
    ElMessage.error(getApiErrorMessage(err) || '生成合同号失败')
  }
}

const loadDealerOrders = async () => {
  dealerOrderLoading.value = true
  try {
    const keyword = dealerOrderKeyword.value || undefined
    const responses = await Promise.all(['pending', 'approved'].map((status) => apiGet<DealerOrderListResponse>('/dealer-orders/', {
      params: {
        status,
        keyword,
        page: 1,
        page_size: 100,
      },
    })))
    const map = new Map<string, DealerOrder>()
    for (const res of responses) {
      for (const order of res.data || []) {
        if (order.order_no) map.set(order.order_no, order)
      }
    }
    dealerOrders.value = Array.from(map.values())
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || '读取经销商订单失败')
  } finally {
    dealerOrderLoading.value = false
  }
}

const dealerOrderStatusText = (order: DealerOrder) => {
  const status = String(order.status || '').trim()
  if (['complete', 'completed'].includes(status)) return '已完成'
  if (Number(order.factory_pending || 0) === 1) return '新备注审核中'
  const map: Record<string, string> = {
    pending: '待审核',
    approved: '已通过',
    contracted: '已转合同',
    partial_allocated: '部分配货',
    allocated: '已配货',
    rejected: '已驳回',
    cancelled: '已取消',
  }
  return map[status] || status || '-'
}

const canConvertDealerOrder = (order: DealerOrder) => {
  return ['pending', 'approved'].includes(String(order.status || '').trim()) && Number(order.factory_pending || 0) !== 1
}

const isRushHint = (order: DealerOrder) => {
  const remark = String(order.remark || '').toLowerCase()
  if (remark.includes('急') || remark.includes('加急')) return true
  const delivery = String(order.delivery_date || '').trim()
  if (!delivery) return false
  const days = (new Date(delivery).getTime() - Date.now()) / 86400000
  return days <= 3
}

const normalizeDealerOrderItems = (order: DealerOrder) => {
  const source: DealerOrderLine[] = order.items?.length
    ? order.items
    : [{ model: order.model, quantity: order.quantity, remark: order.remark, extra_remark: order.extra_remark, factory_remark: order.factory_remark, ERMQ: order.ERMQ }]
  return source
    .map((item) => {
      const model = String(item.model || '').trim()
      const qty = Math.max(1, Number(item.quantity || 1))
      const remark = String(item.remark || '').trim()
      const extraRemark = String(item.factory_remark || item.extra_remark || '').trim()
      const ermq = Number(item.ERMQ || 0)
      const high = model.includes('加高') || remark.includes('加高') || extraRemark.includes('加高')
      const rowNote = [remark ? `[备注]${remark}` : '', extraRemark ? `[附加]${extraRemark}` : '', ermq > 0 ? `[改数]${ermq}` : ''].filter(Boolean).join(' ')
      return { model, qty, high, rowNote, remark, extraRemark, ermq }
    })
    .filter((item) => item.model)
}

const openDealerOrderConvertDialog = async (order: DealerOrder) => {
  if (!canConvertDealerOrder(order)) {
    ElMessage.warning('只有待审核或已通过审核的经销商订单可以转合同')
    return
  }
  const rows = normalizeDealerOrderItems(order)
  if (rows.length === 0) {
    ElMessage.warning('该经销商订单没有可转合同的机型明细')
    return
  }
  dealerConvertForm.contractNo = ''
  dealerConvertForm.deliveryDate = String(order.delivery_date || '').slice(0, 10) || todayYmd()
  dealerConvertForm.customer = String(order.customer_name || '').trim()
  dealerConvertForm.agent = String(order.contact_name || '').trim()
  dealerConvertForm.isRush = isRushHint(order)
  dealerConvertForm.items = rows
  dealerConvertForm.contractNote = String(order.review_note || '').trim()
  dealerConvertForm.sourceOrderNo = String(order.order_no || '').trim()
  dealerConvertCanUseSpot.value = true
  dealerConvertSpotBlockReason.value = ''
  try {
    dealerConvertForm.contractNo = await fetchNextContractId()
  } catch (err) {
    ElMessage.error(getApiErrorMessage(err) || '生成合同号失败')
    return
  }
  dealerOrderDialogVisible.value = false
  dealerConvertDialogVisible.value = true
}

const normalizeStatus = (status: unknown) => {
  const text = String(status || '').trim()
  return text === '未下单' || !text ? '待规划' : text
}

const rowTab = (row: any): StatusTab | null => {
  const status = normalizeStatus(row['状态'])
  if (status === '待规划' || status === '已规划') return status
  if (completedStatuses.has(status)) return '已完成'
  return null
}

const contractMonth = (dueDate: string) => {
  const text = String(dueDate || '').trim()
  const match = text.match(/^(\d{4}-\d{2})/)
  return match ? match[1] : '未定交期'
}

const buildContractSummaries = (rows: any[]) => {
  const map = new Map<string, any[]>()
  for (const row of rows) {
    const id = String(row['合同号'] || '').trim()
    if (!id) continue
    const list = map.get(id) || []
    list.push(row)
    map.set(id, list)
  }
  return Array.from(map.entries()).map(([id, rowsForContract]) => {
    const first = rowsForContract[0] || {}
    const modelCounts = new Map<string, number>()
    let totalQty = 0
    for (const row of rowsForContract) {
      const model = String(row['机型'] || '').trim() || '未填写机型'
      const qty = Number(row['排产数量'] || 0)
      totalQty += qty
      modelCounts.set(model, (modelCounts.get(model) || 0) + qty)
    }
    const modelSummary = Array.from(modelCounts.entries()).map(([model, qty]) => `${model}×${qty}`).join('，')
    return {
      id,
      customer: String(first['客户名'] || '').trim(),
      agent: String(first['代理商'] || '').trim(),
      dueDate: String(first['要求交期'] || '').slice(0, 10),
      status: normalizeStatus(first['状态']),
      orderNo: String(first['订单号'] || '').trim(),
      rows: rowsForContract,
      totalQty,
      modelSummary: modelSummary || '无机型明细',
    } as ContractSummary
  }).sort((a, b) => {
    const dueCompare = String(a.dueDate || '').localeCompare(String(b.dueDate || ''))
    return dueCompare || a.id.localeCompare(b.id)
  })
}

const contractModelOptions = computed(() => {
  const models = new Set<string>()
  for (const row of allRows.value) {
    const model = String(row['机型'] || '').trim()
    if (model) models.add(model)
  }
  return Array.from(models).sort(compareModels)
})

const contractCards = computed(() => {
  const keyword = contractSearchKeyword.value.trim().toLowerCase()
  const modelFilter = contractModelFilter.value.trim()
  const tabRows = allRows.value.filter((row) => rowTab(row) === activeTab.value)
  const summaries = buildContractSummaries(tabRows)
  return summaries.filter((contract) => {
    if (modelFilter && !contract.rows.some((row) => String(row['机型'] || '').trim() === modelFilter)) {
      return false
    }
    if (!keyword) return true
    return [contract.id, contract.customer, contract.agent, contract.modelSummary]
      .map((value) => value.toLowerCase())
      .some((value) => value.includes(keyword))
  })
})

const groupedContracts = computed(() => {
  const groups = new Map<string, ContractSummary[]>()
  for (const contract of contractCards.value) {
    const month = contractMonth(contract.dueDate)
    groups.set(month, [...(groups.get(month) || []), contract])
  }
  return Array.from(groups.entries()).map(([month, contracts]) => ({ month, contracts }))
})

const tabCounts = computed<Record<StatusTab, number>>(() => {
  const counts: Record<StatusTab, number> = { 待规划: 0, 已规划: 0, 已完成: 0 }
  const seenByTab: Record<StatusTab, Set<string>> = {
    待规划: new Set(),
    已规划: new Set(),
    已完成: new Set(),
  }
  for (const row of allRows.value) {
    const tab = rowTab(row)
    const id = String(row['合同号'] || '').trim()
    if (tab && id) seenByTab[tab].add(id)
  }
  for (const tab of statusTabs) counts[tab] = seenByTab[tab].size
  return counts
})

const selectedContract = computed(() => contractCards.value.find((contract) => contract.id === selectedContractId.value) || null)
const canCancelSelected = computed(() => Boolean(selectedContract.value && cancellableStatuses.has(selectedContract.value.status)))
const canMarkPlannedSelected = computed(() => Boolean(selectedContract.value && selectedContract.value.status === '待规划'))
const canEditSelected = computed(() => Boolean(selectedContract.value && !completedStatuses.has(selectedContract.value.status)))
const hasAvailableAction = computed(() => canEditSelected.value || canMarkPlannedSelected.value || canCancelSelected.value)
const showOrderNo = computed(() => activeTab.value === '已完成')

const syncSelection = () => {
  const first = contractCards.value[0]
  if (!first) {
    selectedContractId.value = ''
    openMonths.value = []
    return
  }
  if (!selectedContract.value) selectedContractId.value = first.id
  openMonths.value = []
}

const selectContract = async (id: string) => {
  selectedContractId.value = id
  await nextTick()
  detailPanelRef.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

const statusTagType = (status: string) => {
  if (status === '待规划') return 'warning'
  if (status === '已规划') return 'primary'
  if (completedStatuses.has(status)) return 'success'
  return 'info'
}

const buildContractEditPayload = () => ({
  客户名: contractEditForm.customer.trim(),
  代理商: contractEditForm.agent.trim(),
  要求交期: contractEditForm.dueDate,
  items: contractEditForm.items
    .map((item) => ({
      机型: item.model.trim(),
      排产数量: Number(item.qty || 0),
      备注: item.remark.trim(),
    }))
    .filter((item) => item.机型 && item.排产数量 > 0),
})

const validateContractEditForm = () => {
  if (!hasText(contractEditForm.contractNo) || !hasText(contractEditForm.customer) || !hasText(contractEditForm.dueDate)) {
    ElMessage.warning('请先完整填写客户名和要求交期')
    return false
  }
  const validRows = contractEditForm.items.filter((item) => hasText(item.model) && isPositiveInteger(item.qty))
  if (validRows.length === 0) {
    ElMessage.warning('请至少保留 1 条机型明细')
    return false
  }
  const invalidModels = validRows.map((item) => item.model.trim()).filter((m) => !isModelInDictionary(m))
  if (invalidModels.length > 0) {
    ElMessage.warning(`以下机型不在字典中：${Array.from(new Set(invalidModels)).join('，')}`)
    return false
  }
  return true
}

const openContractEditDialog = () => {
  const contract = selectedContract.value
  if (!contract) return
  contractEditForm.contractNo = contract.id
  contractEditForm.customer = contract.customer || ''
  contractEditForm.agent = contract.agent || ''
  contractEditForm.dueDate = contract.dueDate || todayYmd()
  contractEditForm.items = contract.rows.map((row) => ({
    model: String(row['机型'] || '').trim(),
    qty: Math.max(1, Number(row['排产数量'] || 1)),
    remark: String(row['备注'] || '').trim(),
  }))
  if (contractEditForm.items.length === 0) {
    contractEditForm.items = [{ model: '', qty: 1, remark: '' }]
  }
  contractEditPreview.value = null
  contractUnitDecisions.value = []
  contractDecisionSupplements.value = []
  contractImpactDialogVisible.value = false
  contractEditDialogVisible.value = true
}

const addContractEditItem = () => {
  contractEditForm.items.push({ model: '', qty: 1, remark: '' })
}

const removeContractEditItem = (index: number) => {
  if (contractEditForm.items.length <= 1) return
  contractEditForm.items.splice(index, 1)
}

const buildRecommendedImpactDecision = (preview: ContractEditPreview) => {
  const plan = preview.unit_plan || {}
  const decisions: ContractUnitDecision[] = []
  for (const item of plan.assignments || []) {
    const unitId = String(item.unit_id || '').trim()
    if (!unitId) continue
    decisions.push({
      unit_id: unitId,
      from_model: String(item.from_model || item.model || ''),
      to_model: String(item.to_model || item.model || ''),
      model_family: String(item.model_family || ''),
      batch_status: String(item.batch_status || ''),
      batch_id: String(item.batch_id || ''),
      slot_index: item.slot_index ?? '',
      action: 'keep',
    })
  }
  for (const item of plan.releases || []) {
    const unitId = String(item.unit_id || '').trim()
    if (!unitId) continue
    decisions.push({
      unit_id: unitId,
      from_model: String(item.model || item.from_model || ''),
      to_model: String(item.model || item.from_model || ''),
      model_family: String(item.model_family || ''),
      batch_status: String(item.batch_status || ''),
      batch_id: String(item.batch_id || ''),
      slot_index: item.slot_index ?? '',
      action: 'release',
    })
  }
  contractUnitDecisions.value = decisions
  const supplementsByModel = new Map<string, ContractSupplementDecision>()
  for (const item of plan.supplements || []) {
    const model = String(item.model || '')
    if (!model) continue
    supplementsByModel.set(model, {
      model,
      model_family: String(item.model_family || ''),
      qty: Number(item.qty || 0),
      reason: String(item.reason || ''),
    })
  }
  const counts = preview.diff?.new_demand?.counts || {}
  const families = preview.families || {}
  for (const model of Object.keys(counts)) {
    if (!supplementsByModel.has(model)) {
      supplementsByModel.set(model, {
        model,
        model_family: String(families[model] || ''),
        qty: 0,
        reason: '如释放更多卡片，可在这里补排',
      })
    }
  }
  contractDecisionSupplements.value = Array.from(supplementsByModel.values()).map((item) => ({
    model: String(item.model || ''),
    model_family: String(item.model_family || ''),
    qty: Number(item.qty || 0),
    reason: String(item.reason || ''),
  })).filter((item) => item.model)
}

const targetModelsForFamily = (family: string) => {
  const families = contractEditPreview.value?.families || {}
  const counts = contractEditPreview.value?.diff?.new_demand?.counts || {}
  return Object.entries(families)
    .filter(([model, f]) => Object.prototype.hasOwnProperty.call(counts, model) && String(f || '') === String(family || ''))
    .map(([model]) => model)
}

const contractImpactError = computed(() => {
  const preview = contractEditPreview.value
  if (!preview?.requires_mapping) return ''
  const counts = preview.diff?.new_demand?.counts || {}
  const byModel = new Map<string, number>()
  for (const row of contractUnitDecisions.value) {
    if (row.action !== 'keep') continue
    const model = String(row.to_model || '').trim()
    if (!model) return `卡片 ${row.unit_id} 还没有选择目标机型`
    if (!Object.prototype.hasOwnProperty.call(counts, model)) return `${model} 不在新合同明细中`
    byModel.set(model, (byModel.get(model) || 0) + 1)
  }
  for (const item of contractDecisionSupplements.value) {
    const model = String(item.model || '').trim()
    if (!model) continue
    byModel.set(model, (byModel.get(model) || 0) + Number(item.qty || 0))
  }
  for (const [model, qty] of Object.entries(counts)) {
    const expected = Number(qty || 0)
    const actual = Number(byModel.get(model) || 0)
    if (actual !== expected) return `${model} 数量不一致：当前方案 ${actual}，合同 ${expected}`
  }
  return ''
})

const submitContractEdit = async (mappingDecision?: any) => {
  const contractNo = contractEditForm.contractNo.trim()
  const payload = {
    ...buildContractEditPayload(),
    confirmed_impact: Boolean(mappingDecision),
    mapping_decision: mappingDecision || null,
  }
  const res = await apiPut<MessageResponse & { sync?: any; conflicts?: any[] }>(
    `/planning/contract/${encodeURIComponent(contractNo)}`,
    payload,
    { timeout: 120000 },
  )
  ElMessage.success(res.message || '合同修改已保存')
  contractEditDialogVisible.value = false
  contractImpactDialogVisible.value = false
  const oldTab = activeTab.value
  await fetchContracts(true)
  activeTab.value = oldTab
  selectedContractId.value = contractNo
}

const precheckContractEdit = async () => {
  if (!validateContractEditForm()) return
  await submitWithLock(contractEditSaving, async () => {
    const contractNo = contractEditForm.contractNo.trim()
    const payload = buildContractEditPayload()
    const preview = await apiPost<ContractEditPreview>(
      `/planning/contract/${encodeURIComponent(contractNo)}/edit-preview`,
      payload,
      { timeout: 120000 },
    )
    if (preview.blocked) {
      ElMessageBox.alert(preview.blocked_reason || '当前合同修改被拦截', '无法保存', { type: 'error' })
      return
    }
    contractEditPreview.value = preview
    if (preview.requires_mapping) {
      buildRecommendedImpactDecision(preview)
      contractImpactDialogVisible.value = true
      return
    }
    try {
      await ElMessageBox.confirm('该修改不会触发机型数量重排，确认保存并同步全局数据？', '确认保存', {
        confirmButtonText: '确认保存',
        cancelButtonText: '返回',
        type: 'warning',
      })
    } catch {
      return
    }
    await submitContractEdit()
  }, { errorMessage: '合同编辑预检失败' })
}

const confirmContractEditImpact = async () => {
  const preview = contractEditPreview.value
  if (!preview) return
  if (contractImpactError.value) {
    ElMessage.warning(contractImpactError.value)
    return
  }
  const assignments = contractUnitDecisions.value
    .filter((row) => row.action === 'keep')
    .map((row) => ({
      unit_id: row.unit_id,
      from_model: row.from_model,
      to_model: row.to_model,
      model_family: row.model_family,
      batch_status: row.batch_status,
      batch_id: row.batch_id,
      slot_index: row.slot_index,
    }))
  const releases = contractUnitDecisions.value
    .filter((row) => row.action === 'release')
    .map((row) => ({
      unit_id: row.unit_id,
      model: row.from_model,
      model_family: row.model_family,
      batch_status: row.batch_status,
      batch_id: row.batch_id,
      slot_index: row.slot_index,
    }))
  const supplements = contractDecisionSupplements.value
    .filter((item) => item.model && Number(item.qty || 0) > 0)
    .map((item) => ({ model: item.model, model_family: item.model_family, qty: Number(item.qty), reason: item.reason || '人工确认补排' }))
  await submitWithLock(contractEditSaving, async () => {
    await submitContractEdit({
      preview_token: preview.preview_token,
      unit_plan: { assignments, releases, supplements },
    })
  }, { errorMessage: '合同修改保存失败' })
}

const fetchContracts = async (force = false) => {
  loading.value = true
  try {
    allRows.value = await contractsStore.fetchPlanningContracts(force)
    syncSelection()
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || '读取合同数据失败')
  } finally {
    loading.value = false
  }
}

const cancelSelectedContract = async () => {
  const contract = selectedContract.value
  if (!contract) return
  try {
    await ElMessageBox.confirm(`确认取消合同「${contract.id}」？取消后将同步清理预测沙盒并重算。`, '取消合同', {
      confirmButtonText: '确认取消',
      cancelButtonText: '返回',
      type: 'warning',
    })
  } catch {
    return
  }
  await submitWithLock(executing, async () => {
    await apiPost(`/planning/contract/${encodeURIComponent(contract.id)}/status`, { status: '已取消' })
    await fetchContracts(true)
  }, { successMessage: '合同已取消，预测沙盒已同步重算', errorMessage: '取消合同失败' })
}

const markSelectedContractPlanned = async () => {
  const contract = selectedContract.value
  if (!contract || contract.status !== '待规划') return
  try {
    await ElMessageBox.confirm(`确认将合同「${contract.id}」同步到沙盘并转为已规划？`, '转为已规划', {
      confirmButtonText: '确认转为已规划',
      cancelButtonText: '返回',
      type: 'warning',
    })
  } catch {
    return
  }
  await submitWithLock(executing, async () => {
    const contractId = contract.id
    await apiPost(`/planning/contract/${encodeURIComponent(contractId)}/status`, { status: '已规划' })
    activeTab.value = '已规划'
    selectedContractId.value = contractId
    await fetchContracts(true)
  }, { successMessage: '合同已转为已规划并同步沙盘', errorMessage: '转为已规划失败' })
}

const addBatchItem = () => {
  batchItems.value.push({ model: '', qty: 1, high: false, rowNote: '' })
}

const contractFileAccept = '.pdf,.doc,.docx,.jpg,.jpeg'
const allowedContractFileExts = new Set(contractFileAccept.split(','))
const contractFileMaxSize = 50 * 1024 * 1024

const batchFileKey = (file: File) => `${file.name}__${file.size}__${file.lastModified || 0}`

const getBatchUploadRaw = (uploadFile: any) => uploadFile?.raw as File | undefined

const getContractFileError = (file: File) => {
  const name = String(file.name || '').trim()
  const dotIndex = name.lastIndexOf('.')
  const ext = dotIndex >= 0 ? name.slice(dotIndex).toLowerCase() : ''
  if (!name || !ext) return '请选择具体文件，不支持文件夹'
  if (!allowedContractFileExts.has(ext)) return '仅支持 PDF、Word、JPG/JPEG 文件'
  if (file.size > contractFileMaxSize) return '单个文件不能超过 50MB'
  return ''
}

const syncBatchPickedFiles = (uploadFiles: any[] = batchUploadFiles.value, notifyDuplicate = false) => {
  const seen = new Set<string>()
  const nextUploadFiles: any[] = []
  const nextPickedFiles: File[] = []
  let duplicateCount = 0

  for (const item of uploadFiles || []) {
    const raw = getBatchUploadRaw(item)
    if (!raw || getContractFileError(raw)) continue
    const key = batchFileKey(raw)
    if (seen.has(key)) {
      duplicateCount += 1
      continue
    }
    seen.add(key)
    nextUploadFiles.push(item)
    nextPickedFiles.push(raw)
  }

  if (notifyDuplicate && duplicateCount > 0) ElMessage.warning('重复文件已自动忽略')
  batchUploadFiles.value = nextUploadFiles
  batchPickedFiles.value = nextPickedFiles
}

const onBatchUploadDrop = (evt: DragEvent) => {
  const items = Array.from(evt.dataTransfer?.items || [])
  const hasDirectory = items.some((item: any) => {
    const entry = typeof item.webkitGetAsEntry === 'function' ? item.webkitGetAsEntry() : null
    return Boolean(entry?.isDirectory)
  })
  if (!hasDirectory) return
  evt.preventDefault()
  evt.stopPropagation()
  ElMessage.warning('请拖入文件，不支持拖入文件夹')
}

const onBatchFileChange = (uploadFile: any, uploadFiles: any[] = []) => {
  const raw = getBatchUploadRaw(uploadFile)
  if (!raw) return
  const error = getContractFileError(raw)
  if (error) {
    ElMessage.warning(`${raw.name || '该项目'}：${error}`)
    batchUploadFiles.value = (uploadFiles || batchUploadFiles.value).filter((item) => item.uid !== uploadFile.uid)
    syncBatchPickedFiles(batchUploadFiles.value)
    return
  }
  syncBatchPickedFiles(uploadFiles, true)
}

const onBatchFileRemove = (_uploadFile: any, uploadFiles: any[] = []) => {
  syncBatchPickedFiles(uploadFiles)
}

const getInStockCountByModel = async () => {
  const inventoryRows = await apiGetAll<any>('/inventory/')
  const map = new Map<string, number>()
  for (const row of inventoryRows) {
    const model = String(row['机型'] || '').trim()
    const status = String(row['状态'] || '').trim()
    if (!model || !status.startsWith('库存中')) continue
    map.set(model, (map.get(model) || 0) + 1)
  }
  return map
}

const evaluateSpotModeAvailability = async (rows: Array<{ model: string; qty: number }>) => {
  const requiredByModel = new Map<string, number>()
  for (const row of rows) {
    const model = String(row.model || '').trim()
    if (!model) continue
    requiredByModel.set(model, (requiredByModel.get(model) || 0) + Number(row.qty || 0))
  }
  const stockByModel = await getInStockCountByModel()
  const blocked: string[] = []
  for (const [model, required] of requiredByModel.entries()) {
    const inStock = Number(stockByModel.get(model) || 0)
    if (inStock <= 0) blocked.push(`${model}(无机台)`)
    else if (inStock < required) blocked.push(`${model}(库存${inStock} < 需求${required})`)
  }
  return {
    canUseSpot: blocked.length === 0,
    reason: blocked.length === 0 ? '' : blocked.join('，'),
  }
}

const submitDealerConvert = async (saveMode: 'sandbox' | 'spot') => {
  if (!hasText(dealerConvertForm.contractNo) || !hasText(dealerConvertForm.customer) || !hasText(dealerConvertForm.deliveryDate)) {
    ElMessage.warning('请先完整填写合同号/客户名/要求交期')
    return
  }
  const validItems = dealerConvertForm.items
    .map((item) => ({
      ...item,
      rowNote: [item.remark?.trim() ? `[备注]${item.remark.trim()}` : '', item.extraRemark?.trim() ? `[附加]${item.extraRemark.trim()}` : '', item.ermq > 0 ? `[改数]${item.ermq}` : ''].filter(Boolean).join(' '),
    }))
    .filter((item) => hasText(item.model) && isPositiveInteger(item.qty))
  if (validItems.length === 0) {
    ElMessage.warning('请至少填写 1 条机型明细')
    return
  }
  const invalidModels = validItems.map((item) => item.model).filter((m) => !isModelInDictionary(m))
  if (invalidModels.length > 0) {
    ElMessage.warning(`以下机型不在字典中：${Array.from(new Set(invalidModels)).join('，')}`)
    return
  }
  if (saveMode === 'spot') {
    try {
      const spotAvailability = await evaluateSpotModeAvailability(validItems)
      if (!spotAvailability.canUseSpot) {
        dealerConvertCanUseSpot.value = false
        dealerConvertSpotBlockReason.value = spotAvailability.reason
        ElMessage.warning(`“使用现货”不可用：${spotAvailability.reason}`)
        return
      }
    } catch (err: any) {
      ElMessage.error(getApiErrorMessage(err) || '校验现货可用机台失败')
      return
    }
  }

  await submitWithLock(dealerConvertSaving, async () => {
    const payload = {
      contract_no: dealerConvertForm.contractNo.trim(),
      customer_name: dealerConvertForm.customer.trim(),
      agent_name: dealerConvertForm.agent.trim(),
      delivery_date: dealerConvertForm.deliveryDate.trim(),
      save_mode: saveMode,
      is_rush: dealerConvertForm.isRush,
      items: validItems,
      contract_note: dealerConvertForm.contractNote.trim(),
    }
    const res = await apiPost<MessageResponse & { warning?: string; contract_no?: string }>(
      `/dealer-orders/${encodeURIComponent(dealerConvertForm.sourceOrderNo)}/convert-to-contract`,
      payload,
    )
    const autoInserted = Number(res.rush_auto_inserted || 0)
    const pendingRushCards = Math.max(0, Number(res.rush_created || 0) - autoInserted)
    const rushText = [
      autoInserted > 0 ? `已自动进入沙盘 ${autoInserted} 条` : '',
      pendingRushCards > 0 ? `已生成急单卡 ${pendingRushCards} 张` : '',
    ].filter(Boolean).join('，')
    const modeText = saveMode === 'spot'
      ? '已按“使用现货”处理（合同状态=已规划）'
      : (dealerConvertForm.isRush ? '已按“进入生产看板”处理（合同状态=待规划）' : '已按“进入沙盘”处理（合同状态=待规划）')
    ElMessage.success(res.warning || `${res.message || '转合同成功'}，${modeText}${rushText ? `，${rushText}` : ''}`)
    dealerConvertDialogVisible.value = false
    activeTab.value = saveMode === 'spot' ? '已规划' : '待规划'
    selectedContractId.value = String(res.contract_no || dealerConvertForm.contractNo).trim()
    await fetchContracts(true)
    await loadDealerOrders()
    if (saveMode === 'sandbox') {
      if (dealerConvertForm.isRush) {
        router.push('/production-kanban')
      } else {
        router.push('/prediction-sandbox')
      }
    } else if (saveMode === 'spot') {
      router.push({ path: '/sales-orders', query: { tab: 'import' } })
    }
  }, { errorMessage: '经销商订单转合同失败' })
}

const askSaveMode = async (canSpot: boolean, reason: string) => {
  canUseSpotMode.value = canSpot
  spotModeBlockReason.value = reason
  saveModeDialogVisible.value = true
  return await new Promise<'sandbox' | 'spot' | null>((resolve) => {
    saveModeDialogResolver = resolve
  })
}

const chooseSaveMode = (mode: 'sandbox' | 'spot') => {
  if (mode === 'spot' && !canUseSpotMode.value) return
  saveModeDialogVisible.value = false
  const resolver = saveModeDialogResolver
  saveModeDialogResolver = null
  resolver?.(mode)
}

const closeSaveModeDialog = () => {
  saveModeDialogVisible.value = false
  const resolver = saveModeDialogResolver
  saveModeDialogResolver = null
  resolver?.(null)
}

const onSaveModeDialogClosed = () => {
  if (!saveModeDialogResolver) return
  const resolver = saveModeDialogResolver
  saveModeDialogResolver = null
  resolver(null)
}

const submitBatchContracts = async () => {
  const cid = batchForm.value.contractId.trim()
  const customer = batchForm.value.customer.trim()
  const deadline = batchForm.value.deadline.trim()
  if (!hasText(cid) || !hasText(customer) || !hasText(deadline)) {
    ElMessage.warning('请先完整填写合同号/客户名/要求交期')
    return
  }
  const validRows = batchItems.value.filter((r) => hasText(r.model) && isPositiveInteger(r.qty))
  if (validRows.length === 0) {
    ElMessage.warning('请至少填写 1 条机型明细')
    return
  }
  const invalidModels = validRows.map((r) => String(r.model || '').trim()).filter((m) => !isModelInDictionary(m))
  if (invalidModels.length > 0) {
    ElMessage.warning(`以下机型不在字典中：${Array.from(new Set(invalidModels)).join('，')}`)
    return
  }

  let saveMode: 'sandbox' | 'spot' | null = null
  try {
    const spotAvailability = await evaluateSpotModeAvailability(validRows)
    saveMode = await askSaveMode(spotAvailability.canUseSpot, spotAvailability.reason)
    if (saveMode === 'spot' && !spotAvailability.canUseSpot) {
      ElMessage.warning(`“使用现货”不可用：${spotAvailability.reason}`)
      return
    }
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || '校验现货可用机台失败')
    return
  }
  if (!saveMode) return

  await submitWithLock(batchSaving, async () => {
    const payloadRows = validRows.map((r) => ({
      合同号: cid,
      客户名: customer,
      代理商: batchForm.value.agent.trim(),
      机型: r.model.trim(),
      排产数量: Number(r.qty),
      要求交期: deadline,
      备注: [batchForm.value.contractNote.trim() ? `[总]${batchForm.value.contractNote.trim()}` : '', r.high ? '加高' : '', r.rowNote.trim()].filter(Boolean).join(' '),
    }))
    const res = await apiPost<MessageResponse>('/planning/contracts/batch-create', {
      rows: payloadRows,
      is_rush: Boolean(batchForm.value.isRush),
      save_mode: saveMode,
      dealer_order_no: dealerOrderSource.value,
    })

    if (batchPickedFiles.value.length > 0) {
      for (const f of batchPickedFiles.value) {
        const fd = new FormData()
        fd.append('file', f)
        await apiPost(`/planning/contract/${encodeURIComponent(cid)}/files`, fd, {
          params: { customer_name: customer, uploader_name: 'Web' },
          headers: { 'Content-Type': 'multipart/form-data' },
        })
      }
    }
    const autoInserted = Number(res.rush_auto_inserted || 0)
    const pendingRushCards = Math.max(0, Number(res.rush_created || 0) - autoInserted)
    const rushText = [
      autoInserted > 0 ? `已自动进入沙盘 ${autoInserted} 条` : '',
      pendingRushCards > 0 ? `已生成急单卡 ${pendingRushCards} 张` : '',
    ].filter(Boolean).join('，')
    const modeText = saveMode === 'spot'
      ? '已按“使用现货”处理（合同状态=已规划）'
      : (batchForm.value.isRush ? '已按“进入生产看板”处理（合同状态=待规划）' : '已按“进入沙盘”处理（合同状态=待规划）')
    ElMessage.success(`${res.message || '批量录入成功'}，${modeText}${rushText ? `，${rushText}` : ''}`)
    activeTab.value = saveMode === 'spot' ? '已规划' : '待规划'
    selectedContractId.value = cid
    batchPanelOpen.value = false
    const isRush = batchForm.value.isRush
    await resetBatchForm()
    batchFormDraft.clearDraft()
    batchItemsDraft.clearDraft()
    await fetchContracts(true)
    if (saveMode === 'sandbox') {
      if (isRush) {
        router.push('/production-kanban')
      } else {
        router.push('/prediction-sandbox')
      }
    } else if (saveMode === 'spot') {
      router.push({ path: '/sales-orders', query: { tab: 'import' } })
    }
  }, { errorMessage: '批量录入失败' })
}

const batchFormDraft = useRefFormDraft('contracts:batch-form', batchForm)
const batchItemsDraft = useRefFormDraft('contracts:batch-items', batchItems)

const attachmentFiles = ref<any[]>([])
const attachmentLoading = ref(false)
const downloadingFile = ref('')
const previewingFile = ref('')
const previewDialogVisible = ref(false)
const previewLoading = ref(false)
const previewTitle = ref('')
const previewType = ref<'pdf' | 'html' | 'unsupported'>('unsupported')
const previewUrl = ref('')
const previewHtml = ref('')
const previewMessage = ref('')

const fetchAttachments = async (contractId: string) => {
  if (!contractId) return
  attachmentLoading.value = true
  try {
    const res: any = await apiGet(`/planning/contract/${encodeURIComponent(contractId)}/files`)
    attachmentFiles.value = res.data || []
  } catch (e) {
    attachmentFiles.value = []
    ElMessage.error('获取附件列表失败')
  } finally {
    attachmentLoading.value = false
  }
}

const downloadAttachment = async (contractId: string, fileName: string) => {
  downloadingFile.value = fileName
  try {
    await apiDownloadBlob(
      `/planning/contract/${encodeURIComponent(contractId)}/files/${encodeURIComponent(fileName)}/download`,
      fileName
    )
    ElMessage.success(`${fileName} 下载完成`)
  } catch (e) {
    ElMessage.error(getApiErrorMessage(e) || '文件下载失败')
  } finally {
    downloadingFile.value = ''
  }
}

const buildPreviewHtml = (bodyHtml: string) => `<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <style>
    body { margin: 0; padding: 24px 32px; color: #1f2937; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; line-height: 1.7; }
    table { width: 100%; border-collapse: collapse; margin: 12px 0; }
    td, th { border: 1px solid #d8dee8; padding: 6px 8px; vertical-align: top; }
    img { max-width: 100%; height: auto; }
    p { margin: 0 0 10px; }
  </style>
</head>
<body>${bodyHtml || '<p>文档无可预览内容</p>'}</body>
</html>`

const previewAttachment = async (contractId: string, fileName: string) => {
  previewingFile.value = fileName
  previewLoading.value = true
  previewDialogVisible.value = true
  previewTitle.value = fileName
  previewType.value = 'unsupported'
  previewUrl.value = ''
  previewHtml.value = ''
  previewMessage.value = ''
  try {
    const res: any = await apiGet(`/planning/contract/${encodeURIComponent(contractId)}/files/${encodeURIComponent(fileName)}/preview`, {
      timeout: 120000,
    })
    const ext = String(res.ext || '').toLowerCase()
    if (res.type === 'url' && ext === '.pdf') {
      previewType.value = 'pdf'
      previewUrl.value = String(res.url || '')
    } else if (res.type === 'html') {
      previewType.value = 'html'
      previewHtml.value = buildPreviewHtml(String(res.html || ''))
    } else {
      previewType.value = 'unsupported'
      previewMessage.value = String(res.message || (ext === '.doc' ? 'DOC 为旧版 Word 格式，请下载后用 Word/WPS 查看。' : '该文件类型暂不支持在线预览。'))
    }
  } catch (e) {
    previewType.value = 'unsupported'
    previewMessage.value = getApiErrorMessage(e) || '预览加载失败，请下载后查看。'
  } finally {
    previewLoading.value = false
    previewingFile.value = ''
  }
}

const deleteAttachment = async (contractId: string, fileName: string) => {
  try {
    await ElMessageBox.confirm(`确认删除文件「${fileName}」？此操作不可恢复。`, '删除附件', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    await apiDelete(`/planning/contract/${encodeURIComponent(contractId)}/files/${encodeURIComponent(fileName)}`)
    ElMessage.success('附件已删除')
    await fetchAttachments(contractId)
  } catch (e) {
    ElMessage.error(getApiErrorMessage(e) || '删除附件失败')
  }
}

const onExistingContractFileChange = async (uploadFile: any) => {
  const raw = getBatchUploadRaw(uploadFile)
  const contract = selectedContract.value
  if (!raw || !contract) return
  const error = getContractFileError(raw)
  if (error) {
    ElMessage.warning(`${raw.name || '该项目'}：${error}`)
    existingAttachmentUploadFiles.value = []
    return
  }
  const fd = new FormData()
  fd.append('file', raw)
  try {
    await apiPost(
      `/planning/contract/${encodeURIComponent(contract.id)}/files`,
      fd,
      { params: { customer_name: contract.customer, uploader_name: 'Web' }, headers: { 'Content-Type': 'multipart/form-data' } }
    )
    ElMessage.success('附件上传成功')
    await fetchAttachments(contract.id)
  } catch (e) {
    ElMessage.error(getApiErrorMessage(e) || '上传附件失败')
  } finally {
    existingAttachmentUploadFiles.value = []
  }
}

watch([activeTab, contractSearchKeyword, contractModelFilter], () => {
  syncSelection()
})

watch(selectedContractId, (newId) => {
  if (newId) {
    fetchAttachments(newId)
  } else {
    attachmentFiles.value = []
  }
})

onMounted(() => {
  void resetBatchForm()
  fetchContracts(true)
})
</script>

<style scoped>
.contract-page {
  padding-right: 6px;
}
.notice {
  margin-top: 12px;
  border: 1px solid var(--color-primary-100);
  background: var(--color-primary-50);
  color: var(--color-primary-700);
  border-radius: var(--radius-md);
  padding: var(--space-2) var(--space-3);
  font-size: var(--font-size-base);
}
.new-row {
  margin-top: var(--space-2);
  border: 1px solid var(--color-gray-200);
  border-radius: var(--radius-md);
  padding: 0 10px;
}
.new-row-toggle {
  border: none;
  background: transparent;
  color: var(--color-gray-700);
  font-size: var(--font-size-lg);
  font-weight: 700;
  cursor: pointer;
  padding: var(--space-2) 0;
}
.batch-slide {
  display: grid;
  grid-template-rows: 0fr;
  transition: grid-template-rows 0.35s cubic-bezier(0.4, 0, 0.2, 1);
}
.batch-slide.open {
  grid-template-rows: 1fr;
}
.batch-slide-inner {
  overflow: hidden;
  padding-top: 0;
  transition: padding-top 0.35s cubic-bezier(0.4, 0, 0.2, 1);
}
.batch-slide.open .batch-slide-inner {
  padding-top: var(--space-2);
}
.batch-panel {
  border: 1px solid var(--color-gray-200);
  border-radius: var(--radius-md);
  padding: var(--space-2);
}
.batch-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-2);
}
.auto-id {
  border: 1px solid var(--color-gray-200);
  background: var(--color-gray-50);
  border-radius: var(--radius-md);
  padding: 8px 10px;
  font-size: var(--font-size-lg);
  font-weight: 700;
  color: var(--color-gray-800);
}
.auto-id-input :deep(.el-input__wrapper) {
  background: var(--color-gray-50);
}
.auto-id-input :deep(.el-input__inner) {
  font-size: var(--font-size-lg);
  font-weight: 700;
  color: var(--color-gray-800);
}
.batch-row-actions,
.batch-save,
.attachment-upload-row {
  margin-top: var(--space-2);
}
.contract-drop-upload :deep(.el-upload) {
  width: 100%;
}
.contract-drop-upload :deep(.el-upload-dragger) {
  width: 100%;
  padding: 18px 12px;
  border-radius: var(--radius-md);
}
.contract-drop-upload :deep(.el-icon--upload) {
  font-size: 28px;
  margin-bottom: 4px;
}
.contract-drop-upload.compact :deep(.el-upload-dragger) {
  padding: 10px 12px;
}
.contract-drop-upload.compact :deep(.el-icon--upload) {
  font-size: 20px;
  margin-bottom: 2px;
}
.contract-drop-upload.compact :deep(.el-upload__text) {
  font-size: var(--font-size-sm);
}
.contract-drop-upload :deep(.el-upload__tip) {
  color: var(--color-gray-500);
}
.ops-label {
  font-size: var(--font-size-sm);
  color: var(--color-gray-900);
  margin-bottom: 4px;
}
.ops-hint,
.tip {
  color: var(--color-gray-500);
  font-size: var(--font-size-sm);
}
.form-table :deep(.el-table__cell) {
  padding: 10px 8px !important;
}
.form-table :deep(.cell) {
  padding: 0 4px !important;
}
.contract-workspace {
  margin-top: var(--space-3);
}
.tabs-row {
  display: flex;
  gap: 10px;
  border-bottom: 1px solid var(--color-gray-200);
}
.status-tab {
  min-width: 132px;
  border: 1px solid var(--color-gray-200);
  border-bottom: none;
  background: var(--color-gray-50);
  color: var(--color-gray-700);
  border-radius: var(--radius-md) var(--radius-md) 0 0;
  padding: 10px 14px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  cursor: pointer;
  font-weight: 700;
}
.status-tab.active {
  background: #fff;
  color: var(--color-primary-700);
  border-color: var(--color-primary-300);
}
.status-tab strong {
  font-size: 12px;
  background: var(--color-gray-200);
  border-radius: 999px;
  padding: 2px 8px;
}
.status-tab.active strong {
  background: var(--color-primary-100);
}
.workspace-grid {
  min-height: 620px;
  display: grid;
  grid-template-columns: minmax(320px, 380px) minmax(0, 1fr);
  gap: var(--space-3);
  padding-top: var(--space-3);
}
.contract-list-panel,
.contract-detail-panel {
  border: 1px solid var(--color-gray-200);
  border-radius: var(--radius-md);
  background: #fff;
}
.contract-list-panel {
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.list-tools {
  padding: var(--space-2);
  border-bottom: 1px solid var(--color-gray-100);
}
.list-filter-control {
  width: 100%;
  margin-top: 8px;
}
.month-list {
  padding: var(--space-2);
  overflow: auto;
  background: linear-gradient(180deg, #f8fbff 0%, #ffffff 160px);
}
.month-list :deep(.el-collapse) {
  border-top: none;
  border-bottom: none;
}
.month-list :deep(.el-collapse-item) {
  margin-bottom: 8px;
  overflow: hidden;
  border: 1px solid #d7e7ff;
  border-left: 4px solid #2f80ed;
  border-radius: var(--radius-md);
  background: #ffffff;
  box-shadow: 0 1px 3px rgba(15, 56, 105, 0.08);
}
.month-list :deep(.el-collapse-item__header) {
  height: 46px;
  padding: 0 12px;
  border-bottom: none;
  background: #eef6ff;
  color: #0f3767;
}
.month-list :deep(.el-collapse-item__wrap) {
  border-bottom: none;
  background: #fbfdff;
}
.month-list :deep(.el-collapse-item__content) {
  padding: 8px;
}
.month-title {
  width: 100%;
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 700;
}
.month-title em {
  color: #315f96;
  font-style: normal;
  font-size: 12px;
  font-weight: 700;
}
.contract-card {
  width: 100%;
  border: 1px solid #cfdbea;
  border-left: 4px solid #8fb5e8;
  background: #ffffff;
  border-radius: var(--radius-md);
  padding: 10px;
  margin-bottom: 8px;
  text-align: left;
  cursor: pointer;
  transition: border-color 0.16s ease, box-shadow 0.16s ease, background 0.16s ease, transform 0.16s ease;
}
.contract-card:hover {
  border-color: #4d96f0;
  background: #f6faff;
  box-shadow: 0 4px 14px rgba(31, 103, 191, 0.16);
}
.contract-card.active {
  border-color: #0d78df;
  border-left-color: #008be8;
  background: #eef7ff;
  box-shadow: 0 0 0 2px rgba(0, 139, 232, 0.14), 0 8px 22px rgba(0, 99, 179, 0.18);
  transform: translateX(2px);
}
.contract-card-head,
.contract-meta,
.attachment-header,
.attachment-item,
.actions-section,
.action-buttons {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}
.action-buttons {
  justify-content: flex-end;
  flex-wrap: wrap;
  flex-shrink: 0;
}
.contract-card-head strong {
  color: var(--color-gray-900);
}
.contract-customer {
  margin-top: 6px;
  color: var(--color-gray-700);
  font-weight: 600;
}
.contract-meta {
  margin-top: 6px;
  color: var(--color-gray-500);
  font-size: var(--font-size-sm);
}
.contract-meta span:first-child {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.contract-detail-panel {
  padding: var(--space-3);
  min-width: 0;
}
.detail-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-2);
}
.detail-kicker {
  color: var(--color-gray-500);
  font-size: var(--font-size-sm);
  font-weight: 700;
}
.detail-head h2 {
  margin: 2px 0 0;
  color: var(--color-gray-900);
  font-size: 26px;
}
.info-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin-top: var(--space-3);
}
.info-grid div {
  border: 1px solid var(--color-gray-200);
  border-radius: var(--radius-md);
  padding: 10px 12px;
  min-width: 0;
}
.info-grid span {
  display: block;
  color: var(--color-gray-500);
  font-size: 12px;
}
.info-grid strong {
  display: block;
  margin-top: 4px;
  color: var(--color-gray-900);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.contract-edit-form {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.edit-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}
.impact-dialog-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.impact-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  color: var(--color-gray-600);
  font-size: var(--font-size-sm);
}
.impact-stats span {
  border: 1px solid var(--color-gray-200);
  border-radius: var(--radius-sm);
  padding: 4px 8px;
  background: var(--color-gray-50);
}
.supplement-title {
  margin-top: 4px;
}
.impact-empty {
  color: var(--color-gray-500);
  font-size: var(--font-size-sm);
  padding: 8px 0;
}
.impact-error {
  margin-top: 4px;
}
.detail-section {
  margin-top: var(--space-3);
}
.section-title {
  color: var(--color-gray-900);
  font-weight: 800;
  margin-bottom: 8px;
}
.attachment-title {
  font-size: var(--font-size-base);
  font-weight: 700;
  color: var(--color-gray-800);
}
.attachment-loading {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--color-gray-500);
  font-size: var(--font-size-sm);
  padding: var(--space-2) 0;
}
.attachment-empty {
  color: var(--color-gray-400);
  font-size: var(--font-size-sm);
  padding: var(--space-2) 0;
}
.attachment-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.attachment-item {
  padding: 8px 12px;
  background: var(--color-gray-50);
  border: 1px solid var(--border-color-light);
  border-radius: var(--radius-md);
}
.attachment-info {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.attachment-name {
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--color-gray-800);
  word-break: break-all;
}
.attachment-meta {
  font-size: 12px;
  color: var(--color-gray-400);
  white-space: nowrap;
  flex-shrink: 0;
}
.attachment-actions {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
}
.preview-loading {
  min-height: 420px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: var(--color-gray-500);
}
.preview-frame {
  width: 100%;
  height: min(72vh, 760px);
  border: 1px solid var(--color-gray-200);
  border-radius: var(--radius-md);
  background: #fff;
}
.preview-empty {
  min-height: 300px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: var(--color-gray-600);
  text-align: center;
}
.preview-empty-title {
  color: var(--color-gray-900);
  font-size: var(--font-size-lg);
  font-weight: 800;
}
.preview-empty-text {
  max-width: 520px;
  line-height: 1.6;
}
.attachment-preview-dialog :deep(.el-dialog__body) {
  padding-top: 8px;
}
.actions-section {
  border-top: 1px solid var(--color-gray-200);
  padding-top: var(--space-3);
}
.save-mode-body {
  display: grid;
  gap: 8px;
}
.save-mode-sub {
  color: var(--color-gray-600);
  font-size: var(--font-size-sm);
}
.save-mode-hint {
  color: var(--color-danger);
  font-size: var(--font-size-sm);
}
.convert-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}
.save-mode-section {
  margin-top: 16px;
}
.save-mode-blocked {
  color: var(--color-danger);
  font-size: var(--font-size-sm);
  margin-top: 6px;
}
.dealer-import-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}
.dealer-import-toolbar .el-input {
  flex: 1;
}
.dealer-import-tip {
  margin-top: 10px;
  color: var(--color-gray-500);
  font-size: var(--font-size-sm);
}

@media (max-width: 960px) {
  .batch-grid,
  .convert-grid,
  .workspace-grid,
  .info-grid {
    grid-template-columns: 1fr;
  }
  .tabs-row {
    overflow-x: auto;
  }
  .status-tab {
    flex: 1 0 120px;
  }
}
</style>
