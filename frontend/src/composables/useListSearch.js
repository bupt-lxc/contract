import { reactive } from 'vue'
import { callApi } from '@/api/bridge.js'
import { createListSearchCore } from '@/utils/listSearchCore.js'

export function useListSearch(config) {
  const core = createListSearchCore(config, callApi)
  core.state = reactive(core.state)
  return core
}
