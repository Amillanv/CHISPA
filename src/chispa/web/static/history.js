/* The history band: one time axis for the window. The events of each step by level, the detections
   of each sensor family, and the selected event: its days, its level changes and its growth steps.
   A click on a step moves the as-of time to the end of that step. The arrow keys move it one step at a time (`scrub`).
   A sideways swipe or a wheel moves the window in detents of one step (`pan`): the dates slide, the as-of time stays. */
import { esc, num, utc, day, FAMILY, FAMILY_ORDER } from "./format.js";

const LEVELS = [["HIGH", "#e5542b"], ["MEDIUM", "#ed903d"], ["LOW", "#f5c16c"]];
const FAMILY_COLOUR = { viirs: "#d9e7ea", abi: "#4fa3b8", modis: "#a59f8f", avhrr: "#6e736f" };
const G = 64, RIGHT = 10, TOP = 22, AXIS = 18, LANE = 7, LANE_GAP = 4, EVENT_LANE = 18;
const NOTCH_PX = 50; // a wheel step this large is one notch of a mouse wheel: one step of the window
const TRAVEL_PX = 30; // smaller steps (a trackpad swipe) add up: one step of the window for each 30 px
const SETTLE_MS = 350; // the dashboard loads the new time or window when the band stops this long

export class History {
  constructor(root, handlers) {
    this.root = root;
    this.handlers = handlers;
    this.state = null;
    root.innerHTML = `<div class="h-head"></div><div class="h-plot" tabindex="0" aria-label="History of the window. A swipe or Shift and the arrow keys move the window. The arrow keys move the as-of time."></div>`;
    this.head = root.querySelector(".h-head");
    this.plot = root.querySelector(".h-plot");
    this.scrubbing = null; // the step that the band shows during a scrub, before the dashboard loads it
    this.pending = 0; // the steps of a pan that the dashboard did not get yet
    this.travel = 0;
    this.timers = {};
    new ResizeObserver(() => this.draw()).observe(this.plot);
    this.plot.addEventListener("keydown", (e) => this.key(e));
    this.plot.addEventListener("wheel", (e) => this.wheel(e), { passive: false });
  }

  /* state: { activity, past, asOf, end, limits, windows, windowIndex, record }. `activity` is the answer for the
     window that ends at `end`. `past` ends at the as-of time, with the events of the as-of time: the steps to the
     as-of time come from it. `end` can differ from the end of `activity` while the answer for a moved window comes.
     `limits` is the number of steps that the window can move: { forward, back }. */
  set(state) {
    this.state = state;
    this.header();
    this.draw();
  }

  header() {
    const { windows, windowIndex } = this.state;
    const buttons = windows.map((w, n) => `<button type="button" data-window="${n}" aria-pressed="${n === windowIndex}">${w.hours >= 48 ? `${w.hours / 24} d` : `${w.hours} h`}</button>`).join("");
    const legend = LEVELS.map(([name]) => `<span data-level="${name}"><span class="swatch"></span>${name}</span>`).join("");
    this.head.innerHTML = `<span class="label">History</span><div class="seg">${buttons}</div><span class="h-range mono" title="The window, UTC. A swipe moves it."></span>
      <span class="note">Events with a new detection in each step, Pantanal box</span><div class="legend">${legend}</div>`;
    this.head.querySelectorAll("[data-window]").forEach((b) => b.addEventListener("click", () => this.handlers.window(Number(b.dataset.window))));
  }

