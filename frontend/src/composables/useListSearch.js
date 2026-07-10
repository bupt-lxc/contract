import { reactive } from 'vue'
import { callApi } from '@/api/bridge.js'
import { createListSearchCore } from '@/utils/listSearchCore.js'

export function useListSearch(config) {
  const state = reactive({
    rows: [],
    total: 0,
    loading: false,
    error: null,
    text: null,
    filters: {},
    sort: config.defaultSort,
    direction: config.defaultDirection,
    pageSize: config.defaultPageSize,
    currentPage: 1,
  })
  const core = createListSearchCore(config, callApi, state)
  return core
}
