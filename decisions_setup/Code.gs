/**
 * TCC↔PSD Course Equivalency — Decisions backend v2
 * Bound to spreadsheet: TCC-PSD Course Equivalency
 *
 * v2 changes over v1:
 *  - Append-only audit history: writes never overwrite. Each edit appends a
 *    new row with is_current=TRUE; the prior row is marked is_current=FALSE
 *    and superseded_by=<new decision_id>.
 *  - Multi-institution support: every decision is keyed by
 *    (course_code, institution); applies_to scopes a decision across colleges.
 *  - Multi credit-type overrides: override_credit_types is a pipe-delimited
 *    array, e.g. "CTE|Social Studies - Elective".
 *  - Server-assigned decision_id for opaque cross-references.
 *
 * Endpoints:
 *   GET  ?action=list           → current decisions (is_current=TRUE) as JSON
 *   GET  ?action=history&course_code=X&institution=Y → audit trail for one course
 *   GET  ?action=ping           → health check
 *   POST { course_code, institution, applies_to, ... } → append a new decision
 *
 * CORS: ContentService.MimeType.JSON sets Access-Control-Allow-Origin: *.
 *
 * Migration: run `migrateV1ToV2()` once from the Apps Script editor to copy
 * existing v1 decisions into the new Decisions_v2 sheet. Idempotent.
 */

const SHEET_NAME_V1 = 'Decisions';
const SHEET_NAME = 'Decisions_v2';

const HEADERS = [
  'decision_id',
  'course_code',
  'institution',
  'applies_to',
  'status',
  'override_credit_types',
  'override_hs_credits',
  'rationale',
  'decided_by',
  'decided_date',
  'source_citation',
  'decided_for_year',
  'is_current',
  'superseded_by',
  'created_at',
  'last_updated',
];

// ---------------- Sheet helpers ----------------

function ensureSheet_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sh = ss.getSheetByName(SHEET_NAME);
  if (!sh) sh = ss.insertSheet(SHEET_NAME);
  const firstRow = sh.getRange(1, 1, 1, HEADERS.length).getValues()[0];
  const needsHeaders = firstRow.join('') === '' || firstRow[0] !== HEADERS[0];
  if (needsHeaders) {
    sh.clear();
    sh.getRange(1, 1, 1, HEADERS.length).setValues([HEADERS]);
    sh.setFrozenRows(1);
    sh.getRange(1, 1, 1, HEADERS.length).setFontWeight('bold');
  }
  return sh;
}

function rowsToObjects_(sh) {
  const lastRow = sh.getLastRow();
  if (lastRow < 2) return [];
  const values = sh.getRange(2, 1, lastRow - 1, HEADERS.length).getValues();
  return values
    .filter(r => r[0] !== '')
    .map(r => Object.fromEntries(HEADERS.map((h, i) => {
      let v = r[i];
      if (v instanceof Date) v = v.toISOString().slice(0, 10);
      if (h === 'is_current') v = (v === true || v === 'TRUE' || v === 'true');
      return [h, v];
    })));
}

function findCurrentRow_(sh, course_code, institution) {
  const lastRow = sh.getLastRow();
  if (lastRow < 2) return -1;
  const values = sh.getRange(2, 1, lastRow - 1, HEADERS.length).getValues();
  // Scan from bottom up to bias toward most recent insertion
  for (let i = values.length - 1; i >= 0; i--) {
    const r = values[i];
    if (
      r[1] === course_code &&
      r[2] === institution &&
      (r[12] === true || r[12] === 'TRUE' || r[12] === 'true')
    ) {
      return i + 2;
    }
  }
  return -1;
}

function newDecisionId_() {
  const ts = new Date().toISOString().replace(/[:.]/g, '').slice(0, 15);
  const rand = Math.random().toString(36).slice(2, 7);
  return 'dec_' + ts + '_' + rand;
}

