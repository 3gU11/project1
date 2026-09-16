import source from '../src/views/sandbox/PredictionSandbox.vue?raw'
import ts from 'typescript'
import { describe, expect, it, vi } from 'vitest'

// Execute the actual handlers with isolated state so no production data is recomputed.
const script = source.split('<script setup lang="ts">')[1].split('</script>')[0]
const ast = ts.createSourceFile('sandbox.ts', script, ts.ScriptTarget.Latest, true)
const handlers = ast.statements.filter(node => ts.isFunctionDeclaration(node)
  && ['toggleSelect', 'handleRecompute'].includes(node.name?.text || ''))
const code = ts.transpile(handlers.map(node => node.getText(ast)).join('\n'), { target: ts.ScriptTarget.ES2020 })

function setup() {
  const batches = [
    { batch_id: 'a', status: 'Predicted', slot: 1 },
    { batch_id: 'b', status: 'Predicted', slot: 2 },
    { batch_id: 'c', status: 'Predicted', slot: 3 },
    { batch_id: 'special', status: 'Predicted', slot: 4, special: true },
    { batch_id: 'confirmed', status: 'Confirmed', slot: 5 },
  ]
  const state = {
    recomputing: { value: false }, batchStore: { loading: false, batches },
    selectedBatches: { value: [] as string[] }, canEditSandbox: { value: true },
    optimizedTargetSlotNo: { value: 1 }, latestAchievementCategories: { value: [] },
    getBatchUniqueId: (b: any) => b.batch_id, isSpecialBatch: (b: any) => !!b.special,
    batchSlotOrder: (b: any) => b.slot,
    runRecompute: vi.fn().mockResolvedValue({}), clearPendingRecomputeJob: vi.fn(),
    refresh: vi.fn().mockResolvedValue(undefined), findSuggestedSlotByGap: () => 1,
    ElMessage: { warning: vi.fn(), success: vi.fn(), error: vi.fn() },
    ElMessageBox: { confirm: vi.fn().mockResolvedValue(undefined) },
  }
  const api = new Function(...Object.keys(state), `${code}; return { toggleSelect, handleRecompute }`)(...Object.values(state))
  return { ...state, ...api }
}

describe('sandbox selection recompute', () => {
  it('recomputes the selected target and preserves selection', async () => {
    const s = setup()
    await s.toggleSelect('b')
    expect(s.runRecompute).toHaveBeenCalledOnce()
    expect(s.runRecompute).toHaveBeenCalledWith(2, true)
    expect(s.selectedBatches.value).toEqual(['b'])
    expect(s.optimizedTargetSlotNo.value).toBe(2)
    expect(s.refresh).toHaveBeenCalledOnce()
    expect(s.recomputing.value).toBe(false)
    await s.toggleSelect('b')
    expect(s.selectedBatches.value).toEqual([])
    await s.toggleSelect('b')
    expect(s.runRecompute).toHaveBeenCalledOnce()
  })

  it.each(['a', 'special', 'confirmed', 'missing'])('does not recompute %s', async id => {
    const s = setup()
    await s.toggleSelect(id)
    expect(s.runRecompute).not.toHaveBeenCalled()
  })

  it('allows read-only selection without writes', async () => {
    const s = setup()
    s.canEditSandbox.value = false
    await s.toggleSelect('b')
    expect(s.selectedBatches.value).toEqual(['b'])
    expect(s.runRecompute).not.toHaveBeenCalled()
  })

  it('blocks selection while loading', async () => {
    const s = setup()
    s.batchStore.loading = true
    await s.toggleSelect('b')
    expect(s.selectedBatches.value).toEqual([])
    expect(s.runRecompute).not.toHaveBeenCalled()
  })

  it('blocks duplicate requests while confirmation is pending', async () => {
    const s = setup()
    Object.assign(s.batchStore.batches[1], { is_manually_adjusted: true })
    let approve!: () => void
    s.ElMessageBox.confirm.mockImplementation(() => new Promise<void>(resolve => { approve = resolve }))
    const pending = s.toggleSelect('b')
    await s.toggleSelect('c')
    await s.handleRecompute()
    expect(s.selectedBatches.value).toEqual(['b'])
    expect(s.ElMessageBox.confirm).toHaveBeenCalledOnce()
    expect(s.runRecompute).not.toHaveBeenCalled()
    approve()
    await pending
    expect(s.runRecompute).toHaveBeenCalledWith(2, true)
  })

  it('cancels without recomputing and releases the lock', async () => {
    const s = setup()
    Object.assign(s.batchStore.batches[1], { is_manually_adjusted: true })
    s.ElMessageBox.confirm.mockRejectedValue('cancel')
    await s.toggleSelect('b')
    expect(s.runRecompute).not.toHaveBeenCalled()
    expect(s.recomputing.value).toBe(false)
    expect(s.optimizedTargetSlotNo.value).toBe(1)
  })

  it('releases the lock after failure and preserves the previous recommendation', async () => {
    const s = setup()
    s.runRecompute.mockRejectedValue(new Error('failed'))
    await s.toggleSelect('b')
    expect(s.ElMessage.error).toHaveBeenCalledWith('failed')
    expect(s.recomputing.value).toBe(false)
    expect(s.optimizedTargetSlotNo.value).toBe(1)
  })

  it('blocks selection during an active request', async () => {
    const s = setup()
    let finish!: (result: object) => void
    s.runRecompute.mockImplementation(() => new Promise(resolve => { finish = resolve }))
    const pending = s.toggleSelect('b')
    await s.toggleSelect('c')
    expect(s.selectedBatches.value).toEqual(['b'])
    expect(s.runRecompute).toHaveBeenCalledOnce()
    finish({})
    await pending
  })

  it('retains explicit full recompute', async () => {
    const s = setup()
    await s.handleRecompute()
    expect(s.runRecompute).toHaveBeenCalledWith(1, false)
    expect(s.selectedBatches.value).toEqual([])
  })
})
