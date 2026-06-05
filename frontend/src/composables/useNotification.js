import { reactive, readonly } from 'vue'
import { callApi } from '@/api/bridge.js'

export function useNotification() {
  const state = reactive({
    poConfig: null,
    poConfigLoading: false,
    poConfigError: null,
    customSchedules: [],
    customSchedulesLoading: false,
    customSchedulesError: null,
    defaults: null,
    defaultsLoading: false,
    defaultsError: null,
    queue: [],
    queueTotal: 0,
    queueLoading: false,
    queueError: null
  })

  async function fetchPoConfig(poId) {
    state.poConfigLoading = true
    state.poConfigError = null
    try {
      state.poConfig = await callApi('get_po_notification_config', { po_id: poId })
    } catch (e) {
      state.poConfigError = e.message
      state.poConfig = null
    } finally {
      state.poConfigLoading = false
    }
  }

  async function savePoConfig(poId, data) {
    await callApi('save_po_notification_config', { po_id: poId, data })
    state.poConfig = data
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

  async function fetchCustomSchedules(poId) {
    state.customSchedulesLoading = true
    state.customSchedulesError = null
    try {
      state.customSchedules = await callApi('get_po_custom_schedules', { po_id: poId })
    } catch (e) {
      state.customSchedulesError = e.message
      state.customSchedules = []
    } finally {
      state.customSchedulesLoading = false
    }
  }

  async function saveCustomSchedules(poId, schedules) {
    await callApi('save_po_custom_schedules', { po_id: poId, schedules })
    await fetchCustomSchedules(poId)
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
    fetchPoConfig,
    savePoConfig,
    fetchCustomSchedules,
    saveCustomSchedules,
    fetchDefaults,
    saveDefaults,
    fetchQueue
  }
}
