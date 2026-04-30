import { api, el, clear, fmtTime } from "/static/common.js";
import { renderGroupedTable, actionButton } from "./ui.js";

const listEl = document.getElementById("questions-list");
const detailPanel = document.getElementById("question-detail");
const detailBody = document.getElementById("question-detail-body");

export async function loadQuestions() {
  try {
    const qs = await api("/api/questions");
    render(qs);
  } catch (e) { listEl.textContent = "Error: " + e.message; }
}

function render(qs) {
  renderGroupedTable({
    container: listEl,
    items: qs,
    groupBy: (q) => q.block || "(unblocked)",
    emptyText: "No questions yet. Use the Czocha preset above, or add one manually.",
    columns: [
      { header: "",      cell: (q) => q.is_active ? el("span", { class: "status-pill ok" }, "active") : "", width: "60px" },
      { header: "#",     cell: (q) => el("span", { class: "muted" }, q.position ? String(q.position) : ""), width: "40px" },
      { header: "Text",  cell: (q) => q.text },
      { header: "Formation", cell: (q) => q.formation ? el("span", { class: "status-pill" }, q.formation) : "", width: "110px" },
      { header: "Actions",
        cell: (q) => [
          actionButton("Activate", { onClick: async () => { await api(`/api/questions/${q.id}/activate`, { method: "PUT" }); await loadQuestions(); } }),
          " ",
          actionButton("Results", { onClick: () => showDetail(q.id) }),
          " ",
          actionButton("×", {
            class: "danger",
            confirm: `Delete "${q.text}"? All votes will be removed.`,
            onClick: async () => {
              await api(`/api/questions/${q.id}`, { method: "DELETE" });
              detailPanel.hidden = true;
              await loadQuestions();
            },
          }),
        ],
        width: "240px",
      },
    ],
  });
}

async function showDetail(qid) {
  const sum = await api(`/api/questions/${qid}/summary`);
  detailPanel.hidden = false;
  clear(detailBody);
  detailBody.appendChild(el("h4", {}, sum.question.text));
  if (Object.keys(sum.latest_breakdown || {}).length) {
    detailBody.appendChild(el("p", {}, el("strong", {}, "Latest snapshot: ")));
    const ul = el("ul", {});
    for (const [k, v] of Object.entries(sum.latest_breakdown)) {
      ul.appendChild(el("li", {}, `${k}: ${v}`));
    }
    detailBody.appendChild(ul);
  }
  if (sum.snapshots.length === 0) {
    detailBody.appendChild(el("div", { class: "muted" }, "No snapshots recorded yet."));
    return;
  }
  for (const s of sum.snapshots) {
    const block = el("div", { class: "panel", style: { marginTop: "8px", background: "var(--panel-2)" } });
    block.appendChild(el("div", {}, el("strong", {}, `Snapshot #${s.snapshot_id}`), " ", el("span", { class: "muted" }, fmtTime(s.recorded_at))));
    const counts = Object.entries(s.by_zone).map(([k, v]) => `${k}: ${v}`).join("  ·  ");
    block.appendChild(el("div", { class: "muted" }, counts));
    const tbl = el("table", {});
    tbl.appendChild(el("thead", {}, el("tr", {}, el("th", {}, "Marker"), el("th", {}, "Person"), el("th", {}, "Zone"))));
    const tb = el("tbody", {});
    for (const e of s.entries) {
      tb.appendChild(el("tr", {}, el("td", {}, "#" + e.aruco_id), el("td", {}, e.person || "—"), el("td", {}, e.zone || "—")));
    }
    tbl.appendChild(tb);
    block.appendChild(tbl);
    detailBody.appendChild(block);
  }
}

export function initQuestions() {
  document.getElementById("add-question-btn").addEventListener("click", async () => {
    const text = document.getElementById("question-text").value.trim();
    const block = document.getElementById("question-block").value.trim();
    const formation = document.getElementById("question-formation").value;
    if (!text) return;
    try {
      await api("/api/questions", { method: "POST", body: { text, block, formation } });
      document.getElementById("question-text").value = "";
      await loadQuestions();
    } catch (e) { alert(e.message); }
  });
  document.getElementById("load-czocha-btn").addEventListener("click", async () => {
    if (!confirm("Load the Czocha Day 1 deck? Existing rows in the same blocks will be replaced.")) return;
    try {
      const res = await api("/api/questions/seed/czocha-day-1?replace=true&include_zones=true", { method: "POST", body: {} });
      await loadQuestions();
      alert(`Loaded ${res.questions.length} questions and ${res.zones.length} zones.`);
    } catch (e) { alert(e.message); }
  });
}