  draw() {
    if (!this.state?.activity) { this.plot.innerHTML = ""; return; }
    const { activity, past, asOf, record } = this.state;
    const W = this.plot.clientWidth, H = this.plot.clientHeight;
    if (W < 50 || H < 50) return;
    const aligned = past && past.steps[0]?.start === activity.steps[0].start;
    const steps = activity.steps.map((s, n) => (aligned && n < past.steps.length ? past.steps[n] : s));
    const start = new Date(steps[0].start).getTime(), end = new Date(steps.at(-1).end).getTime();
    const x = (t) => G + ((new Date(t).getTime() - start) / (end - start)) * (W - G - RIGHT);
    const families = FAMILY_ORDER.filter((f) => steps.some((s) => s.detections[f]));
    const lanesTop = H - AXIS - families.length * (LANE + LANE_GAP) - (record ? EVENT_LANE + 6 : 0);
    const barsBottom = Math.max(lanesTop - 8, TOP + 16);
    const total = (s) => LEVELS.reduce((sum, [name]) => sum + s.events[name], 0);
    const most = Math.max(1, ...steps.map(total));
    const y = (n) => barsBottom - (n / most) * (barsBottom - TOP);
    const step = (W - G - RIGHT) / steps.length;
    // The scale and the names stay. The parts on the time axis move when the window moves.
    const still = [], moving = [];
    still.push(`<line x1="${G}" x2="${W - RIGHT}" y1="${barsBottom}" y2="${barsBottom}" stroke="rgba(255,255,255,0.12)"/>`);
    still.push(`<text x="${G - 8}" y="${TOP + 3}" text-anchor="end">${num(most)}</text><text x="${G - 8}" y="${barsBottom}" text-anchor="end">0</text>`);
    still.push(`<text class="lane-name" x="4" y="${(TOP + barsBottom) / 2 + 3}">EVENTS</text>`);
    steps.forEach((s, n) => {
      let base = 0;
      const left = G + n * step, width = Math.max(1, step - (step > 4 ? 1.2 : 0.3));
      for (const [name, colour] of LEVELS) {
        const value = s.events[name];
        if (!value) continue;
        moving.push(`<rect x="${left}" y="${y(base + value)}" width="${width}" height="${Math.max(0, y(base) - y(base + value))}" fill="${colour}"/>`);
        base += value;
      }
    });
    const lanes = this.lanes(steps, families, lanesTop, step);
    still.push(lanes.still);
    moving.push(lanes.moving);
    if (record) {
      const lane = this.eventLane(record, x, lanesTop + families.length * (LANE + LANE_GAP) + 4, start, end);
      still.push(lane.still);
      moving.push(lane.moving);
    }
    moving.push(this.axis(start, end, x, H, activity.hours));
    const t = new Date(asOf).getTime();
    if (t <= end) {
      const now = Math.max(x(asOf), G);
      if (now < W - RIGHT - 0.5) moving.push(`<rect x="${now}" y="${TOP - 6}" width="${W - RIGHT - now}" height="${H - AXIS - TOP + 6}" fill="rgba(5,5,5,0.62)"/>`);
      if (t >= start) moving.push(`<line x1="${now}" x2="${now}" y1="${TOP - 8}" y2="${H - AXIS}" stroke="#087cff" stroke-width="1.2"/>`);
    }
    still.push(this.asOfLabel(asOf, start, end, x, W));
    const hits = steps.map((s, n) => `<rect class="hit" data-n="${n}" x="${G + n * step}" y="0" width="${step}" height="${H - AXIS}"/>`).join("");
    const scrub = `<g class="scrub" visibility="hidden" pointer-events="none"><rect y="${TOP - 6}" height="${H - AXIS - TOP + 6}" fill="rgba(8,124,255,0.10)"/>
      <line y1="${TOP - 8}" y2="${H - AXIS}" stroke="#087cff" stroke-width="1.2" stroke-dasharray="3 2"/><text class="now" y="${TOP - 10}" text-anchor="end"></text></g>`;
    this.plot.innerHTML = `<svg viewBox="0 0 ${W} ${H}"><defs><clipPath id="h-clip"><rect x="${G}" y="0" width="${W - G}" height="${H}"/></clipPath></defs>
      ${still.join("")}<g clip-path="url(#h-clip)"><g class="slide">${moving.join("")}</g></g><g class="hits">${hits}</g>
      <rect class="col" x="0" y="${TOP - 6}" width="0" height="${H - AXIS - TOP + 6}" fill="rgba(255,255,255,0.05)" pointer-events="none"/>${scrub}</svg>`;
    this.geometry = { step, steps, start, end, stepMs: (end - start) / steps.length };
    this.wire(steps, step);
    this.slide();
    if (this.scrubbing !== null) this.mark(this.scrubbing);
  }

  /* The as-of time over the band. Out of the window, an arrow at the edge says on which side it is. */
  asOfLabel(asOf, start, end, x, W) {
    const t = new Date(asOf).getTime();
    if (t > end) return `<text class="now asof" x="${W - RIGHT}" y="${TOP - 10}" text-anchor="end">as-of ${utc(asOf)} →</text>`;
    if (t < start) return `<text class="now asof" x="${G}" y="${TOP - 10}">← as-of ${utc(asOf)}</text>`;
    return `<text class="now asof" x="${x(asOf) - 4}" y="${TOP - 10}" text-anchor="end">${utc(asOf)}</text>`;
  }

