"""Build the TCC↔PSD equivalency outputs.

Two outputs from the same data:
  - ctc-psd-decisions.html   : decider-facing, edit-enabled
  - ctc-psd-equivalency.html : counselor/student-facing, read-only

Both load decisions from a Google Apps Script Web App URL (Sheet-backed),
falling back to a localStorage cache when offline.
"""
import json
import re
from pathlib import Path
from datetime import date

HERE = Path(__file__).parent
DATA = HERE / "ctc-courses-classified.json"
OUT_DEC = HERE / "ctc-psd-decisions.html"
OUT_PUB = HERE / "ctc-psd-equivalency.html"

# Set this once James deploys the Apps Script Web App. Until then the HTML
# still works — it just shows "Decisions backend not configured" instead of
# attempting fetches.
APPS_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbzWhXfKmN7ryC8wiPXypvHmChGvQ9LdCKPDu6EolyNODNARsdfF41wpG_9GF2cdWWIJ/exec"

# Roles allowed in the decided_by dropdown.
DECIDER_ROLES = [
    "Chief Academic Officer",
    "Director of Secondary Teaching & Learning",
    "Director of CTE",
    "Director of Research & Assessment",
]

# Institutions in scope. Order shown in filters / editor checkboxes.
INSTITUTIONS = [
    {"id": "tcc",        "label": "Tacoma CC"},
    {"id": "olympic",    "label": "Olympic"},
    {"id": "greenriver", "label": "Green River"},
    {"id": "pierce",     "label": "Pierce"},
    {"id": "cloverpark", "label": "Clover Park"},
    {"id": "bates",      "label": "Bates"},
]

courses = json.loads(DATA.read_text())
data_js = json.dumps(courses, separators=(",", ":"))

depts = sorted({c["department"] for c in courses if c["department"]})
ctypes = [
    "ELA",
    "Math",
    "Science (Lab)",
    "Science (Non-Lab)",
    "Social Studies - US History",
    "Social Studies - World History",
    "Social Studies - Washington State History",
    "Social Studies - Civics",
    "Social Studies - Elective",
    "Fine & Performing Arts",
    "World Language",
    "Health",
    "PE / Fitness",
    "CTE",
    "Elective",
]

TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>##TITLE##</title>
<style>
  :root {
    --psd-sea-glass: #6CA18A;
    --psd-pacific: #25424C;
    --psd-driftwood: #D7CDBE;
    --psd-cedar: #466857;
    --psd-whulge: #346780;
    --psd-sea-foam: #EEEBE4;
    --psd-meadow: #5D9068;
    --psd-ocean: #7396A9;
    --psd-skylight: #FFFAEC;
    --flag-bg: #fff4e6;
    --flag-border: #d9822b;
    --sub100-bg: #fde7e7;
    --sub100-border: #b9534d;
    --cte-bg: #fff7d6;
    --cte-border: #b38f1a;
    --decided-bg: #e8f1ec;
    --decided-border: #2f6a4d;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Roboto, sans-serif;
    color: var(--psd-pacific);
    background: var(--psd-sea-foam);
    line-height: 1.4;
  }
  header {
    background: var(--psd-pacific);
    color: var(--psd-sea-foam);
    padding: 20px 28px;
    border-bottom: 4px solid var(--psd-sea-glass);
  }
  header h1 {
    margin: 0 0 4px;
    font-size: 1.5rem;
    font-weight: 600;
    letter-spacing: 0.01em;
  }
  header .sub { color: var(--psd-driftwood); font-size: 0.9rem; }
  header .audience {
    display: inline-block; background: var(--psd-sea-glass); color: white;
    padding: 1px 8px; border-radius: 4px; font-size: 0.7rem;
    text-transform: uppercase; letter-spacing: 0.05em; margin-right: 8px;
  }
  header .contact { color: white; font-weight: 600; margin-left: 6px; }
  .mode-decisions header .contact { display: none; }
  header .catalog-meta {
    margin-top: 8px; font-size: 0.78rem; color: var(--psd-driftwood);
    display: flex; flex-wrap: wrap; gap: 8px 18px;
  }
  header .catalog-meta .inst { color: var(--psd-sea-glass); font-weight: 600; margin-right: 4px; }
  main { padding: 20px 28px 60px; max-width: 1500px; margin: 0 auto; }

  .banner {
    margin: 0 0 14px; padding: 10px 14px; border-radius: 6px;
    font-size: 0.88rem; border: 1px solid;
  }
  .banner-warn { background: var(--flag-bg); border-color: var(--flag-border); color: #6a4310; }
  .banner-ok   { background: #ecf3ee; border-color: var(--psd-meadow); color: var(--psd-cedar); }

  .summary {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
    gap: 8px;
    margin: 0 0 18px;
  }
  .stat { background: white; border: 1px solid var(--psd-driftwood); border-radius: 8px; padding: 10px 12px; }
  .stat .n { font-size: 1.3rem; font-weight: 600; color: var(--psd-cedar); }
  .stat .l { font-size: 0.78rem; color: var(--psd-whulge); text-transform: uppercase; letter-spacing: 0.04em; }

  .toolbar {
    display: grid;
    grid-template-columns: 2fr 1.4fr 1.4fr 1fr 1fr auto;
    gap: 10px;
    background: white;
    border: 1px solid var(--psd-driftwood);
    border-radius: 10px;
    padding: 12px 14px;
    margin: 0 0 18px;
    align-items: end;
  }
  .mode-public .toolbar { grid-template-columns: 2fr 1.4fr 1.4fr 1fr auto; }
  .mode-public .filter-flag { display: none; }
  .mode-public .filter-confidence { display: none; }
  .mode-decisions .filter-recent { display: none; }
  .toolbar2 {
    display: grid; grid-template-columns: 1fr 1fr; gap: 14px;
    background: white; border: 1px solid var(--psd-driftwood); border-radius: 10px;
    padding: 12px 14px; margin: 0 0 18px;
  }
  .toolbar2 .cb-group { border: 0; padding: 0; margin: 0; }
  .toolbar2 fieldset legend {
    font-size: 0.78rem; color: var(--psd-whulge);
    text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 6px;
  }
  .toolbar2 .inline-cb-group { display: flex; flex-wrap: wrap; gap: 6px 12px; }
  .toolbar2 .inline-cb-group label { display: inline-flex; gap: 5px; align-items: center; font-size: 0.88rem; }
  .toolbar2 .filter-confidence label {
    display: block; font-size: 0.78rem; color: var(--psd-whulge);
    text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 6px;
  }
  .toolbar2 .filter-confidence input[type=range] { width: 100%; }
  .toolbar2 .filter-confidence output { color: var(--psd-cedar); font-weight: 600; }
  .toolbar2 .filter-confidence label.cb {
    display: inline-flex; margin-top: 6px; text-transform: none;
    color: var(--psd-pacific); letter-spacing: 0;
  }
  .toolbar label {
    display: flex; flex-direction: column; gap: 4px;
    font-size: 0.78rem; color: var(--psd-whulge);
    text-transform: uppercase; letter-spacing: 0.05em;
  }
  .toolbar input, .toolbar select, .editor input, .editor select, .editor textarea {
    font-size: 0.95rem; padding: 7px 9px;
    border: 1px solid var(--psd-ocean); border-radius: 6px;
    background: var(--psd-skylight); color: var(--psd-pacific);
    font-family: inherit;
  }
  .toolbar input:focus, .toolbar select:focus {
    outline: 2px solid var(--psd-sea-glass); outline-offset: 0;
  }
  .toolbar button {
    background: var(--psd-sea-glass); color: white;
    border: 0; border-radius: 6px; padding: 8px 14px;
    font-weight: 600; cursor: pointer; height: 38px;
  }
  .toolbar button:hover { background: var(--psd-cedar); }
  .toolbar button.secondary { background: var(--psd-driftwood); color: var(--psd-pacific); }
  .toolbar button.secondary:hover { background: var(--psd-ocean); color: white; }

  .toolbar-row2 { display: flex; gap: 14px; flex-wrap: wrap; margin: -8px 0 18px; font-size: 0.85rem; color: var(--psd-pacific); align-items: center; }
  .count-readout { margin-left: auto; color: var(--psd-cedar); font-weight: 600; }

  table { width: 100%; border-collapse: collapse; background: white; border: 1px solid var(--psd-driftwood); border-radius: 10px; overflow: hidden; font-size: 0.9rem; }
  th {
    background: var(--psd-whulge); color: white; text-align: left;
    padding: 10px 12px; font-weight: 600; font-size: 0.8rem;
    text-transform: uppercase; letter-spacing: 0.04em;
    cursor: pointer; user-select: none; position: sticky; top: 0; z-index: 2;
  }
  th .arrow { opacity: 0.5; margin-left: 4px; }
  tr.row { border-top: 1px solid var(--psd-driftwood); cursor: pointer; transition: background 80ms; }
  tr.row:hover { background: var(--psd-skylight); }
  tr.row.open { background: var(--psd-skylight); }
  td { padding: 9px 12px; vertical-align: top; }
  td.code { font-family: ui-monospace, "SF Mono", Menlo, monospace; font-weight: 600; color: var(--psd-cedar); }
  td.credits { text-align: right; font-variant-numeric: tabular-nums; font-weight: 600; }
  td.dept { color: var(--psd-whulge); font-size: 0.85rem; }
  .struck { text-decoration: line-through; color: var(--psd-ocean); }

  .pill { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 0.75rem; font-weight: 600; border: 1px solid transparent; white-space: nowrap; }
  .pill-group { display: inline-flex; gap: 4px; flex-wrap: wrap; }
  .pill-ela    { background: #ecf3f8; color: var(--psd-whulge); border-color: var(--psd-ocean); }
  .pill-math   { background: #eef3ee; color: var(--psd-cedar); border-color: var(--psd-meadow); }
  .pill-science{ background: #e6f0ea; color: var(--psd-cedar); border-color: var(--psd-sea-glass); }
  .pill-ss     { background: #fff7eb; color: #8a5a0e; border-color: #d9a85a; }
  .pill-arts   { background: #f7e8f0; color: #7d3057; border-color: #c275a0; }
  .pill-lang   { background: #ecf1f7; color: #2c4f78; border-color: #5476a4; }
  .pill-health { background: #fdeded; color: #843535; border-color: #c47272; }
  .pill-pe     { background: #fdf0e4; color: #6e4316; border-color: #c08a5c; }
  .pill-cte    { background: var(--cte-bg); color: #6a5510; border-color: var(--cte-border); }
  .pill-elec   { background: #efeae3; color: #4a4035; border-color: var(--psd-driftwood); }

  .flag { display: inline-block; padding: 1px 7px; margin: 0 0 0 5px; border-radius: 4px; font-size: 0.7rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; }
  .flag-review { background: var(--flag-bg); color: var(--flag-border); border: 1px solid var(--flag-border); }
  .flag-sub100 { background: var(--sub100-bg); color: var(--sub100-border); border: 1px solid var(--sub100-border); }
  .flag-cte    { background: var(--cte-bg); color: var(--cte-border); border: 1px solid var(--cte-border); }
  .flag-decided{ background: var(--decided-bg); color: var(--decided-border); border: 1px solid var(--decided-border); }
  .mode-public .flag-review, .mode-public .flag-cte, .mode-public .flag-sub100 { display: none; }

  .dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 4px; vertical-align: middle; }
  .dot-decided { background: var(--decided-border); }
  .dot-pending { background: var(--flag-border); }
  .dot-disputed{ background: var(--sub100-border); }
  .dot-none    { background: var(--psd-driftwood); }

  .detail { background: white; border-top: 1px solid var(--psd-driftwood); padding: 16px 24px 22px; }
  .detail h4 { margin: 0 0 6px; color: var(--psd-cedar); font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.06em; }
  .detail .desc { margin: 0 0 14px; color: var(--psd-pacific); }
  .detail .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 14px; }
  .detail .box { background: var(--psd-skylight); border-radius: 6px; padding: 10px 12px; font-size: 0.88rem; }
  .detail .box .lbl { font-size: 0.72rem; color: var(--psd-whulge); text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: 3px; }
  .detail .flags-list { list-style: none; padding: 0; margin: 6px 0 0; }
  .detail .flags-list li { padding: 6px 10px; background: var(--flag-bg); border-left: 3px solid var(--flag-border); margin: 4px 0; border-radius: 3px; font-size: 0.85rem; }

  .editor { margin-top: 16px; padding: 14px 16px; border-radius: 8px; background: #fafaf6; border: 1px solid var(--psd-driftwood); }
  .editor h4 { margin: 0 0 10px; }
  .editor-row { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px; margin-bottom: 10px; }
  .editor-row label { display: flex; flex-direction: column; gap: 3px; font-size: 0.78rem; color: var(--psd-whulge); text-transform: uppercase; letter-spacing: 0.04em; }
  .editor textarea { width: 100%; min-height: 60px; resize: vertical; }
  .editor .cb-group-label {
    display: block; margin: 10px 0 4px; font-size: 0.78rem;
    color: var(--psd-whulge); text-transform: uppercase; letter-spacing: 0.04em;
  }
  .editor .cb-group-label .hint {
    text-transform: none; color: var(--psd-ocean); font-weight: 400; margin-left: 6px;
  }
  .editor .cb-group {
    display: flex; gap: 6px 12px; flex-wrap: wrap;
    padding: 8px 10px; background: white; border: 1px solid var(--psd-driftwood);
    border-radius: 6px; margin-bottom: 6px;
  }
  .editor .cb-group .cb {
    display: inline-flex; gap: 5px; align-items: center;
    font-size: 0.85rem; color: var(--psd-pacific);
    text-transform: none; letter-spacing: 0;
  }
  .editor .cb-group .cb input[disabled] { opacity: 0.5; }
  .editor .cb-group .cb:has(input[disabled]) { color: var(--psd-ocean); }
  .editor .rationale-label {
    display: block; font-size: 0.78rem; color: var(--psd-whulge);
    text-transform: uppercase; letter-spacing: 0.04em; margin-top: 6px;
  }
  .editor-actions { display: flex; gap: 10px; align-items: center; margin-top: 8px; }
  .editor-actions .status-msg { color: var(--psd-cedar); font-size: 0.85rem; }
  .editor button { background: var(--psd-sea-glass); color: white; border: 0; border-radius: 6px; padding: 8px 14px; font-weight: 600; cursor: pointer; }
  .editor button:hover { background: var(--psd-cedar); }
  .editor button.secondary { background: var(--psd-driftwood); color: var(--psd-pacific); }
  .editor button.danger { background: #b9534d; color: white; }

  .decided-note {
    margin: 12px 0; padding: 10px 12px; background: var(--decided-bg);
    border-left: 4px solid var(--decided-border); border-radius: 4px; font-size: 0.9rem;
  }
  .decided-note .meta { color: var(--decided-border); font-size: 0.78rem; margin-top: 4px; text-transform: uppercase; letter-spacing: 0.04em; }

  .empty { padding: 40px; text-align: center; color: var(--psd-whulge); font-style: italic; }
  footer { margin: 30px 0 0; font-size: 0.8rem; color: var(--psd-whulge); text-align: center; }
  footer a { color: var(--psd-cedar); }
  footer .contact-footer { color: var(--psd-cedar); font-weight: 600; }
  .mode-decisions footer .contact-footer { display: none; }

  .mode-public .col-confidence,
  .mode-public .col-tcc-qtr { display: none; }

  @media print {
    .toolbar, .toolbar-row2, header, footer, .editor, .banner { display: none; }
    body { background: white; }
    main { padding: 0; }
    table { border: 0; }
    th { position: static; }
    tr.row { page-break-inside: avoid; }
  }
</style>
</head>
<body class="mode-##MODE##">
<header>
  <h1>##H1##</h1>
  <div class="sub">
    <span class="audience">##AUDIENCE##</span>
    Mapping TCC → Washington SBE credit types ·
    5 quarter credits = 1.0 HS credit (100-level &amp; above)
    <span class="contact">· Questions? Talk to your high school counselor.</span>
  </div>
  <div class="catalog-meta" id="catalog-meta"></div>
</header>

<main>
  <div id="banner" class="banner banner-warn" style="display:none;"></div>

  <section class="summary" id="summary"></section>

  <section class="toolbar">
    <label>Search
      <input id="search" type="search" placeholder="code, title, description…" autocomplete="off" />
    </label>
    <label>Credit Type
      <select id="filter-type">
        <option value="">All types</option>
        ##TYPE_OPTIONS##
      </select>
    </label>
    <label>Department
      <select id="filter-dept">
        <option value="">All departments</option>
        ##DEPT_OPTIONS##
      </select>
    </label>
    <label>Level
      <select id="filter-level">
        <option value="">All levels</option>
        <option value="100+">100-level &amp; above</option>
        <option value="sub100">Sub-100 (Fresh Start)</option>
      </select>
    </label>
    <label class="filter-flag">Review Status
      <select id="filter-flag">
        <option value="">All</option>
        <option value="flagged">Has review flag</option>
        <option value="clean">No flags</option>
        <option value="lowconf">Confidence &lt; 0.80</option>
        <option value="decided">Has decision</option>
        <option value="pending">Pending decision</option>
      </select>
    </label>
    <label class="filter-recent">Recent decisions
      <select id="filter-recent">
        <option value="">All</option>
        <option value="30d">Last 30 days</option>
        <option value="sy">Current school year</option>
      </select>
    </label>
    <button id="clear" class="secondary" title="Reset all filters">Clear filters</button>
  </section>

  <section class="toolbar2">
    <fieldset class="cb-group inline-cb-group" id="filter-institution-group">
      <legend>Institutions</legend>
      <!-- populated at boot -->
    </fieldset>
    <div class="filter-confidence">
      <label for="filter-confidence-slider">
        Hide rows with confidence ≥
        <output id="filter-confidence-value">0.80</output>
        and a decision
      </label>
      <input id="filter-confidence-slider" type="range" min="0" max="1" step="0.05" value="0.80" />
      <label class="cb"><input type="checkbox" id="filter-show-decided" /> show decided rows anyway</label>
    </div>
  </section>

  <div class="toolbar-row2">
    <button id="export-csv" class="secondary" style="height:34px;padding:6px 12px;font-size:0.85rem;">Export filtered → CSV</button>
    <button id="print" class="secondary" style="height:34px;padding:6px 12px;font-size:0.85rem;">Print view</button>
    <button id="refresh-decisions" class="secondary" style="height:34px;padding:6px 12px;font-size:0.85rem;display:none;">Refresh decisions</button>
    <span id="sync-indicator" style="font-size:0.8rem;color:var(--psd-whulge);display:none;">Last synced: never</span>
    <span class="count-readout" id="count-readout"></span>
  </div>

  <table id="tbl">
    <thead>
      <tr>
        <th data-sort="code">Code <span class="arrow">↕</span></th>
        <th data-sort="title">Title <span class="arrow">↕</span></th>
        <th data-sort="department">Department <span class="arrow">↕</span></th>
        <th data-sort="credits_total" style="text-align:right;" class="col-tcc-qtr">TCC qtr <span class="arrow">↕</span></th>
        <th data-sort="hs_credits" style="text-align:right;">HS credits <span class="arrow">↕</span></th>
        <th data-sort="credit_type">Credit Type <span class="arrow">↕</span></th>
        <th data-sort="confidence" style="text-align:right;" class="col-confidence">Conf <span class="arrow">↕</span></th>
      </tr>
    </thead>
    <tbody id="tbody"></tbody>
  </table>

  <div class="empty" id="empty" style="display:none;">No courses match the current filters.</div>

  <footer>
    <span class="contact-footer">Questions? Talk to your high school counselor. ·</span>
    Source: <a href="https://catalog.tacomacc.edu/" target="_blank" rel="noopener">TCC 2025-2026 Catalog</a> ·
    Credit framework: <a href="https://sbe.wa.gov/our-work/graduation-requirements" target="_blank" rel="noopener">WA SBE Graduation Requirements</a> ·
    Peninsula School District
  </footer>
</main>

<script>
const MODE = "##MODE##";              // "decisions" or "public"
const APPS_SCRIPT_URL = "##APPS_SCRIPT_URL##";
const DECIDER_ROLES = ##DECIDER_ROLES##;
const INSTITUTIONS = ##INSTITUTIONS##;
const INSTITUTION_LABEL = Object.fromEntries(INSTITUTIONS.map(i => [i.id, i.label]));
let DATA = ##DATA##;
// Public mode loads data from a sidecar JSON file alongside the HTML.
const DATA_SIDECAR_URL = "./equivalency-data.json";

// In-memory decisions keyed by course_code
let DECISIONS = {};
const LS_KEY = "ctc-psd-decisions-cache-v1";

const PILL_CLASS = {
  "ELA": "pill-ela",
  "Math": "pill-math",
  "Science (Lab)": "pill-science",
  "Science (Non-Lab)": "pill-science",
  "Social Studies - US History": "pill-ss",
  "Social Studies - World History": "pill-ss",
  "Social Studies - Washington State History": "pill-ss",
  "Social Studies - Civics": "pill-ss",
  "Social Studies - Elective": "pill-ss",
  "Fine & Performing Arts": "pill-arts",
  "World Language": "pill-lang",
  "Health": "pill-health",
  "PE / Fitness": "pill-pe",
  "CTE": "pill-cte",
  "Elective": "pill-elec",
};

const $ = (s) => document.querySelector(s);
const tbody = $("#tbody");
const search = $("#search");
const filterType = $("#filter-type");
const filterDept = $("#filter-dept");
const filterLevel = $("#filter-level");
const filterFlag = $("#filter-flag");
const filterRecent = $("#filter-recent");
const filterInstGroup = $("#filter-institution-group");
const filterConfSlider = $("#filter-confidence-slider");
const filterConfValue = $("#filter-confidence-value");
const filterShowDecided = $("#filter-show-decided");

// Selected institution filter values. Empty = all institutions.
let selectedInsts = new Set();

function populateInstitutionFilter() {
  const present = new Set(DATA.map(c => c.institution).filter(Boolean));
  filterInstGroup.innerHTML = "<legend>Institutions</legend>";
  for (const inst of INSTITUTIONS) {
    if (!present.has(inst.id)) continue;
    const label = document.createElement("label");
    label.className = "cb";
    label.innerHTML = `<input type="checkbox" value="${inst.id}" checked /> ${inst.label}`;
    label.querySelector("input").addEventListener("change", (e) => {
      if (e.target.checked) selectedInsts.add(inst.id);
      else selectedInsts.delete(inst.id);
      render();
      buildSummary();
    });
    selectedInsts.add(inst.id);
    filterInstGroup.appendChild(label);
  }
}

// Current school year cutoff for the public "this SY" filter
function currentSchoolYearStart() {
  const now = new Date();
  const year = now.getMonth() >= 8 ? now.getFullYear() : now.getFullYear() - 1;
  return new Date(year, 8, 1); // Sep 1
}
const empty = $("#empty");
const countReadout = $("#count-readout");
const banner = $("#banner");

let sortKey = "code";
let sortDir = 1;
let openCode = null;

// ---- Decision storage ----
// v2: DECISIONS is keyed by "course_code|institution".
// Lookup maps rebuilt on every fetch / save:
//   DECISIONS_BY_KEY:      "course_code|institution" → decision (same as DECISIONS)
//   DECISIONS_BY_CODE_ALL: course_code → decision (when applies_to includes "all")
let DECISIONS_BY_KEY = new Map();
let DECISIONS_BY_CODE_ALL = new Map();

function parsePipe(s) {
  if (s == null || s === "") return [];
  if (Array.isArray(s)) return s.slice();
  return String(s).split("|").map(x => x.trim()).filter(Boolean);
}
function joinPipe(arr) {
  if (!arr || !arr.length) return "";
  return arr.join("|");
}

function normalizeDecision(d) {
  return {
    ...d,
    applies_to: parsePipe(d.applies_to),
    override_credit_types: parsePipe(d.override_credit_types || d.override_credit_type),
    override_credit_type: "",
    institution: d.institution || "tcc",
  };
}

function decisionKey(d) {
  return (d.course_code || "") + "|" + (d.institution || "tcc");
}

function indexDecisions() {
  DECISIONS_BY_KEY = new Map();
  DECISIONS_BY_CODE_ALL = new Map();
  for (const key of Object.keys(DECISIONS)) {
    const d = DECISIONS[key];
    if (!d || !d.course_code) continue;
    DECISIONS_BY_KEY.set(decisionKey(d), d);
    if (d.applies_to && d.applies_to.includes("all")) {
      DECISIONS_BY_CODE_ALL.set(d.course_code, d);
    }
  }
}

function loadCache() {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (!raw) return;
    const parsed = JSON.parse(raw);
    DECISIONS = {};
    for (const k of Object.keys(parsed)) {
      const d = normalizeDecision(parsed[k]);
      DECISIONS[decisionKey(d)] = d;
    }
    indexDecisions();
  } catch {}
}
function saveCache() {
  try { localStorage.setItem(LS_KEY, JSON.stringify(DECISIONS)); } catch {}
}

function backendConfigured() {
  return APPS_SCRIPT_URL && !APPS_SCRIPT_URL.startsWith("REPLACE_WITH");
}

function updateSyncIndicator(state) {
  const el = document.getElementById("sync-indicator");
  if (!el) return;
  const now = new Date().toLocaleTimeString();
  if (state === "ok")      el.textContent = "Last synced: " + now;
  else if (state === "paused") el.textContent = "Auto-sync paused (editor open)";
  else if (state === "err") el.textContent = "Last sync failed at " + now;
}

async function fetchDecisions() {
  if (!backendConfigured()) {
    if (MODE === "decisions") {
      banner.style.display = "";
      banner.className = "banner banner-warn";
      banner.innerHTML = "<strong>Decisions backend not configured yet.</strong> See <code>decisions_setup/SETUP.md</code> — deploy the Apps Script and paste the URL into <code>APPS_SCRIPT_URL</code>. Decisions you make here will only persist locally until then.";
    }
    return false;
  }
  try {
    const res = await fetch(APPS_SCRIPT_URL + "?action=list", { method: "GET" });
    if (!res.ok) throw new Error("HTTP " + res.status);
    const j = await res.json();
    if (!j.ok) throw new Error(j.error || "unknown");
    DECISIONS = {};
    for (const raw of j.decisions) {
      const d = normalizeDecision(raw);
      DECISIONS[decisionKey(d)] = d;
    }
    indexDecisions();
    saveCache();
    banner.style.display = "none";
    updateSyncIndicator("ok");
    return true;
  } catch (err) {
    banner.style.display = "";
    banner.className = "banner banner-warn";
    banner.textContent = "Couldn't load live decisions (" + err.message + "). Showing cached copy.";
    updateSyncIndicator("err");
    return false;
  }
}

async function postDecision(decision) {
  // Serialize arrays to pipe-delim strings for the Apps Script payload.
  const payload = {
    ...decision,
    applies_to: Array.isArray(decision.applies_to) ? joinPipe(decision.applies_to) : decision.applies_to,
    override_credit_types: Array.isArray(decision.override_credit_types) ? joinPipe(decision.override_credit_types) : (decision.override_credit_types || ""),
  };
  if (!backendConfigured()) {
    const d = normalizeDecision({ ...payload, last_updated: new Date().toISOString() });
    DECISIONS[decisionKey(d)] = d;
    indexDecisions();
    saveCache();
    return { ok: true, offline: true };
  }
  const res = await fetch(APPS_SCRIPT_URL, {
    method: "POST",
    headers: { "Content-Type": "text/plain;charset=utf-8" },  // avoids CORS preflight
    body: JSON.stringify(payload),
  });
  const j = await res.json();
  if (!j.ok) throw new Error(j.error || "save failed");
  const d = normalizeDecision(j.decision);
  DECISIONS[decisionKey(d)] = d;
  indexDecisions();
  saveCache();
  return j;
}

function effective(c) {
  // Cross-institution decision lookup:
  //   1. Direct match: a decision keyed to (c.code, c.institution)
  //   2. All-scope match: a decision with applies_to includes "all" and
  //      course_code matches either c.code or c.common_code
  const inst = c.institution || "tcc";
  let d = DECISIONS_BY_KEY.get(c.code + "|" + inst);
  if (!d) {
    const codeForAll = c.common_code || c.code;
    d = DECISIONS_BY_CODE_ALL.get(codeForAll) || DECISIONS_BY_CODE_ALL.get(c.code);
  }
  const auto_types = c.credit_types || (c.credit_type ? [c.credit_type] : []);
  const override_types = d && d.override_credit_types && d.override_credit_types.length
    ? d.override_credit_types.slice()
    : null;
  const credit_types = override_types || auto_types.slice();
  return {
    credit_type: credit_types[0] || "Elective",
    credit_types,
    hs_credits: (d && (d.override_hs_credits !== "" && d.override_hs_credits != null)) ? d.override_hs_credits : c.hs_credits,
    decided: !!d,
    decision: d || null,
    decision_is_cross: !!(d && d.applies_to && d.applies_to.includes("all") && d.institution !== inst),
  };
}

function fmtCredits(v) {
  if (v == null) return "—";
  if (typeof v === "object") return v.min + "–" + v.max;
  return String(v);
}
function pill(type) {
  const cls = PILL_CLASS[type] || "pill-elec";
  return '<span class="pill ' + cls + '">' + type + '</span>';
}
function pills(types) {
  if (!types || !types.length) return pill("Elective");
  return '<span class="pill-group">' + types.map(pill).join("") + '</span>';
}
function sameTypes(a, b) {
  if (!a || !b) return false;
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return false;
  return true;
}
function flagBadges(c) {
  const out = [];
  const eff = effective(c);
  if (eff.decision) {
    const status = eff.decision.status || "decided";
    out.push('<span class="flag flag-decided"><span class="dot dot-' + status + '"></span>' + status + '</span>');
  }
  if (MODE === "decisions") {
    if (c.is_sub_100) out.push('<span class="flag flag-sub100">Sub-100</span>');
    const autoTypes = c.credit_types || [c.credit_type];
    if (autoTypes.includes("CTE")) out.push('<span class="flag flag-cte">CTE review</span>');
    const otherFlags = c.review_flags.filter(f => !/Sub-100/i.test(f) && !/^CTE/.test(f));
    if (otherFlags.length) out.push('<span class="flag flag-review">Review</span>');
  }
  return out.join(" ");
}

function applyFilters() {
  const q = search.value.trim().toLowerCase();
  const t = filterType.value;
  const d = filterDept.value;
  const l = filterLevel.value;
  const f = filterFlag.value;
  const recent = filterRecent ? filterRecent.value : "";
  const confThreshold = parseFloat(filterConfSlider ? filterConfSlider.value : "0");
  const showDecided = filterShowDecided ? filterShowDecided.checked : true;
  const syStart = recent === "sy" ? currentSchoolYearStart() : null;
  const cutoff30 = recent === "30d" ? new Date(Date.now() - 30 * 86400000) : null;
  return DATA.filter(c => {
    if (q) {
      const hay = (c.code + " " + c.title + " " + (c.description || "")).toLowerCase();
      if (!hay.includes(q)) return false;
    }
    const eff = effective(c);
    if (selectedInsts.size && !selectedInsts.has(c.institution)) return false;
    if (t && !eff.credit_types.includes(t)) return false;
    if (d && c.department !== d) return false;
    if (l === "100+" && c.is_sub_100) return false;
    if (l === "sub100" && !c.is_sub_100) return false;
    if (f === "flagged" && !c.review_flags.length) return false;
    if (f === "clean" && c.review_flags.length) return false;
    if (f === "lowconf" && c.confidence >= 0.80) return false;
    if (f === "decided" && !eff.decision) return false;
    if (f === "pending" && eff.decision && eff.decision.status === "decided") return false;
    if (f === "pending" && !c.review_flags.length && !eff.decision) return false;
    if (recent && !eff.decision) return false;
    if (recent && eff.decision && eff.decision.decided_date) {
      const dd = new Date(eff.decision.decided_date);
      if (recent === "30d" && dd < cutoff30) return false;
      if (recent === "sy" && dd < syStart) return false;
    } else if (recent) {
      return false;
    }
    // Confidence-slider gate (decisions mode only — `filter-confidence` is
    // hidden in public mode via CSS, the slider stays at default 0.80).
    if (MODE === "decisions" && confThreshold > 0 && c.confidence >= confThreshold) {
      if (eff.decision && !showDecided) return false;
    }
    return true;
  });
}

function sortRows(rows) {
  return rows.slice().sort((a, b) => {
    const ea = effective(a), eb = effective(b);
    const get = (c, e) => {
      if (sortKey === "credit_type") return e.credit_type;
      if (sortKey === "hs_credits") {
        const v = e.hs_credits;
        return v == null ? -1 : (typeof v === "object" ? v.min : v);
      }
      if (sortKey === "credits_total") {
        const v = c.credits_total;
        return v == null ? -1 : (typeof v === "object" ? v.min : v);
      }
      return c[sortKey] ?? "";
    };
    const av = get(a, ea), bv = get(b, eb);
    if (av < bv) return -1 * sortDir;
    if (av > bv) return 1 * sortDir;
    return 0;
  });
}

function render() {
  const rows = sortRows(applyFilters());
  empty.style.display = rows.length ? "none" : "block";
  $("#tbl").style.display = rows.length ? "" : "none";
  countReadout.textContent = `${rows.length.toLocaleString()} of ${DATA.length.toLocaleString()} courses`;
  tbody.innerHTML = "";
  const frag = document.createDocumentFragment();
  for (const c of rows) {
    const eff = effective(c);
    const tr = document.createElement("tr");
    tr.className = "row" + (c.code === openCode ? " open" : "");
    tr.dataset.code = c.code;
    const hsCell = eff.decision && eff.decision.override_hs_credits !== "" && eff.decision.override_hs_credits != null && String(eff.hs_credits) !== String(c.hs_credits)
      ? `<span class="struck">${fmtCredits(c.hs_credits)}</span> ${fmtCredits(eff.hs_credits)}`
      : fmtCredits(c.hs_credits);
    const autoTypes = c.credit_types || [c.credit_type];
    const typeCell = eff.decision && eff.decision.override_credit_type && !sameTypes(eff.credit_types, autoTypes)
      ? `<span class="struck">${pills(autoTypes)}</span> ${pills(eff.credit_types)}`
      : pills(eff.credit_types);
    tr.innerHTML =
      `<td class="code">${c.code}</td>` +
      `<td>${escapeHTML(c.title)} ${flagBadges(c)}</td>` +
      `<td class="dept">${escapeHTML(c.department || "")}</td>` +
      `<td class="credits col-tcc-qtr">${fmtCredits(c.credits_total)}</td>` +
      `<td class="credits">${hsCell}</td>` +
      `<td>${typeCell}</td>` +
      `<td class="credits col-confidence">${(c.confidence * 100).toFixed(0)}%</td>`;
    frag.appendChild(tr);
    if (c.code === openCode) frag.appendChild(detailRow(c, eff));
  }
  tbody.appendChild(frag);
}

function detailRow(c, eff) {
  const tr = document.createElement("tr");
  const decided = eff.decision;
  const editor = MODE === "decisions" ? editorHTML(c, decided) : "";
  const scopeLabel = decided && decided.applies_to
    ? (decided.applies_to.includes("all")
        ? "all colleges"
        : decided.applies_to.map(id => INSTITUTION_LABEL[id] || id).join(", "))
    : "";
  const decidedNote = decided
    ? `<div class="decided-note">
        <strong>Decision (${decided.status || "decided"}):</strong> ${escapeHTML(decided.rationale) || "<em>no rationale</em>"}
        <div class="meta">
          ${decided.decided_by ? escapeHTML(decided.decided_by) + " · " : ""}
          ${decided.decided_date ? escapeHTML(decided.decided_date) + " · " : ""}
          ${scopeLabel ? "applies to: " + escapeHTML(scopeLabel) + " · " : ""}
          ${decided.source_citation ? "source: " + escapeHTML(decided.source_citation) : ""}
        </div>
      </div>`
    : "";

  let advanced = "";
  if (MODE === "decisions") {
    advanced = `<div class="grid" style="margin-top:10px;">
      <div class="box"><div class="lbl">Components</div>${
        c.components.length
          ? c.components.map(co => co.type + ": " + (co.credits != null ? co.credits : (co.credits_min + "–" + co.credits_max))).join("<br>")
          : "—"}</div>
      <div class="box"><div class="lbl">Prerequisites</div>${escapeHTML(c.prerequisites) || "—"}</div>
      <div class="box"><div class="lbl">Level</div>${c.level} ${c.is_sub_100 ? "(sub-100)" : "(100+)"}</div>
      <div class="box"><div class="lbl">Auto classification</div>${escapeHTML((c.credit_types || [c.credit_type]).join(" + "))} · ${escapeHTML(c.classification_rule)} · confidence ${(c.confidence*100).toFixed(0)}%</div>
    </div>
    ${c.review_flags.length
      ? `<h4 style="margin-top:14px;">Review flags</h4><ul class="flags-list">${c.review_flags.map(f => "<li>" + escapeHTML(f) + "</li>").join("")}</ul>`
      : ""}`;
  } else {
    advanced = `<div class="grid" style="margin-top:10px;">
      <div class="box"><div class="lbl">Components</div>${
        c.components.length
          ? c.components.map(co => co.type + ": " + (co.credits != null ? co.credits : (co.credits_min + "–" + co.credits_max))).join("<br>")
          : "—"}</div>
      <div class="box"><div class="lbl">Prerequisites</div>${escapeHTML(c.prerequisites) || "—"}</div>
    </div>`;
  }

  tr.innerHTML = `<td colspan="7" class="detail">
    <h4>Description</h4>
    <p class="desc">${escapeHTML(c.description) || "<em>None provided.</em>"}</p>
    ${decidedNote}
    ${advanced}
    ${editor}
  </td>`;
  return tr;
}

function editorHTML(c, d) {
  const v = d || {};
  const roleOpts = DECIDER_ROLES.map(r => `<option value="${r}"${v.decided_by===r?" selected":""}>${r}</option>`).join("");
  const statusOpts = ["pending","decided","disputed"].map(s => `<option value="${s}"${(v.status||"decided")===s?" selected":""}>${s}</option>`).join("");
  const today = new Date().toISOString().slice(0,10);

  // applies_to default: "all" for &-courses, [c.institution] for local.
  // Locked = local-prefix courses can only scope to their own institution
  // (you can't decide an Olympic-specific code's behavior at TCC).
  const isCommon = !!c.is_common_course;
  const currentApplies = (v.applies_to && v.applies_to.length)
    ? v.applies_to
    : (isCommon ? ["all"] : [c.institution || "tcc"]);
  const allChecked = currentApplies.includes("all");
  const appliesChecks =
    `<label class="cb"><input type="checkbox" name="applies_to" value="all" ${allChecked?"checked":""} ${isCommon?"":"disabled title=\"Only available for & WA Common Course Numbers\""}/> all colleges</label>` +
    INSTITUTIONS.map(inst => {
      const checked = !allChecked && currentApplies.includes(inst.id);
      const disabledForLocal = !isCommon && inst.id !== (c.institution || "tcc");
      return `<label class="cb"><input type="checkbox" name="applies_to" value="${inst.id}" ${checked?"checked":""} ${allChecked || disabledForLocal?"disabled":""}/> ${escapeHTML(inst.label)}</label>`;
    }).join("");

  // override_credit_types multi-select via checkbox group
  const currentOverride = v.override_credit_types || [];
  const ctypeChecks = Object.keys(PILL_CLASS).map(t => {
    const checked = currentOverride.includes(t);
    return `<label class="cb"><input type="checkbox" name="override_credit_types" value="${escapeHTML(t)}" ${checked?"checked":""}/> ${escapeHTML(t)}</label>`;
  }).join("");

  const autoLabel = (c.credit_types || [c.credit_type]).join(" + ");

  return `<div class="editor" data-code="${c.code}" data-institution="${c.institution || "tcc"}">
    <h4>Decision editor</h4>
    <div class="editor-row">
      <label>Status<select name="status">${statusOpts}</select></label>
      <label>Decided by<select name="decided_by"><option value="">—</option>${roleOpts}</select></label>
      <label>Decided date<input name="decided_date" type="date" value="${v.decided_date || today}" /></label>
    </div>
    <label class="cb-group-label">Applies to ${isCommon ? '<span class="hint">(WA Common Course — defaults to all colleges)</span>' : '<span class="hint">(local-prefix course — single college only)</span>'}</label>
    <div class="cb-group">${appliesChecks}</div>
    <label class="cb-group-label">Override credit types <span class="hint">(leave all unchecked to keep auto: ${escapeHTML(autoLabel)})</span></label>
    <div class="cb-group">${ctypeChecks}</div>
    <div class="editor-row">
      <label>Override HS credits
        <input name="override_hs_credits" type="text" placeholder="(keep auto: ${fmtCredits(c.hs_credits)})" value="${v.override_hs_credits ?? ""}" />
      </label>
      <label>Source citation
        <input name="source_citation" type="text" placeholder="WAC §, OSPI memo, etc." value="${escapeHTML(v.source_citation || "")}" />
      </label>
      <label>Decided for year
        <input name="decided_for_year" type="text" value="${escapeHTML(v.decided_for_year || "2025-2026")}" />
      </label>
    </div>
    <label class="rationale-label">Rationale
      <textarea name="rationale" placeholder="Why this decision? Cite the rule, precedent, or pathway.">${escapeHTML(v.rationale || "")}</textarea>
    </label>
    <div class="editor-actions">
      <button data-act="save">Save decision</button>
      ${d ? '<button class="danger" data-act="clear">Clear decision</button>' : ''}
      <span class="status-msg"></span>
    </div>
  </div>`;
}

function escapeHTML(s) {
  return String(s ?? "").replace(/[&<>"']/g, m => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[m]));
}

function buildSummary() {
  // Double-count: a course with credit_types ["CTE", "SS - Elective"] adds 1
  // to both buckets. This is the intentional behavior (8.1 in the plan).
  const counts = {};
  for (const c of DATA) {
    const types = effective(c).credit_types;
    for (const t of types) counts[t] = (counts[t] || 0) + 1;
  }
  const order = Object.keys(PILL_CLASS);
  const sum = $("#summary");
  sum.innerHTML = "";
  for (const t of order) {
    if (!counts[t]) continue;
    const d = document.createElement("div");
    d.className = "stat";
    d.innerHTML = `<div class="n">${counts[t]}</div><div class="l">${t}</div>`;
    d.style.cursor = "pointer";
    d.title = "Filter to " + t;
    d.addEventListener("click", () => { filterType.value = t; render(); });
    sum.appendChild(d);
  }
}

function buildCatalogMeta() {
  const el = document.getElementById("catalog-meta");
  if (!el) return;
  // One badge per unique (institution, catalog_year) seen in the dataset.
  // Uses the most recent uploaded_at for that pair.
  const groups = new Map();
  for (const c of DATA) {
    if (!c.institution) continue;
    const key = c.institution + "|" + (c.catalog_year || "");
    const prev = groups.get(key);
    if (!prev || (c.uploaded_at || "") > (prev.uploaded_at || "")) {
      groups.set(key, {
        institution: c.institution, catalog_year: c.catalog_year,
        uploaded_at: c.uploaded_at, count: (prev ? prev.count : 0) + 1,
      });
    } else {
      prev.count += 1;
    }
  }
  const INST_LABEL = {
    tcc: "TCC", olympic: "Olympic", greenriver: "Green River",
    pierce: "Pierce", cloverpark: "Clover Park", bates: "Bates",
  };
  el.innerHTML = "";
  for (const g of [...groups.values()].sort((a, b) => a.institution.localeCompare(b.institution))) {
    const label = INST_LABEL[g.institution] || g.institution;
    const div = document.createElement("div");
    div.innerHTML = `<span class="inst">${label} ${g.catalog_year || ""}</span>` +
      (g.uploaded_at ? `(uploaded ${g.uploaded_at})` : "") +
      ` · ${g.count.toLocaleString()} courses`;
    el.appendChild(div);
  }
}

function exportCSV() {
  const rows = sortRows(applyFilters());
  const header = ["institution","code","title","department","credits_total_qtr","hs_credits","level","is_sub_100","credit_types","effective_credit_types","effective_hs_credits","confidence","review_flags","decision_status","decision_by","decision_date","decision_rationale","catalog_year","uploaded_at","description"];
  const csv = [header.join(",")];
  const q = (v) => {
    if (v == null) return "";
    let s = typeof v === "object" ? JSON.stringify(v) : String(v);
    if (/[",\n]/.test(s)) s = '"' + s.replace(/"/g, '""') + '"';
    return s;
  };
  for (const c of rows) {
    const eff = effective(c);
    const d = eff.decision || {};
    const autoTypes = (c.credit_types || [c.credit_type]).join(" | ");
    csv.push([
      c.institution, c.code, c.title, c.department, c.credits_total, c.hs_credits, c.level, c.is_sub_100,
      autoTypes, eff.credit_types.join(" | "), eff.hs_credits, c.confidence,
      c.review_flags.join(" | "),
      d.status || "", d.decided_by || "", d.decided_date || "", d.rationale || "",
      c.catalog_year || "", c.uploaded_at || "",
      c.description
    ].map(q).join(","));
  }
  const blob = new Blob([csv.join("\n")], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "ctc-psd-equivalency-filtered.csv";
  a.click();
  URL.revokeObjectURL(a.href);
}

async function handleEditor(ev) {
  const btn = ev.target.closest("button[data-act]");
  if (!btn) return;
  ev.stopPropagation();
  const editor = btn.closest(".editor");
  const code = editor.dataset.code;
  const statusMsg = editor.querySelector(".status-msg");
  const act = btn.dataset.act;
  const institution = editor.dataset.institution || "tcc";
  if (act === "save") {
    const fd = { course_code: code, institution };
    // Collect single-value inputs (not checkbox groups)
    editor.querySelectorAll("[name]:not(input[type=checkbox])").forEach(el => {
      fd[el.name] = el.value;
    });
    // Collect checkbox groups into arrays
    const applies = [];
    editor.querySelectorAll('input[type=checkbox][name="applies_to"]:checked').forEach(el => applies.push(el.value));
    fd.applies_to = applies.length ? applies : [institution];
    const overrides = [];
    editor.querySelectorAll('input[type=checkbox][name="override_credit_types"]:checked').forEach(el => overrides.push(el.value));
    fd.override_credit_types = overrides;
    statusMsg.textContent = "Saving…";
    try {
      const r = await postDecision(fd);
      statusMsg.textContent = r.offline ? "Saved locally (no backend)" : "Saved.";
      render();
      buildSummary();
    } catch (e) {
      statusMsg.textContent = "Error: " + e.message;
    }
  } else if (act === "clear") {
    if (!confirm("Clear the decision for " + code + "?")) return;
    // Clearing = append a new row with status='pending' and blank overrides
    // (preserves audit trail). The cleared row will not match any auto types,
    // so effective() falls through to auto classification.
    const cleared = {
      course_code: code, institution,
      applies_to: [institution], status: "pending",
      override_credit_types: [], override_hs_credits: "",
      rationale: "(cleared)", decided_by: "", decided_date: "",
      source_citation: "", decided_for_year: "",
    };
    statusMsg.textContent = "Clearing…";
    try {
      await postDecision(cleared);
      // Local removal so the UI immediately reflects the cleared state
      delete DECISIONS[code + "|" + institution];
      indexDecisions();
      saveCache();
      statusMsg.textContent = "Cleared.";
      render();
      buildSummary();
    } catch (e) {
      statusMsg.textContent = "Error: " + e.message;
    }
  }
}

// Wire up events
search.addEventListener("input", render);
filterType.addEventListener("change", render);
filterDept.addEventListener("change", render);
filterLevel.addEventListener("change", render);
filterFlag.addEventListener("change", render);
filterRecent.addEventListener("change", render);
filterConfSlider.addEventListener("input", () => {
  filterConfValue.textContent = parseFloat(filterConfSlider.value).toFixed(2);
  render();
});
filterShowDecided.addEventListener("change", render);
$("#clear").addEventListener("click", () => {
  search.value = ""; filterType.value = ""; filterDept.value = "";
  filterLevel.value = ""; filterFlag.value = ""; filterRecent.value = "";
  filterConfSlider.value = "0.80";
  filterConfValue.textContent = "0.80";
  filterShowDecided.checked = false;
  // Recheck every institution checkbox
  filterInstGroup.querySelectorAll('input[type=checkbox]').forEach(el => {
    el.checked = true;
    selectedInsts.add(el.value);
  });
  openCode = null;
  render();
});
$("#export-csv").addEventListener("click", exportCSV);
$("#print").addEventListener("click", () => window.print());
const refreshBtn = $("#refresh-decisions");
const syncIndicator = document.getElementById("sync-indicator");
if (MODE === "decisions") {
  refreshBtn.style.display = "";
  refreshBtn.addEventListener("click", async () => {
    refreshBtn.textContent = "Refreshing…";
    await fetchDecisions();
    refreshBtn.textContent = "Refresh decisions";
    render();
    buildSummary();
  });
}
// Auto-refresh every 30s in both modes. Pause when the tab is hidden.
// In decisions mode, also pause while a row editor is open so we don't
// clobber a decider's unsaved input.
if (backendConfigured()) {
  syncIndicator.style.display = "";
  setInterval(async () => {
    if (document.hidden) return;
    if (MODE === "decisions" && document.querySelector(".editor")) {
      updateSyncIndicator("paused");
      return;
    }
    const ok = await fetchDecisions();
    if (ok) { render(); buildSummary(); }
  }, 30000);
}
document.querySelectorAll("th[data-sort]").forEach(th => {
  th.addEventListener("click", () => {
    const k = th.dataset.sort;
    if (k === sortKey) sortDir *= -1; else { sortKey = k; sortDir = 1; }
    document.querySelectorAll("th .arrow").forEach(a => a.textContent = "↕");
    th.querySelector(".arrow").textContent = sortDir === 1 ? "↑" : "↓";
    render();
  });
});
tbody.addEventListener("click", (e) => {
  if (e.target.closest(".editor")) return handleEditor(e);
  const tr = e.target.closest("tr.row");
  if (!tr) return;
  openCode = (openCode === tr.dataset.code) ? null : tr.dataset.code;
  render();
});

// Boot
async function boot() {
  loadCache();
  // Sidecar load for public mode (DATA was injected as null)
  if (DATA === null) {
    countReadout.textContent = "Loading…";
    try {
      const res = await fetch(DATA_SIDECAR_URL, { cache: "default" });
      if (!res.ok) throw new Error("HTTP " + res.status);
      DATA = await res.json();
    } catch (err) {
      banner.style.display = "";
      banner.className = "banner banner-warn";
      banner.innerHTML = "Couldn't load course data (" + escapeHTML(err.message)
        + "). The HTML file must be served over http(s) — opening it from <code>file://</code> won't work because of browser security. Contact IT if this is hosted and still failing.";
      DATA = [];
    }
  }
  populateInstitutionFilter();
  buildCatalogMeta();
  buildSummary();
  render();
  fetchDecisions().then(() => { buildSummary(); render(); });
}
boot();
</script>
</body>
</html>
"""

type_opts = "\n".join(f'<option value="{t}">{t}</option>' for t in ctypes)
dept_opts = "\n".join(f'<option value="{d}">{d}</option>' for d in depts)


def emit(mode):
    title = "TCC → PSD Course Equivalency"
    h1 = "Tacoma Community College → PSD Course Equivalency"
    if mode == "decisions":
        audience = "Deciders only"
        h1 = h1 + "  ·  Decisions tool"
        data_injection = data_js  # inline JSON
    else:
        audience = "Counselors · TCC staff · students & families"
        # Public mode: sidecar JSON, fetched at boot. DATA starts as null and
        # the boot sequence pulls equivalency-data.json from the same origin.
        data_injection = "null"

    html = (
        TEMPLATE
        .replace("##TITLE##", title)
        .replace("##H1##", h1)
        .replace("##AUDIENCE##", audience)
        .replace("##MODE##", mode)
        .replace("##DATA##", data_injection)
        .replace("##TYPE_OPTIONS##", type_opts)
        .replace("##DEPT_OPTIONS##", dept_opts)
        .replace("##DATE##", date.today().isoformat())
        .replace("##APPS_SCRIPT_URL##", APPS_SCRIPT_URL)
        .replace("##DECIDER_ROLES##", json.dumps(DECIDER_ROLES))
        .replace("##INSTITUTIONS##", json.dumps(INSTITUTIONS))
    )
    return html


OUT_DEC.write_text(emit("decisions"))
OUT_PUB.write_text(emit("public"))

# Sidecar JSON for the public file — same payload, separate fetch.
OUT_PUB_JSON = HERE / "equivalency-data.json"
OUT_PUB_JSON.write_text(json.dumps(courses, separators=(",", ":")))
print(f"Wrote {OUT_PUB_JSON.name}  ({OUT_PUB_JSON.stat().st_size / 1024:.0f} KB)")
print(f"Wrote {OUT_DEC.name}  ({OUT_DEC.stat().st_size / 1024:.0f} KB)")
print(f"Wrote {OUT_PUB.name}  ({OUT_PUB.stat().st_size / 1024:.0f} KB)")
print()
print("Apps Script URL currently set to:", APPS_SCRIPT_URL)
if APPS_SCRIPT_URL.startswith("REPLACE_WITH"):
    print("→ Deploy the script per decisions_setup/SETUP.md and update APPS_SCRIPT_URL at the top of build_html.py.")
