<template>
  <div class="page">
    <div class="head">
      <h1>👥 账号与权限管理</h1>
      <el-button type="primary" :loading="loading" @click="loadUsers">刷新数据</el-button>
    </div>

    <el-row :gutter="10" class="metrics">
      <el-col :span="8"><el-statistic title="总账号数" :value="users.length" /></el-col>
      <el-col :span="8"><el-statistic title="活跃账号" :value="activeCount" /></el-col>
      <el-col :span="8"><el-statistic title="待审核" :value="pendingCount" /></el-col>
    </el-row>

    <el-tabs>
      <el-tab-pane label="系统账号列表">
        <el-table :data="users" border stripe size="small" height="540">
          <el-table-column prop="username" label="用户名" width="140" />
          <el-table-column prop="name" label="姓名" width="120" />
          <el-table-column label="角色" width="120">
            <template #default="scope">
              <el-select v-model="scope.row.role" @change="patchUser(scope.row)">
                <el-option label="老板 (Boss)" value="Boss" />
                <el-option label="系统管理员 (Admin)" value="Admin" />
                <el-option label="销售专员 (Sales)" value="Sales" />
                <el-option label="生产专员 (Prod)" value="Prod" />
                <el-option label="仓库管理员 (Inbound)" value="Inbound" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="130">
            <template #default="scope">
              <el-select v-model="scope.row.status" @change="patchUser(scope.row)">
                <el-option label="活跃 (active)" value="active" />
                <el-option label="待审核 (pending)" value="pending" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column prop="register_time" label="注册时间" width="170" />
          <el-table-column prop="audit_time" label="审核时间" width="170" />
          <el-table-column prop="auditor" label="审核人" width="120" />
        </el-table>
      </el-tab-pane>
      <el-tab-pane :label="`待审核申请 (${pendingCount})`">
        <div v-if="pendingUsers.length === 0" class="empty">暂无待审核申请</div>
        <el-card v-for="u in pendingUsers" :key="u.username" class="pending-card">
          <div class="pending-row">
            <div>
              <div><b>{{ u.name }}</b> ({{ u.username }})</div>
              <div class="sub">角色: {{ u.role }} | 申请时间: {{ u.register_time || '-' }}</div>
            </div>
            <div class="actions">
              <el-button type="success" :loading="saving" @click="auditUser(u.username, 'approve')">通过</el-button>
              <el-button type="danger" :loading="saving" @click="auditUser(u.username, 'reject')">拒绝</el-button>
            </div>
          </div>
        </el-card>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useUserStore } from '../store/user'
import { apiGetAll, apiPost, apiPatch, getApiErrorMessage } from '../utils/request'

const userStore = useUserStore()
const loading = ref(false)
const saving = ref(false)
const users = ref<any[]>([])

const pendingUsers = computed(() => users.value.filter((u) => String(u.status || '') === 'pending'))
const pendingCount = computed(() => pendingUsers.value.length)
const activeCount = computed(() => users.value.filter((u) => String(u.status || '') === 'active').length)

const loadUsers = async () => {
  loading.value = true
  try {
    users.value = await apiGetAll<any>('/users/')
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || '读取用户失败')
  } finally {
    loading.value = false
  }
}

const auditUser = async (username: string, action: 'approve' | 'reject') => {
  saving.value = true
  try {
    await apiPost('/users/audit', {
      username,
      action,
      auditor: userStore.userInfo?.name || 'system',
    })
    ElMessage.success('审核成功')
    await loadUsers()
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || '审核失败')
  } finally {
    saving.value = false
  }
}

const patchUser = async (row: any) => {
  saving.value = true
  try {
    await apiPatch(`/users/${encodeURIComponent(String(row.username || ''))}`, {
      role: row.role,
      status: row.status,
      name: row.name,
    })
    ElMessage.success('更新成功')
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || '更新失败')
    await loadUsers()
  } finally {
    saving.value = false
  }
}

loadUsers()
</script>

<style scoped>
.head{display:flex;justify-content:space-between;align-items:center;margin-bottom: var(--space-2)}.head h1{margin:0;font-size:30px}
.metrics{margin-bottom: var(--space-2)}
.pending-card{margin-bottom: var(--space-2)}
.pending-row{display:flex;justify-content:space-between;align-items:center}
.sub{font-size: var(--font-size-sm);color:var(--color-gray-500);margin-top:3px}
.actions{display:flex;gap:8px}
.empty{padding:16px;color:#94a3b8}
</style>
