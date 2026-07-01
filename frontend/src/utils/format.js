/**
 * Convert an ISO UTC timestamp string to CST (UTC+8) display format.
 * Handles raw ISO strings from the database as well as pre-formatted strings.
 *
 * @param {string|null|undefined} isoStr - ISO UTC timestamp, e.g. "2026-07-01T03:52:15.737354+00:00"
 * @returns {string} CST display format, e.g. "2026-07-01 11:52:15"
 */
export function formatDateTime(isoStr) {
  if (!isoStr) return '-'
  try {
    let s = String(isoStr)
    // Normalize Z suffix to +00:00
    if (s.endsWith('Z')) s = s.slice(0, -1) + '+00:00'

    if (!s.includes('T')) {
      // Already formatted or date-only — return as-is (max 19 chars)
      return s.slice(0, 19)
    }

    const date = new Date(s)
    if (isNaN(date.getTime())) {
      // Fallback: strip T and microseconds
      return s.replace('T', ' ').split('.')[0].slice(0, 19)
    }

    const year = date.getFullYear()
    const month = String(date.getMonth() + 1).padStart(2, '0')
    const day = String(date.getDate()).padStart(2, '0')
    const hour = String(date.getHours()).padStart(2, '0')
    const min = String(date.getMinutes()).padStart(2, '0')
    const sec = String(date.getSeconds()).padStart(2, '0')
    return `${year}-${month}-${day} ${hour}:${min}:${sec}`
  } catch {
    return String(isoStr).replace('T', ' ').split('.')[0].slice(0, 19)
  }
}

/**
 * Extract date portion (YYYY-MM-DD) from a value.
 * @param {string|null|undefined} val
 * @returns {string}
 */
export function formatDate(val) {
  if (!val) return '-'
  return String(val).slice(0, 10)
}
