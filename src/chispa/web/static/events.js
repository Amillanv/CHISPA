/* The right column: the list of events at the as-of time, and the record of one event.
   The record follows the questions of triage: where and how sure, is it moving, how did it get here,
   what do the sensors see now, what is near it. Each value is a field of the tool answer. */
import { esc, num, pct, utc, day, dur, coord, km, compass, FAMILY, FAMILY_ORDER, INPUT, PART, GOES_GROUP, GOES_NOTE } from "./format.js";
import { matrix } from "./matrix.js";
import { vitals, timeline } from "./timeline.js";

const RANK = { HIGH: 2, MEDIUM: 1, LOW: 0 };
const SORTS = {
  level: (a, b) => RANK[b.level] - RANK[a.level] || a.newest_observation_age_h - b.newest_observation_age_h,
  newest: (a, b) => a.newest_observation_age_h - b.newest_observation_age_h,
  size: (a, b) => b.detections - a.detections,
};

export function list(root, { events, sort, filter, selectedId, asOf, sinceHours, on }) {
  const count = (l) => events.filter((e) => e.level === l).length;
  const shown = events.filter((e) => filter.has(e.level)).sort(SORTS[sort]);
  const chips = ["HIGH", "MEDIUM", "LOW"].map((l) => `<button type="button" class="chip" data-filter="${l}" data-level="${l}" aria-pressed="${filter.has(l)}"><span class="swatch"></span>${l}<b>${count(l)}</b></button>`).join("");
  const sorts = Object.keys(SORTS).map((s) => `<button type="button" data-sort="${s}" aria-pressed="${s === sort}">${s[0].toUpperCase()}${s.slice(1)}</button>`).join("");
  const rows = shown.map((e) => row(e, e.event_id === selectedId)).join("");
  root.innerHTML = `
    <div class="list-head">
      <div class="top"><h2>Events <span class="num">${num(events.length)}</span></h2><div class="seg" title="Sequence">${sorts}</div></div>
      <div class="lede">With a new detection in the ${sinceHours} h to ${utc(asOf)} UTC</div>
      <div class="filters">${chips}</div>
    </div>
    <div class="rows">${rows || empty(events.length)}</div>`;
  root.querySelectorAll("[data-sort]").forEach((b) => b.addEventListener("click", () => on.sort(b.dataset.sort)));
  root.querySelectorAll("[data-filter]").forEach((b) => b.addEventListener("click", () => on.filter(b.dataset.filter)));
  root.querySelectorAll(".row").forEach((r) => {
    const id = Number(r.dataset.id);
    r.addEventListener("click", () => on.select(id));
    r.addEventListener("mouseenter", () => on.hover(id));
    r.addEventListener("mouseleave", () => on.hover(null));
  });
  root.querySelector(".row.selected")?.scrollIntoView({ block: "nearest" });
}

function empty(total) {
  if (total) return `<div class="empty-state">The filters hide all ${num(total)} events. Select a level to show them.</div>`;
  return `<div class="empty-state">No event has a new detection in this window. No detection is not "no fire".</div>`;
}

function row(e, selected) {
  const fams = FAMILY_ORDER.filter((f) => e.sensor_families.includes(f)).map((f) => `<span class="fam" style="--fam:var(--${f})">${FAMILY[f]}</span>`).join("");
  const power = e.max_frp_mw === null ? "" : ` · ${num(e.max_frp_mw)} MW`;
  return `<div class="row${selected ? " selected" : ""}" data-id="${e.event_id}" data-level="${e.level}">
    <span class="where">${coord(e.lat, e.lon)}</span>
    <span class="age" title="Newest detection before the as-of time">${dur(e.newest_observation_age_h)}</span>
    <span class="facts"><span class="lv">${e.level}</span> · ${num(e.detections)} det. · ${dur(e.hours_from_first_detection)} old${power}</span>
    ${daysSpark(e.timeline)}
    <span class="fams">${fams}</span>
  </div>`;
}

function daysSpark(timeline) {
  const days = timeline.slice(-12), most = Math.max(1, ...days.map((d) => d.detections));
  const w = 56 / 12;
  const bars = days.map((d, n) => {
    const h = 2 + 16 * (Math.log1p(d.detections) / Math.log1p(most));
    return `<rect x="${(12 - days.length + n) * w}" y="${20 - h}" width="${w - 1}" height="${h}" fill="var(--lv)" fill-opacity="${n === days.length - 1 ? 0.95 : 0.4}"/>`;
  }).join("");
  return `<svg width="56" height="20" viewBox="0 0 56 20" aria-label="Detections of each day">${bars}</svg>`;
}

