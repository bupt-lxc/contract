import { reactive, readonly } from 'vue'
import { callApi } from '@/api/bridge.js'

export function useGr(pageSize = 20) {
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

  async function searchGrs(text = null, filters = null) {
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
      const result = await callApi('search_grs', payload)
      state.rows = result.rows || result
      state.total = result.total || state.rows.length
    } catch (e) {
      state.error = e.message
      state.rows = []
    } finally {
      state.loading = false
    }
  }

  async function createGr(data) { return await callApi('create_gr', { data }) }
  async function updateGr(grId, data) { return await callApi('update_gr', { gr_id: grId, data }) }
  async function approveGr(grId, conValue) { await callApi('approve_gr', { gr_id: grId, con_value: conValue }) }
  async function denyGr(grId) { await callApi('deny_gr', { gr_id: grId }) }
  async function finishGr(grId) { await callApi('finish_gr', { gr_id: grId }) }
  async function submitGr(grId) { await callApi('submit_gr', { gr_id: grId }) }

  function setFilters(filters) { Object.assign(state.filters, filters); state.currentPage = 1 }
  function resetFilters() { state.filters = {}; state.currentPage = 1 }
  function onSortChange({ prop, order }) { state.sort = prop || 'created_at'; state.direction = order === 'ascending' ? 'asc' : 'desc' }
  function onPageChange(page) { state.currentPage = page }
  function onPageSizeChange(size) { state.pageSize = size; state.currentPage = 1 }

  return {
    state: readonly(state),
    searchGrs, createGr, updateGr, approveGr, denyGr, finishGr, submitGr,
    setFilters, resetFilters, onSortChange, onPageChange, onPageSizeChange
  }
}
