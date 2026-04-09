<template>
  <div class="archive-page">
    <div class="head-row">
      <el-button class="back-btn" size="small" @click="goBack">⬅ 返回</el-button>
      <h1 class="title">📁 机台档案</h1>
    </div>

    <el-alert :closable="false" type="info" title="💡 管理每台机器的电子档案（照片/文档），文件存储在物理文件夹中。" />

    <div class="query-row">
      <div class="field-label">🔍 搜索/选择流水号</div>
      <el-select v-model="selectedSerial" filterable clearable placeholder="请选择流水号" style="width: 320px" @change="onSerialChange">
        <el-option v-for="sn in serials" :key="sn" :label="sn" :value="sn" />
      </el-select>
      <div v-if="selectedSerial" class="machine-meta">
        <div class="sn-title">{{ selectedSerial }}</div>
        <div class="sn-sub">机型: {{ selectedMachine?.model || '-' }} | 状态: {{ selectedMachine?.status || '-' }}</div>
      </div>
    </div>

    <el-divider />

    <template v-if="selectedSerial">
      <div class="empty-bar">{{ imageFiles.length > 0 ? `📷 现有图片存档（${imageFiles.length} 张）` : '暂无图片存档' }}</div>

      <el-divider />

      <h3 class="section-title">📤 上传机台档案 (必填项)</h3>
      <el-alert :closable="false" type="info" title="请填入对应部件编号，并上传照片。系统将自动使用编号重命名文件。" />

      <div class="upload-card">
        <el-row :gutter="10">
          <el-col :span="8">
            <div class="small-title">🟢 手轮号</div>
            <el-input v-model="partInput.wheelNo" />
            <div class="small-title">上传手轮照片</div>
            <el-upload :auto-upload="false" :show-file-list="true" :limit="1" :on-change="onPartFileChange('wheel')" :on-remove="onPartFileRemove('wheel')">
              <el-button>选择文件</el-button>
            </el-upload>
          </el-col>
          <el-col :span="8">
            <div class="small-title">🔵 电机号</div>
            <el-input v-model="partInput.motorNo" />
            <div class="small-title">上传电机照片</div>
            <el-upload :auto-upload="false" :show-file-list="true" :limit="1" :on-change="onPartFileChange('motor')" :on-remove="onPartFileRemove('motor')">
              <el-button>选择文件</el-button>
            </el-upload>
          </el-col>
          <el-col :span="8">
            <div class="small-title">🟠 板号</div>
            <el-input v-model="partInput.boardNo" />
            <div class="small-title">上传主板照片</div>
            <el-upload :auto-upload="false" :show-file-list="true" :limit="1" :on-change="onPartFileChange('board')" :on-remove="onPartFileRemove('board')">
              <el-button>选择文件</el-button>
            </el-upload>
          </el-col>
        </el-row>
      </div>

      <div class="upload-card">
        <div class="small-title">⚪ 其他/注释照片</div>
        <el-row :gutter="10">
          <el-col :span="8">
            <div class="small-title">图片说明（选填）</div>
            <el-input v-model="otherLabel" placeholder="例如：机身侧面、包装等" />
          </el-col>
          <el-col :span="16">
            <div class="small-title">上传其他照片（支持多选）</div>
            <el-upload :auto-upload="false" :show-file-list="true" multiple :on-change="onOtherFileChange" :on-remove="onOtherFileRemove">
              <el-button>选择文件</el-button>
            </el-upload>
          </el-col>
        </el-row>
      </div>

      <el-button type="danger" :loading="saving" @click="saveAllArchivePhotos">💾 保存所有档案照片</el-button>
    </template>
    <el-empty v-else description="请先选择流水号，随后显示机台档案上传与图片列表" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, type UploadUserFile } from 'element-plus'
import { useRouter } from 'vue-router'
import { apiGet, apiPost, getApiErrorMessage } from '../utils/request'
type ListResponse<T = any> = { data: T[] }

const router = useRouter()
const loadingSerials = ref(false)
const saving = ref(false)
const serials = ref<string[]>([])
const selectedSerial = ref('')
const files = ref<any[]>([])
const inventoryMap = ref<Record<string, { model: string; status: string }>>({})
const selectedMachine = computed(() => inventoryMap.value[selectedSerial.value] || null)
const imageFiles = computed(() => files.value.filter((f) => Boolean(f.is_image)))

const partInput = reactive({
  wheelNo: '',
  motorNo: '',
  boardNo: '',
})
const partFiles = reactive<{
  wheel: File | null
  motor: File | null
  board: File | null
}>({
  wheel: null,
  motor: null,
  board: null,
})
const otherLabel = ref('')
const otherFiles = ref<File[]>([])

const goBack = () => {
  router.back()
}

