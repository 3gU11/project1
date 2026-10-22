<template>
  <div class="workflow-page">
    <div class="page-head"><div><h1>审批中心</h1><p class="intro">处理分配给当前账号的逆向审批，并查看流程处理结果。</p></div><el-button :loading="loading" @click="load">刷新</el-button></div>
    <el-tabs v-model="tab" @tab-change="load"><el-tab-pane label="待我审批" name="pending" /><el-tab-pane label="审批记录" name="approved" /><el-tab-pane label="全部审批中" name="all" /></el-tabs>
    <el-table v-loading="loading" :data="visibleRows" stripe>
      <el-table-column prop="instance_no" label="流程编号" min-width="210"/><el-table-column prop="workflow_key" label="流程类型" min-width="160"/><el-table-column prop="business_type" label="业务类型" width="110"/><el-table-column prop="business_id" label="业务单号" min-width="150"/><el-table-column prop="initiator_id" label="发起人" width="110"/>
      <el-table-column prop="status" label="状态" width="100"><template #default="{row}"><el-tag type="warning">{{row.status}}</el-tag></template></el-table-column><el-table-column label="创建时间" min-width="165"><template #default="{row}">{{formatTime(row.created_at)}}</template></el-table-column>
      <el-table-column label="操作" fixed="right" width="250"><template #default="{row}"><template v-if="row.canApprove"><el-button size="small" type="success" @click="act(row,'approve')">通过</el-button><el-button size="small" type="danger" plain @click="act(row,'reject')">驳回</el-button><el-button size="small" @click="transfer(row)">转交</el-button></template><template v-else-if="isExecutor && row.workflow_key !== 'shipment-recall' && ['已通过','执行中','执行异常','重试中'].includes(row.status)"><el-button v-if="row.status === '已通过'" size="small" @click="lease(row)">获取执行权</el-button><el-button size="small" type="primary" @click="execute(row)">{{ row.status === '执行异常' || row.status === '重试中' ? '重试执行' : '执行' }}</el-button></template><span v-else class="muted">暂无可用操作</span></template></el-table-column>
    </el-table><el-empty v-if="!loading && visibleRows.length === 0" description="暂无待处理审批" />
  </div>
</template>
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { apiGet, apiPost } from '../../utils/request'
import { useUserStore } from '../../store/user'
const userStore=useUserStore(); const loading=ref(false); const tab=ref('pending'); const rows=ref<any[]>([])
const isExecutor=computed(()=>userStore.hasRole(['admin','boss'])); const formatTime=(v:any)=>v?String(v).replace('T',' ').slice(0,19):'-'
const load=async()=>{loading.value=true;try{const [i,t]=await Promise.all([apiGet<{data:any[]}>('/workflows/instances?limit=500'),apiGet<{data:any[]}>('/workflows/tasks?limit=500')]);const map=new Map((t.data||[]).map((x:any)=>[String(x.instance_id),x]));rows.value=(i.data||[]).map((x:any)=>{const task=map.get(String(x.id));return {...x,assignee_id:task?.assignee_id,canApprove:task?.status==='待处理'&&task?.assignee_id===userStore.userInfo?.username}})}finally{loading.value=false}}
const isAdmin=isExecutor.value
const visibleRows=computed(()=>{if(tab.value==='pending') return rows.value.filter(x=>x.canApprove); if(tab.value==='approved') return rows.value.filter(x=>x.status!=='审批中' && (isAdmin || x.initiator_id===userStore.userInfo?.username || x.assignee_id===userStore.userInfo?.username)); return isAdmin ? rows.value.filter(x=>x.status==='审批中') : rows.value.filter(x=>x.status==='审批中' && (x.initiator_id===userStore.userInfo?.username || x.assignee_id===userStore.userInfo?.username))})
const act=async(row:any,action:string)=>{const r=await ElMessageBox.prompt(action==='approve'?'可填写审批意见':'请输入驳回原因',action==='approve'?'审批通过':'审批驳回',{inputValidator:action==='reject'?(v:string)=>v.trim()?true:'请输入驳回原因':undefined}).catch(()=>null);if(!r)return;await apiPost(`/workflows/instances/${row.instance_no}/${action}`,{reason:r.value});ElMessage.success(action==='approve'?'审批已通过':'流程已驳回');window.dispatchEvent(new Event('workflow-pending-updated'));await load()}
const transfer=async(row:any)=>{const r=await ElMessageBox.prompt('请输入新的审批人账号','转交审批',{inputValidator:(v:string)=>v.trim()?true:'请输入账号'}).catch(()=>null);if(!r)return;await apiPost(`/workflows/instances/${row.instance_no}/transfer?assignee_id=${encodeURIComponent(r.value)}`,{reason:'审批中心转交'});ElMessage.success('已转交');window.dispatchEvent(new Event('workflow-pending-updated'));await load()}
const lease=async(row:any)=>{await apiPost(`/workflows/instances/${row.instance_no}/lease`);ElMessage.success('已获取执行权');await load()};const execute=async(row:any)=>{const response=await apiPost<{data:{notification_delivery_pending?:boolean}}>(`/workflows/instances/${row.instance_no}/execute`);if(response.data?.notification_delivery_pending)ElMessage.warning('业务操作已成功，流程通知暂未送达；管理员可重试通知');else ElMessage.success('执行完成');await load()};onMounted(load)
</script>
<style scoped>.workflow-page{padding:28px;max-width:1500px}.page-head{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:10px}h1{margin:0 0 8px;font-size:24px;color:#1f2937}.intro{color:#64748b}.muted{color:#94a3b8;font-size:12px}</style>
