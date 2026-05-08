import { defineStore } from 'pinia'
import * as sandboxApi from '../services/sandboxApi'

export const useBatchStore = defineStore('sandbox-batch', {
  state: () => ({
    batches: [] as any[],
    loading: false,
    filter: '',
    error: null as string | null
  }),
  getters: {
    filteredBatches(state) {
      return state.batches
    },
    modelTypes(state) {
      const types = new Set(state.batches.map((b: any) => b.model_type))
      return [...types].sort()
    }
  },
  actions: {
    async fetchBatches(params: Record<string, any> = {}, options: { silent?: boolean } = {}) {
      if (!options.silent) this.loading = true
      this.error = null
      try {
        const res = await sandboxApi.getBatches(params) as any
        this.batches = res.batches || []
      } catch (e: any) {
        this.error = e.message
      } finally {
        if (!options.silent) this.loading = false
      }
    },
    async confirmBatch(id: string, batchCode?: string, expectedInboundDate?: string) {
      await sandboxApi.confirmBatch(id, batchCode, expectedInboundDate)
      await this.fetchBatches()
    },
    async batchConfirm(ids: string[]) {
      await sandboxApi.batchConfirm(ids)
      await this.fetchBatches()
    },
    setFilter(type: string) {
      this.filter = type
    },
    updateBatchInList(batch: any) {
      const idx = this.batches.findIndex((b: any) => b.batch_id === batch.batch_id)
      if (idx >= 0) this.batches[idx] = { ...this.batches[idx], ...batch }
    },
    removeBatchInList(batchId: string) {
      this.batches = this.batches.filter((b: any) => b.batch_id !== batchId)
    }
  }
})
