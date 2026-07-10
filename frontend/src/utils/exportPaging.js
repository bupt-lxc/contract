export async function fetchAllSearchRows(callApi, apiMethod, params, limit = 500) {
  const allRows = []
  let offset = 0

  while (true) {
    const result = await callApi(apiMethod, { ...params, limit, offset })
    const rows = Array.isArray(result) ? result : (result.items || result.rows || [])
    if (!rows.length) break
    allRows.push(...rows)
    if (rows.length < limit) break
    offset += limit
  }

  return allRows
}
