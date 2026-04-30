// Small DRY helpers for the admin tabs.
import { el, clear } from "/static/common.js";

export function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])
  );
}

/**
 * Render a list of items grouped by a key, into a series of tables — used by
 * the People / Markers / Zones / Questions tabs to avoid copy-pasting the
 * same group-and-tabulate pattern.
 *
 * opts:
 *   container: element to render into (cleared first)
 *   items:     [item]
 *   groupBy:   (item) => string  (group key)
 *   columns:   [{ header: string, cell: (item) => Node|string, width?: string }]
 *   emptyText: string
 *   groupCount: bool — show "(n)" next to each group header
 */
export function renderGroupedTable({ container, items, groupBy, columns, emptyText, groupCount = true }) {
  clear(container);
  if (!items || items.length === 0) {
    container.appendChild(el("div", { class: "muted" }, emptyText || "Nothing here yet."));
    return;
  }
  const groups = new Map();
  for (const it of items) {
    const k = groupBy(it) || "(none)";
    if (!groups.has(k)) groups.set(k, []);
    groups.get(k).push(it);
  }
  for (const [name, list] of groups) {
    const wrap = el("div", { style: { marginBottom: "16px" } });
    const header = el("div", {
      style: { fontWeight: 600, padding: "6px 0", fontSize: "14px", color: "#cbd5e1" }
    }, name);
    if (groupCount) {
      header.appendChild(el("span", { class: "muted", style: { fontWeight: 400 } }, ` (${list.length})`));
    }
    wrap.appendChild(header);
    const tbl = el("table", {});
    tbl.appendChild(el("thead", {}, el("tr", {},
      ...columns.map((c) => el("th", c.width ? { style: { width: c.width } } : {}, c.header)),
    )));
    const tb = el("tbody", {});
    for (const it of list) {
      tb.appendChild(el("tr", {},
        ...columns.map((c) => {
          const v = c.cell(it);
          const td = el("td", c.cellAttrs ? c.cellAttrs(it) : {});
          if (v instanceof Node) td.appendChild(v);
          else if (Array.isArray(v)) v.forEach((x) => x && td.appendChild(typeof x === "string" ? document.createTextNode(x) : x));
          else if (v != null) td.appendChild(document.createTextNode(String(v)));
          return td;
        }),
      ));
    }
    tbl.appendChild(tb);
    wrap.appendChild(tbl);
    container.appendChild(wrap);
  }
}

/**
 * Helper to make an action-cell button. Handles its async click + optional
 * confirm prompt + auto-reload.
 */
export function actionButton(label, opts = {}) {
  const b = el("button", opts.class ? { class: opts.class } : {}, label);
  if (opts.title) b.title = opts.title;
  b.addEventListener("click", async (ev) => {
    ev.stopPropagation();
    if (opts.confirm && !confirm(opts.confirm)) return;
    try {
      await opts.onClick?.(ev);
    } catch (e) { alert(e.message); }
  });
  return b;
}

/**
 * Show a small modal dialog with arbitrary body. Returns a {dialog, close} pair.
 */
export function openModal({ title, bodyHtml, buttons = [] }) {
  const dlg = document.createElement("dialog");
  dlg.style.maxWidth = "440px";
  const titleHtml = title ? `<h3 style="margin-top:0;">${escapeHtml(title)}</h3>` : "";
  dlg.innerHTML = titleHtml + (bodyHtml || "") +
    `<div data-actions style="display:flex; gap:8px; justify-content:flex-end; margin-top:12px;"></div>`;
  const actions = dlg.querySelector("[data-actions]");
  for (const btn of buttons) {
    const b = el("button", btn.class ? { class: btn.class } : {}, btn.label);
    b.addEventListener("click", async () => {
      try {
        const close = await btn.onClick?.();
        if (close !== false) dlg.close();
      } catch (e) { alert(e.message); }
    });
    actions.appendChild(b);
  }
  dlg.addEventListener("close", () => dlg.remove());
  document.body.appendChild(dlg);
  dlg.showModal();
  return { dialog: dlg, close: () => dlg.close() };
}
