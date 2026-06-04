/**
 * Sandbox API client — proxies through V8betaVer1.0 FastAPI to Go scheduling service.
 * All paths are relative to /api/v1/sandbox/ (handled by request.ts baseURL).
 */
import { apiGet, apiPost, apiPatch } from '../utils/request'

const P = '/sandbox'

// Batches
export const getBatches = (params?: Record<string, any>) =>
  apiGet(`${P}/batches`, { params })

export const getBatch = (id: string) =>
  apiGet(`${P}/batches/${id}`)

export const getBatchUnits = (id: string) =>
  apiGet(`${P}/batches/${id}/units`)

export const confirmBatch = (id: string, batchCode?: string, expectedInboundDate?: string) =>
  apiPost(`${P}/batches/${id}/confirm`, {
    ...(batchCode ? { batch_code: batchCode } : {}),
    ...(expectedInboundDate ? { expected_inbound_date: expectedInboundDate } : {}),
  })

export const batchConfirm = (batchIds: string[]) =>
  apiPost(`${P}/batches/batch-confirm`, { batch_ids: batchIds })

export const insertEmptySlot = (id: string, beforeSlotIndex: number, sizeKey?: string) =>
  apiPost(`${P}/batches/${id}/insert-empty-slot`, {
    before_slot_index: beforeSlotIndex,
    ...(sizeKey ? { size_key: sizeKey } : {})
  })

export const updateBatchStockModels = (id: string, stocks: Array<{ model_type: string; count: number }>) =>
  apiPatch(`${P}/batches/${id}/stock-models`, { stocks })

// Units
export const getUnit = (id: string) =>
  apiGet(`${P}/units/${id}`)

export const updateUnit = (id: string, data: Record<string, any>) =>
  apiPatch(`${P}/units/${id}`, data)

export const unlockUnit = (id: string) =>
  apiPatch(`${P}/units/${id}/unlock`)

export const moveUnitBatch = (id: string, targetBatchId: string, targetSlot: number) =>
  apiPost(`${P}/units/${id}/move-batch`, { target_batch_id: targetBatchId, target_slot: targetSlot })

export const moveUnitToSpecial = (id: string) =>
  apiPost(`${P}/units/${id}/move-to-special`)

export const insertCascade = (id: string, targetBatchId: string, targetSlot: number) =>
  apiPost(`${P}/units/${id}/insert-cascade`, { target_batch_id: targetBatchId, target_slot: targetSlot })

export const reorderUnitSlot = (id: string, newSlotIndex: number) =>
  apiPost(`${P}/units/${id}/reorder-slot`, { new_slot_index: newSlotIndex })

export const repairFamilyMismatches = () =>
  apiPost(`${P}/units/repair-family-mismatches`)

export const swapContent = (data: Record<string, any>) =>
  apiPost(`${P}/units/swap-content`, data)

export const rushInsert = (data: Record<string, any>) =>
  apiPost(`${P}/units/rush-insert`, data)

export const convertUnitToRush = (id: string) =>
  apiPost(`${P}/units/${id}/convert-to-rush`)

export const transferSwapUnits = (data: { urgent_unit_id: string; target_unit_id: string; reason?: string }) =>
  apiPost(`${P}/units/transfer-swap`, data)

export const findSwapAlternatives = (urgentUnitId: string) =>
  apiPost(`${P}/units/transfer-swap/find-alternatives`, { urgent_unit_id: urgentUnitId })

export const returnUnitToSandbox = (unitId: string, targetBatchId: string) =>
  apiPost(`${P}/units/${unitId}/return-to-sandbox`, { target_batch_id: targetBatchId })

export const getRushOrders = (params?: Record<string, any>) =>
  apiGet(`${P}/rush-orders`, { params })

export const updateRushOrderStatus = (id: string | number, status: string) =>
  apiPatch(`${P}/rush-orders/${id}`, { status })

export const returnRushOrderToSandbox = (id: string | number) =>
  apiPost(`${P}/rush-orders/${id}/return-to-sandbox`)

export const createSpecialCard = (data: Record<string, any>) =>
  apiPost(`${P}/units/special-card`, data)

export const getEmptyContainers = (modelType?: string) =>
  apiGet(`${P}/units/empty-containers`, { params: modelType ? { model_type: modelType } : {} })

export const markSpot = (id: string) =>
  apiPost(`${P}/units/${id}/mark-spot`)

// Forecast
export const recompute = (targetSlotNo?: number, isClicked?: boolean) =>
  apiPost(
    `${P}/forecast/recompute`,
    {
      target_slot_no: targetSlotNo ?? 1,
      is_clicked: !!isClicked
    },
    { timeout: 130000 }
  )

export const getForecastAchievement = () =>
  apiGet(`${P}/forecast/achievement`)

export const getModelTypes = () =>
  apiGet(`${P}/model-types`)

// Capacity
export const getCapacityRatio = () =>
  apiGet(`${P}/capacity-ratio`)

export const updateCapacityRatio = (data: Record<string, any>) =>
  apiPatch(`${P}/capacity-ratio`, data)

// Production Lines
export const getProductionLines = () =>
  apiGet(`${P}/production-lines`)

export const assignLine = (id: string, batchId: string) =>
  apiPost(`${P}/production-lines/${id}/assign`, { batch_id: batchId })

export const manualComplete = (id: string) =>
  apiPost(`${P}/production-lines/${id}/manual-complete`)

export const lockLineUnits = (lineId: string, unitIds: string[], orderRemark: string) =>
  apiPost(`${P}/production-lines/${lineId}/lock-units`, {
    unit_ids: unitIds,
    order_remark: orderRemark,
  })

// Revoke confirmed batch (delete from plan_import + revert status)
export const revokeBatch = (batchId: string) =>
  apiPost(`${P}/batches/${batchId}/revoke`)

// Sync batch cards to plan_import after confirm
export const previewSyncToPlan = (batchId: string, batchCode: string) =>
  apiGet(`${P}/batches/${batchId}/sync-preview`, { params: { batch_code: batchCode } })

export const syncBatchToPlan = (batchId: string, batchCode: string) =>
  apiPost(`${P}/batches/${batchId}/sync-to-plan`, { batch_code: batchCode })

export const getLastBatchCode = () =>
  apiGet(`${P}/batches/last-batch-code`)

// Auto-import plan_import → finished_goods_data on line assignment
export const importBatchToFinishedGoods = (batchId: string) =>
  apiPost(`${P}/batches/${batchId}/import-to-finished-goods`, undefined, { timeout: 120000 })

// Production Queue (overflow waiting orders)
export const getProductionQueue = (params?: Record<string, any>) =>
  apiGet(`${P}/production-queue`, { params })
