export async function callApi(name, payload = {}) {
  const api = window.pywebview?.api;
  if (!api || !api[name]) {
    throw new Error(`API not available: ${name}`);
  }
  const result = await api[name](payload);
  if (!result.ok) {
    throw new Error(result.error?.message || "Unknown API error");
  }
  return result.data;
}
