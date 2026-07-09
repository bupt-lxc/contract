import * as XLSX from 'xlsx'
import { callApi } from '@/api/bridge.js'

/**
 * Reusable Excel export composable.
 *
 * Usage — list views (paginated fetch, respects current filters):
 *   const { exportAll } = useExport()
 *   await exportAll('search_scs', { text, filters, sort, direction }, columns, 'SC_List')
 *
 * Usage — detail views (already-loaded data):
 *   const { exportRows } = useExport()
 *   exportRows(detail.pos, columns, 'SC_POs')
 */

export function useExport() {
  /** Return today's date as YYYY-MM-DD for default filenames. */
  function _today() {
    return new Date().toISOString().slice(0, 10)
  }

  /**
   * Convert a Uint8Array to a binary string in chunks to avoid
   * "Maximum call stack size exceeded" when spreading large arrays
   * into String.fromCharCode arguments.
   */
  function _uint8ToString(uint8Array) {
    let result = ''
    const chunkSize = 0x8000
    for (let i = 0; i < uint8Array.length; i += chunkSize) {
      result += String.fromCharCode(...uint8Array.subarray(i, i + chunkSize))
    }
    return result
  }

  /**
   * Export an in-memory array of rows directly to an .xlsx file.
   *
   * @param {Array}    rows     – array of row objects
   * @param {Array}    columns  – [{ key, label, getValue? }]
   * @param {string}   filename – without extension
   */
  async function exportRows(rows, columns, filename) {
    let ws
    if (!rows.length) {
      ws = XLSX.utils.aoa_to_sheet([columns.map(c => c.label)])
    } else {
      const sheetData = rows.map(row => {
        const obj = {}
        columns.forEach(col => {
          const raw = col.getValue ? col.getValue(row) : (row[col.key] ?? '')
          obj[col.label] = raw
        })
        return obj
      })
      ws = XLSX.utils.json_to_sheet(sheetData)
    }

    ws['!cols'] = columns.map(c => ({ wch: Math.max(c.label.length, 12) }))

    const wb = XLSX.utils.book_new()
    XLSX.utils.book_append_sheet(wb, ws, 'Sheet1')

    const wbArray = XLSX.write(wb, { type: 'array', bookType: 'xlsx' })
    const binary = _uint8ToString(new Uint8Array(wbArray))
    const b64 = btoa(binary)
    return await callApi('save_file', { filename: `${filename}.xlsx`, data: b64 })
  }

  /**
   * Build a multi-sheet workbook and save via native dialog.
   *
   * @param {Array}    sheets    – [{ name: string, rows: Array, columns: Array }]
   * @param {string}   filename  – without extension
   *
   * columns format per sheet: [{ key, label, getValue? }]
   */
  async function exportMultiSheet(sheets, filename) {
    const wb = XLSX.utils.book_new()

    for (const sheet of sheets) {
      let ws
      if (!sheet.rows.length) {
        ws = XLSX.utils.aoa_to_sheet([sheet.columns.map(c => c.label)])
      } else {
        const sheetData = sheet.rows.map(row => {
          const obj = {}
          sheet.columns.forEach(col => {
            const raw = col.getValue ? col.getValue(row) : (row[col.key] ?? '')
            obj[col.label] = raw
          })
          return obj
        })
        ws = XLSX.utils.json_to_sheet(sheetData)
      }

      ws['!cols'] = sheet.columns.map(c => ({ wch: Math.max(c.label.length, 12) }))
      XLSX.utils.book_append_sheet(wb, ws, sheet.name)
    }

    const wbArray = XLSX.write(wb, { type: 'array', bookType: 'xlsx' })
    const binary = _uint8ToString(new Uint8Array(wbArray))
    const b64 = btoa(binary)
    return await callApi('save_file', { filename: `${filename}.xlsx`, data: b64 })
  }

  /**
   * Paginate through ALL results of a search-style API and export to .xlsx.
   *
   * @param {string}  apiMethod – e.g. 'search_scs'
   * @param {object}  params    – { text, filters, sort, direction } (limit/offset are added automatically)
   * @param {Array}   columns   – same as exportRows
   * @param {string}  filename  – without extension
   */
  async function exportAll(apiMethod, params, columns, filename) {
    const allRows = []
    const limit = 500
    let offset = 0

    while (true) {
      const result = await callApi(apiMethod, { ...params, limit, offset })
      const rows = Array.isArray(result) ? result : (result.items || result.rows || [])
      if (!rows.length) break
      allRows.push(...rows)
      if (rows.length < limit) break
      offset += limit
    }

    return await exportRows(allRows, columns, filename)
  }

  /**
   * Escape a value for CSV output (handle commas, quotes, newlines).
   */
  function _escapeCSV(val) {
    const s = String(val ?? '')
    if (s.includes(',') || s.includes('"') || s.includes('\n') || s.includes('\r')) {
      return '"' + s.replace(/"/g, '""') + '"'
    }
    return s
  }

  /**
   * Convert rows + columns definition to a CSV string.
   * columns: [{ key, label, getValue? }]
   */
  function _toCSV(rows, columns) {
    const header = columns.map(c => _escapeCSV(c.label)).join(',')
    const body = rows.map(row =>
      columns.map(col => {
        const raw = col.getValue ? col.getValue(row) : (row[col.key] ?? '')
        return _escapeCSV(raw)
      }).join(',')
    ).join('\n')
    return header + '\n' + body
  }

  /**
   * Export an in-memory array of rows as a .csv file.
   */
  async function exportCSV(rows, columns, filename) {
    const csv = _toCSV(rows, columns)
    const b64 = btoa(unescape(encodeURIComponent(csv)))
    return await callApi('save_file', { filename: `${filename}.csv`, data: b64 })
  }

  /**
   * Paginate through ALL search results and export as .csv.
   */
  async function exportAllCSV(apiMethod, params, columns, filename) {
    const allRows = []
    const limit = 500
    let offset = 0

    while (true) {
      const result = await callApi(apiMethod, { ...params, limit, offset })
      const rows = Array.isArray(result) ? result : (result.items || result.rows || [])
      if (!rows.length) break
      allRows.push(...rows)
      if (rows.length < limit) break
      offset += limit
    }

    return await exportCSV(allRows, columns, filename)
  }

  return { exportRows, exportAll, exportMultiSheet, exportCSV, exportAllCSV }
}
