import { reactive } from 'vue'

class ApiError extends Error {
  constructor(error) {
    super(error.message || 'API error')
    this.code = error.code || 'UNKNOWN'
  }
}

const DEV_MODE = window.location.protocol === 'http:'

export const loadingState = reactive({ count: 0 })

export async function callApi(method, payload = {}) {
  loadingState.count++
  try {
    let result
    if (DEV_MODE) {
      if (!window.pywebview?.api) {
        throw new ApiError({ code: 'DEV_NO_BRIDGE', message: 'Dev mode: no pywebview bridge. Run in the desktop app.' })
      }
      result = await window.pywebview.api[method](payload)
    } else {
      result = await window.pywebview.api[method](payload)
    }
    if (!result.ok) {
      throw new ApiError(result.error)
    }
    return result.data
  } finally {
    loadingState.count--
  }
}

export { ApiError }
