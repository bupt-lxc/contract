export function requestTypeLabel(type) {
  if (!type) return ''
  const map = { FC: 'FC', call_off: 'Call Off', new: '' }
  return map[type] || type
}

export function requestTypeAbbr(type) {
  if (!type) return ''
  const map = { FC: 'FC', call_off: 'CO', new: '' }
  return map[type] || type
}
