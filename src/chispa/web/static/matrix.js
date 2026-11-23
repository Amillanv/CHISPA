/* The growth matrix: the measured steps of an event as a field of dots, north up, in one look.
   The centre is the event. The dashed ring is the floor: a pixel nearer than the floor is not a new pixel.
   Each step with new pixels is a ray in its direction. The radius is on a log scale, with rings at the floor
   and at 5 km, so that a step of 1 km and a step of 20 km both show. A longer step stops at the edge.
   The newest ray is bright. A pulse runs along it only if that step has a speed.
   The rays are past steps between VIIRS passes, not a forecast. */

const N = 11;           // dots from the centre to the edge
const GAP = 6;          // pixels between two dots
const PAD = 14;         // room for the letters of the directions
const SIZE = 2 * N * GAP + 2 * PAD;
const EDGE_M = 20000;   // the distance at the edge of the matrix
const BEND_M = 250;     // the log scale is almost linear below this distance
const RING_M = 5000;
const HEAT = [245, 193, 108], EMBER = [237, 144, 61];
const DUST = "#a59f8f", WHITE = "#f2f2ea";

/* The distance from the centre in dots, for a distance on the ground in metres. */
function reach(metres) {
  return (N * Math.log1p(Math.min(metres, EDGE_M) / BEND_M)) / Math.log1p(EDGE_M / BEND_M);
}

export function matrix(steps, floor_m) {
  const rays = steps.filter((s) => s.direction_deg !== null);
  const newest = steps.length && steps.at(-1).direction_deg !== null ? steps.at(-1) : null;
  const older = rays.filter((s) => s !== newest).slice(-24);
  const period = newest?.speed_m_h ? Math.min(6, Math.max(0.8, 2.4 * (100 / newest.speed_m_h))) : 0;
  const floor = reach(floor_m), ring = reach(RING_M);
  const dots = [];
  for (let j = -N; j <= N; j++) {
    for (let i = -N; i <= N; i++) {
      const r = Math.hypot(i, j);
      if (r > N + 0.35) continue;
      let dot = { fill: WHITE, size: 0.85, opacity: r < floor ? 0.16 : 0.1 };
      older.forEach((step, n) => {
        const hit = along(i, j, step);
        if (hit && hit.across <= 0.55) dot = { fill: DUST, size: 1.3, opacity: 0.25 + 0.45 * ((n + 1) / older.length) };
      });
      if (newest) {
        const hit = along(i, j, newest);
        if (hit && hit.across <= 0.55) {
          const tip = hit.length - hit.t < 0.75;
          dot = { fill: mix(hit.share), size: tip ? 2.3 : 1.6, opacity: 1, pulse: period && !tip ? hit.share : null };
        }
      }
      dots.push(circle(PAD + (i + N) * GAP, PAD + (j + N) * GAP, dot, period));
    }
  }
  const c = PAD + N * GAP, label = c + ring * GAP * Math.SQRT1_2;
  return `<svg class="matrix" viewBox="0 0 ${SIZE} ${SIZE}" role="img" aria-label="Measured growth steps, north up">
    <circle cx="${c}" cy="${c}" r="${floor * GAP}" fill="none" stroke="${WHITE}" stroke-opacity="0.45" stroke-width="0.8" stroke-dasharray="2 2"/>
    <circle cx="${c}" cy="${c}" r="${ring * GAP}" fill="none" stroke="${WHITE}" stroke-opacity="0.16" stroke-width="0.6" stroke-dasharray="1 3"/>
    ${dots.join("")}
    <circle cx="${c}" cy="${c}" r="2.4" fill="${WHITE}"/>
    ${letter(c, 8, "N")}${letter(SIZE - 6, c + 3, "E")}${letter(c, SIZE - 2, "S")}${letter(6, c + 3, "W")}
    <text x="${label + 3}" y="${2 * c - label - 3}" class="mx-scale">5 km</text>
    <text x="${SIZE - 2}" y="${SIZE - 2}" class="mx-scale" style="text-anchor:end">edge ${EDGE_M / 1000} km</text>
  </svg>`;
}

/* Where a dot is along a ray: the distance along it and across it, in dots, and the share of its length. */
function along(i, j, step) {
  const angle = (step.direction_deg * Math.PI) / 180;
  const east = i, north = -j;
  const t = east * Math.sin(angle) + north * Math.cos(angle);
  const across = Math.abs(east * Math.cos(angle) - north * Math.sin(angle));
  const length = reach(step.advance_m);
  if (t < 0.4 || t > length + 0.45) return null;
  return { t, across, length, share: Math.min(1, t / length) };
}

function mix(share) {
  const c = EMBER.map((e, k) => Math.round(e + (HEAT[k] - e) * share));
  return `rgb(${c.join(",")})`;
}

function circle(x, y, dot, period) {
  const pulse = dot.pulse !== null && dot.pulse !== undefined;
  const style = pulse ? ` class="pulse" style="--d:${dot.pulse.toFixed(2)};--period:${period.toFixed(2)}s"` : "";
  return `<circle cx="${x}" cy="${y}" r="${dot.size}" fill="${dot.fill}" fill-opacity="${dot.opacity.toFixed(2)}"${style}/>`;
}

function letter(x, y, text) {
  return `<text x="${x}" y="${y}" text-anchor="middle" class="mx-dir">${text}</text>`;
}
