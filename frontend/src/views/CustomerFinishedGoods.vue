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
      ><el-button @click="openPendingUploads"
        >交付信息待处理<template v-if="pendingUploadCount">（{{ pendingUploadCount }}）</template></el-button
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
      /><el-table-column label="交付信息" min-width="150">
        <template #default="{ row }"
          ><el-tag :type="row.delivery_info_uploaded ? 'success' : 'info'">{{
            row.delivery_info_uploaded ? "已上传" : "未上传"
          }}</el-tag>
          <div v-if="row.delivery_info_file_name" class="contract-return-file">
            {{ row.delivery_info_file_name }}
          </div>
        </template>
      </el-table-column><el-table-column prop="Location_Code" label="库位" /><el-table-column
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
      <el-alert
        v-if="mode === 'contract' && contractRow"
        :title="
          contractRow.delivery_info_uploaded
            ? `交付信息：已上传${contractRow.delivery_info_file_name ? '（' + contractRow.delivery_info_file_name + '）' : ''}`
            : '交付信息：未上传（东莞回传订货合同）'
        "
        :type="contractRow.delivery_info_uploaded ? 'success' : 'warning'"
        :closable="false"
        show-icon
        class="delivery-info-alert"
      />
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

    <el-dialog v-model="pendingUploadsVisible" title="交付信息上传（待处理）" width="980px">
      <el-alert
        title="小程序只上传附件。请打开附件预览，根据合同填写购货单位/地址/机台号，并手动选择机台；系统只把合同关联到所选机台，不自动发货。"
        type="info"
        :closable="false"
        show-icon
        class="delivery-info-alert"
      />
      <el-table
        :data="pendingUploads"
        border
        stripe
        v-loading="pendingUploadsLoading"
        max-height="420"
      >
        <el-table-column prop="id" label="#" width="70" />
        <el-table-column prop="file_name" label="附件" min-width="220" />
        <el-table-column prop="uploader" label="上传人" width="130" />
        <el-table-column prop="uploaded_at" label="上传时间" width="170" />
        <el-table-column label="操作" width="220">
          <template #default="{ row }">
            <el-button link @click="previewPendingUpload(row)">预览附件</el-button>
            <el-button link @click="downloadPendingUpload(row)">下载</el-button>
            <el-button link type="primary" @click="openProcessUpload(row)">处理</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!pendingUploadsLoading && !pendingUploads.length" description="暂无待处理的交付信息" />
      <template #footer>
        <el-button @click="pendingUploadsVisible = false">关闭</el-button>
        <el-button :loading="pendingUploadsLoading" @click="loadPendingUploads">刷新</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="processVisible" title="处理交付信息：查看合同、填写信息并选择机台" width="980px">
      <el-descriptions v-if="processUpload" :column="2" border size="small" class="contract-info">
        <el-descriptions-item label="附件">{{ processUpload.file_name }}</el-descriptions-item>
        <el-descriptions-item label="上传人">{{ processUpload.uploader || "—" }}</el-descriptions-item>
      </el-descriptions>
      <div class="toolbar process-search">
        <el-button @click="previewPendingUpload(processUpload)">打开附件预览</el-button>
        <el-button @click="downloadPendingUpload(processUpload)">下载附件</el-button>
      </div>
      <el-form label-width="110px" class="action-form">
        <el-form-item label="购货单位">
          <el-input v-model="processBuyerName" placeholder="根据合同预览填写购货单位名称" />
        </el-form-item>
        <el-form-item label="购货单位地址">
          <el-input v-model="processBuyerAddress" placeholder="根据合同预览填写地址" />
        </el-form-item>
        <el-form-item label="合同机台号">
          <el-input v-model="processMachineNos" placeholder="根据合同预览填写机台号，多个用逗号分隔" />
        </el-form-item>
      </el-form>
      <el-alert
        title="请核对附件后手动勾选机台。所选机台必须属于同一个销售订单；处理只关联合同，不自动确认出货。"
        type="warning"
        :closable="false"
        show-icon
      />
      <div class="toolbar process-search">
        <el-input
          v-model="machineKeyword"
          placeholder="按流水号 / 客户 / 订单号搜索机台"
          clearable
          @keyup.enter="searchProcessMachines"
        />
        <el-button type="primary" :loading="machineSearching" @click="searchProcessMachines"
          >查询机台</el-button
        >
      </div>
      <el-table
        :data="machineCandidates"
        border
        stripe
        max-height="320"
        @selection-change="selectedMachines = $event"
      >
        <el-table-column type="selection" width="48" />
        <el-table-column prop="流水号" label="流水号" min-width="120" />
        <el-table-column prop="机型" label="机型" min-width="120" />
        <el-table-column prop="客户" label="客户" min-width="150" />
        <el-table-column prop="占用订单号" label="订单号" min-width="130" />
        <el-table-column prop="状态" label="机台状态" min-width="130" />
      </el-table>
      <p class="hint">已选 {{ selectedMachines.length }} 台机台</p>
      <template #footer>
        <el-button @click="clearProcessSelection">取消</el-button>
        <el-button
          type="primary"
          :loading="processBusy"
          :disabled="!selectedMachines.length"
          @click="confirmProcessUpload"
          >确认处理</el-button
        >
      </template>
    </el-dialog>

    <el-dialog
      v-model="previewVisible"
      :title="`预览：${previewFileName}`"
      width="900px"
      @closed="closePreview"
    >
      <iframe v-if="isPreviewPdf" :src="previewUrl" class="delivery-info-preview" />
      <img v-else :src="previewUrl" class="delivery-info-preview-image" />
    </el-dialog>
  </div>
