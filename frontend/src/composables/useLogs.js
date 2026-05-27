import { reactive, readonly } from 'vue'
import { callApi } from '@/api/bridge.js'

export function useLogs(pageSize = 50) {
  const state = reactive({
    rows: [],
    total: 0,
    loading: false,
    error: null,
    filters: {},
    sort: 'created_at',
    direction: 'desc',
    pageSize: pageSize,
    currentPage: 1
  })

  async function searchLogs(text = null, filters = null) {
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
      const result = await callApi('search_audit_logs', payload)
      state.rows = result.rows || result
      state.total = result.total || state.rows.length
    } catch (e) {
      state.error = e.message
      state.rows = []
    } finally {
      state.loading = false
    }
  }

  function setFilters(filters) {
    Object.assign(state.filters, filters)
    state.currentPage = 1
  }

  function resetFilters() {
    state.filters = {}
    state.currentPage = 1
  }

  function onSortChange({ prop, order }) {
    state.sort = prop || 'created_at'
    state.direction = order === 'ascending' ? 'asc' : 'desc'
  }

  function onPageChange(page) {
    state.currentPage = page
  }

  function onPageSizeChange(size) {
    state.pageSize = size
    state.currentPage = 1
  }

  return {
    state: readonly(state),
    searchLogs,
    setFilters,
    resetFilters,
    onSortChange,
    onPageChange,
    onPageSizeChange
  }
}
