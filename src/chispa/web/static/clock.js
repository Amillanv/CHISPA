/* The clock in the bar: the mode, the time, the lag of the live data and the time zone of the page.
   The time is the as-of time in a replay, and the time now when live. Each time on the page is in the zone of the clock.
   The lag is the time from the newest pass of the poller (tool `live_status`) to the as-of time. */
import { stamp, zoned, zoneLabel, zoneTag, counter } from "./format.js";

const $ = (id) => document.getElementById(id);

/* The zone of the page: the IANA name of Pantanal time, or null for UTC. */
export function zoneOf(state) {
  return state.zone === "local" ? state.settings.time_zone : null;
}

export function drawClock(state) {
  const mode = $("mode"), zone = zoneOf(state);
  mode.className = `mode${state.live ? " live" : ""}`;
  mode.innerHTML = `<span class="dot"></span>${state.live ? "Live" : "Replay"}`;
  mode.title = state.live ? "The as-of time is now." : "Go back to live.";
  $("zone").innerHTML = [["local", "Pantanal"], ["utc", "UTC"]]
    .map(([key, name]) => `<button type="button" data-zone="${key}" aria-pressed="${state.zone === key}">${name}</button>`).join("");
  tick(state);
  const select = $("replays");
  const options = state.settings.replays.map((t) => `<option value="${t}"${!state.live && t === state.anchor ? " selected" : ""}>${stamp(t, zone)}</option>`).join("");
  select.innerHTML = `<option value="">Replay a moment (${zoneTag(zone)})</option>${options}`;
}

/* Each second: the time and the lag. Live: the time now, with seconds. Replay: the as-of time, with its year.
   The tool `live_status` gives the times. The page only compares them with its clock. */
export function tick(state) {
  const zone = zoneOf(state), live = state.live;
  const moment = live ? Date.now() : new Date(state.asOf).getTime();
  $("asof-label").textContent = `${live ? "Now" : "As-of"} · ${zoneLabel(zone, moment)}`;
  if (live) {
    const t = zoned(moment, zone ?? "UTC", true);
    $("asof").innerHTML = `<span class="d">${t.date}</span>${t.time}`;
  } else {
    $("asof").innerHTML = `<span class="d">${stamp(moment, zone).slice(0, 10)}</span>${stamp(moment, zone, false)}`;
  }
  $("lag-label").textContent = live ? "Lag" : "Lag at as-of";
  const [text, kind, title] = lag(state.pass, moment, zone);
  $("lag").textContent = text;
  $("lag-box").className = `reading lag${kind ? ` ${kind}` : ""}`;
  $("lag-box").title = title;
}

/* The text, the kind and the explanation of the lag, from the answer of `live_status`. */
function lag(pass, moment, zone) {
  if (pass === undefined) return ["–", "", "Reading the poll log."];
  if (pass === null) return ["unknown", "late", "The page could not read the status of the poller."];
  if (pass.archive) return ["archive", "archive", "Before the live logs. The store has archive data, with an estimate of when each detection became available."];
  if (!pass.complete_pass_at) return ["no pass", "late", "The poll log has no pass with no failure before this time."];
  const seconds = (moment - new Date(pass.complete_pass_at).getTime()) / 1000;
  return [counter(seconds), moment >= new Date(pass.late_at).getTime() ? "late" : "", passText(pass, zone)];
}

function passText(pass, zone) {
  const names = { firms: "FIRMS", goes: "GOES", inpe: "INPE" };
  const lines = Object.entries(pass.sources).map(([name, s]) => `${names[name] ?? name}: ${s.items - s.failed} of ${s.items} items answered, ${s.new_rows} new rows.`);
  for (const name of ["goes", "inpe"]) {
    if (!pass.sources[name]) lines.push(`${names[name]}: no row. No new item was read and no failure was recorded.`);
  }
  const at = (time) => `${stamp(time, zone)} ${zoneTag(zone)}`;
  return [
    `The lag is the time since the newest pass in which no source failed: ${at(pass.complete_pass_at)}.`,
    `The data is late from ${at(pass.late_at)}.`,
    `Newest pass: ${at(pass.newest_pass_at)}.`, ...lines,
  ].join("\n");
}
