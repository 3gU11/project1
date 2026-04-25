<template>
  <div class="page">
    <div class="head">
      <h1>👥 账号与权限管理</h1>
      <el-button type="primary" :loading="loading" @click="loadAll">刷新数据</el-button>
    </div>

    <el-row :gutter="10" class="metrics">
      <el-col :span="8"><el-statistic title="总账号数" :value="users.length" /></el-col>
      <el-col :span="8"><el-statistic title="活跃账号" :value="activeCount" /></el-col>
      <el-col :span="8"><el-statistic title="角色数" :value="roles.length" /></el-col>
    </el-row>

    <el-tabs v-model="activeTab">
      <el-tab-pane label="系统账号列表" name="users">
        <el-table :data="users" border stripe size="small" height="540">
          <el-table-column prop="username" label="用户名" width="140" />
          <el-table-column prop="name" label="姓名" width="120" />
          <el-table-column label="角色" width="180">
            <template #default="scope">
              <el-select v-model="scope.row.role" filterable @change="patchUser(scope.row)">
                <el-option
                  v-for="role in roles"
                  :key="role.role_id"
                  :label="roleLabel(role)"
                  :value="role.role_id"
                />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="130">
            <template #default="scope">
              <el-select v-model="scope.row.status" @change="patchUser(scope.row)">
                <el-option label="活跃 (active)" value="active" />
                <el-option label="待审核 (pending)" value="pending" />
                <el-option label="已拒绝 (rejected)" value="rejected" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column prop="register_time" label="注册时间" width="120" />
          <el-table-column prop="audit_time" label="审核时间" width="120" />
          <el-table-column prop="auditor" label="审核人" min-width="120" />
        </el-table>
      </el-tab-pane>

      <el-tab-pane :label="`待审核申请 (${pendingCount})`" name="pending">
        <div v-if="pendingUsers.length === 0" class="empty">暂无待审核申请</div>
        <el-card v-for="u in pendingUsers" :key="u.username" class="pending-card">
          <div class="pending-row">
            <div>
              <div><b>{{ u.name }}</b> ({{ u.username }})</div>
              <div class="sub">角色: {{ displayRoleName(u.role) }} | 申请时间: {{ u.register_time || '-' }}</div>
            </div>
            <div class="actions">
              <el-button type="success" :loading="saving" @click="auditUser(u.username, 'approve')">通过</el-button>
              <el-button type="danger" :loading="saving" @click="auditUser(u.username, 'reject')">拒绝</el-button>
            </div>
          </div>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="角色管理" name="roles">
        <el-card class="role-card">
          <template #header>新增角色</template>
          <el-form :inline="true" :model="roleForm">
            <el-form-item label="角色编码">
              <el-input v-model="roleForm.role_id" placeholder="如 Finance" clearable />
            </el-form-item>
            <el-form-item label="角色名称">
              <el-input v-model="roleForm.role_name" placeholder="如 财务" clearable />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="saving" @click="createRole">新增</el-button>
            </el-form-item>
          </el-form>
        </el-card>

        <el-table :data="roles" border stripe size="small" class="role-table">
          <el-table-column prop="role_id" label="角色编码" width="180" />
          <el-table-column label="角色名称" min-width="180">
            <template #default="scope">
              <el-input v-model="scope.row.role_name" @change="updateRole(scope.row)" />
            </template>
          </el-table-column>
          <el-table-column prop="user_count" label="用户数" width="90" />
          <el-table-column label="操作" width="260">
            <template #default="scope">
              <el-button size="small" type="primary" @click="selectRole(scope.row)">分配权限</el-button>
              <el-button size="small" type="danger" :disabled="Number(scope.row.user_count || 0) > 0" @click="deleteRole(scope.row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="权限分配" name="permissions">
        <div class="perm-layout">
          <el-card class="role-list">
            <template #header>选择角色</template>
            <el-radio-group v-model="selectedRoleId" class="role-radio" @change="loadSelectedRolePermissions">
              <el-radio-button v-for="role in roles" :key="role.role_id" :label="role.role_id">
                {{ role.role_name || role.role_id }}
              </el-radio-button>
            </el-radio-group>
          </el-card>

          <el-card class="perm-card">
            <template #header>
              <div class="perm-head">
                <span>当前角色：{{ displayRoleName(selectedRoleId) || '未选择' }}</span>
                <div class="actions">
                  <el-button size="small" @click="checkAllPermissions">全选</el-button>
                  <el-button size="small" @click="selectedPermissions = []">清空</el-button>
                  <el-button type="primary" :loading="saving" @click="savePermissions">保存权限</el-button>
                </div>
              </div>
            </template>
            <el-checkbox-group v-model="selectedPermissions" class="perm-grid">
              <el-checkbox v-for="perm in permissionCatalog" :key="perm.code" :value="perm.code" border>
                <span class="perm-label">{{ perm.label }}</span>
                <span class="perm-code">{{ perm.code }}</span>
              </el-checkbox>
            </el-checkbox-group>
          </el-card>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useUserStore } from '../store/user'
import { apiDelete, apiGet, apiGetAll, apiPatch, apiPost, apiPut, getApiErrorMessage } from '../utils/request'

type RoleRow = { role_id: string; role_name: string; user_count?: number }
type PermissionItem = { code: string; label: string; group?: string }

const userStore = useUserStore()
const loading = ref(false)
const saving = ref(false)
const activeTab = ref('users')
const users = ref<any[]>([])
const roles = ref<RoleRow[]>([])
const permissionCatalog = ref<PermissionItem[]>([])
const selectedRoleId = ref('')
const selectedPermissions = ref<string[]>([])
const roleForm = reactive({ role_id: '', role_name: '' })

