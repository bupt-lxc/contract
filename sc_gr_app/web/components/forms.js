import { escapeHtml } from "./format.js";

export function collectFormData(controls) {
  const data = {};
  for (const control of controls) {
    if (!control.name) {
      continue;
    }
    const value = typeof control.value === "string" ? control.value.trim() : control.value;
    if (value === "" || value === null || value === undefined) {
      continue;
    }
    data[control.name] = value;
  }
  return data;
}

export function field(name, label, value = "", type = "text", options = {}) {
  const readonly = options.readonly ? " readonly" : "";
  const required = options.required ? " required" : "";
  const hidden = type === "hidden" ? " hidden" : "";
  return `
    <label class="form-field"${hidden}>
      <span>${escapeHtml(label)}</span>
      <input name="${escapeHtml(name)}" type="${escapeHtml(type)}" value="${escapeHtml(value)}"${readonly}${required}>
    </label>
  `;
}
