import { reactive, readonly } from 'vue'
import { callApi } from '@/api/bridge.js'

export function useVendor() {
  const state = reactive({
    rows: [],
    loading: false,
    error: null
  })

  async function searchVendors(text = null, filters = null) {
    state.loading = true
    state.error = null
    try {
      const result = await callApi('search_vendors', { text, filters })
      state.rows = result.rows || result
    } catch (e) {
      state.error = e.message
      state.rows = []
    } finally {
      state.loading = false
    }
  }

  async function createVendor(data) {
    const result = await callApi('create_vendor', { data })
    await searchVendors()
    return result
  }

  async function updateVendor(vendorId, data) {
    const result = await callApi('update_vendor', { vendor_id: vendorId, data })
    await searchVendors()
    return result
  }

  async function disableVendor(vendorId) {
    await callApi('disable_vendor', { vendor_id: vendorId })
    await searchVendors()
  }

  async function deleteVendor(vendorId) {
    await callApi('delete_vendor', { vendor_id: vendorId })
    await searchVendors()
  }

  async function checkKsrmDuplicate(ksrmCode, excludeVendorId = null) {
    const result = await callApi('check_ksrm_duplicate', { ksrm_code: ksrmCode, exclude_vendor_id: excludeVendorId })
    return result.duplicate
  }

  return {
    state: readonly(state),
    searchVendors,
    createVendor,
    updateVendor,
    disableVendor,
    deleteVendor,
    checkKsrmDuplicate
  }
}
