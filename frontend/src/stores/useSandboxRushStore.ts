import { defineStore } from 'pinia'
import * as sandboxApi from '../services/sandboxApi'

let rushIdCounter = 0

export const useRushStore = defineStore('sandbox-rush', {
  state: () => ({
    rushOrders: [] as any[],
    emptyContainers: [] as any[],
    loadingContainers: false,
    loadingRushOrders: false
  }),
  actions: {
    addRushOrder(order: any) {
      this.rushOrders.push({
        id: `rush-${Date.now()}-${++rushIdCounter}`,
        ...order
      })
    },
    removeRushOrder(id: string | number) {
      this.rushOrders = this.rushOrders.filter((r: any) => String(r.id) !== String(id))
    },
    async fetchRushOrders() {
      this.loadingRushOrders = true
      try {
        const res = await sandboxApi.getRushOrders({ status: 'pending' }) as any
        const rows = Array.isArray(res) ? res : (res?.data || res?.rows || [])
        this.rushOrders = rows.map((row: any) => ({
          id: row.id,
          contract_no: row.contract_no,
          customer: row.customer || '',
          model_type: row.model_type,
          dealer_name: row.dealer_name || '',
          due_date: row.due_date || '',
          remark: row.remark || '',
          status: row.status || 'pending'
        }))
      } finally {
        this.loadingRushOrders = false
      }
    },
    async markRushOrderStatus(id: string | number, status: string) {
      await sandboxApi.updateRushOrderStatus(id, status)
      // Remove it from local state immediately for snappy UI
      this.removeRushOrder(id)
    },
    async returnRushOrderToSandbox(id: string | number) {
      await sandboxApi.returnRushOrderToSandbox(id)
      this.removeRushOrder(id)
    },
    clearRushOrders() {
      this.rushOrders = []
    },
    async fetchEmptyContainers(modelType: string) {
      this.loadingContainers = true
      try {
        const res = await sandboxApi.getEmptyContainers(modelType) as any
        this.emptyContainers = res.units || []
      } finally {
        this.loadingContainers = false
      }
    },
    async executeRushInsert(targetUnitId: string, fallbackUnitId: string, rushOrder: any) {
      return sandboxApi.rushInsert({
        target_unit_id: targetUnitId,
        fallback_unit_id: fallbackUnitId,
        rush_order: {
          contract_no: rushOrder.contract_no,
          customer: rushOrder.customer || '',
          model_type: rushOrder.model_type,
          dealer_name: rushOrder.dealer_name || '',
          due_date: rushOrder.due_date || '',
          remark: rushOrder.remark || ''
        },
        reason: '急单插入'
      })
    },
    async executeRushInsertAtTarget(targetUnitId: string, rushOrder: any) {
      return sandboxApi.rushInsert({
        mode: 'manual',
        target_unit_id: targetUnitId,
        rush_order: {
          contract_no: rushOrder.contract_no,
          customer: rushOrder.customer || '',
          model_type: rushOrder.model_type,
          dealer_name: rushOrder.dealer_name || '',
          due_date: rushOrder.due_date || '',
          remark: rushOrder.remark || ''
        },
        reason: '拖拽急单插入'
      })
    },
    async executeRushAutoInsert(rushOrder: any) {
      return sandboxApi.rushInsert({
        mode: 'auto',
        rush_order: {
          contract_no: rushOrder.contract_no,
          customer: rushOrder.customer || '',
          model_type: rushOrder.model_type,
          dealer_name: rushOrder.dealer_name || '',
          due_date: rushOrder.due_date || '',
          remark: rushOrder.remark || ''
        },
        reason: '自动急单插入'
      })
    }
  }
})