function json_(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

// ---------------- HTTP handlers ----------------

function doGet(e) {
  try {
    const sh = ensureSheet_();
    const action = (e.parameter || {}).action || 'list';
    if (action === 'list') {
      const all = rowsToObjects_(sh);
      return json_({ ok: true, decisions: all.filter(d => d.is_current) });
    }
    if (action === 'history') {
      const code = (e.parameter || {}).course_code;
      const inst = (e.parameter || {}).institution;
      if (!code) return json_({ ok: false, error: 'missing course_code' });
      const all = rowsToObjects_(sh);
      const hist = all
        .filter(d => d.course_code === code && (!inst || d.institution === inst))
        .sort((a, b) => String(a.created_at).localeCompare(String(b.created_at)));
      return json_({ ok: true, history: hist });
    }
    if (action === 'ping') {
      return json_({
        ok: true, message: 'pong', sheet: SHEET_NAME,
        schema: 'v2', rows: sh.getLastRow() - 1,
      });
    }
    return json_({ ok: false, error: 'unknown action: ' + action });
  } catch (err) {
    return json_({ ok: false, error: String(err) });
  }
}

function doPost(e) {
  try {
    const sh = ensureSheet_();
    const body = JSON.parse(e.postData.contents);
    if (!body.course_code) return json_({ ok: false, error: 'missing course_code' });
    if (!body.institution) return json_({ ok: false, error: 'missing institution' });

    const now = new Date().toISOString();
    const newId = newDecisionId_();

    // Supersede prior current row for this (course_code, institution) pair
    const priorRow = findCurrentRow_(sh, body.course_code, body.institution);
    let prior_id = '';
    if (priorRow > 0) {
      // Mark prior is_current=FALSE and superseded_by=newId
      sh.getRange(priorRow, 13).setValue(false);
      sh.getRange(priorRow, 14).setValue(newId);
      prior_id = sh.getRange(priorRow, 1).getValue();
    }

    const created_at = priorRow > 0 ? sh.getRange(priorRow, 15).getValue() : (body.created_at || now);

    const row = HEADERS.map(h => {
      switch (h) {
        case 'decision_id':       return newId;
        case 'is_current':        return true;
        case 'superseded_by':     return '';
        case 'created_at':        return created_at instanceof Date ? created_at.toISOString() : (created_at || now);
        case 'last_updated':      return now;
        default:                  return body[h] !== undefined ? body[h] : '';
      }
    });
    sh.appendRow(row);

    return json_({
      ok: true,
      action: priorRow > 0 ? 'supersede' : 'insert',
      decision_id: newId,
      superseded_id: prior_id,
      decision: Object.fromEntries(HEADERS.map((h, i) => [h, row[i]])),
    });
  } catch (err) {
    return json_({ ok: false, error: String(err) });
  }
}

// ---------------- Migration ----------------

/**
 * One-shot migration from v1 Decisions sheet to v2 Decisions_v2 sheet.
 * Idempotent: skips course_codes that already have a current v2 row.
 * Run this once from the Apps Script editor after deploying v2.
 *
 * v1 → v2 field mapping:
 *   course_code            → course_code  (institution forced to "tcc")
 *   status                 → status
 *   override_credit_type   → override_credit_types (single value, pipe-delim of 1)
 *   override_hs_credits    → override_hs_credits
 *   rationale              → rationale
 *   decided_by             → decided_by
 *   decided_date           → decided_date
 *   source_citation        → source_citation
 *   decided_for_year       → decided_for_year
 *   last_updated           → last_updated
 *
 * applies_to default: "all" if code contains "&" (WA Common Course Number);
 *                     otherwise "tcc" (local-prefix course is TCC-scoped).
 */
function migrateV1ToV2() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const v1 = ss.getSheetByName(SHEET_NAME_V1);
  if (!v1) {
    Logger.log('No v1 sheet "' + SHEET_NAME_V1 + '" found — nothing to migrate.');
    return;
  }
  const v2 = ensureSheet_();

  const lastRow = v1.getLastRow();
  if (lastRow < 2) {
    Logger.log('v1 sheet is empty.');
    return;
  }
  const v1Headers = v1.getRange(1, 1, 1, v1.getLastColumn()).getValues()[0];
  const idx = (h) => v1Headers.indexOf(h);
  const v1Values = v1.getRange(2, 1, lastRow - 1, v1.getLastColumn()).getValues();

  const v2Current = rowsToObjects_(v2).filter(d => d.is_current);
  const seen = new Set(v2Current.map(d => d.course_code + '|' + d.institution));

  let inserted = 0, skipped = 0;
  for (const r of v1Values) {
    const code = r[idx('course_code')];
    if (!code) continue;
    const institution = 'tcc';
    const key = code + '|' + institution;
    if (seen.has(key)) { skipped += 1; continue; }

    const applies_to = String(code).includes('&') ? 'all' : 'tcc';
    const override_v1 = r[idx('override_credit_type')] || '';
    const override_credit_types = override_v1 ? String(override_v1) : '';
    const decided_date_raw = r[idx('decided_date')];
    const decided_date = decided_date_raw instanceof Date
      ? decided_date_raw.toISOString().slice(0, 10)
      : (decided_date_raw || '');
    const last_updated_raw = r[idx('last_updated')];
    const last_updated = last_updated_raw instanceof Date
      ? last_updated_raw.toISOString()
      : (last_updated_raw || new Date().toISOString());

    const row = [
      newDecisionId_(),                        // decision_id
      code,                                    // course_code
      institution,                             // institution
      applies_to,                              // applies_to
      r[idx('status')] || 'decided',           // status
      override_credit_types,                   // override_credit_types
      r[idx('override_hs_credits')] || '',     // override_hs_credits
      r[idx('rationale')] || '',               // rationale
      r[idx('decided_by')] || '',              // decided_by
      decided_date,                            // decided_date
      r[idx('source_citation')] || '',         // source_citation
      r[idx('decided_for_year')] || '',        // decided_for_year
      true,                                    // is_current
      '',                                      // superseded_by
      decided_date || last_updated,            // created_at
      last_updated,                            // last_updated
    ];
    v2.appendRow(row);
    inserted += 1;
    Utilities.sleep(10); // gentle rate limiting
  }
  Logger.log('Migration complete. Inserted: ' + inserted + ', skipped: ' + skipped);
  SpreadsheetApp.getActive().toast('Migrated ' + inserted + ' rows (' + skipped + ' already in v2).', 'TCC-PSD migration', 5);
}
