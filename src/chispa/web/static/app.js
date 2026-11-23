/* The page: the state, the requests to the routes, and the drawing of each part.
   The as-of time is the one control of the page. Live: the as-of time is now and moves each few minutes.
   Replay: a recorded moment. The history band can move the as-of time back inside its window. */
import { MapView } from "./map.js";
import { History } from "./history.js";
import * as panels from "./panels.js";
import { list, dossier } from "./events.js";
import { esc, dur, coord, num } from "./format.js";
import { drawClock, tick } from "./clock.js";

const $ = (id) => document.getElementById(id);
const state = {
  settings: null, live: true, anchor: null, asOf: null, windowIndex: 1,
  events: [], day: null, activity: null, past: null, pass: null, years: {}, year: null, ladderZone: "utc",
  selectedId: null, record: null, recordError: null, open: null, view: "list",
  sort: "level", filter: new Set(["HIGH", "MEDIUM", "LOW"]),
};
const tickets = { moment: 0, window: 0, record: 0 };
let map, band, busy = 0, fly = false;

async function get(path, params = {}) {
  const url = new URL(path, location.origin);
  for (const [name, value] of Object.entries(params)) url.searchParams.set(name, value);
  $("progress").hidden = ++busy === 0;
  try {
    const answer = await fetch(url);
    const body = await answer.json();
    if (!answer.ok) throw new Error(body.error ?? `The server answered ${answer.status}.`);
    return body;
  } finally {
    $("progress").hidden = --busy === 0;
  }
}

function now() {
  const d = new Date();
  d.setUTCSeconds(0, 0);
  return d.toISOString().replace(".000Z", "Z");
}

async function init() {
  state.settings = await get("/api/settings");
  state.year = state.settings.test_year;
  readUrl();
  map = new MapView($("map"), state.settings, { select: (id) => select(id, true), hover: hoverFromMap });
  band = new History($("history"), { asOf: moveAsOf, window: changeWindow });
  if (!state.settings.map_key) $("readout").textContent = "No map key. Write MAPTILER_KEY in the file .env.";
  wireBar();
  loadYears();
  state.live ? goLive() : (loadWindow(), loadMoment());
  setInterval(() => { if (state.live) goLive(); }, state.settings.refresh_s * 1000);
  setInterval(() => tick(state), 1000);
  new ResizeObserver(() => map.resize()).observe(document.body);
}

function goLive() {
  state.live = true;
  state.anchor = state.asOf = now();
  loadWindow();
  loadMoment();
}

function replay(iso) {
  state.live = false;
  state.anchor = state.asOf = iso;
  loadWindow();
  loadMoment();
}

function moveAsOf(iso) {
  state.live = false;
  state.asOf = iso;
  state.past = null;
  loadMoment();
  drawHistory();
}

/* A new window ends at the as-of time. Thus its steps stay on the step ends of the as-of time. */
function changeWindow(n) {
  state.windowIndex = n;
  state.anchor = state.asOf;
  state.past = null;
  loadWindow();
  writeUrl();
}

/* The steps from the start of the window to the as-of time, with the events of the as-of time.
   None when the as-of time is the end of the window: then the window answer is already that. */
function pastParams() {
  const w = state.settings.windows[state.windowIndex];
  const hours = w.hours - (new Date(state.anchor) - new Date(state.asOf)) / 3_600_000;
  return hours > 0 && hours < w.hours ? { as_of: state.asOf, hours, step_hours: w.step_hours } : null;
}

async function loadWindow() {
  const ticket = ++tickets.window;
  const w = state.settings.windows[state.windowIndex];
  try {
    const activity = await get("/api/activity", { as_of: state.anchor, hours: w.hours, step_hours: w.step_hours });
    if (ticket === tickets.window) { state.activity = activity; drawHistory(); }
  } catch (error) { console.error(error); }
}

