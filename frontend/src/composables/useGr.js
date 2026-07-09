import { readonly } from 'vue'
import { callApi } from '@/api/bridge.js'
import { useListSearch } from './useListSearch.js'

export function useGr(pageSize = 10) {
  const list = useListSearch({
    apiMethod: 'search_grs',
    defaultSort: 'created_at',
    defaultDirection: 'desc',
    defaultPageSize: pageSize,
    allowedFilterKeys: new Set([
      'status', 'gr_id', 'gr_no', 'po_id', 'sc_id', 'requester_id',
      'vendor_id', 'estimated_amount_min', 'estimated_amount_max',
      'tax_rate', 'con_value_min', 'con_value_max', 'gross_cost_min',
      'gross_cost_max', 'pending_date_from', 'pending_date_to',
      'approved_date_from', 'approved_date_to', 'confirmed_at_from',
      'confirmed_at_to', 'goods_service_description', 'confirmation_name',
      'last_delivery', 'is_cancellation', 'remark', 'created_by',
      'deadline_from', 'deadline_to',
    ]),
    allowedSortKeys: new Set([
      'gr_id', 'gr_no', 'po_no', 'sc_no', 'vendor_name', 'estimated_amount',
      'con_value', 'gross_cost', 'tax_rate', 'goods_service_description',
      'confirmation_name', 'last_delivery', 'status', 'created_at',
      'approved_at', 'cancelled_at', 'pending_date', 'approved_date',
      'confirmed_at',
    ]),
  })

  async function createGr(data) { return await callApi('create_gr', { data }) }
  async function updateGr(grId, data) { return await callApi('update_gr', { gr_id: grId, data }) }
  async function approveGr(grId, conValue) { await callApi('approve_gr', { gr_id: grId, con_value: conValue }) }
  async function denyGr(grId) { await callApi('deny_gr', { gr_id: grId }) }
  async function finishGr(grId, confirmCascade = false) {
    return await callApi('finish_gr', { gr_id: grId, confirm_cascade: confirmCascade })
  }
  async function submitGr(grId) { await callApi('submit_gr', { gr_id: grId }) }

  function setFilters(filters) { list.state.filters = { ...(filters || {}) }; list.state.currentPage = 1 }
  function resetFilters() { list.reset() }
  function onSortChange({ prop, order }) { list.changeSort({ prop, order }) }
  function onPageChange(page) { list.changePage(page) }
  function onPageSizeChange(size) { list.changePageSize(size) }

  return {
    state: readonly(list.state),
    searchGrs: list.search,
    createGr, updateGr, approveGr, denyGr, finishGr, submitGr,
    setFilters, resetFilters, onSortChange, onPageChange, onPageSizeChange,
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