export function dossier(root, { record, error, trackRecord, settings, open, zone, all, on }) {
  if (error) { root.innerHTML = `${top(null, on)}<div class="loading">${esc(error)}</div>`; wireTop(root, on); return; }
  if (!record) { root.innerHTML = `${top(null, on)}<div class="loading">Reading the event record.</div>`; wireTop(root, on); return; }
  const r = record;
  const tz = zone === "local" ? settings.time_zone : null;
  root.innerHTML = `${top(r, on)}
    <div class="dz-scroll">
      <div class="dz-head" data-level="${r.level}">
        <span class="dz-level"><i></i>${r.level}</span>
        <div class="dz-where">${coord(r.lat, r.lon)}</div>
        <div class="dz-brief">${brief(r)}</div>
        <div class="seg dz-zone" title="The zone of each time of this event">${zoneButtons(zone)}</div>
        ${vitals(r, tz)}
        ${r.notes.map((n) => `<div class="flag">${esc(n)}</div>`).join("")}
      </div>
      ${triage(r, trackRecord, settings, open)}
      ${growth(r, settings)}
      ${timeline(r, tz, all, settings.live_start)}
      ${sensorsNow(r)}
      ${place(r)}
      ${detections(r)}
    </div>`;
  wireTop(root, on);
  root.querySelectorAll("[data-tile]").forEach((b) => b.addEventListener("click", () => on.tile(b.dataset.tile)));
  root.querySelectorAll("[data-zone]").forEach((b) => b.addEventListener("click", () => on.zone(b.dataset.zone)));
  root.querySelectorAll("[data-passes]").forEach((b) => b.addEventListener("click", on.passes));
}

function top(r, on) {
  return `<div class="dz-top"><button class="back" type="button" data-back>← Events</button>
    <span class="dz-id">${r ? `Event ${r.event_id}` : ""}</span><button class="ghost" type="button" data-zoom ${r ? "" : "disabled"}>Zoom</button></div>`;
}

function wireTop(root, on) {
  root.querySelector("[data-back]").addEventListener("click", on.back);
  root.querySelector("[data-zoom]").addEventListener("click", on.zoom);
}

function brief(r) {
  const names = FAMILY_ORDER.filter((f) => r.sensor_families.includes(f)).map((f) => FAMILY[f]);
  const families = names.length > 1 ? `${names.slice(0, -1).join(", ")} and ${names.at(-1)}` : names[0];
  return `${num(r.detections)} ${r.detections === 1 ? "detection" : "detections"} from ${families}.`;
}

function triage(r, trackRecord, settings, open) {
  const out = r.notes.some((n) => n.includes("not in the Pantanal biome"));
  const share = trackRecord?.events.find((x) => x.final_level === r.level);
  const levelNote = out ? "No check of the level for this place." : share
    ? `${pct(Number(share.matched_share))} of the ${num(Number(share.events))} events with final level ${r.level} in ${trackRecord.year} matched a mapped fire.` : "";
  const c = r.confidence, s = r.severity;
  const rankNote = !c ? "No rank. The record says why." : out ? "No check for this place."
    : `Above ${pct(c.rank)} of ${num(c.reference_alerts)} alerts of ${settings.confidence_year}, at ${dur(settings.confidence_moments_h[c.model_moment_h])}.`;
  const sevNote = s ? "A heuristic. Not a forecast." : "No severity. The record says why.";
  const tiles = `<div class="triage">
    <button class="tile" type="button" data-tile="level" aria-expanded="${open === "level"}" data-level="${r.level}">
      <span class="label">Level</span><span class="v" style="color:var(--lv)">${r.level}</span><span class="c">${levelNote}</span></button>
    <button class="tile" type="button" data-tile="rank" aria-expanded="${open === "rank"}">
      <span class="label">Rank</span><span class="v">${c ? c.rank.toFixed(2) : "–"}</span>
      <span class="meter"><i style="width:${c ? pct(c.rank, 1) : 0}"></i></span><span class="c">${rankNote}</span></button>
    <button class="tile" type="button" data-tile="severity" aria-expanded="${open === "severity"}">
      <span class="label">Severity</span><span class="v">${s ? num(s.value) : "–"}<small>/ 100</small></span>
      <span class="meter"><i style="width:${s ? s.value : 0}%"></i></span><span class="c">${sevNote}</span></button>
  </div>`;
  return tiles + (open ? explain(open, r, settings) : "");
}