async function loadMoment() {
  const ticket = ++tickets.moment;
  drawClock(state);
  writeUrl();
  try {
    const past = pastParams();
    const [alerts, day, steps, pass] = await Promise.all([
      get("/api/alerts", { as_of: state.asOf }),
      get("/api/activity", { as_of: state.asOf, hours: 24, step_hours: 1 }),
      past ? get("/api/activity", past) : null,
      get("/api/live", { as_of: state.asOf }),
    ]);
    if (ticket !== tickets.moment) return;
    state.pass = pass;
    tick(state);
    state.events = alerts.events;
    state.day = day;
    state.past = steps;
    drawHistory();
    map.setEvents(state.events);
    drawLeft();
    drawRight();
    if (state.selectedId) { loadRecord(fly); fly = false; }
  } catch (error) {
    $("right").innerHTML = `<div class="loading">${esc(error.message)}</div>`;
  }
}

async function loadRecord(move) {
  const ticket = ++tickets.record;
  state.recordError = null;
  try {
    const record = await get(`/api/event/${state.selectedId}`, { as_of: state.asOf });
    if (ticket !== tickets.record) return;
    state.record = record;
    state.selectedId = record.event_id;
    map.select(record, move);
    map.setDetections(record.newest_detections);
  } catch (error) {
    if (ticket !== tickets.record) return;
    state.record = null;
    state.recordError = error.message;
    map.select(null);
  }
  writeUrl();
  drawRight();
  drawHistory();
}

async function loadYears() {
  for (const year of state.settings.evaluated_years) {
    try { state.years[year] = await get(`/api/evaluation/${year}`); } catch (error) { console.error(error); }
  }
  drawRecordCard();
  drawRight();
}

function select(id, move) {
  if (id === null || id === undefined) return;
  state.selectedId = id;
  state.view = "dossier";
  state.record = null;
  state.open = null;
  const row = state.events.find((e) => e.event_id === id);
  if (row) map.select(row, move);
  drawRight();
  loadRecord(false);
}

function back() {
  state.view = "list";
  state.selectedId = null;
  state.record = null;
  map.select(null);
  writeUrl();
  drawRight();
  drawHistory();
}

function drawLeft() {
  panels.situation($("situation"), { events: state.events, day: state.day, asOf: state.asOf, sinceHours: state.settings.since_hours });
  panels.sensors($("sensors"), { day: state.day, asOf: state.asOf });
}

function drawRecordCard() {
  panels.record($("record"), {
    summary: state.years[state.year], years: state.settings.evaluated_years, year: state.year,
    onYear: (year) => { state.year = year; drawRecordCard(); }, onLimits: openLimits,
  });
}

function drawRight() {
  if (state.view === "dossier") {
    dossier($("right"), {
      record: state.record, error: state.recordError, trackRecord: state.years[state.settings.test_year], settings: state.settings, open: state.open, zone: state.ladderZone,
      on: {
        back, zoom: () => state.record && map.select(state.record, true),
        tile: (name) => { state.open = state.open === name ? null : name; drawRight(); },
        zone: (zone) => { state.ladderZone = zone; drawRight(); },
      },
    });
    return;
  }
  list($("right"), {
    events: state.events, sort: state.sort, filter: state.filter, selectedId: state.selectedId, asOf: state.asOf, sinceHours: state.settings.since_hours,
    on: {
      select: (id) => select(id, true), hover: (id) => map.hover(id),
      sort: (sort) => { state.sort = sort; drawRight(); },
      filter: (level) => { state.filter.has(level) ? state.filter.delete(level) : state.filter.add(level); drawRight(); },
    },
  });
}

function drawHistory() {
  band.set({ activity: state.activity, past: state.past, asOf: state.asOf, windows: state.settings.windows, windowIndex: state.windowIndex, record: state.view === "dossier" ? state.record : null });
}

