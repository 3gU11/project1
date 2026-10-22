<template>
  <div class="page">
    <h1>🏢 客户成品管理</h1>
    <h2>东莞机台</h2>
    <p class="hint">
      默认展示全部状态的东莞现货机台，实际状态和库位以各行显示为准。订单状态跟随关联的原销售订单。
    </p>
    <div class="toolbar">
      <el-input
        v-model="keyword"
        placeholder="搜索流水号、机型、订单或合同"
        clearable
        @keyup.enter="searchMachines"
        @clear="searchMachines"
      />
      <el-select
        v-model="machineStatus"
        placeholder="全部机台状态"
        clearable
        style="min-width: 180px"
        @change="searchMachines"
      >
        <el-option
          v-for="status in machineStatuses"
          :key="status"
          :label="status"
          :value="status"
        />
      </el-select>
      <el-button type="primary" :loading="loading" @click="searchMachines"
        >查询 / 刷新</el-button
      ><el-button
        :disabled="!selected.length"
        @click="openOrderActions(selected)"
        >批量订单规划</el-button
      >
    </div>
    <el-alert
      v-if="machineError"
      :title="machineError"
      type="error"
      :closable="false"
      show-icon
    /><el-table
      class="stock-machines-table"
      :data="rows"
      border
      stripe
      v-loading="loading"
      @selection-change="selected = $event"
      ><el-table-column type="selection" width="48" /><el-table-column
        prop="流水号"
        label="流水号"
      /><el-table-column prop="机型" label="机型" /><el-table-column
        prop="客户"
        label="客户"
      /><el-table-column prop="占用订单号" label="订单号" /><el-table-column
        prop="合同号"
        label="合同号"
      /><el-table-column prop="Location_Code" label="库位" /><el-table-column
        label="订单状态"
        min-width="130"
      >
        <template #default="{ row }"
          ><el-tag
            :type="row.order_status_label === '已完成' ? 'success' : 'primary'"
            >{{ row.order_status_label || "状态暂不可用" }}</el-tag
          ></template
        >
      </el-table-column>
      <el-table-column
        prop="状态"
        label="机台状态"
        min-width="150"
      /><el-table-column label="操作" width="270"
        ><template #default="{ row }"
          ><el-button link type="primary" @click="openOrderActions([row])"
            >订单规划</el-button
          ><el-button link @click="openContract(row)">确认出货</el-button
          ><el-button link @click="openArchive(row)"
            >机台档案</el-button
          ></template
        ></el-table-column
      ></el-table
    >
    <el-pagination
      v-model:current-page="machinePage"
      :page-size="machinePageSize"
      :total="machineTotal"
      layout="total, prev, pager, next"
      @current-change="load"
    />
    <el-dialog
      v-model="actionVisible"
      title="原销售订单规划"
      width="800px"
      :close-on-click-modal="!actionBusy"
      :close-on-press-escape="!actionBusy"
      :show-close="!actionBusy"
    >
      <el-alert
        title="按原订单执行，不只处理选中的机台。同一订单只处理一次；确认发货将处理该订单全部待发货现货机台。"
        type="info"
        :closable="false"
      />
      <el-form label-width="90px" class="action-form">
        <el-form-item label="操作"
          ><el-radio-group
            v-model="orderAction"
            :disabled="actionBusy"
            @change="clearActionPreview"
          >
            <el-radio-button value="mark_shipped">已发货</el-radio-button>
            <el-radio-button value="mark_in_stock">撤销发货</el-radio-button>
          </el-radio-group></el-form-item
        >
        <el-form-item label="备注"
          ><el-input
            v-model="actionRemark"
            type="textarea"
            maxlength="1000"
            show-word-limit
            :disabled="actionBusy"
        /></el-form-item>
      </el-form>
      <el-button
        :loading="previewBusy"
        :disabled="actionBusy"
        @click="previewActions"
        >预览影响范围</el-button
      >
      <el-alert
        v-if="actionError"
        :title="actionError"
        type="error"
        :closable="false"
      />
      <el-table :data="actionPreview" border class="action-preview">
        <el-table-column prop="order_no" label="原订单号" min-width="180" />
        <el-table-column prop="order_status" label="当前状态" width="110" />
        <el-table-column prop="machine_count" label="涉及台数" width="90" />
        <el-table-column label="涉及流水号" min-width="180"
          ><template #default="{ row }">{{
            row.serial_nos.join("、") || "—"
          }}</template></el-table-column
        >
        <el-table-column label="校验结果" min-width="180"
          ><template #default="{ row }">{{
            row.can_execute ? "可执行" : row.reason
          }}</template></el-table-column
        >
      </el-table>
      <el-table v-if="actionResults.length" :data="actionResults" border>
        <el-table-column prop="order_no" label="原订单号" />
        <el-table-column label="处理结果"
          ><template #default="{ row }"
            >{{ row.success ? (["审批中", "待审批"].includes(row.workflow_status || "") ? "已提交审批" : "已处理") : "失败" }}：{{ row.message }}
            {{ row.warning || "" }}</template
          ></el-table-column
        >
      </el-table>
      <template #footer
        ><el-button :disabled="actionBusy" @click="actionVisible = false"
          >关闭</el-button
        ><el-button
          type="primary"
          :loading="actionBusy"
          :disabled="!canExecuteActions"
          @click="executeActions"
          >确认执行</el-button
        ></template
      > </el-dialog
    ><el-dialog v-model="fileVisible" :title="fileTitle" width="700px"
      ><el-descriptions v-if="mode === 'contract' && contractRow" :column="2" border size="small" class="contract-info">
        <el-descriptions-item label="流水号">{{ contractRow["流水号"] }}</el-descriptions-item>
        <el-descriptions-item label="机型">{{ contractRow["机型"] }}</el-descriptions-item>
        <el-descriptions-item label="原销售订单">{{ contractRow["占用订单号"] || "—" }}</el-descriptions-item>
        <el-descriptions-item label="当前状态">{{ contractRow["状态"] || "—" }}</el-descriptions-item>
      </el-descriptions>
      <template v-if="mode === 'contract'">
        <h3 class="contract-section-title">工厂发往东莞仓库总合同</h3>
        <div v-for="f in orderFiles" :key="`order-${f.file_name}`" class="file">{{ f.file_name }}</div>
        <el-empty v-if="!orderFiles.length" description="暂无订单总合同附件" />
        <h3 class="contract-section-title">当前机台东莞出货合同</h3>
        <div v-for="f in machineFiles" :key="`machine-${f.file_name}`" class="file">{{ f.file_name }}</div>
        <el-empty v-if="!machineFiles.length" description="暂无当前机台合同附件" />
        <el-select v-model="uploadScope" class="upload-scope" placeholder="选择附件归属">
          <el-option label="订单总合同" value="order" />
          <el-option label="当前机台小合同" value="machine" />
        </el-select>
      </template>
      ><el-upload
        drag
        :auto-upload="false"
        :show-file-list="false"
        :on-change="uploadFile"
        ><div>拖入文件或点击上传</div></el-upload
      >
      <div v-for="f in mode === 'contract' ? [] : files" :key="f.file_name" class="file">
        {{ f.file_name }}
      </div>
      <el-empty v-if="mode !== 'contract' && !files.length" description="暂无附件" />
      <template #footer v-if="mode === 'contract'"><el-button @click="fileVisible = false">关闭</el-button><el-button type="primary" :loading="shippingBusy" @click="confirmCustomerShipping">确认出货</el-button></template>
    /></el-dialog>
  </div>
