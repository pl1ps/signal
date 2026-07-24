"use strict";

const SECTIONS_EL = document.getElementById("sections");
const NOTICE_EL = document.getElementById("notice");
const STAMP_EL = document.getElementById("stamp");

/** Build one card. Anchors (not divs) so keyboard and long-press work. */
function buildCard(item) {
  const card = document.createElement("a");
  card.className = "card";
  card.href = item.url;
  card.target = "_blank";
  card.rel = "noopener";

  const title = document.createElement("h3");
  title.className = "card-title";
  title.textContent = item.title;
  card.appendChild(title);

  if (item.why) {
    const why = document.createElement("p");
    why.className = "card-why";
    why.textContent = item.why;
    card.appendChild(why);
  }

  if (item.summary) {
    const summary = document.createElement("p");
    summary.className = "card-summary";
    summary.textContent = item.summary;
    card.appendChild(summary);
  }

  const meta = document.createElement("p");
  meta.className = "card-meta";
  const signal = item.signal && item.signal.value
    ? ` · ${item.signal.value} ${item.signal.metric}`
    : "";
  meta.textContent = `${item.source_label}${signal}`;
  card.appendChild(meta);

  return card;
}

function buildSection(section) {
  const wrapper = document.createElement("section");
  wrapper.className = "section";

  const head = document.createElement("div");
  head.className = "section-head";

  const title = document.createElement("h2");
  title.className = "section-title";
  title.textContent = section.title;

  const rule = document.createElement("span");
  rule.className = "section-rule";

  const count = document.createElement("span");
  count.className = "section-count";
  count.textContent = section.items.length;

  head.append(title, rule, count);
  wrapper.appendChild(head);

  section.items.forEach((item) => wrapper.appendChild(buildCard(item)));
  return wrapper;
}

function formatStamp(iso) {
  const when = new Date(iso);
  if (Number.isNaN(when.getTime())) return "Updated recently";
  const time = when.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  return `Updated ${time}`;
}

/** Say plainly what is degraded — never pretend the digest is complete. */
function showNotice(status) {
  const problems = [];
  if (status && status.ai_used === false) {
    problems.push("Summaries are unavailable, so these are raw headlines.");
  }
  if (status && status.sources_failed && status.sources_failed.length) {
    problems.push(`Some sources did not respond: ${status.sources_failed.join(", ")}.`);
  }
  if (!problems.length) {
    NOTICE_EL.hidden = true;
    return;
  }
  NOTICE_EL.textContent = problems.join(" ");
  NOTICE_EL.hidden = false;
}

function renderDigest(digest) {
  STAMP_EL.textContent = formatStamp(digest.generated_at);
  showNotice(digest.status);

  SECTIONS_EL.textContent = "";
  const sections = digest.sections || [];

  if (!sections.length) {
    const empty = document.createElement("p");
    empty.className = "card-summary";
    empty.textContent = "Nothing cleared the filter today. Check back tomorrow.";
    SECTIONS_EL.appendChild(empty);
  } else {
    sections.forEach((section) => SECTIONS_EL.appendChild(buildSection(section)));
  }

  if (typeof window.renderReadout === "function") {
    window.renderReadout(digest.readout || { scanned: 0, kept: 0, levels: [] });
  }
}

async function loadDigest() {
  try {
    const response = await fetch("digest.json", { cache: "no-cache" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    renderDigest(await response.json());
  } catch (error) {
    // The service worker serves the last good digest when offline; if even
    // that is missing, say what to do rather than showing a blank screen.
    STAMP_EL.textContent = "Offline";
    NOTICE_EL.textContent = "No digest available yet. Connect once to download today's briefing.";
    NOTICE_EL.hidden = false;
  }
}

document.getElementById("refresh").addEventListener("click", loadDigest);
loadDigest();