function hoverFromMap(id, mouse) {
  const tip = $("tip");
  map.hover(id);
  document.querySelectorAll(".row.hover").forEach((r) => r.classList.remove("hover"));
  const e = id === null ? null : state.events.find((x) => x.event_id === id);
  if (!e || !mouse) { tip.hidden = true; return; }
  document.querySelector(`.row[data-id="${id}"]`)?.classList.add("hover");
  tip.innerHTML = `<div data-level="${e.level}"><span class="swatch"></span><b>${e.level}</b> · <span class="mono">${coord(e.lat, e.lon)}</span></div>
    <div>${num(e.detections)} detections · newest ${dur(e.newest_observation_age_h)} before</div>`;
  tip.style.left = `${mouse.clientX + 14}px`;
  tip.style.top = `${mouse.clientY + 14}px`;
  tip.hidden = false;
}

function openLimits() {
  const summary = state.years[state.year];
  // A bullet of SUMMARY.md can go on in indented lines. Join them to their bullet.
  const bullets = [];
  for (const line of (summary?.limits ?? "").split("\n")) {
    if (line.startsWith("- ")) bullets.push(line.slice(2));
    else if (/^\s+\S/.test(line) && bullets.length) bullets[bullets.length - 1] += ` ${line.trim()}`;
  }
  const lines = bullets.map((b) => `<li>${esc(b)}</li>`).join("");
  $("limits-body").innerHTML = `
    <h3>This page</h3><ul>
      <li>The sources are satellites only. No camera detection and no report from a person.</li>
      <li>The base image is a mosaic from MapTiler. It is not an image of the as-of time.</li>
      <li>An event is a group of detections. One event is not always one fire: large fires can join into one event.</li>
      <li>The confidence rank is a rank, not a probability. The severity is a heuristic of priorities, not a forecast.</li>
      <li>Measured growth gives past steps between VIIRS passes. It is not a forecast. The speed has no reference.</li>
      <li>No detection is not "no fire". A sensor does not see through thick cloud.</li>
    </ul>
    <h3>The results, ${esc(summary?.year ?? "")}</h3><ul>${lines}</ul>`;
  $("limits").showModal();
}

function wireBar() {
  $("mode").addEventListener("click", () => { if (!state.live) goLive(); });
  $("replays").addEventListener("change", (e) => { if (e.target.value) replay(e.target.value); });
  $("limits-open").addEventListener("click", openLimits);
  $("limits-close").addEventListener("click", () => $("limits").close());
  $("drawer-toggle").addEventListener("click", () => $("left").classList.toggle("open"));
  $("fit").addEventListener("click", () => map.fit());
  $("zoom-in").addEventListener("click", () => map.zoom(1));
  $("zoom-out").addEventListener("click", () => map.zoom(-1));
  $("pitch").addEventListener("click", () => $("pitch").setAttribute("aria-pressed", map.toggleSolid()));
  document.querySelectorAll("[data-base]").forEach((b) => b.addEventListener("click", () => {
    document.querySelectorAll("[data-base]").forEach((x) => x.setAttribute("aria-pressed", x === b));
    map.setBase(b.dataset.base);
  }));
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && state.view === "dossier" && !$("limits").open) back(); });
}

function readUrl() {
  const params = new URLSearchParams(location.search);
  const asOf = params.get("as_of");
  if (asOf) { state.live = false; state.anchor = state.asOf = asOf; }
  const event = Number(params.get("event"));
  if (event) { state.selectedId = event; state.view = "dossier"; fly = true; }
  const windowIndex = Number(params.get("window"));
  if (windowIndex >= 0 && windowIndex < state.settings.windows.length && params.has("window")) state.windowIndex = windowIndex;
}

function writeUrl() {
  const params = new URLSearchParams();
  if (!state.live) params.set("as_of", state.asOf);
  if (state.selectedId) params.set("event", state.selectedId);
  if (state.windowIndex !== 1) params.set("window", state.windowIndex);
  window.history.replaceState(null, "", params.size ? `?${params}` : location.pathname);
}

init().catch((error) => { document.body.insertAdjacentHTML("beforeend", `<div class="tip" style="left:20px;top:60px">${esc(error.message)}</div>`); });