</template>
<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { apiDownloadBlob, apiGet, apiGetBlobUrl, apiPost, getApiErrorMessage } from "../utils/request";
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
// 交付信息上传（待处理）：V8 操作人员查看附件后手动选择机台处理。
const pendingUploads = ref<any[]>([]);
const pendingUploadsLoading = ref(false);
const pendingUploadsVisible = ref(false);
const pendingUploadCount = ref(0);
const processVisible = ref(false);
const processUpload = ref<any>(null);
const processBusy = ref(false);
const machineKeyword = ref("");
const machineSearching = ref(false);
const machineCandidates = ref<any[]>([]);
const selectedMachines = ref<any[]>([]);
// 附件在线预览（操作人员对照合同填写信息、选择机台）。
const previewVisible = ref(false);
const previewUrl = ref("");
const previewFileName = ref("");
const isPreviewPdf = computed(() => /\.pdf$/i.test(previewFileName.value));
// 处理时由操作人员根据合同预览填写。
const processBuyerName = ref("");
const processBuyerAddress = ref("");
const processMachineNos = ref("");
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
        pending.map(row => `订单 ${row.order_no}：审批已发起，等待审批人处理`).join("\n") +
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
    if ((workflowResponse as any)?.approval_pending) { ElMessage.info((workflowResponse as any).message); window.dispatchEvent(new Event('workflow-pending-updated')); return }

    ElMessage.success("确认出货成功");
    fileVisible.value = false;
    await load();
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error) || "确认出货失败，请刷新后重试");
  } finally {
    shippingBusy.value = false;
  }
};
const loadPendingUploads = async () => {
  pendingUploadsLoading.value = true;
  try {
    const response = await apiGet<any>("/inventory/delivery-info-uploads", {
      params: { status: "pending", limit: 100 },
    });
    pendingUploads.value = response.data || [];
    pendingUploadCount.value = pendingUploads.value.length;
  } catch (error) {
    pendingUploadCount.value = 0;
  } finally {
    pendingUploadsLoading.value = false;
  }
};
const openPendingUploads = () => {
  pendingUploadsVisible.value = true;
  void loadPendingUploads();
};
const downloadPendingUpload = async (row: any) => {
  try {
    await apiDownloadBlob(
      `/inventory/delivery-info-uploads/${row.id}/file`,
      row.file_name || "交付信息附件",
    );
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error) || "附件下载失败");
  }
};
/** 在线预览合同附件：操作人员对照合同填写购货单位/地址/机台号。 */
const previewPendingUpload = async (row: any) => {
  try {
    if (previewUrl.value) URL.revokeObjectURL(previewUrl.value);
    previewUrl.value = await apiGetBlobUrl(
      `/inventory/delivery-info-uploads/${row.id}/file`,
    );
    previewFileName.value = row.file_name || "交付信息附件";
    previewVisible.value = true;
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error) || "附件预览失败");
  }
};
const closePreview = () => {
  previewVisible.value = false;
  if (previewUrl.value) {
    URL.revokeObjectURL(previewUrl.value);
    previewUrl.value = "";
  }
};
const clearProcessSelection = () => {
  processUpload.value = null;
  processVisible.value = false;
  processBusy.value = false;
  machineKeyword.value = "";
  machineCandidates.value = [];
  selectedMachines.value = [];
  processBuyerName.value = "";
  processBuyerAddress.value = "";
  processMachineNos.value = "";
};
const openProcessUpload = (row: any) => {
  processUpload.value = row;
  processVisible.value = true;
  processBusy.value = false;
  processBuyerName.value = String(row.buyer_name || "");
  processBuyerAddress.value = String(row.buyer_address || "");
  processMachineNos.value = String(row.machine_nos || "");
  const firstMachineNo = processMachineNos.value
    .split(/[、,，\s/]+/)
    .find((item) => item.trim());
  machineKeyword.value = firstMachineNo ? firstMachineNo.trim() : "";
  machineCandidates.value = [];
  selectedMachines.value = [];
};
const searchProcessMachines = async () => {
  machineSearching.value = true;
  try {
    const response = await apiGet<any>("/inventory/customer-finished-goods", {
      params: { customer: "东莞", keyword: machineKeyword.value, limit: 100 },
    });
    machineCandidates.value = response.data || [];
    selectedMachines.value = [];
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error) || "机台查询失败");
    machineCandidates.value = [];
  } finally {
    machineSearching.value = false;
  }
};
const confirmProcessUpload = async () => {
  if (!processUpload.value || !selectedMachines.value.length) {
    ElMessage.warning("请先选择要处理的机台");
    return;
  }
  const orders = [
    ...new Set(selectedMachines.value.map((row) => String(row["占用订单号"] || "").trim())),
  ].filter(Boolean);
  if (orders.length !== 1) {
    ElMessage.warning("所选机台必须属于同一个销售订单");
    return;
  }
  processBusy.value = true;
  try {
    await apiPost(`/inventory/delivery-info-uploads/${processUpload.value.id}/process`, {
      serial_nos: selectedMachines.value.map((row) => String(row["流水号"] || "").trim()),
      buyer_name: processBuyerName.value.trim(),
      buyer_address: processBuyerAddress.value.trim(),
      machine_nos: processMachineNos.value.trim(),
    });
    ElMessage.success("交付信息已处理，合同已关联到所选机台");
    clearProcessSelection();
    await Promise.all([load(), loadPendingUploads()]);
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error) || "处理失败，请重试");
  } finally {
    processBusy.value = false;
  }
};
onMounted(() => {
  void load();
  void loadPendingUploads();
});
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
.delivery-info-alert { margin-bottom: 16px; }
.process-search { margin-top: 14px; }
.delivery-info-preview {
  width: 100%;
  height: 70vh;
  border: 0;
}
.delivery-info-preview-image {
  display: block;
  width: 100%;
  max-height: 70vh;
  object-fit: contain;
}
.contract-return-file { margin-top: 4px; color: #909399; font-size: 12px; word-break: break-all; }
.contract-section-title { margin: 16px 0 8px; font-size: 14px; }
.upload-scope { width: 180px; margin: 12px 0 4px; }
</style>


