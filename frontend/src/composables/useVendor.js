import { callApi } from '@/api/bridge.js'
import { useListSearch } from './useListSearch.js'

export function useVendor() {
  const list = useListSearch({
    apiMethod: 'search_vendors',
    defaultSort: 'vendor_name',
    defaultDirection: 'asc',
    defaultPageSize: 10,
    allowedFilterKeys: new Set([
      'vendor_name', 'company_name_cn', 'vendor_id', 'ksrm_vendor_code',
      'service_scope', 'created_by', 'contact_person', 'email', 'phone',
      'description',
    ]),
    allowedSortKeys: new Set([
      'vendor_id', 'vendor_name', 'ksrm_vendor_code', 'company_name_cn',
      'service_scope', 'created_at', 'updated_at',
    ]),
  })

  async function createVendor(data) {
    const result = await callApi('create_vendor', { data })
    await list.reload()
    return result
  }

  async function updateVendor(vendorId, data) {
    const result = await callApi('update_vendor', { vendor_id: vendorId, data })
    await list.reload()
    return result
  }

  async function disableVendor(vendorId) {
    await callApi('disable_vendor', { vendor_id: vendorId })
    await list.reload()
  }

  async function deleteVendor(vendorId) {
    await callApi('delete_vendor', { vendor_id: vendorId })
    await list.reload()
  }

  async function checkKsrmDuplicate(ksrmCode, excludeVendorId = null) {
    const result = await callApi('check_ksrm_duplicate', { ksrm_code: ksrmCode, exclude_vendor_id: excludeVendorId })
    return result.duplicate
  }

  function setFilters(filters) { list.state.filters = { ...(filters || {}) }; list.state.currentPage = 1 }
  function resetFilters() { list.reset() }
  function onSortChange({ prop, order }) { list.changeSort({ prop, order }) }
  function onPageChange(page) { list.changePage(page) }
  function onPageSizeChange(size) { list.changePageSize(size) }

  return {
    state: list.state,
    searchVendors: list.search,
    createVendor,
    updateVendor,
    disableVendor,
    deleteVendor,
    checkKsrmDuplicate,
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
