import { readonly } from 'vue'
import { callApi } from '@/api/bridge.js'
import { useListSearch } from './useListSearch.js'

export function usePo(pageSize = 10) {
  const list = useListSearch({
    apiMethod: 'search_pos',
    defaultSort: 'created_at',
    defaultDirection: 'desc',
    defaultPageSize: pageSize,
    allowedFilterKeys: new Set([
      'status', 'po_id', 'po_no', 'sc_id', 'vendor_id', 'vendor_name',
      'requester_name', 'is_fc_po', 'contract_type', 'contract_no',
      'payment_frequency', 'contract_pos', 'cost_center', 'purchaser',
      'po_amount_min', 'po_amount_max',
      'contract_from_from', 'contract_from_to',
      'contract_to_from', 'contract_to_to',
      'active_date_from', 'active_date_to',
      'deadline_from', 'deadline_to',
    ]),
    allowedSortKeys: new Set([
      'po_id', 'po_no', 'sc_no', 'vendor_name', 'requester_name',
      'po_amount', 'status', 'contract_to', 'contract_type',
      'cost_center', 'active_date', 'created_at', 'updated_at',
    ]),
  })

  async function createPo(data) { return await callApi('create_po', { data }) }
  async function updatePo(poId, data) { return await callApi('update_po', { po_id: poId, data }) }
  async function submitPo(poId) { await callApi('submit_po', { po_id: poId }) }
  async function finishPo(poId) { await callApi('finish_po', { po_id: poId }) }

  function setFilters(filters) { list.state.filters = { ...(filters || {}) }; list.state.currentPage = 1 }
  function resetFilters() { list.reset() }
  function onSortChange({ prop, order }) { list.changeSort({ prop, order }) }
  function onPageChange(page) { list.changePage(page) }
  function onPageSizeChange(size) { list.changePageSize(size) }

  return {
    state: readonly(list.state),
    searchPos: list.search,
    createPo, updatePo, submitPo, finishPo,
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