</template>
<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { apiGet, apiPost, getApiErrorMessage } from "../utils/request";
const keyword = ref(""),
  rows = ref<any[]>([]),
  selected = ref<any[]>([]),
  loading = ref(false),
  fileVisible = ref(false),
  fileTitle = ref(""),
  files = ref<any[]>([]),
  orderFiles = ref<any[]>([]),
  machineFiles = ref<any[]>([]),
  mode = ref(""),
  fileRow = ref<any>(),
  contractRow = ref<any>(),
  shippingBusy = ref(false);
const uploadScope = ref<"order" | "machine">("machine");
const machineStatus = ref("");
const machineStatuses = ref<string[]>([]);
const machinePage = ref(1);
const machinePageSize = 50;
const machineTotal = ref(0);
const machineError = ref("");
let machineRequest = 0;
const load = async () => {
  const requestId = ++machineRequest;
  loading.value = true;
  machineError.value = "";
  selected.value = [];
  try {
    const response = await apiGet<{
      data: any[];
      total: number;
      statuses: string[];
    }>("/inventory/customer-finished-goods", {
      params: {
        customer: "东莞",
        keyword: keyword.value,
        machine_status: machineStatus.value,
        skip: (machinePage.value - 1) * machinePageSize,
        limit: machinePageSize,
      },
    });
    if (requestId !== machineRequest) return;
    rows.value = response.data || [];
    machineTotal.value = response.total || 0;
    machineStatuses.value = response.statuses || [];
  } catch (error) {
    if (requestId !== machineRequest) return;
    rows.value = [];
    machineTotal.value = 0;
    machineError.value =
      getApiErrorMessage(error) || "东莞机台加载失败，请重试";
  } finally {
    if (requestId === machineRequest) loading.value = false;
  }
};
const searchMachines = () => {
  machinePage.value = 1;
  void load();
};

