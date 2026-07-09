import { reactive, readonly } from 'vue'
import { callApi } from '@/api/bridge.js'

export function usePo(pageSize = 10) {
  const state = reactive({
    rows: [],
    total: 0,
    loading: false,
    error: null,
    filters: {},
    sort: 'created_at',
    direction: 'desc',
    pageSize,
    currentPage: 1
  })

  async function searchPos(text = null, filters = null) {
    state.loading = true
    state.error = null
    try {
      const payload = {
        text,
        filters,
        sort: state.sort,
        direction: state.direction,
        limit: state.pageSize,
        offset: (state.currentPage - 1) * state.pageSize
      }
      const result = await callApi('search_pos', payload)
      state.rows = result.rows || result
      state.total = result.total || state.rows.length
    } catch (e) {
      state.error = e.message
      state.rows = []
    } finally {
      state.loading = false
    }
  }

  async function createPo(data) { return await callApi('create_po', { data }) }
  async function updatePo(poId, data) { return await callApi('update_po', { po_id: poId, data }) }
  async function submitPo(poId) { await callApi('submit_po', { po_id: poId }) }
  async function finishPo(poId) { await callApi('finish_po', { po_id: poId }) }
  async function listPoManualAmounts(poId) { return callApi('list_po_manual_amounts', { po_id: poId }) }
  async function createPoManualAmount(poId, data) { return callApi('create_po_manual_amount', { po_id: poId, data }) }
  async function deletePoManualAmount(manualAmountId) { return callApi('delete_po_manual_amount', { manual_amount_id: manualAmountId }) }

  function setFilters(filters) { Object.assign(state.filters, filters); state.currentPage = 1 }
  function resetFilters() { state.filters = {}; state.currentPage = 1 }
  function onSortChange({ prop, order }) { state.sort = prop || 'created_at'; state.direction = order === 'ascending' ? 'asc' : 'desc' }
  function onPageChange(page) { state.currentPage = page }
  function onPageSizeChange(size) { state.pageSize = size; state.currentPage = 1 }

  return {
    state: readonly(state),
    searchPos, createPo, updatePo, submitPo, finishPo,
    listPoManualAmounts, createPoManualAmount, deletePoManualAmount,
    setFilters, resetFilters, onSortChange, onPageChange, onPageSizeChange
  }
}