function explain(open, r, settings) {
  if (open === "level") {
    return `<div class="explain"><div class="label">How the level rises</div><div class="note" style="color:var(--fg-2)">
      LOW: one pass with low or nominal source confidence. MEDIUM: a high source confidence, or two passes of one sensor family.
      HIGH: passes from two or more sensor families. The level counts evidence. It does not give the size of a fire.
      The share in the tile is for the level at the end of the year. An event that is LOW now can rise later.</div></div>`;
  }
  if (open === "rank" && r.confidence) {
    const most = Math.max(...r.confidence.largest_effects.map((e) => Math.abs(e.effect)), 1);
    const rows = r.confidence.largest_effects.map((e) => {
      const width = (Math.abs(e.effect) / most) * 50;
      return `<div class="effect"><span>${INPUT[e.input] ?? esc(e.input)}</span><span class="axis"><i class="${e.effect >= 0 ? "up" : "down"}" style="width:${width}%"></i></span>
        <span class="n">${e.effect >= 0 ? "+" : "−"}${Math.abs(e.effect).toFixed(2)}</span></div>`;
    }).join("");
    const [early, late] = ["0", "24"].map((m) => dur(settings.confidence_moments_h[m]));
    return `<div class="explain"><div class="label" style="margin-bottom:10px">Inputs with the largest effect</div><div class="effects">${rows}</div>
      <p class="note">A rank, not a probability. It puts alerts in a sequence by their chance to match a mapped fire.
      The model was checked only ${early} and ${late} after the first detection of an alert.</p></div>`;
  }
  if (open === "severity" && r.severity) {
    const rows = Object.entries(r.severity.points).map(([name, points]) => {
      const max = settings.severity_points[name];
      const cells = Array.from({ length: max }, (_, k) => `<i class="${k < Math.round(points) ? "on" : ""}"></i>`).join("");
      return `<div class="part"><span>${PART[name]}</span><span class="cells" style="--max:${max}">${cells}</span><span class="n">${num(points)} <small>/ ${max}</small></span></div>`;
    }).join("");
    return `<div class="explain"><div class="label" style="margin-bottom:10px">Points of each part</div><div class="parts">${rows}</div>
      <p class="note">In 2024 the number did not say more about the burned area than a count of detections. It is a heuristic.</p></div>`;
  }
  return "";
}

function growth(r, settings) {
  const steps = r.growth_steps, newest = r.growth, floor = settings.growth_floor_m;
  const moved = steps.filter((s) => s.direction_deg !== null);
  const last = moved.at(-1);
  let read;
  if (!newest) {
    read = `<div class="big quiet">No step yet</div><p class="note">Less than two VIIRS passes saw this event. A GOES pixel is too large for a step.</p>`;
  } else if (newest.direction_deg !== null) {
    const speed = newest.speed_m_h === null ? `– <span class="muted">step under ${settings.growth_speed_min_h} h</span>` : `${num(newest.speed_m_h)} m/h`;
    read = `<div class="big">${km(newest.advance_m)} <span class="muted">${compass(newest.direction_deg)}</span></div>
      <dl><dt>Direction</dt><dd>${newest.direction_deg}°</dd><dt>New pixels</dt><dd>${newest.new_pixels}</dd>
      <dt>Step</dt><dd>${dur(newest.hours_from_the_pass_before)}</dd><dt>Speed</dt><dd>${speed}</dd><dt>Pass</dt><dd>${short(newest.at)}</dd></dl>`;
  } else {
    read = `<div class="big quiet">No measured advance</div>
      <dl><dt>Newest step</dt><dd>${short(newest.at)}</dd><dt>From the pass before</dt><dd>${dur(newest.hours_from_the_pass_before)}</dd>
      <dt>Last advance</dt><dd>${last ? `${km(last.advance_m)} ${compass(last.direction_deg)}` : "none"}</dd>${last ? `<dt>At</dt><dd>${short(last.at)}</dd>` : ""}</dl>`;
  }
  return `<div class="block"><div class="label"><span>Measured growth</span><span>${moved.length} of ${steps.length} steps past ${num(floor)} m</span></div>
    <div class="growth">${matrix(steps, floor)}<div class="read">${read}</div></div>
    <p class="note">Steps between VIIRS passes, north up, log scale. The dashed ring is the floor of ${num(floor)} m:
    a movement less than the floor cannot be told apart from the error of the positions. "No measured advance" does not say
    that the fire did not move. A ray is a past step, not a forecast. The speed has no reference.</p></div>`;
}

