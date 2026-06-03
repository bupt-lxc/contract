import { reactive, ref } from 'vue'
import { ElMessageBox } from 'element-plus'

export function useBatchAction() {
  const state = reactive({
    active: false,
    total: 0,
    current: 0,
    currentId: '',
    succeeded: 0,
    failed: 0,
    skipped: 0,
    failedItems: [],
    aborted: false
  })

  const abortController = ref(null)

  function getEntityId(row) {
    return row.sc_id || row.gr_id || row.po_id || ''
  }

  function qualifyRows(rows, action) {
    const qualifiers = {
      submit: r => r.status === 'draft',
      confirm: r => r.status === 'manager_confirm',
      approve: r => r.status === 'pending'
    }
    const fn = qualifiers[action]
    return fn ? rows.filter(fn) : []
  }

  async function runBatch(rows, actionName, actionFn, t) {
    const qualifying = qualifyRows(rows, actionName)
    if (!qualifying.length) {
      await ElMessageBox.alert(
        t('batch.noQualifying', { action: t(`batch.${actionName}`) }),
        t('common.confirm')
      )
      return null
    }

    const confirmMessages = {
      submit: 'batch.submitConfirm',
      confirm: 'batch.confirmConfirm',
      approve: 'batch.approveConfirm'
    }
    try {
      await ElMessageBox.confirm(
        t(confirmMessages[actionName], { count: qualifying.length }),
        t('common.confirm'),
        { type: 'warning' }
      )
    } catch {
      return null
    }

    state.active = true
    state.total = qualifying.length
    state.current = 0
    state.currentId = ''
    state.succeeded = 0
    state.failed = 0
    state.skipped = 0
    state.failedItems = []
    state.aborted = false
    abortController.value = new AbortController()
    const signal = abortController.value.signal

    for (let i = 0; i < qualifying.length; i++) {
      if (signal.aborted) {
        state.skipped += qualifying.length - i
        state.aborted = true
        break
      }
      const row = qualifying[i]
      state.current = i + 1
      state.currentId = getEntityId(row)
      try {
        await actionFn(row)
        state.succeeded++
      } catch (e) {
        state.failed++
        state.failedItems.push({
          id: getEntityId(row),
          reason: e.message || String(e)
        })
      }
    }

    state.active = false
    abortController.value = null

    return {
      total: state.total,
      succeeded: state.succeeded,
      failed: state.failed,
      skipped: state.skipped,
      failedItems: state.failedItems,
      aborted: state.aborted
    }
  }

  function abort() {
    abortController.value?.abort()
  }

  return { state, runBatch, abort }
}