type OrderAction = "mark_shipped" | "mark_in_stock";
type ActionPreview = {
  order_no: string;
  order_status: string;
  machine_count: number;
  serial_nos: string[];
  can_execute: boolean;
  reason: string;
  fingerprint: string;
};
type ActionResult = {
  workflow_status?: string;
  instance_no?: string;
  order_no: string;
  success: boolean;
  message: string;
  warning?: string;
};
const actionVisible = ref(false);
const orderAction = ref<OrderAction>("mark_shipped");
const actionRemark = ref("");
const actionSerials = ref<string[]>([]);
const actionPreview = ref<ActionPreview[]>([]);
const actionResults = ref<ActionResult[]>([]);
const actionBusy = ref(false);
const previewBusy = ref(false);
const actionError = ref("");
let previewRequest = 0;
const canExecuteActions = computed(
  () =>
    !actionBusy.value &&
    !previewBusy.value &&
    actionPreview.value.length > 0 &&
    actionPreview.value.every((row) => row.can_execute),
);
const clearActionPreview = () => {
  ++previewRequest;
  previewBusy.value = false;
  actionPreview.value = [];
  actionResults.value = [];
  actionError.value = "";
};
const openOrderActions = (machines: any[]) => {
  if (machines.some((row) => !String(row["占用订单号"] || "").trim())) {
    ElMessage.warning("存在未关联原销售订单的机台，请调整选择");
    return;
  }
  clearActionPreview();
  actionSerials.value = [
    ...new Set(machines.map((row) => String(row["流水号"])).filter(Boolean)),
  ];
  orderAction.value = "mark_shipped";
  actionRemark.value = "";
  actionVisible.value = true;
};
const previewActions = async () => {
  const id = ++previewRequest;
  actionPreview.value = [];
  actionResults.value = [];
  actionError.value = "";
  previewBusy.value = true;
  try {
    const response = await apiPost<{ data: ActionPreview[] }>(
      "/inventory/customer-order-actions/preview",
      { serial_nos: actionSerials.value, action: orderAction.value },
    );
    if (id === previewRequest) actionPreview.value = response.data;
  } catch (error) {
    if (id === previewRequest)
      actionError.value =
        getApiErrorMessage(error) || "预览失败，请检查操作权限或稍后重试";
  } finally {
    if (id === previewRequest) previewBusy.value = false;
  }
};
const executeActions = async () => {
  if (!canExecuteActions.value) return;
  actionBusy.value = true;
  try {
    await ElMessageBox.confirm(
      `将对 ${actionPreview.value.length} 张原销售订单执行“${orderAction.value === "mark_shipped" ? "已发货" : "撤销发货"}”，涉及范围以上方预览为准。是否继续？`,
      "确认原订单规划",
      {
        type: "warning",
        confirmButtonText: "确认执行",
        cancelButtonText: "取消",
      },
    );
    const response = await apiPost<{ data: ActionResult[] }>(
      "/inventory/customer-order-actions/execute",
      {
        serial_nos: actionSerials.value,
        action: orderAction.value,
        remark: actionRemark.value,
        expected: Object.fromEntries(
          actionPreview.value.map((row) => [row.order_no, row.fingerprint]),
        ),
      },
      { timeout: 120000 },
    );
    actionResults.value = response.data;
    actionPreview.value = [];
    const pending = response.data.filter(row => row.success && ["审批中", "待审批"].includes(row.workflow_status || ""));
    const failed = response.data.filter(row => !row.success);
    if (pending.length) {
      void ElMessageBox.alert(
        pending.map(row => `订单 ${row.order_no}：审批已发起，等待审批人处理。流程编号：${row.instance_no || "—"}`).join("\n") +
          "\n审批通过后系统会自动执行，审批前订单状态保持不变。" +
          (failed.length ? `\n另有 ${failed.length} 张订单提交失败，请查看处理结果。` : ""),
        "审批已发起",
        { type: "success", confirmButtonText: "知道了" },
      ).catch(() => {});
    } else if (failed.length) {
      ElMessage.error("部分操作失败，请查看处理结果");
    } else {
      ElMessage.success("操作已执行，请查看处理结果");
    }
    await load();
  } catch (error) {
    if (error !== "cancel" && error !== "close") {
      actionError.value =
        getApiErrorMessage(error) ||
        "执行未确认成功，请刷新核实订单进度后重新预览";
      actionPreview.value = [];
      await load();
    }
  } finally {
    actionBusy.value = false;
  }
};

