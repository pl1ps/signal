"use strict";

/**
 * The signature element: every item scanned today is a bar. Noise sits low;
 * items that survived the filter spike in amber. This is the product's whole
 * premise — subtraction — drawn as an instrument reading.
 */
window.renderReadout = function renderReadout(readout) {
  const host = document.getElementById("readout");
  const levels = readout.levels || [];

  document.getElementById("scanned").textContent = readout.scanned || 0;
  document.getElementById("kept").textContent = readout.kept || 0;

  host.textContent = "";

  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  levels.forEach((level, index) => {
    const bar = document.createElement("span");
    bar.className = level.kept ? "bar kept" : "bar";

    // digest.json is fetched data, so a malformed level must not reach CSS:
    // "NaN%" is an invalid height and would silently collapse the bar.
    const value = Number(level.v);
    const safe = Number.isFinite(value) ? Math.min(1, Math.max(0, value)) : 0;
    const height = Math.max(6, Math.round(safe * 100));
    bar.style.setProperty("--h", `${height}%`);

    if (!reduceMotion) {
      // One orchestrated moment: a fast staggered sweep, like a scan completing.
      bar.style.animation = "rise 420ms cubic-bezier(0.2, 0.8, 0.2, 1) both";
      bar.style.animationDelay = `${index * 12}ms`;
    }

    host.appendChild(bar);
  });
};
