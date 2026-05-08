import { defineStore } from 'pinia'
import * as sandboxApi from '../services/sandboxApi'

export const useLineStore = defineStore('sandbox-line', {
  state: () => ({
    lines: [] as any[],
    loading: false,
    error: null as string | null
  }),
  actions: {
    async fetchLines(options: { silent?: boolean } = {}) {
      if (!options.silent) this.loading = true
      this.error = null
      try {
        const res = await sandboxApi.getProductionLines() as any
        this.lines = res.lines || []
      } catch (e: any) {
        this.error = e.message
      } finally {
        if (!options.silent) this.loading = false
      }
    },
    async assignLine(lineId: string, batchId: string) {
      await sandboxApi.assignLine(lineId, batchId)
      await this.fetchLines()
    },
    async manualComplete(lineId: string) {
      await sandboxApi.manualComplete(lineId)
      await this.fetchLines()
    },
    updateLineInList(line: any) {
      const idx = this.lines.findIndex((l: any) => l.production_line_id === line.production_line_id)
      if (idx >= 0) this.lines[idx] = { ...this.lines[idx], ...line }
    }
  }
})
