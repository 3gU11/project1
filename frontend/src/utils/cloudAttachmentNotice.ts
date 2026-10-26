/**
 * 转合同后云端合同附件的带入结果提示。
 *
 * 后端 /dealer-orders/{order_no}/convert-to-contract 会返回 cloud_attachments 汇总：
 * synced = 本次新带入合同的附件数，skipped = 已在合同目录的附件数，failed = 失败的附件数。
 * 失败时不能静默，否则用户会以为附件已全部带入合同（合同管理里看起来“附件不全”）。
 */
export type CloudAttachmentSyncSummary = {
  orders?: number
  scanned?: number
  synced?: number
  skipped?: number
  failed?: number
  errors?: Array<{ order_no?: string; attachment_id?: string; error?: string }>
}

export type CloudAttachmentNotice = { level: 'success' | 'warning'; text: string }

export const buildCloudAttachmentNotice = (
  summary?: CloudAttachmentSyncSummary | null,
): CloudAttachmentNotice | null => {
  if (!summary) return null
  const synced = Number(summary.synced || 0)
  const failed = Number(summary.failed || 0)
  if (failed > 0) {
    const firstError = String(summary.errors?.[0]?.error || '').trim()
    const detail = firstError ? `（${firstError.slice(0, 80)}）` : ''
    return {
      level: 'warning',
      text: `有 ${failed} 个云端合同附件未能带入合同${detail}，请在合同管理中检查或重新从云端同步`,
    }
  }
  if (synced > 0) {
    return { level: 'success', text: `已带入 ${synced} 个云端合同附件` }
  }
  return null
}
