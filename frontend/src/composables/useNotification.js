import { reactive, readonly } from 'vue'
import { callApi } from '@/api/bridge.js'

export function useNotification() {
  const state = reactive({
    scConfig: null,
    scConfigLoading: false,
    scConfigError: null,
    defaults: null,
    defaultsLoading: false,
    defaultsError: null,
    queue: [],
    queueTotal: 0,
    queueLoading: false,
    queueError: null
  })

  async function fetchScConfig(scId) {
    state.scConfigLoading = true
    state.scConfigError = null
    try {
      state.scConfig = await callApi('get_sc_notification_config', { sc_id: scId })
    } catch (e) {
      state.scConfigError = e.message
      state.scConfig = null
    } finally {
      state.scConfigLoading = false
    }
  }

  async function saveScConfig(scId, data) {
    await callApi('save_sc_notification_config', { sc_id: scId, data })
    state.scConfig = data
  }

  async function fetchDefaults() {
    state.defaultsLoading = true
    state.defaultsError = null
    try {
      const result = await callApi('get_notification_defaults', {})
      state.defaults = result
    } catch (e) {
      state.defaultsError = e.message
      state.defaults = null
    } finally {
      state.defaultsLoading = false
    }
  }

  async function saveDefaults(data) {
    await callApi('save_notification_defaults', { data })
    // Re-fetch defaults from the server so state.defaults always
    // has the same shape (notify.* keys) that NotificationDefaults expects.
    await fetchDefaults()
  }

  async function fetchQueue({ scId, status, entity_type, entity_id, limit = 50, offset = 0 } = {}) {
    state.queueLoading = true
    state.queueError = null
    try {
      const result = await callApi('list_notification_queue', { sc_id: scId, status, entity_type, entity_id, limit, offset })
      state.queue = result.items
      state.queueTotal = result.total
    } catch (e) {
      state.queueError = e.message
      state.queue = []
      state.queueTotal = 0
    } finally {
      state.queueLoading = false
    }
  }

  return {
    state: readonly(state),
    fetchScConfig,
    saveScConfig,
    fetchDefaults,
    saveDefaults,
    fetchQueue
  }
}
