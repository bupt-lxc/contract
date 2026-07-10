import { callApi } from '@/api/bridge.js'
import { useListSearch } from './useListSearch.js'

export function useSc(pageSize = 10) {
  const list = useListSearch({
    apiMethod: 'search_scs',
    defaultSort: 'created_at',
    defaultDirection: 'desc',
    defaultPageSize: pageSize,
    allowedFilterKeys: new Set([
      'status', 'request_type', 'service_scope', 'is_calloff', 'asset',
      'cost_center', 'sc_id', 'sc_no', 'requester_id', 'requester_name',
      'created_by', 'created_by_name', 'description', 'calloff_po_id',
      'service_period_start_from', 'service_period_start_to',
      'sc_amount_min', 'sc_amount_max',
      'pending_date_from', 'pending_date_to',
      'approved_date_from', 'approved_date_to',
      'confirmed_at_from', 'confirmed_at_to',
      'deadline_from', 'deadline_to',
    ]),
    allowedSortKeys: new Set([
      'sc_id', 'sc_no', 'requester_id', 'requester_name', 'request_type',
      'service_scope', 'cost_center', 'sc_amount', 'status', 'created_at',
      'updated_at', 'asset', 'pending_date', 'approved_date', 'confirmed_at',
      'calloff_po_id', 'service_period_start', 'service_period_end',
      'submitted_date', 'finished_at',
    ]),
  })

  list.state.detail = null
  list.state.detailLoading = false
  list.state.detailError = null

  async function fetchDetail(scId) {
    list.state.detailLoading = true
    list.state.detailError = null
    try {
      list.state.detail = await callApi('get_sc_detail', { sc_id: scId })
    } catch (e) {
      list.state.detailError = e.message
      list.state.detail = null
    } finally {
      list.state.detailLoading = false
    }
  }

  async function createDraft(data) {
    return await callApi('create_sc_draft', { data })
  }

  async function submitSc(scId, data) {
    return await callApi('submit_sc', { sc_id: scId, data })
  }

  async function updateSc(scId, data) {
    return await callApi('update_sc', { sc_id: scId, data })
  }

  async function approveSc(scId) {
    await callApi('approve_sc', { sc_id: scId })
  }

  async function denySc(scId) {
    await callApi('deny_sc', { sc_id: scId })
  }

  async function finishSc(scId) {
    await callApi('finish_sc', { sc_id: scId })
  }

  function setFilters(filters) {
    list.state.filters = { ...(filters || {}) }
    list.state.currentPage = 1
  }

  function resetFilters() { list.reset() }
  function onSortChange({ prop, order }) { list.changeSort({ prop, order }) }
  function onPageChange(page) { list.changePage(page) }
  function onPageSizeChange(size) { list.changePageSize(size) }

  return {
    state: list.state,
    searchScs: list.search,
    fetchDetail,
    createDraft, submitSc, updateSc,
    approveSc, denySc, finishSc,
    setFilters, resetFilters,
    onSortChange, onPageChange, onPageSizeChange,
    initializeFromRoute: list.initializeFromRoute,
    restoreFromRoute: list.restoreFromRoute,
    applyFilter: list.applyFilter,
    changePage: list.changePage,
    changePageSize: list.changePageSize,
    changeSort: list.changeSort,
    reset: list.reset,
    reload: list.reload,
    exportCriteria: list.exportCriteria,
  }
}