const pendingUsers = computed(() => users.value.filter((u) => String(u.status || '') === 'pending'))
const pendingCount = computed(() => pendingUsers.value.length)
const activeCount = computed(() => users.value.filter((u) => String(u.status || '') === 'active').length)

const roleLabel = (role: RoleRow) => `${role.role_name || role.role_id} (${role.role_id})`
const displayRoleName = (roleId: string) => {
  const role = roles.value.find((r) => r.role_id === roleId)
  return role ? roleLabel(role) : roleId
}

const loadUsers = async () => {
  const rows = await apiGetAll<any>('/users/')
  users.value = rows.map((row: any) => ({
    ...row,
    register_time: String(row?.register_time || '').slice(0, 10),
    audit_time: String(row?.audit_time || '').slice(0, 10),
  }))
}

const loadRoles = async () => {
  const res = await apiGet<{ data: RoleRow[] }>('/roles/')
  roles.value = res.data || []
  if (!selectedRoleId.value && roles.value.length > 0) selectedRoleId.value = roles.value[0].role_id
}

const loadPermissionCatalog = async () => {
  const res = await apiGet<{ data: PermissionItem[] }>('/roles/permissions/catalog')
  permissionCatalog.value = res.data || []
}

const loadSelectedRolePermissions = async () => {
  if (!selectedRoleId.value) return
  try {
    const res = await apiGet<{ permissions: string[] }>(`/roles/${encodeURIComponent(selectedRoleId.value)}/permissions`)
    selectedPermissions.value = res.permissions || []
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || '读取角色权限失败')
  }
}

const loadAll = async () => {
  loading.value = true
  try {
    await Promise.all([loadRoles(), loadPermissionCatalog(), loadUsers()])
    await loadSelectedRolePermissions()
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || '读取数据失败')
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
    await loadRoles()
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || '更新失败')
    await loadUsers()
  } finally {
    saving.value = false
  }
}

const createRole = async () => {
  if (!roleForm.role_id.trim()) {
    ElMessage.warning('请填写角色编码')
    return
  }
  saving.value = true
  try {
    await apiPost('/roles/', { role_id: roleForm.role_id.trim(), role_name: roleForm.role_name.trim() || roleForm.role_id.trim() })
    ElMessage.success('角色新增成功')
    roleForm.role_id = ''
    roleForm.role_name = ''
    await loadRoles()
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || '新增角色失败')
  } finally {
    saving.value = false
  }
}

const updateRole = async (role: RoleRow) => {
  saving.value = true
  try {
    await apiPatch(`/roles/${encodeURIComponent(role.role_id)}`, { role_name: role.role_name || role.role_id })
    ElMessage.success('角色已更新')
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || '更新角色失败')
    await loadRoles()
  } finally {
    saving.value = false
  }
}

const deleteRole = async (role: RoleRow) => {
  try {
    await ElMessageBox.confirm(`确认删除角色 ${role.role_name || role.role_id}？`, '删除角色', { type: 'warning' })
    saving.value = true
    await apiDelete(`/roles/${encodeURIComponent(role.role_id)}`)
    ElMessage.success('角色已删除')
    if (selectedRoleId.value === role.role_id) selectedRoleId.value = ''
    await loadRoles()
    await loadSelectedRolePermissions()
  } catch (err: any) {
    if (err !== 'cancel') ElMessage.error(getApiErrorMessage(err) || '删除角色失败')
  } finally {
    saving.value = false
  }
}

const selectRole = async (role: RoleRow) => {
  selectedRoleId.value = role.role_id
  activeTab.value = 'permissions'
  await loadSelectedRolePermissions()
}

const checkAllPermissions = () => {
  selectedPermissions.value = permissionCatalog.value.map((p) => p.code)
}

const savePermissions = async () => {
  if (!selectedRoleId.value) {
    ElMessage.warning('请先选择角色')
    return
  }
  saving.value = true
  try {
    const res = await apiPut<{ permissions: string[] }>(`/roles/${encodeURIComponent(selectedRoleId.value)}/permissions`, {
      permissions: selectedPermissions.value,
    })
    selectedPermissions.value = res.permissions || selectedPermissions.value
    ElMessage.success('权限保存成功，相关用户重新登录后生效')
  } catch (err: any) {
    ElMessage.error(getApiErrorMessage(err) || '保存权限失败')
  } finally {
    saving.value = false
  }
}

loadAll()
</script>

<style scoped>
.head{display:flex;justify-content:space-between;align-items:center;margin-bottom: var(--space-2)}.head h1{margin:0;font-size:30px}
.metrics{margin-bottom: var(--space-2)}
.pending-card,.role-card{margin-bottom: var(--space-2)}
.pending-row{display:flex;justify-content:space-between;align-items:center}
.sub{font-size: var(--font-size-sm);color:var(--color-gray-500);margin-top:3px}
.actions{display:flex;gap:8px;align-items:center}
.empty{padding:16px;color:#94a3b8}
.role-table{margin-top: var(--space-2)}
.perm-layout{display:grid;grid-template-columns:260px 1fr;gap:16px}
.role-radio{display:flex;flex-direction:column;align-items:stretch;gap:8px}
.role-radio :deep(.el-radio-button__inner){width:100%;text-align:left;border-left:1px solid var(--el-border-color)}
.perm-head{display:flex;justify-content:space-between;align-items:center;gap:12px}
.perm-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:10px}
.perm-grid :deep(.el-checkbox){margin-right:0;height:auto;padding:10px 12px;display:flex;align-items:center}
.perm-label{font-weight:700;margin-right:8px}
.perm-code{font-size:12px;color:#64748b}
@media (max-width: 900px){.perm-layout{grid-template-columns:1fr}.perm-head{align-items:flex-start;flex-direction:column}}
</style>
