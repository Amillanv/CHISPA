/* The clock in the bar: the mode, the as-of time, the Pantanal time and the lag of the live data.
   The lag is the time from the newest pass of the poller (tool `live_status`) to the as-of time. */
import { utc, zoned, offset, counter } from "./format.js";

const $ = (id) => document.getElementById(id);

export function drawClock(state) {
  const mode = $("mode");
  mode.className = `mode${state.live ? " live" : ""}`;
  mode.innerHTML = `<span class="dot"></span>${state.live ? "Live" : "Replay"}`;
  mode.title = state.live ? "The as-of time is now." : "Go back to live.";
  $("asof").textContent = utc(state.asOf);
  tick(state);
  const select = $("replays");
  const options = state.settings.replays.map((t) => `<option value="${t}"${!state.live && t === state.anchor ? " selected" : ""}>${utc(t)}</option>`).join("");
  select.innerHTML = `<option value="">Replay a moment</option>${options}`;
}

/* Each second: the Pantanal time and the lag. Live: the time now. Replay: the as-of time.
   The tool `live_status` gives the times. The page only compares them with its clock. */
export function tick(state) {
  const zone = state.settings.time_zone, live = state.live;
  const moment = live ? Date.now() : new Date(state.asOf).getTime();
  const local = zoned(moment, zone, live);
  $("local").innerHTML = `<span class="d">${local.date}</span>${local.time}`;
  $("local-label").textContent = `Pantanal, ${offset(moment, zone)}`;
  $("lag-label").textContent = live ? "Lag" : "Lag at as-of";
  const [text, kind, title] = lag(state.pass, moment);
  $("lag").textContent = text;
  $("lag-box").className = `reading lag${kind ? ` ${kind}` : ""}`;
  $("lag-box").title = title;
}

/* The text, the kind and the explanation of the lag, from the answer of `live_status`. */
function lag(pass, moment) {
  if (pass === undefined) return ["–", "", "Reading the poll log."];
  if (pass === null) return ["unknown", "late", "The page could not read the status of the poller."];
  if (pass.archive) return ["archive", "archive", "Before the live logs. The store has archive data, with an estimate of when each detection became available."];
  if (!pass.complete_pass_at) return ["no pass", "late", "The poll log has no pass with no failure before this time."];
  const seconds = (moment - new Date(pass.complete_pass_at).getTime()) / 1000;
  return [counter(seconds), moment >= new Date(pass.late_at).getTime() ? "late" : "", passText(pass)];
}

function passText(pass) {
  const names = { firms: "FIRMS", goes: "GOES", inpe: "INPE" };
  const lines = Object.entries(pass.sources).map(([name, s]) => `${names[name] ?? name}: ${s.items - s.failed} of ${s.items} items answered, ${s.new_rows} new rows.`);
  for (const name of ["goes", "inpe"]) {
    if (!pass.sources[name]) lines.push(`${names[name]}: no row. No new item was read and no failure was recorded.`);
  }
  return [
    `The lag is the time since the newest pass in which no source failed: ${utc(pass.complete_pass_at)} UTC.`,
    `The data is late from ${utc(pass.late_at)} UTC.`,
    `Newest pass: ${utc(pass.newest_pass_at)} UTC.`, ...lines,
  ].join("\n");
}
