import { defineStore } from 'pinia'
import { inventoryApi } from '@/api/inventory'
import { mapLayoutSlots, mapMachine, type MobileMachine } from '@/utils/mapper'

export const useInventoryStore = defineStore('inventory', {
  state: () => ({
    list: [] as MobileMachine[],
    stats: {
      total: 0,
      inStock: 0,
      pending: 0,
      error: 0,
    },
    slots: [] as Array<{ code: string; status: string; current: number; max: number }>,
    loading: false,
  }),
  actions: {
    async loadInventory(keyword = '') {
      this.loading = true
      try {
        const res = await inventoryApi.getInventoryList({ skip: 0, limit: 200 })
        const rows = (res?.data || []) as Record<string, unknown>[]
        let mapped = rows.map((r, i) => mapMachine(r, i))
        if (keyword.trim()) {
          const q = keyword.trim().toLowerCase()
          mapped = mapped.filter(
            (x) =>
              x.serialNo.toLowerCase().includes(q) ||
              x.model.toLowerCase().includes(q) ||
              x.slotCode.toLowerCase().includes(q)
          )
        }
        this.list = mapped
        this.stats.total = mapped.length
        this.stats.inStock = mapped.filter((x) => x.status.includes('库存中')).length
        this.stats.pending = mapped.filter((x) => x.status.includes('待')).length
        this.stats.error = mapped.filter((x) => x.status.includes('异常')).length
      } finally {
        this.loading = false
      }
    },
    async loadSlots() {
      const res = await inventoryApi.getLayout()
      this.slots = mapLayoutSlots(res)
    },
  },
})
