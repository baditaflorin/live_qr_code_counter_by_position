import { api, el, fmtTime } from "/static/common.js";
import { renderGroupedTable, actionButton } from "./ui.js";

const peopleListEl = document.getElementById("people-list");

export async function loadPeople() {
  try {
    const people = await api("/api/people");
    render(people);
  } catch (e) {
    peopleListEl.textContent = "Error: " + e.message;
  }
}

function render(people) {
  renderGroupedTable({
    container: peopleListEl,
    items: people,
    groupBy: () => "All people",
    groupCount: true,
    emptyText: "No people yet.",
    columns: [
      { header: "Name",    cell: (p) => p.name },
      { header: "Notes",   cell: (p) => el("span", { class: "muted" }, p.notes || "") },
      { header: "Markers", cell: (p) => p.marker_ids.length ? p.marker_ids.map((id) => "#" + id).join(", ") : "—" },
      { header: "Created", cell: (p) => el("span", { class: "muted" }, fmtTime(p.created_at)), width: "180px" },
      { header: "Actions",
        cell: (p) => [
          actionButton("Assign new marker", { onClick: () => assignMarker(p) }),
          " ",
          actionButton("Download PDF", {
            onClick: () => {
              if (!p.marker_ids.length) { alert("No markers to print."); return; }
              window.open(`/api/markers/pdf?ids=${p.marker_ids.join(",")}`, "_blank");
            },
          }),
          " ",
          actionButton("Edit", { onClick: () => editPerson(p) }),
          " ",
          actionButton("Delete", {
            class: "danger",
            confirm: `Delete ${p.name}? Markers will be unassigned.`,
            onClick: async () => { await api(`/api/people/${p.id}`, { method: "DELETE" }); await loadPeople(); },
          }),
        ],
        width: "440px",
      },
    ],
  });
}

async function assignMarker(person) {
  const arr = await api("/api/markers/batch", { method: "POST", body: { count: 1, person_id: person.id } });
  await loadPeople();
  alert(`Created marker #${arr[0].aruco_id} for ${person.name}.`);
}

async function editPerson(p) {
  const name = prompt("Name", p.name);
  if (name == null) return;
  const notes = prompt("Notes", p.notes || "");
  await api(`/api/people/${p.id}`, { method: "PUT", body: { name, notes } });
  await loadPeople();
}

export function initPeople() {
  document.getElementById("add-person-btn").addEventListener("click", async () => {
    const name = document.getElementById("person-name").value.trim();
    const notes = document.getElementById("person-notes").value.trim();
    const withMarkers = Number(document.getElementById("person-with-markers").value || 0);
    if (!name) { alert("Name required"); return; }
    try {
      const p = await api("/api/people", { method: "POST", body: { name, notes } });
      if (withMarkers > 0) {
        await api("/api/markers/batch", { method: "POST", body: { count: withMarkers, person_id: p.id } });
      }
      document.getElementById("person-name").value = "";
      document.getElementById("person-notes").value = "";
      await loadPeople();
    } catch (e) { alert(e.message); }
  });

  // CSV roster import
  const fileInput = document.getElementById("roster-file");
  const conflictSel = document.getElementById("roster-conflict");
  const dryBtn = document.getElementById("roster-dry-run");
  const importBtn = document.getElementById("roster-import");
  const preview = document.getElementById("roster-preview");

  fileInput.addEventListener("change", () => {
    importBtn.disabled = !fileInput.files?.length;
    preview.textContent = fileInput.files?.length
      ? `Selected: ${fileInput.files[0].name} (${fileInput.files[0].size} bytes). Run a dry-run before importing.`
      : "";
  });

  async function postRoster(dryRun) {
    if (!fileInput.files?.length) return;
    const fd = new FormData();
    fd.append("file", fileInput.files[0]);
    fd.append("dry_run", dryRun ? "true" : "false");
    fd.append("on_conflict", conflictSel.value);
    preview.textContent = dryRun ? "Running dry run…" : "Importing…";
    try {
      const res = await fetch("/api/people/import", { method: "POST", body: fd });
      if (!res.ok) {
        const j = await res.json().catch(() => ({}));
        throw new Error(j.detail || `HTTP ${res.status}`);
      }
      const data = await res.json();
      renderOutcomes(data, dryRun);
      if (!dryRun) await loadPeople();
    } catch (e) { preview.textContent = "Error: " + e.message; }
  }

  function renderOutcomes(data, dryRun) {
    const counts = {};
    for (const o of data.outcomes) counts[o.status] = (counts[o.status] || 0) + 1;
    const summary = Object.entries(counts)
      .map(([k, v]) => `${k}: ${v}`).join("  ·  ");
    const head = `${dryRun ? "Dry run" : "Imported"} ${data.rows} rows  ·  ${summary}`;
    preview.innerHTML = "";
    preview.appendChild(el("div", { style: { fontWeight: 600, marginBottom: "6px" } }, head));
    // Show first 10 rows of outcomes for sanity check.
    const tbl = el("table", { style: { fontSize: "12px", maxHeight: "240px", overflow: "auto", display: "block" } });
    tbl.appendChild(el("thead", {}, el("tr", {},
      el("th", {}, "Row"), el("th", {}, "Name"), el("th", {}, "Status"),
      el("th", {}, "Person"), el("th", {}, "Markers"),
    )));
    const tb = el("tbody", {});
    for (const o of data.outcomes.slice(0, 50)) {
      tb.appendChild(el("tr", {},
        el("td", {}, String(o.row)),
        el("td", {}, o.name),
        el("td", {}, o.status),
        el("td", {}, o.person_id ? "#" + o.person_id : ""),
        el("td", {}, (o.marker_ids || o.would_create_markers ? (o.marker_ids?.join(", ") || `${o.would_create_markers} planned`) : "")),
      ));
    }
    tbl.appendChild(tb);
    preview.appendChild(tbl);
    if (data.outcomes.length > 50) {
      preview.appendChild(el("div", { class: "muted" }, `… and ${data.outcomes.length - 50} more`));
    }
  }

  dryBtn.addEventListener("click", () => postRoster(true));
  importBtn.addEventListener("click", () => postRoster(false));
}
