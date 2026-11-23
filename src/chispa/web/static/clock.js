/* The clock in the bar: the mode, the as-of time, the Pantanal time and the lag of the live data.
   The lag is the time from the newest pass of the poller (tool `live_status`) to the as-of time. */
import { utc, dur, zoned, offset, counter } from "./format.js";

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

/* Each second: the Pantanal time and the lag. Live: the time now and the age of the newest poller pass.
   Replay: the as-of time, and the age of the newest pass at that time. */
export function tick(state) {
  const zone = state.settings.time_zone, live = state.live;
  const moment = live ? Date.now() : new Date(state.asOf).getTime();
  const local = zoned(moment, zone, live);
  $("local").innerHTML = `<span class="d">${local.date}</span>${local.time}`;
  $("local-label").textContent = `Pantanal, ${offset(moment, zone)}`;
  const box = $("lag-box"), last = state.pass?.last_pass_at;
  $("lag-label").textContent = live ? "Lag" : "Lag at as-of";
  if (!state.pass) { $("lag").textContent = "–"; return; }
  if (!last) {
    box.className = "reading lag archive";
    $("lag").textContent = "archive";
    box.title = "No poller pass before this time. The store has archive data, with an estimate of when each detection became available.";
    return;
  }
  const seconds = (moment - new Date(last).getTime()) / 1000;
  const failed = Object.values(state.pass.sources).reduce((sum, s) => sum + s.failed, 0);
  box.className = `reading lag${seconds > state.settings.poll_late_s || failed ? " late" : ""}`;
  $("lag").textContent = counter(seconds);
  box.title = passText(state.pass, state.settings);
}

function passText(pass, settings) {
  const names = { firms: "FIRMS", goes: "GOES", inpe: "INPE" };
  const lines = Object.entries(pass.sources).map(([name, s]) => `${names[name] ?? name}: ${s.items - s.failed} of ${s.items} answered, ${s.new_rows} new rows.`);
  if (!pass.sources.goes) lines.push("GOES: no new scan in this pass.");
  return [`Newest poller pass: ${utc(pass.last_pass_at)} UTC.`, ...lines, "The lag is the time since that pass. Late after " + dur(settings.poll_late_s / 3600) + "."].join("\n");
}
