/* The history of one event: the headline numbers and the timeline of its passes.
   A row is one pass: when a satellite saw it, how long it took to reach CHISPA, and the alert it made.
   Each value is a field of the event record. This file formats the values. It adds no fact. */
import { esc, num, dur, hoursBetween, day, when, zoneLabel, zoneTag, FAMILY, GOES_GROUP, ANSWER } from "./format.js";

const FOLDED = 10; // the newest passes that the folded timeline shows, with each pass that made an alert
const RUNS_FOLDED = 4; // the newest runs of GOES scans that the folded timeline shows, with each run of fire


/* The four numbers of triage time: age, the delay of the first alert, the last detection and the last clear look. */
export function vitals(r, zone) {
  const newest = r.newest_detections[0];
  // The rows are in the sequence of observation: the pass of the first alert is the pass with the earliest alert.
  const raised = r.passes.filter((p) => p.alerts.length);
  const first = raised.length ? raised.reduce((a, b) => (b.alerts[0].at < a.alerts[0].at ? b : a)) : null;
  const delay = first ? hoursBetween(first.observed_at, first.alerts[0].at) : null;
  const seen = newest ? `${FAMILY[newest.sensor_family]} ${esc(newest.platform)}, ` : "";
  return `<div class="vitals">
    <div><span class="label">Age, at least</span><span class="v">${dur(r.hours_from_first_detection)}</span>
      <span class="c">first seen ${when(r.first_observed_at, zone)}</span></div>
    <div><span class="label">First alert</span><span class="v${first?.poller_stop_h ? " stop" : ""}">${delay === null ? "–" : `+${dur(delay)}`}</span>
      <span class="c">after its pass ${first ? kind(first) : ""}</span></div>
    <div><span class="label">Last seen</span><span class="v">${dur(r.newest_observation_age_h)} ago</span>
      <span class="c">${seen}${when(r.last_observed_at, zone)}</span></div>
    ${clearLook(r, zone)}
  </div>`;
}

/* Measured or estimated. A measured time can include a stop of the poller: up to that time is our delay, not the delay of the source. */
function kind(p) {
  if (p.estimated) return `<span class="kind est">estimated</span>`;
  if (p.poller_stop_h) return `<span class="kind stop">up to ${dur(p.poller_stop_h)} is a stop of the poller</span>`;
  return `<span class="kind">measured</span>`;
}

/* The newest GOES scan after the last detection that examined the place and found no fire (`goes_view`). */
function clearLook(r, zone) {
  const g = r.goes_view;
  const total = g?.scans_after_last_detection ?? 0;
  const clear = g?.after_last_detection.no_fire ?? 0;
  let value = "–", note = "no saved GOES scan for this time";
  if (g && g.newest_no_fire_at) {
    value = `${dur(hoursBetween(g.newest_no_fire_at, r.as_of))} ago`;
    note = `GOES: examined, no fire, ${when(g.newest_no_fire_at, zone)}. ${num(clear)} of ${num(total)} scans since last seen`;
  } else if (g && !total) {
    value = "not yet";
    note = "no GOES scan after the last detection yet";
  } else if (g) {
    value = "none";
    note = `none of ${num(total)} GOES ${total === 1 ? "scan" : "scans"} since last seen said "examined, no fire"`;
  }
  return `<div title="The newest GOES scan after the last detection in which GOES examined the place and found no fire. It does not say that the fire is out: GOES can miss a small fire.">
    <span class="label">Last clear look</span><span class="v">${value}</span><span class="c">${note}</span></div>`;
}

export function timeline(r, zone, all, liveStart) {
  const rows = r.passes;
  const shown = new Set(all ? rows : rows.filter((p, n) => p.alerts.length || n >= rows.length - FOLDED));
  const parts = [];
  let last = -1;
  rows.forEach((p, n) => {
    if (!shown.has(p)) return;
    if (n - last > 1) parts.push(`<button type="button" class="more" data-passes>${n - last - 1} more ${n - last - 1 === 1 ? "pass" : "passes"}</button>`);
    parts.push(row(p, zone));
    last = n;
  });
  parts.push(...runs(r, zone, all));
  const head = `<div class="pass head"><span>Observed</span><span>Sensor</span><span>To CHISPA</span><span>MW</span><span>Alert</span></div>`;
  return `<div class="block"><div class="label"><span>Timeline</span><span>${rows.length} of ${num(r.pass_count)} passes · ${zoneLabel(zone, r.first_observed_at)}</span></div>
    <div class="passes">${head}${parts.join("")}</div>
    ${absorbed(r, zone)}
    ${days(r)}
    <p class="note">The rows are in the sequence of observation. A pass is one GOES scan with a detection, or one pass of
    another satellite. MW is its largest fire power. "To CHISPA" is the time from the observation
    to the moment that CHISPA had the pass, and thus made its alert. From ${when(liveStart, zone)} ${zoneTag(zone)} it is measured by the poller.
    Before, it is an estimate. A time in yellow includes a stop of the poller: up to the time of the stop is our delay.
    The time when a source published a pass is not in the record. After the last detection, a GOES row is a run of
    saved scans with one answer for the place of the last detection. "Could not see" is cloud, no decision or glint.</p></div>`;
}