  lanes(steps, families, top, step) {
    const still = [], moving = [];
    families.forEach((family, k) => {
      const yy = top + k * (LANE + LANE_GAP);
      const most = Math.max(1, ...steps.map((s) => s.detections[family] ?? 0));
      still.push(`<text class="lane-name" x="4" y="${yy + LANE}">${FAMILY[family]}</text><rect x="${G}" y="${yy}" width="${steps.length * step}" height="${LANE}" fill="rgba(255,255,255,0.025)"/>`);
      steps.forEach((s, n) => {
        const count = s.detections[family] ?? 0;
        if (!count) return;
        const strength = 0.2 + 0.8 * (Math.log1p(count) / Math.log1p(most));
        moving.push(`<rect x="${G + n * step}" y="${yy}" width="${Math.max(1, step - 0.6)}" height="${LANE}" fill="${FAMILY_COLOUR[family]}" fill-opacity="${strength.toFixed(2)}"/>`);
      });
    });
    return { still: still.join(""), moving: moving.join("") };
  }

  /* The selected event: its detections of each day, its level changes and its VIIRS growth steps. */
  eventLane(record, x, top, start, end) {
    const inside = (t) => { const v = new Date(t).getTime(); return v >= start && v <= end; };
    const most = Math.max(1, ...record.timeline.map((d) => d.detections));
    const still = `<text class="lane-name" x="4" y="${top + 12}" style="fill:#4f9dff">EVENT</text><rect x="${G}" y="${top}" width="${x(end) - G}" height="${EVENT_LANE}" fill="rgba(8,124,255,0.05)"/>`;
    const parts = [];
    for (const d of record.timeline) {
      const midnight = new Date(`${d.day}T00:00:00Z`).getTime();
      const from = Math.max(midnight, start), to = Math.min(midnight + 86_400_000, end);
      if (to <= from) continue;
      const h = 3 + (EVENT_LANE - 4) * (Math.log1p(d.detections) / Math.log1p(most));
      parts.push(`<rect x="${x(from)}" y="${top + EVENT_LANE - h}" width="${Math.max(1, x(to) - x(from) - 1)}" height="${h}" fill="#087cff" fill-opacity="0.35"/>`);
    }
    for (const s of record.growth_steps.filter((s) => inside(s.at))) {
      const moved = s.direction_deg !== null;
      parts.push(`<line x1="${x(s.at)}" x2="${x(s.at)}" y1="${top + (moved ? 0 : 9)}" y2="${top + EVENT_LANE}" stroke="${moved ? "#f5c16c" : "rgba(242,242,234,0.35)"}" stroke-width="${moved ? 1.5 : 1}"/>`);
    }
    const colour = Object.fromEntries(LEVELS);
    for (const c of record.level_changes.filter((c) => inside(c.at))) {
      const cx = x(c.at);
      parts.push(`<path d="M${cx} ${top - 4}l4 4l-4 4l-4-4z" fill="${colour[c.level]}" stroke="#050505"/>`);
    }
    return { still, moving: parts.join("") };
  }

  axis(start, end, x, H, hours) {
    const every = hours <= 72 ? 12 : hours <= 168 ? 24 : 120;
    const parts = [];
    const first = Math.ceil(start / 3_600_000 / every) * every * 3_600_000;
    for (let t = first; t <= end; t += every * 3_600_000) {
      const iso = new Date(t).toISOString();
      const text = iso.slice(11, 13) === "00" ? day(iso) : iso.slice(11, 16);
      parts.push(`<line x1="${x(t)}" x2="${x(t)}" y1="${H - AXIS}" y2="${H - AXIS + 3}" stroke="rgba(255,255,255,0.25)"/><text x="${x(t) + 3}" y="${H - 4}">${text}</text>`);
    }
    return parts.join("");
  }

  wire(steps, step) {
    const svg = this.plot.querySelector("svg"), column = svg.querySelector(".col"), tip = document.getElementById("tip");
    svg.querySelectorAll(".hit").forEach((hit) => {
      const s = steps[Number(hit.dataset.n)];
      hit.addEventListener("mouseenter", () => {
        column.setAttribute("x", hit.getAttribute("x"));
        column.setAttribute("width", step);
        const fams = FAMILY_ORDER.filter((f) => s.detections[f]).map((f) => `${FAMILY[f]} ${num(s.detections[f])}`).join(" · ") || "no detection";
        tip.innerHTML = `<div class="mono">${utc(s.start)} – ${utc(s.end, false)}</div>
          <div>${LEVELS.map(([n]) => `<span data-level="${n}"><span class="swatch"></span>${n} <b>${s.events[n]}</b></span>`).join("&nbsp;&nbsp;")}</div>
          <div class="muted">${esc(fams)}</div>${new Date(s.end) > new Date(this.state.asOf) ? `<div class="muted">After the as-of time: events of the end of the window.</div>` : ""}
          <div class="muted">Click: as-of time ${utc(s.end, false)}</div>`;
        tip.hidden = false;
      });
      hit.addEventListener("mousemove", (e) => { tip.style.left = `${Math.min(e.clientX + 14, innerWidth - 270)}px`; tip.style.top = `${e.clientY - 90}px`; });
      hit.addEventListener("mouseleave", () => { tip.hidden = true; column.setAttribute("width", 0); });
      hit.addEventListener("click", () => this.handlers.asOf(s.end));
    });
  }

