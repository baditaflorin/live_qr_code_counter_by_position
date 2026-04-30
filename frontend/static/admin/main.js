// Entry point for the Admin page. Wires the four tabs to their respective
// modules. Each module owns its own DOM section and exposes an `init()` to
// bind events plus a `loadX()` to (re)fetch and render.

import { api } from "/static/common.js";
import { initPeople, loadPeople } from "./people.js";
import { initMarkers, loadMarkers } from "./markers.js";
import { initZones, loadZones } from "./zones.js";
import { initQuestions, loadQuestions } from "./questions.js";

const TABS = {
  people:    { load: loadPeople },
  markers:   { load: loadMarkers },
  zones:     { load: loadZones },
  questions: { load: loadQuestions },
};

const tabBtns = document.querySelectorAll(".tabs button");
tabBtns.forEach((b) => b.addEventListener("click", () => activate(b.dataset.tab)));

function activate(name) {
  tabBtns.forEach((x) => x.classList.toggle("active", x.dataset.tab === name));
  for (const k of Object.keys(TABS)) {
    document.getElementById("tab-" + k).hidden = k !== name;
  }
  TABS[name]?.load();
}

// system info pill (Markers tab footer)
api("/api/system").then((s) => {
  const e = document.getElementById("dict-info");
  if (e) e.textContent = `dictionary: ${s.dictionary} (${s.dictionary_size} markers)`;
}).catch(() => {});

// boot
initPeople();
initMarkers();
initZones();
initQuestions();
loadPeople();
