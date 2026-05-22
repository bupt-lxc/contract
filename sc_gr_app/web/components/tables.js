import { escapeHtml, text } from "./format.js";

function renderCell(column, row) {
  const rawValue = column.value ? column.value(row) : row[column.key];
  if (column.render) {
    return column.render(rawValue, row);
  }
  return escapeHtml(text(rawValue));
}

function renderState(kind, title, message) {
  return `
    <div class="state-panel ${kind}">
      <div>
        <h3>${escapeHtml(title)}</h3>
        <p>${escapeHtml(message)}</p>
      </div>
    </div>
  `;
}

export function shouldOpenRowFromKeydown(event) {
  if (event.key !== "Enter" && event.key !== " ") {
    return false;
  }

  const target = event.target;
  const tagName = target?.tagName?.toLowerCase();
  if (["button", "input", "select", "textarea", "a"].includes(tagName)) {
    return false;
  }
  return !target?.closest?.("[data-action]");
}

export function renderTable(container, options) {
  const {
    title,
    columns,
    rows,
    sortKey,
    sortDirection,
    loading,
    error,
    emptyMessage = "No records match the current criteria.",
  } = options;

  if (loading) {
    container.innerHTML = `
      <div class="table-shell">
        <div class="table-caption">
          <strong>${escapeHtml(title)}</strong>
          <span>Loading</span>
        </div>
        ${renderState("loading", "Loading records", "Fetching the latest table data from the desktop bridge.")}
      </div>
    `;
    return;
  }

  if (error) {
    container.innerHTML = `
      <div class="table-shell">
        <div class="table-caption">
          <strong>${escapeHtml(title)}</strong>
          <span>Error</span>
        </div>
        ${renderState("error", "Unable to load records", error)}
      </div>
    `;
    return;
  }

  if (!rows.length) {
    container.innerHTML = `
      <div class="table-shell">
        <div class="table-caption">
          <strong>${escapeHtml(title)}</strong>
          <span>0 records</span>
        </div>
        ${renderState("empty", "No records found", emptyMessage)}
      </div>
    `;
    return;
  }

  const headers = columns.map((column) => {
    const active = column.sortKey && column.sortKey === sortKey;
    const mark = active ? sortDirection.toUpperCase() : "";
    const width = column.width ? ` style="width:${column.width}"` : "";
    const label = escapeHtml(column.label);
    if (!column.sortKey) {
      return `<th${width}>${label}</th>`;
    }
    return `
      <th${width}>
        <button type="button" class="sortable-header" data-sort-key="${escapeHtml(column.sortKey)}">
          <span>${label}</span>
          <span class="sort-mark">${mark}</span>
        </button>
      </th>
    `;
  }).join("");

  const body = rows.map((row, index) => {
    const cells = columns.map((column) => {
      const className = column.className ? ` class="${escapeHtml(column.className)}"` : "";
      return `<td${className}>${renderCell(column, row)}</td>`;
    }).join("");
    return `<tr data-row-index="${index}" tabindex="0" role="button">${cells}</tr>`;
  }).join("");

  container.innerHTML = `
    <div class="table-shell">
      <div class="table-caption">
        <strong>${escapeHtml(title)}</strong>
        <span>${rows.length} record${rows.length === 1 ? "" : "s"}</span>
      </div>
      <table class="data-table">
        <thead><tr>${headers}</tr></thead>
        <tbody>${body}</tbody>
      </table>
    </div>
  `;

  container.querySelectorAll("[data-sort-key]").forEach((button) => {
    button.addEventListener("click", () => {
      options.onSort(button.dataset.sortKey);
    });
  });

  container.querySelectorAll("[data-action]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      const rowElement = button.closest("tr");
      const row = rows[Number(rowElement?.dataset.rowIndex)];
      options.onAction?.(button.dataset.action, row);
    });
  });

  container.querySelectorAll("tbody tr").forEach((rowElement) => {
    const openRow = () => {
      const row = rows[Number(rowElement.dataset.rowIndex)];
      options.onRowClick?.(row);
    };
    rowElement.addEventListener("click", openRow);
    rowElement.addEventListener("keydown", (event) => {
      if (shouldOpenRowFromKeydown(event)) {
        event.preventDefault();
        openRow();
      }
    });
  });
}
