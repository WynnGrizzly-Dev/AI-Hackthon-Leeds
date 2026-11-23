// Browser port of eye-guard/retina1.py. Same landmarks and thresholds. Times are in seconds.
export const SETTINGS = {
  workLimit: 3 * 3600, awayReset: 5 * 60, lowBlink: 8, rednessIncrease: 0.12, calibration: 60,
};
export const LEFT = [33, 160, 158, 133, 153, 144];
export const RIGHT = [362, 385, 387, 263, 373, 380];

const dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
export const ear = (p) => (dist(p[1], p[5]) + dist(p[2], p[4])) / (2 * dist(p[0], p[3]));

export function median(values) {
  const s = [...values].sort((a, b) => a - b);
  const m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

function inside(x, y, poly) {
  let hit = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const a = poly[i], b = poly[j];
    if ((a.y > y) !== (b.y > y) && x < ((b.x - a.x) * (y - a.y)) / (b.y - a.y) + a.x) hit = !hit;
  }
  return hit;
}

// Mean red / (green + blue) inside the eye outline, ignoring dark iris, pupil and lashes.
export function eyeRedness(ctx, pts) {
  const x0 = Math.floor(Math.min(...pts.map((p) => p.x))), y0 = Math.floor(Math.min(...pts.map((p) => p.y)));
  const w = Math.ceil(Math.max(...pts.map((p) => p.x))) - x0, h = Math.ceil(Math.max(...pts.map((p) => p.y))) - y0;
  if (w < 1 || h < 1) return null;
  const { data } = ctx.getImageData(x0, y0, w, h);
  let r = 0, g = 0, b = 0, n = 0;
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const i = (y * w + x) * 4;
      if (0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2] < 80) continue;
      if (!inside(x0 + x + 0.5, y0 + y + 0.5, pts)) continue;
      r += data[i]; g += data[i + 1]; b += data[i + 2]; n++;
    }
  }
  return n < 15 ? null : r / (g + b + 1e-6);
}

export function createMonitor(start) {
  let blinks = [], base = [], red = [], closed = false;
  let lastSeen = start, lastTick = start, blinkStart = start;
  let work = 0, baseline = null;

  // sample: { ear, redness } when a face is visible, otherwise null.
  // hidden: the tab is in the background, where browsers slow updates too much to count blinks.
  return function tick(now, sample, hidden = false) {
    if (hidden) { blinks = []; closed = false; blinkStart = now; }
    if (sample) {
      lastSeen = now;
      if (!hidden) {
        if (sample.ear < 0.19) closed = true;
        else if (sample.ear >= 0.21 && closed) { closed = false; blinks.push(now); }
      }
      if (sample.ear > 0.22 && sample.redness) {
        if (now - start < SETTINGS.calibration) base.push(sample.redness);
        else { red.push(sample.redness); if (red.length > 120) red.shift(); }
      }
    }
    blinks = blinks.filter((t) => now - t <= 60);

    const face = now - lastSeen < 5;
    if (!face && now - lastSeen > SETTINGS.awayReset) work = 0;
    else if (face) work += now - lastTick;
    lastTick = now;

    const calibrating = now - start < SETTINGS.calibration;
    if (!calibrating && baseline === null && base.length) baseline = median(base);
    const blinksPerMin = face && now - blinkStart > 60 ? blinks.length : null;

    const warnings = [];
    if (work > SETTINGS.workLimit) warnings.push(`You've been working for over ${SETTINGS.workLimit / 3600} hours. Take a break!`);
    if (baseline && red.length && median(red) > baseline * (1 + SETTINGS.rednessIncrease)) warnings.push('Your eyes look redder than when you started. Take some rest!');
    if (blinksPerMin !== null && blinksPerMin < SETTINGS.lowBlink) warnings.push("You're blinking too little. Blink more or look away for 20 seconds.");
    return { work, face, calibrating, blinksPerMin, warnings };
  };
}
