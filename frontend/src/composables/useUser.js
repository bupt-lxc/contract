import { reactive, readonly } from 'vue'
import { callApi } from '@/api/bridge.js'

export function useUser() {
  const state = reactive({
    users: [],
    loading: false,
    error: null
  })

  async function fetchUsers() {
    state.loading = true
    state.error = null
    try {
      state.users = await callApi('list_users')
    } catch (e) {
      state.error = e.message
    } finally {
      state.loading = false
    }
  }

  async function createUser(data) {
    const result = await callApi('create_user', { data })
    await fetchUsers()
    return result
  }

  async function updateUser(machineId, data) {
    const result = await callApi('update_user', { machine_id: machineId, data })
    await fetchUsers()
    return result
  }

  async function disableUser(machineId) {
    await callApi('disable_user', { machine_id: machineId })
    await fetchUsers()
  }

  async function enableUser(machineId) {
    await callApi('enable_user', { machine_id: machineId })
    await fetchUsers()
  }

  return {
    state: readonly(state),
    fetchUsers,
    createUser,
    updateUser,
    disableUser,
    enableUser
  }
}
