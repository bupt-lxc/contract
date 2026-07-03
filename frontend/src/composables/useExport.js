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
   * Export an in-memory array of rows directly to an .xlsx file.
   *
   * @param {Array}    rows     – array of row objects
   * @param {Array}    columns  – [{ key, label, getValue? }]
   * @param {string}   filename – without extension
   */
  async function exportRows(rows, columns, filename) {
    const sheetData = rows.map(row => {
      const obj = {}
      columns.forEach(col => {
        const raw = col.getValue ? col.getValue(row) : (row[col.key] ?? '')
        obj[col.label] = raw
      })
      return obj
    })

    const ws = XLSX.utils.json_to_sheet(sheetData)
    ws['!cols'] = columns.map(c => ({ wch: Math.max(c.label.length, 12) }))

    const wb = XLSX.utils.book_new()
    XLSX.utils.book_append_sheet(wb, ws, 'Sheet1')

    const wbArray = XLSX.write(wb, { type: 'array', bookType: 'xlsx' })
    const binary = String.fromCharCode(...new Uint8Array(wbArray))
    const b64 = btoa(binary)
    await callApi('save_file', { filename: `${filename}.xlsx`, data: b64 })
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
      const sheetData = sheet.rows.map(row => {
        const obj = {}
        sheet.columns.forEach(col => {
          const raw = col.getValue ? col.getValue(row) : (row[col.key] ?? '')
          obj[col.label] = raw
        })
        return obj
      })

      const ws = XLSX.utils.json_to_sheet(sheetData)
      ws['!cols'] = sheet.columns.map(c => ({ wch: Math.max(c.label.length, 12) }))
      XLSX.utils.book_append_sheet(wb, ws, sheet.name)
    }

    const wbArray = XLSX.write(wb, { type: 'array', bookType: 'xlsx' })
    const binary = String.fromCharCode(...new Uint8Array(wbArray))
    const b64 = btoa(binary)
    await callApi('save_file', { filename: `${filename}.xlsx`, data: b64 })
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

    await exportRows(allRows, columns, filename)
  }

  return { exportRows, exportAll, exportMultiSheet }
}