  /* The arrow keys move the as-of time. With Shift they move the window. */
  key(e) {
    if (!this.state?.activity || !["ArrowLeft", "ArrowRight"].includes(e.key)) return;
    e.preventDefault();
    const move = e.key === "ArrowLeft" ? -1 : 1;
    e.shiftKey ? this.pan(move) : this.scrub(move);
  }

  /* A sideways swipe, or a notch of a mouse wheel, moves the window: one step for each detent. The band takes a
     sideways swipe, thus the browser does not go back a page. A small up or down movement goes on to the page. */
  wheel(e) {
    if (!this.state?.activity) return;
    const sideways = Math.abs(e.deltaX) > Math.abs(e.deltaY);
    const px = (sideways ? e.deltaX : e.deltaY) * (e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? this.plot.clientWidth : 1);
    const notch = Math.abs(px) >= NOTCH_PX || e.deltaMode === 1;
    if (!sideways && !notch) return;
    e.preventDefault();
    if (notch) { this.travel = 0; this.pan(Math.sign(px)); return; }
    this.travel += px;
    if (Math.abs(this.travel) >= TRAVEL_PX) { this.pan(Math.sign(this.travel)); this.travel = 0; }
  }

  /* Move the window by steps at once. When the band stops, the dashboard loads the moved window. */
  pan(move) {
    const { forward, back } = this.state.limits;
    const next = Math.max(-back, Math.min(forward, this.pending + move));
    if (next === this.pending) return;
    this.pending = next;
    this.slide();
    clearTimeout(this.timers.pan);
    this.timers.pan = setTimeout(() => {
      const steps = this.pending;
      this.pending = 0;
      if (steps) this.handlers.pan(steps);
    }, SETTLE_MS);
  }

  /* Draw the steps where the window will be: the drawn answer can be for an older position of the window. */
  slide() {
    const g = this.geometry, svg = this.plot.querySelector("svg");
    if (!g || !svg) return;
    const offset = (new Date(this.state.end).getTime() - g.end) / g.stepMs + this.pending;
    svg.querySelector(".slide").setAttribute("transform", `translate(${(-offset * g.step).toFixed(1)},0)`);
    svg.classList.toggle("moving", Math.abs(offset) > 1e-6);
    const range = this.head.querySelector(".h-range");
    if (range) range.textContent = `${utc(g.start + offset * g.stepMs)} → ${utc(g.end + offset * g.stepMs)}`;
  }

  /* Move the shown step at once. When the band stops, the dashboard loads the end of that step as the as-of time. */
  scrub(move) {
    const steps = this.state.activity.steps, asOf = new Date(this.state.asOf).getTime();
    const at = steps.findIndex((s) => new Date(s.end).getTime() >= asOf);
    const from = this.scrubbing ?? (at < 0 ? steps.length - 1 : at);
    const n = Math.min(steps.length - 1, Math.max(0, from + move));
    if (n === from && this.scrubbing === null) return;
    this.scrubbing = n;
    this.mark(n);
    clearTimeout(this.timers.scrub);
    this.timers.scrub = setTimeout(() => {
      this.scrubbing = null;
      if (steps[n].end !== this.state.asOf) this.handlers.asOf(steps[n].end);
      else this.draw();
    }, SETTLE_MS);
  }

  /* The scrub mark: the step, a dashed line at its end and the time that the dashboard will load. */
  mark(n) {
    const { step, steps } = this.geometry ?? {};
    const group = this.plot.querySelector(".scrub");
    if (!group || !steps?.[n]) return;
    const left = G + n * step, end = left + step;
    group.querySelector("rect").setAttribute("x", left);
    group.querySelector("rect").setAttribute("width", step);
    group.querySelectorAll("line").forEach((line) => { line.setAttribute("x1", end); line.setAttribute("x2", end); });
    const label = group.querySelector("text");
    label.setAttribute("x", Math.max(G + 90, end - 4));
    label.textContent = `${utc(steps[n].end)} · ${num(LEVELS.reduce((sum, [name]) => sum + steps[n].events[name], 0))} events`;
    group.setAttribute("visibility", "visible");
    this.plot.querySelector("text.asof")?.setAttribute("visibility", "hidden"); // its line stays: the as-of time now
    document.getElementById("tip").hidden = true;
  }
}
