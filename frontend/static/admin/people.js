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
}
