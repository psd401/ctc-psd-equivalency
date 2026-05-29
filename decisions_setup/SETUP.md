# Decisions backend — v2 upgrade

Goal: migrate the Sheet from the original 10-column schema (v1) to a 16-column append-only schema (v2) that supports multi-institution, cross-college decisions, multi-credit-type overrides, and an audit history. Existing v1 decisions (3 rows as of this writing: ABE19, CHP101, SCI105) are migrated automatically.

Time: ~10 minutes.

## Why this upgrade

- Multi-institution support — when the tool adds Olympic, Green River, Pierce, Clover Park, and Bates, decisions need to be scoped to an institution
- Cross-college decisions — a decision about `HIST&146` (a WA Common Course Number) should apply at every college that offers it
- Multi credit-type overrides — Business Law (CTE + Social Studies Elective) needs an array, not a single value
- Audit history — see who changed what, when. Append-only — old rows are never overwritten

## What you do

### 1. Snapshot the Sheet (insurance)

In the Sheet: **File → Make a copy** → name it **"Decisions backup YYYY-MM-DD"**. Save it somewhere outside the same folder. Done. The original 3 decisions are now safe.

### 2. Replace the Apps Script code

- Open the Sheet → **Extensions → Apps Script**
- Open `Code.gs` (the file you pasted before)
- Replace the entire contents with the new [`Code.gs`](./Code.gs)
- ⌘S to save

Don't worry — the old endpoint URL **keeps working** until you finish step 3.

### 3. Run the migration

- In the Apps Script editor, click the function dropdown (top toolbar, between the disk icon and the Debug button) → select **`migrateV1ToV2`** → click **Run** ▶
- Authorize again if asked (the script now reads from a second sheet)
- The migration creates a new tab called **Decisions_v2** with the 3 existing decisions copied over, each given a fresh `decision_id`, `institution = "tcc"`, `applies_to = "tcc"` (or `"all"` for `&`-prefix courses), `is_current = TRUE`
- Toast notification confirms how many rows were inserted vs skipped

### 4. Deploy a new Web app version

- **Deploy → Manage deployments → pencil icon (Edit)**
- Version: **New version**
- Description: `v2 — append-only, multi-institution`
- Click **Deploy**
- Copy the URL — it's the **same URL as before** (Apps Script keeps the URL stable across deployments)

So: **no URL change needed**. The HTML tool will start hitting the v2 endpoint immediately. Verify with:

```
<your-url>?action=ping
```

Should return:

```json
{"ok": true, "message": "pong", "sheet": "Decisions_v2", "schema": "v2", "rows": 3}
```

### 5. Verify the 3 migrated decisions

In the Sheet, open the **Decisions_v2** tab. You should see:

- ABE19 — `institution = tcc`, `applies_to = tcc`, `is_current = TRUE`
- CHP101 — same
- SCI105 — same

In the HTML tool, refresh — the 3 decisions should still appear on those courses.

### 6. (Later) Archive v1

After 2 weeks of stability (no rollback needed):

- Right-click the **Decisions** tab → **Rename** → `Decisions_v1_archive`
- Hide it (right-click → Hide sheet) so it doesn't clutter the view

## Endpoints (v2)

| Endpoint | Behavior |
|---|---|
| `GET /exec?action=list` | Returns current decisions (is_current=TRUE) as JSON |
| `GET /exec?action=history&course_code=X&institution=Y` | Returns the audit trail for one course at one institution, oldest first |
| `GET /exec?action=ping` | Health check |
| `POST /exec` (JSON body) | Appends a new decision row, supersedes the prior current row for the same `(course_code, institution)` pair |

### Decision payload (POST)

```json
{
  "course_code": "HIST&146",
  "institution": "tcc",
  "applies_to": "all",
  "status": "decided",
  "override_credit_types": "Social Studies - US History|Social Studies - World History",
  "override_hs_credits": "1.0",
  "rationale": "...",
  "decided_by": "Director of Secondary Teaching & Learning",
  "decided_date": "2026-05-29",
  "source_citation": "OSPI K-12 SS standards p.14",
  "decided_for_year": "2025-2026"
}
```

`applies_to` and `override_credit_types` are pipe-delimited (`|`) strings — easier to scan in the Sheet than nested JSON.

## Rollback

If something goes wrong:

- The original `Decisions` sheet is **untouched** by the migration. v1-only HTML still works against the same URL (Apps Script doesn't strip v1 fields)
- To roll back entirely: paste the **previous** `Code.gs` over the new one, **Deploy → Manage deployments → New version**, and the URL serves v1 again
- The backup copy from step 1 is the ultimate safety net

## Schema (v2)

```
decision_id | course_code | institution | applies_to | status |
override_credit_types | override_hs_credits | rationale | decided_by |
decided_date | source_citation | decided_for_year |
is_current | superseded_by | created_at | last_updated
```

## Idempotency

`migrateV1ToV2()` can be re-run safely. It checks `(course_code, institution)` in v2 and skips rows that already exist. Useful if a row was added to v1 mid-migration.