const loadSerials = async () => {
  loadingSerials.value = true
  try {
    const [snRes, invRes] = await Promise.all([apiGet<ListResponse>('/inventory/machine-archive/serials'), apiGet<ListResponse>('/inventory/')])
    serials.value = snRes.data || []
    const map: Record<string, { model: string; status: string }> = {}
    for (const row of invRes.data || []) {
      const sn = String(row['流水号'] || '').trim()
      if (!sn) continue
      map[sn] = {
        model: String(row['机型'] || ''),
        status: String(row['状态'] || ''),
      }
    }
    inventoryMap.value = map
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || '读取流水号失败')
  } finally {
    loadingSerials.value = false
  }
}

const loadFiles = async () => {
  if (!selectedSerial.value) {
    files.value = []
    return
  }
  try {
    const res = await apiGet<ListResponse>(`/inventory/machine-archive/${encodeURIComponent(selectedSerial.value)}/files`)
    files.value = res.data || []
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || '读取档案失败')
    files.value = []
  }
}

const onSerialChange = async () => {
  resetUploadDraft()
  await loadFiles()
}

const onPartFileChange = (key: 'wheel' | 'motor' | 'board') => (uploadFile: UploadUserFile) => {
  const raw = uploadFile.raw as File | undefined
  if (!raw) return
  partFiles[key] = raw
}

const onPartFileRemove = (key: 'wheel' | 'motor' | 'board') => () => {
  partFiles[key] = null
}

const onOtherFileChange = (uploadFile: UploadUserFile) => {
  const raw = uploadFile.raw as File | undefined
  if (!raw) return
  otherFiles.value.push(raw)
}

const onOtherFileRemove = (uploadFile: UploadUserFile) => {
  const raw = uploadFile.raw as File | undefined
  if (!raw) return
  otherFiles.value = otherFiles.value.filter((f) => !(f.name === raw.name && f.size === raw.size))
}

const resetUploadDraft = () => {
  partInput.wheelNo = ''
  partInput.motorNo = ''
  partInput.boardNo = ''
  partFiles.wheel = null
  partFiles.motor = null
  partFiles.board = null
  otherLabel.value = ''
  otherFiles.value = []
}

const uploadByLabel = async (label: string, fileList: File[]) => {
  const formData = new FormData()
  formData.append('label', label)
  for (const f of fileList) formData.append('files', f)
  await apiPost(`/inventory/machine-archive/${encodeURIComponent(selectedSerial.value)}/upload`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

const saveAllArchivePhotos = async () => {
  if (!selectedSerial.value) {
    ElMessage.warning('请先选择流水号')
    return
  }
  if (partFiles.wheel && !partInput.wheelNo.trim()) return ElMessage.warning('请填写【手轮号】')
  if (partFiles.motor && !partInput.motorNo.trim()) return ElMessage.warning('请填写【电机号】')
  if (partFiles.board && !partInput.boardNo.trim()) return ElMessage.warning('请填写【板号】')
  const hasAny = Boolean(partFiles.wheel || partFiles.motor || partFiles.board || otherFiles.value.length > 0)
  if (!hasAny) return ElMessage.warning('未检测到待保存文件')

  saving.value = true
  try {
    if (partFiles.wheel) await uploadByLabel(`手轮_${partInput.wheelNo.trim()}`, [partFiles.wheel])
    if (partFiles.motor) await uploadByLabel(`电机_${partInput.motorNo.trim()}`, [partFiles.motor])
    if (partFiles.board) await uploadByLabel(`板号_${partInput.boardNo.trim()}`, [partFiles.board])
    if (otherFiles.value.length > 0) await uploadByLabel(otherLabel.value.trim() || '其他', otherFiles.value)
    ElMessage.success('档案保存成功')
    resetUploadDraft()
    await loadFiles()
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || '上传失败')
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  loadSerials()
})
</script>

<style scoped>
.archive-page {
  padding-right: 6px;
}
.head-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}
.back-btn {
  padding: 4px 12px;
}
.title {
  margin: 0;
  font-size: 42px;
  font-weight: 800;
  color: #1f2937;
}
.query-row {
  margin-top: 10px;
}
.field-label {
  color: #334155;
  font-size: 12px;
  margin-bottom: 4px;
}
.machine-meta {
  margin-left: 20px;
  display: inline-block;
  vertical-align: top;
}
.sn-title {
  font-size: 32px;
  font-weight: 700;
  color: #111827;
  line-height: 1.1;
}
.sn-sub {
  margin-top: 4px;
  font-size: 12px;
  color: #94a3b8;
}
.empty-bar {
  border: 1px solid #dbeafe;
  background: #eff6ff;
  border-radius: 8px;
  color: #1d4ed8;
  font-size: 13px;
  padding: 8px 12px;
}
.section-title {
  margin: 0 0 8px;
  font-size: 34px;
  font-weight: 800;
  color: #111827;
}
.upload-card {
  margin-top: 10px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 10px;
}
.small-title {
  font-size: 12px;
  color: #334155;
  margin-bottom: 4px;
  margin-top: 2px;
}
</style>
