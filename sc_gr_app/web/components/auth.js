export async function loadCurrentUserState(state, api) {
  try {
    if (!api?.current_user) {
      throw new Error("API not available: current_user");
    }
    const result = await api.current_user();
    if (!result.ok) {
      throw new Error(result.error?.message || "Unknown API error");
    }
    state.user = result.data;
    state.userError = null;
  } catch (error) {
    state.user = null;
    state.userError = error.message;
  }
}