function zoneButtons(zone) {
  return [["local", "Pantanal"], ["utc", "UTC"]].map(([key, name]) => `<button type="button" data-zone="${key}" aria-pressed="${zone === key}">${name}</button>`).join("");
}

/* "2024-09-10T05:01:00+00:00" -> "09-10 05:01". */
function short(text) {
  return `${day(text)} ${utc(text, false)}`;
}

function sensorsNow(r) {
  const g = r.goes_view;
  const goes = g ? `${GOES_GROUP[g.group] ?? esc(g.group)}<small>${GOES_NOTE[g.group] ?? ""}. Pixel at the centre, scan ${utc(g.scan_at)} UTC.</small>${goesAfter(g)}` : `–<small>no saved scan for this time</small>`;
  const n = r.viirs_passes_after_last_detection;
  const viirs = n === null ? `–<small>no pass list for this year</small>` : `${n === 0 ? "No pass" : `${n} ${n === 1 ? "pass" : "passes"}`} after the newest detection<small>${n ? "with no detection of this event" : "since the newest detection"}</small>`;
  return `<div class="block"><div class="label"><span>What the sensors see now</span></div>
    <div class="see"><div><span class="who">GOES</span><span class="what">${goes}</span></div><div><span class="who">VIIRS</span><span class="what">${viirs}</span></div></div>
    <p class="note">One pixel. "Examined, no fire" does not say that the fire is out: GOES can miss a small fire, and cloud and smoke can hide it.</p></div>`;
}

/* What GOES said in each saved scan after the newest detection: "11 scans after the newest detection: 11 could not decide." */
function goesAfter(g) {
  const counts = Object.entries(g.after_last_detection).sort((a, b) => b[1] - a[1]);
  const total = counts.reduce((sum, [, n]) => sum + n, 0);
  if (!total) return `<small>No saved scan after the newest detection.</small>`;
  const parts = counts.map(([group, n]) => `${num(n)} ${GOES_GROUP[group] ?? esc(group)}`).join(" · ");
  return `<small>${num(total)} saved ${total === 1 ? "scan" : "scans"} after the newest detection: ${parts}.</small>`;
}

function place(r) {
  const f = r.severity?.facts;
  if (!f) return "";
  const land = (name, distance) => (name ? `${esc(name)}<small>${distance === 0 ? "a detection is in it" : `${num(distance, 1)} km`}</small>` : "–");
  return `<div class="block"><div class="label"><span>Place</span><span>layers of the severity</span></div>
    <dl class="facts-list">
      <dt>Land cover</dt><dd>${f.cover ? `${esc(f.cover)}<small>${pct(f.cover_share)} of the detections</small>` : "–<small>no class in the map</small>"}</dd>
      <dt>People</dt><dd><span class="mono">${num(f.people_near)}</span><small>in approximately 10 km around a detection</small></dd>
      <dt>Indigenous land</dt><dd>${land(f.indigenous_name, f.indigenous_km)}</dd>
      <dt>Protected land</dt><dd>${land(f.protected_name, f.protected_km)}</dd>
      <dt>Extent</dt><dd><span class="mono">${num(f.extent_km, 1)} km</span><small>longer side of the box of the detections</small></dd>
      <dt>Fire power</dt><dd><span class="mono">${f.max_frp_mw === null ? "–" : `${num(f.max_frp_mw)} MW`}</span><small>largest FRP</small></dd>
    </dl></div>`;
}

function detections(r) {
  const rows = r.newest_detections.map((d) => `<tr><td>${utc(d.observed_at)}</td><td>${FAMILY[d.sensor_family]} ${esc(d.platform)}</td><td>${esc(d.source)}</td><td>${d.frp_mw === null ? "–" : num(d.frp_mw, 1)}</td></tr>`).join("");
  return `<div class="block"><details class="raw"><summary class="label">Newest detections <span>${r.newest_detections.length} of ${num(r.detections)}</span></summary>
    <table class="table"><thead><tr><th>Observed, UTC</th><th>Sensor</th><th>Source</th><th>FRP, MW</th></tr></thead><tbody>${rows}</tbody></table></details></div>`;
}