const openContract = async (r: any) => {
  mode.value = "contract";
  fileRow.value = r;
  contractRow.value = r;
  uploadScope.value = "machine";
  fileTitle.value = "确认出货：" + r["流水号"];
  const orderContract = String(r["合同号"] || r["占用订单号"] || "").trim();
  const [orderResult, machineResult] = await Promise.all([
    orderContract ? apiGet<any>("/planning/contract/" + encodeURIComponent(orderContract) + "/files") : Promise.resolve({ data: [] }),
    apiGet<any>("/planning/contract/" + encodeURIComponent(machineContractId(r)) + "/files"),
  ]);
  orderFiles.value = orderResult.data || [];
  machineFiles.value = machineResult.data || [];
  files.value = [];
  fileVisible.value = true;
};
const machineContractId = (r: any) => `DG-SHIPPING-${String(r["占用订单号"] || "ORDER").trim()}-${String(r["流水号"] || "MACHINE").trim()}`;
const openArchive = async (r: any) => {
  mode.value = "archive";
  fileRow.value = r;
  fileTitle.value = "机台档案：" + r["流水号"];
  const x: any = await apiGet(
    "/inventory/machine-archive/" + encodeURIComponent(r["流水号"]) + "/files",
  );
  files.value = x.data || [];
  fileVisible.value = true;
};
const uploadFile = async (u: any) => {
  const fd = new FormData();
  fd.append("file", u.raw);
  if (mode.value === "contract")
    await apiPost(
      "/planning/contract/" +
        encodeURIComponent(uploadScope.value === "order"
          ? String(fileRow.value["合同号"] || fileRow.value["占用订单号"] || "ORDER").trim()
          : machineContractId(fileRow.value)) +
        "/files",
      fd,
      {
        params: {
          customer_name: "东莞",
          uploader_name: "Web",
        },
        headers: { "Content-Type": "multipart/form-data" },
      },
    );
  else
    await apiPost(
      "/inventory/machine-archive/" +
        encodeURIComponent(fileRow.value["流水号"]) +
        "/upload",
      fd,
      { headers: { "Content-Type": "multipart/form-data" } },
    );
  ElMessage.success("附件上传成功");
  mode.value === "contract"
    ? openContract(fileRow.value)
    : openArchive(fileRow.value);
};
const confirmCustomerShipping = async () => {
  const row = contractRow.value;
  if (!row || shippingBusy.value) return;
  const serialNo = String(row["流水号"] || "").trim();
  const orderNo = String(row["占用订单号"] || "").trim();
  if (!serialNo || !orderNo) {
    ElMessage.error("机台缺少流水号或原销售订单，无法确认出货");
    return;
  }
  shippingBusy.value = true;
  try {
    const workflowResponse = await apiPost("/inventory/shipping/confirm", { serial_nos: [serialNo], expected_order_no: orderNo }, { timeout: 120000 });
    if ((workflowResponse as any)?.approval_pending) { ElMessage.info((workflowResponse as any).message + '（' + (workflowResponse as any).instance_no + '）'); window.dispatchEvent(new Event('workflow-pending-updated')); return }
    
    ElMessage.success("确认出货成功");
    fileVisible.value = false;
    await load();
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error) || "确认出货失败，请刷新后重试");
  } finally {
    shippingBusy.value = false;
  }
};
onMounted(load);
</script>
<style scoped>
.page {
  padding: 24px;
}
.action-form {
  margin-top: 16px;
}
.action-preview {
  margin: 16px 0;
}
.hint {
  color: #606266;
  line-height: 1.6;
}
.el-pagination {
  margin-top: 16px;
}
.toolbar {
  display: flex;
  gap: 12px;
  margin: 16px 0;
}
.file {
  padding: 8px;
  border-bottom: 1px solid #eee;
}
.contract-info { margin-bottom: 16px; }
.contract-section-title { margin: 16px 0 8px; font-size: 14px; }
.upload-scope { width: 180px; margin: 12px 0 4px; }
</style>
