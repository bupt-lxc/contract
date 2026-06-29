import { reactive, readonly } from 'vue'
import { callApi } from '@/api/bridge.js'

export function useSc(pageSize = 20) {
  const state = reactive({
    rows: [],
    total: 0,
    loading: false,
    error: null,
    filters: {},
    sort: 'created_at',
    direction: 'desc',
    pageSize,
    currentPage: 1,
    detail: null,
    detailLoading: false,
    detailError: null
  })

  async function searchScs(text = null, filters = null) {
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
      const result = await callApi('search_scs', payload)
      state.rows = result.rows || result
      state.total = result.total || state.rows.length
    } catch (e) {
      state.error = e.message
      state.rows = []
    } finally {
      state.loading = false
    }
  }

  async function fetchDetail(scId) {
    state.detailLoading = true
    state.detailError = null
    try {
      state.detail = await callApi('get_sc_detail', { sc_id: scId })
    } catch (e) {
      state.detailError = e.message
      state.detail = null
    } finally {
      state.detailLoading = false
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

  async function approveSc(scId, cascadePos = false) {
    await callApi('approve_sc', { sc_id: scId, cascade_pos: cascadePos })
  }

  async function denySc(scId) {
    await callApi('deny_sc', { sc_id: scId })
  }

  async function finishSc(scId) {
    await callApi('finish_sc', { sc_id: scId })
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

  function onPageChange(page) { state.currentPage = page }
  function onPageSizeChange(size) { state.pageSize = size; state.currentPage = 1 }

  return {
    state: readonly(state),
    searchScs, fetchDetail,
    createDraft, submitSc, updateSc,
    approveSc, denySc, finishSc,
    setFilters, resetFilters,
    onSortChange, onPageChange, onPageSizeChange
  }
}
