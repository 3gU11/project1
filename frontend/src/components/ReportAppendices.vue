<template>
  <section v-if="hasAppendixData" class="report-appendices">
    <h3 class="appendix-title">附表分析</h3>

    <template v-if="dealerSummary.length">
      <h4>代理商统计</h4>
      <el-table :data="dealerSummary" border stripe size="small" max-height="360">
        <el-table-column prop="代理商" label="代理商" min-width="180" />
        <el-table-column prop="所售数量" label="所售数量" width="120" align="right" />
        <el-table-column prop="总销售占比" label="总销售占比" width="140" align="right" />
      </el-table>
    </template>

    <h4>总族类比例</h4>
    <el-table :data="familyRows" border stripe size="small" max-height="360">
      <el-table-column prop="总族类" label="总族类" min-width="160" />
      <el-table-column prop="累计出货" label="累计出货" width="120" align="right" />
      <el-table-column prop="总族类比例" label="总族类比例" width="140" align="right" />
      <el-table-column prop="机型数" label="机型数" width="100" align="right" />
    </el-table>

    <h4>丝杆订货需求比例</h4>
    <el-table :data="screwRows" border stripe size="small" max-height="360">
      <el-table-column prop="xs_name" label="XS 名称" min-width="165" />
      <el-table-column prop="xs_quantity" label="数量" width="82" align="right" />
      <el-table-column prop="xs_ratio" label="订货参考占比" width="120" align="right" />
      <el-table-column prop="auto_name" label="AUTO 名称" min-width="165" />
      <el-table-column prop="auto_quantity" label="数量" width="82" align="right" />
      <el-table-column prop="auto_ratio" label="订货参考占比" width="120" align="right" />
      <el-table-column prop="g_name" label="G 名称" min-width="165" />
      <el-table-column prop="g_quantity" label="数量" width="82" align="right" />
      <el-table-column prop="g_ratio" label="订货参考占比" width="120" align="right" />
    </el-table>

    <h4>机型累计占比（全部机型）</h4>
    <el-table :data="modelRows" border stripe size="small" max-height="500">
      <el-table-column prop="排名" label="排名" width="80" align="right" />
      <el-table-column prop="机型" label="机型" min-width="180" />
      <el-table-column prop="总族类" label="总族类" min-width="130" />
      <el-table-column prop="累计出货" label="累计出货" width="120" align="right" />
      <el-table-column prop="累计占比" label="累计占比" width="120" align="right" />
      <el-table-column prop="字典状态" label="字典状态" width="110" align="center" />
    </el-table>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'

type AppendixRows = {
  '总族类比例'?: Record<string, unknown>[]
  '丝杆订货需求比例'?: Record<string, unknown>[]
  '机型累计占比'?: Record<string, unknown>[]
}

const props = withDefaults(defineProps<{
  appendices?: AppendixRows
  dealerSummary?: Record<string, unknown>[]
}>(), {
  appendices: () => ({}),
  dealerSummary: () => [],
})

const familyRows = computed(() => props.appendices['总族类比例'] || [])
const screwRows = computed(() => props.appendices['丝杆订货需求比例'] || [])
const modelRows = computed(() => props.appendices['机型累计占比'] || [])
const hasAppendixData = computed(() => familyRows.value.length || screwRows.value.length || modelRows.value.length || props.dealerSummary.length)
</script>

<style scoped>
.report-appendices {
  margin-top: 24px;
}

.appendix-title {
  margin: 0 0 14px;
  font-size: 18px;
}

h4 {
  margin: 20px 0 8px;
  font-size: 15px;
}
</style>
