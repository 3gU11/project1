import { defineStore } from 'pinia'
import { inboundApi } from '@/api/inbound'
import { mapLayoutSlots, mapMachine, type MobileMachine } from '@/utils/mapper'

export const useInboundStore = defineStore('inbound', {
  state: () => ({
    pendingList: [] as MobileMachine[],
    selectedSerialNos: [] as string[],
    slots: [] as Array<{ code: string; status: string; current: number; max: number }>,
    loading: false,
  }),
  actions: {
    async loadPendingList() {
      this.loading = true
      try {
        const res = await inboundApi.getPendingList(0, 200)
        const rows = (res?.data || []) as Record<string, unknown>[]
        this.pendingList = rows.map((r, i) => mapMachine(r, i))
      } finally {
        this.loading = false
      }
    },
    toggleSelect(serialNo: string) {
      const idx = this.selectedSerialNos.indexOf(serialNo)
      if (idx >= 0) {
        this.selectedSerialNos.splice(idx, 1)
      } else {
        this.selectedSerialNos.push(serialNo)
      }
    },
    clearSelected() {
      this.selectedSerialNos = []
    },
    async loadSlots() {
      const res = await inboundApi.getLayout()
      this.slots = mapLayoutSlots(res)
    },
    async confirmInbound(slotCode: string) {
      await Promise.all(this.selectedSerialNos.map((sn) => inboundApi.confirmInbound(sn, slotCode)))
      this.selectedSerialNos = []
      await this.loadPendingList()
      await this.loadSlots()
    },
  },
})
