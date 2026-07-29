export type BatchResultSummary = {
  successCount: number
  failedSerialNos: string[]
  failureMessages: string[]
}

export const summarizeBatchResults = (
  serialNos: string[],
  results: PromiseSettledResult<unknown>[],
): BatchResultSummary => {
  const failedSerialNos: string[] = []
  const failureMessages: string[] = []
  let successCount = 0

  results.forEach((result, index) => {
    if (result.status === 'fulfilled') {
      successCount += 1
      return
    }
    failedSerialNos.push(serialNos[index])
    const reason = result.reason as any
    failureMessages.push(
      String(reason?.response?.data?.detail?.message || reason?.response?.data?.detail || reason?.message || '入库失败'),
    )
  })

  return { successCount, failedSerialNos, failureMessages }
}
