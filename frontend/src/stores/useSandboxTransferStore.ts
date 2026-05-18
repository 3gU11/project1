import { defineStore } from 'pinia'
import * as sandboxApi from '../services/sandboxApi'

let pairIdCounter = 0

const STORAGE_KEY = 'v7ex_transfer_queue'

function loadPairs(): TransferPair[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : []
  } catch {
    return []
  }
}

function savePairs(pairs: TransferPair[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(pairs))
  } catch {
    // localStorage full or unavailable, silently ignore
  }
}

export interface TransferAlternative {
  unit_id: string
  line_name?: string
  model_type: string
  contract_no: string
  customer?: string
  buffer_days: number | null
  is_empty: boolean
  batch_id?: string
  batch_code?: string
  slot_index?: number
  expected_inbound?: string
}

export interface TransferPair {
  id: string
  urgentUnit: any
  targetUnit: any | null
  reason: string
  status: 'pending' | 'executing' | 'done' | 'failed'
  error?: string
  alternatives?: {
    production_line_targets: TransferAlternative[]
    confirmed_slots: TransferAlternative[]
    predicted_slots: TransferAlternative[]
  } | null
}

export const useTransferStore = defineStore('sandbox-transfer', {
  state: () => ({
    pairs: loadPairs() as TransferPair[],
    loading: false,
    selectingTargetFor: null as string | null
  }),
  actions: {
    addPair(urgentUnit: any, targetUnit: any | null, reason: string = '') {
      const id = `transfer-${Date.now()}-${++pairIdCounter}`
      this.pairs.push({
        id,
        urgentUnit: { ...urgentUnit },
        targetUnit: targetUnit ? { ...targetUnit } : null,
        reason,
        status: 'pending',
        alternatives: null,
      })
      savePairs(this.pairs)
      return id
    },
    removePair(id: string) {
      if (this.selectingTargetFor === id) this.selectingTargetFor = null
      this.pairs = this.pairs.filter(p => p.id !== id)
      savePairs(this.pairs)
    },
    startTargetSelection(pairId: string) {
      this.selectingTargetFor = pairId
    },
    cancelTargetSelection() {
      this.selectingTargetFor = null
    },
    async executeSwapWithTarget(pairId: string, targetUnit: any) {
      const pair = this.pairs.find(p => p.id === pairId)
      if (!pair) return
      if (!pair.urgentUnit?.unit_id) {
        pair.status = 'failed'
        pair.error = '急合同单元无效'
        return
      }
      pair.targetUnit = { ...targetUnit }
      pair.status = 'executing'
      pair.error = undefined
      pair.alternatives = null
      this.selectingTargetFor = null
      savePairs(this.pairs)
      try {
        await sandboxApi.transferSwapUnits({
          urgent_unit_id: pair.urgentUnit.unit_id,
          target_unit_id: targetUnit.unit_id,
          reason: pair.reason || '生产看板调货'
        })
        pair.status = 'done'
        savePairs(this.pairs)
      } catch (e: any) {
        const detail = e?.response?.data?.detail || e?.message || '调货失败'
        pair.status = 'failed'
        pair.error = detail
        savePairs(this.pairs)
        // auto-find alternatives when due-date check fails
        if (detail.includes('due date') || detail.includes('交期') || detail.includes('buffer')) {
          await this.findAlternatives(pairId)
        }
        throw e
      }
    },
    async findAlternatives(pairId: string) {
      const pair = this.pairs.find(p => p.id === pairId)
      if (!pair || !pair.urgentUnit?.unit_id) return
      try {
        const res = await sandboxApi.findSwapAlternatives(pair.urgentUnit.unit_id)
        pair.alternatives = res.data || res
        savePairs(this.pairs)
      } catch {
        pair.alternatives = null
        savePairs(this.pairs)
      }
    },
    async retrySwapWithAlternative(pairId: string, alternative: TransferAlternative) {
      const pair = this.pairs.find(p => p.id === pairId)
      if (!pair) return
      pair.alternatives = null
      pair.error = undefined
      pair.status = 'executing'
      savePairs(this.pairs)
      try {
        await sandboxApi.transferSwapUnits({
          urgent_unit_id: pair.urgentUnit.unit_id,
          target_unit_id: alternative.unit_id,
          reason: pair.reason || '生产看板调货(替代)'
        })
        pair.status = 'done'
        savePairs(this.pairs)
      } catch (e: any) {
        pair.status = 'failed'
        pair.error = e?.response?.data?.detail || e?.message || '替代调货失败'
        savePairs(this.pairs)
        throw e
      }
    },
    async returnUrgentToSandbox(pairId: string, targetBatchId: string) {
      const pair = this.pairs.find(p => p.id === pairId)
      if (!pair || !pair.urgentUnit?.unit_id) return
      pair.status = 'executing'
      pair.error = undefined
      savePairs(this.pairs)
      try {
        await sandboxApi.returnUnitToSandbox(pair.urgentUnit.unit_id, targetBatchId)
        pair.status = 'done'
        pair.error = undefined
        savePairs(this.pairs)
      } catch (e: any) {
        pair.status = 'failed'
        pair.error = e?.response?.data?.detail || e?.message || '退回沙盘失败'
        savePairs(this.pairs)
        throw e
      }
    },
    clearCompleted() {
      this.pairs = this.pairs.filter(p => p.status === 'pending' || p.status === 'executing')
      savePairs(this.pairs)
    }
  }
})