/* The rows after the last detection: the saved GOES scans, one row for each run of one answer (`goes_view`).
   Folded: each run of fire or possible fire, and the newest runs. No row if no scan came after the last detection. */
function runs(r, zone, all) {
  const list = r.goes_view?.runs_after_last_detection ?? [];
  const fire = (run) => run.answer === "fire" || run.answer === "possible_fire";
  const rows = [];
  let hidden = 0;
  list.forEach((run, n) => {
    if (!all && !fire(run) && n < list.length - RUNS_FOLDED) { hidden += 1; return; }
    if (hidden) rows.push(`<button type="button" class="more" data-passes>${hidden} more GOES ${hidden === 1 ? "row" : "rows"}</button>`);
    hidden = 0;
    rows.push(runRow(run, r.goes_view.newest_no_fire_at, zone));
  });
  return rows;
}

function runRow(run, clear, zone) {
  const groups = Object.entries(run.groups);
  const detail = run.answer === "not_seen"
    ? ` (${groups.length === 1 ? GOES_GROUP[groups[0][0]] : groups.map(([g, n]) => `${num(n)} ${GOES_GROUP[g] ?? esc(g)}`).join(" · ")})` : "";
  const span = run.scans === 1 ? "" : `${num(run.scans)} scans to ${when(run.to, zone)}: `;
  const look = run.to === clear ? " · last clear look" : "";
  const title = `GOES scans from ${when(run.from, zone)} to ${when(run.to, zone)} ${zoneTag(zone)} at the place of the last detection. `
    + `"Examined, no fire" is for each pixel of that place. It does not say that the fire is out: GOES can miss a small fire.`;
  return `<div class="pass run ${run.answer}" title="${title}">
    <span class="t">${when(run.from, zone)}</span>
    <span class="s"><i style="background:var(--abi)"></i>GOES</span>
    <span class="x">${span}${ANSWER[run.answer]}${detail}${look}</span></div>`;
}

function row(p, zone) {
  const hours = hoursBetween(p.observed_at, p.available_at);
  const width = Math.min(100, (Math.log1p(hours * 60) / Math.log1p(24 * 60)) * 100);
  const stop = p.poller_stop_h ? ` For ${dur(p.poller_stop_h)} of this time the poller did not read the source. The source can have published at any time in that stop.` : "";
  const at = (time) => `${when(time, zone)} ${zoneTag(zone)}`;
  const alerts = p.alerts.length ? ` Alerts: ${p.alerts.map((a) => `${a.level} at ${at(a.at)}`).join(", ")}.` : "";
  const title = `${p.detections} ${p.detections === 1 ? "detection" : "detections"}. Observed ${at(p.observed_at)}. `
    + `CHISPA had it ${at(p.available_at)}${p.estimated ? ": an estimate" : ""}.${stop}${alerts} The largest fire power: `
    + `${p.max_frp_mw === null ? "not given" : `${num(p.max_frp_mw, 1)} MW`}.`;
  const levels = p.alerts.map((a) => `<span data-level="${a.level}">${a.level}</span>`).join(`<i>→</i>`);
  return `<div class="pass${p.alerts.length ? " raised" : ""}" title="${title}">
    <span class="t">${when(p.observed_at, zone)}</span>
    <span class="s"><i style="background:var(--${p.sensor_family})"></i>${esc(p.platform)}</span>
    <span class="lag${p.estimated ? " est" : ""}${p.poller_stop_h ? " stop" : ""}"><span class="track"><b style="width:${width.toFixed(0)}%"></b></span><em>+${dur(hours)}</em></span>
    <span class="n">${p.max_frp_mw === null ? "–" : num(p.max_frp_mw)}</span>
    <span class="a">${levels}</span></div>`;
}

function absorbed(r, zone) {
  if (!r.absorbed.length) return "";
  const items = r.absorbed.map((m) => `<li><span class="mono">${when(m.at, zone)}</span> alert ${m.alert_id} joined ${m.into_id}</li>`).join("");
  return `<details class="absorbed"><summary>Absorbed ${num(r.absorbed.length)} ${r.absorbed.length === 1 ? "alert" : "alerts"}:
    ${when(r.absorbed[0].at, zone)} to ${when(r.absorbed.at(-1).at, zone)}</summary><ul>${items}</ul></details>`;
}

function days(r) {
  const list = r.timeline.slice(-30), most = Math.max(1, ...list.map((d) => d.detections));
  const bars = list.map((d) => `<span style="height:${(8 + 92 * Math.log1p(d.detections) / Math.log1p(most)).toFixed(0)}%" title="${d.day}: ${num(d.detections)} detections, ${d.sensor_families.map((f) => FAMILY[f]).join(", ")}"></span>`).join("");
  return `<div class="days">${bars}</div><div class="days-axis"><span>${day(list[0].day, null)}</span><span>detections of each UTC day${r.timeline.length > 30 ? ", last 30" : ""}</span><span>${day(list.at(-1).day, null)}</span></div>`;
}
