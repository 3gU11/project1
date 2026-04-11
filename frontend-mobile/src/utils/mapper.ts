export type MobileMachine = {
  id: string
  serialNo: string
  model: string
  batchNo: string
  slotCode: string
  status: string
  updatedAt: string
}

export const mapMachine = (raw: Record<string, unknown>, index = 0): MobileMachine => {
  const serialNo = String(raw.serialNo ?? raw['流水号'] ?? '').trim()
  const model = String(raw.model ?? raw['机型'] ?? '').trim()
  const batchNo = String(raw.batchNo ?? raw['批次号'] ?? '').trim()
  const slotCode = String(raw.slotCode ?? raw.Location_Code ?? '').trim()
  const status = String(raw.status ?? raw['状态'] ?? '').trim()
  const updatedAt = String(raw.updatedAt ?? raw['更新时间'] ?? '').trim()
  return {
    id: serialNo || `${index}`,
    serialNo,
    model,
    batchNo,
    slotCode,
    status,
    updatedAt,
  }
}

export const mapLayoutSlots = (raw: any): Array<{ code: string; status: string; current: number; max: number }> => {
  const slots = raw?.layout_json?.slots
  if (Array.isArray(slots) && slots.length > 0) {
    return slots.map((s: any) => ({
      code: String(s.code ?? s.slotCode ?? ''),
      status: String(s.status ?? 'idle'),
      current: Number(s.current ?? 0),
      max: Number(s.max ?? 30),
    }))
  }
  const defaults: Array<{ code: string; status: string; current: number; max: number }> = []
  for (let row = 1; row <= 3; row += 1) {
    for (let col = 1; col <= 6; col += 1) {
      defaults.push({ code: `A-${row}-${String(col).padStart(2, '0')}`, status: 'idle', current: 0, max: 30 })
    }
  }
  return defaults
}
