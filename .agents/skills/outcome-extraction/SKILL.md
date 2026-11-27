---
name: cos-outcome-extraction
description: >-
  Extracts outcome measures and outcome measurement instruments (OMIs) from
  clinical-trial registry records for Core Outcome Set (COS) development. Runs a
  two-part pipeline: (1) de-duplicates and AI-screens ClinicalTrials.gov + WHO
  ICTRP downloads against study-specific exclusion criteria, producing a
  checkable screening table; (2) explodes each study's outcomes into one row per
  outcome and decomposes them into Outcome / OMI / Metric / Time frame, classifying
  domains with the Dodd et al. (2018) taxonomy. Use when extracting trial outcomes,
  building a COS, screening trial registries, processing ClinicalTrials.gov or
  ICTRP exports, or when the user mentions COS, ISARIC, outcome extraction, or
  outcome measurement instruments.
---

# COS Outcome Extraction

## Overview

Two parts, both writing into `assets/COS_extraction_template.xlsx`:

- **Part 1 — Screening.** Merge ClinicalTrials.gov (CTG) and WHO ICTRP downloads,
  remove duplicates, AI-screen the unique records against the project's
  exclusion criteria. Output: the `1. Screening` sheet, made for a human to check.
- **Part 2 — Extraction.** Explode each included study's outcomes into one row per
  outcome and decompose each into **Outcome / OMI / Metric / Time frame**, with
  domain classification. Output: the `2. Extraction` sheet.

The exclusion criteria are **study-specific** — always take them from the user
for the current project; never assume universal criteria.

## The core rule (do not skip)

Registries pack the *what*, *how*, *criteria*, *form* and *when* into one string.
Separate them:

| Field | What to record | Example (complete TMA response) |
|-------|----------------|---------------------------------|
| **Outcome** | What is explicitly being assessed | complete TMA response |
| **OMI / measurement method** | The stated instrument, test or assessment method | platelet count, LDH, serum creatinine (lab) |
| **Definition / criteria** | Thresholds and rules defining the outcome | platelets ≥150×10⁹/L and LDH < ULN and ≥25 % creatinine reduction, on two measurements ≥4 weeks apart |
| **Outcome metric** | Change from baseline, number/percentage, time to response, etc. | percentage achieving response (and, as a separate endpoint, time to response) |
| **Timepoint / assessment period** | When, or over what period, it is assessed | during 26 weeks of treatment |

Platelet, LDH and creatinine thresholds are the *defining criteria* of the outcome, not
outcomes of their own; percentage achieving response and time to response are
*different metrics* and stay as separate rows.

Keep the author's own wording in the **★ Verbatim outcome** column, never paraphrased.
Every row carries the Record ID of its source entry; when one entry yields several rows,
each row shows its own part of the entry's text (see extraction rule 1).

## Automation boundary (token policy)

Spend tokens only on judgement. Columns are colour-coded in the template:
grey = deterministic (scripts, no AI), blue = AI, amber = human.

- **Deterministic (scripts):** IDs, title, sponsor, country, dates, phase, age,
  sex, enrolment, condition, intervention, de-duplication, and the verbatim
  outcome text + its timepoint. Run the scripts below — no model calls.
  Registry columns output by `dedupe.py`: `ctg_id` / `ctg_url` (ClinicalTrials.gov)
  and `ictrp_id` / `ictrp_url` (source registry via ICTRP) — both populated when
  a record appears in both databases, enabling direct one-click verification in either.
- **AI only:** the Outcome/OMI/Metric decomposition, domain classification against
  the closed lists, screening decisions, funder type, income group, control type,
  population. Everything AI writes gets a confidence + "needs review" flag.

> Prefer the **ClinicalTrials.gov v2 JSON API** over the CSV download: it returns
> `measure`, `description`, `timeFrame` as separate fields, so the verbatim
> outcome and timepoint are split for free.

## Workflow

```
Part 1 — Screening
- [ ] Get the project's exclusion criteria from the user (numbered list)
- [ ] Run dedupe.py on the CTG + ICTRP downloads
- [ ] Review fuzzy-flagged duplicates (match basis contains "CONFIRM")
- [ ] AI-screen each Unique record against the criteria; record criterion ID + confidence
- [ ] Write the 1. Screening sheet; PRISMA counts auto-fill at the top
- [ ] Human checks Exclude rows + all low-confidence rows

Part 2 — Extraction
- [ ] Run parse_outcomes.py on the included studies -> one row per outcome (grey cols)
- [ ] For each row, AI fills Outcome / OMI / OMI type / Metric / Domain (Dodd)
- [ ] Flag rows where the verbatim text hides a scale inside the outcome (see below)
- [ ] Human reviews; reviewer decision = Accept / Edit / Reject
```

### Step detail — Part 1

1. **De-duplicate.** `python scripts/dedupe.py --ctg CTG.csv --ictrp ICTRP.csv --out screening.csv`
   Merges on real registry-ID matches first (ICTRP re-publishes CTG records, so most
   duplicates are exact NCT matches), then ICTRP bridge flags / shared secondary IDs,
   then a fuzzy title+date fallback that is **flagged for confirmation, never silent**.
   PRISMA counts print to stderr. Every removed duplicate carries a `match` basis.
2. **Screen with AI.** For each `Unique` record, decide Include / Exclude / Unsure
   against the project criteria. On Exclude, record the **criterion ID** matched and a
   short reason. Set confidence; mark `Needs review = Y` for any Low-confidence or
   borderline call.

### Step detail — Part 2

1. **Explode outcomes.** `python scripts/parse_outcomes.py --ctg CTG.csv --ictrp ICTRP.csv --out outcomes.csv`
   Produces one row per registry entry with `verbatim_outcome`, `time_frame`, and
   `type_of_outcome` filled; the AI columns are intentionally blank.
2. **Decompose with AI.** Apply the extraction rules below to each entry and fill
   Outcome, Definition / criteria, OMI, OMI type, Metric, Time frame, Domain (Dodd),
   Confidence and Confidence rationale, using the controlled lists.

### Extraction rules (reviewer-approved, nephrology pilot, Nov 2026)

1. **Preserve the original wording.** ★ Verbatim outcome holds the author-reported text,
   copied word for word (no paraphrase, no added words). Every row keeps the Record ID of
   its source entry.
   - **Entry with one measure** → the complete entry.
   - **Entry that clearly separates distinct measures** (numbered items "1. … 2. …",
     bullets " - ", or comma-separated items each with its own time frame or unit) → each
     row gets only its own item, as an exact excerpt. Rows that come from the same item
     share it (e.g. "Change from baseline in hematologic parameters (platelets, LDH,
     hemoglobin)" for the platelet, LDH and haemoglobin rows).
   - **Measures not clearly separated** (one sentence naming several things, e.g.
     "Fever (T>37) and chill and pyosis and redness …") → every row keeps the whole
     entry.
   - **One row drawn from several entries** (e.g. a Safety profile row, rule 10) → the
     entries' texts joined, in registry order.

2. **Split bundled outcomes during extraction.** When an entry lists several outcomes,
   extract one outcome per row. Do not leave the reviewer to separate them later.
   - *Exception:* an **explicitly defined composite** outcome stays as one row; record
     its components and its combination rule in Definition / criteria.
   - A list that is not clearly defined as a composite is split; note any uncertainty
     about how the components were assessed in Confidence rationale.
   - *Example:* "Fever (T>37), chill, pyosis and redness at catheter site" is not
     defined as a composite → four rows (fever T>37 °C; chills; pus at the catheter site;
     redness at the catheter site). Do not replace them with an umbrella term such as
     "exit-site infection".

3. **Do not interpret information that is not stated.** Extract only what the registry
   entry or the available full protocol explicitly describes. The study title, clinical
   context or likely intention is not enough to establish an outcome definition. If
   the full protocol clarifies an ambiguous entry, use it and record the source
   (e.g. "Definition from protocol v3, section 8.2") in Confidence rationale.

4. **Separate outcome, measurement, criteria, metric and timepoint** into their own
   fields (see the core-rule table above).

5. **Do not infer an outcome from a named instrument or test.** If only a measurement
   method is reported, record Outcome = `Outcome not explicitly defined` and put the
   method in OMI.
   - "Catheter venous blood sample culture" does not establish catheter-related
     bloodstream infection as the outcome.
   - A named questionnaire (FACIT-Fatigue, EQ-5D-5L, SF-36 v2, PGIS, BDI) identifies the
     instrument; its score is the measurement result. Do not add an unstated outcome
     construct (e.g. do not write "fatigue" or "depression" unless the source says so).
   - Assign a measurement method to a particular outcome only when the source supports
     that link.
   - Never leave a named instrument sitting in the Outcome column.

6. **Distinguish standalone outcomes from components of another outcome.** Platelet count
   is a standalone outcome when the protocol separately assesses its change. When it is
   only used within the definition of complete TMA response, keep it as a component in
   that outcome's Definition / criteria. Do not create extra rows from composite
   components unless they are also assessed separately.

7. **Preserve endpoint differences and missing information.**
   - Keep different metrics, timepoints and primary/secondary designations as separate
     rows, even when they concern the same outcome.
   - Write `Not specified` for missing details; do not assume a method, score type,
     definition or time frame.
   - Do not transfer information between endpoints unless the protocol establishes that it
     applies. (A registry structure that explicitly ties a line to an endpoint, such as the
     EU CTR "Timepoint(s) of evaluation of this end point" directly under it, does
     establish this.)

8. **Non-outcome registry lines.** Objective statements and stand-alone timepoint lines
   are not outcomes. Extract an outcome from an objective only if the objective
   explicitly names it and no endpoint already covers it; otherwise mark the row Reject.

9. **Every row that is not High confidence gets a Confidence rationale**: one sentence
   on why (bundled, definition missing, outcome not explicitly defined, domain ambiguous,
   registry inconsistency, parsing artefact, information taken from protocol).

10. **All general safety items go in one "Safety profile" row per study.** AEs, SAEs and
    the safety monitoring used to detect them (safety laboratory parameters, liver
    enzymes, vital signs, ECG/QTc, Holter, deaths reported as safety events) are one row:
    Outcome = `Safety profile`, OMI = the items as listed (e.g. "SAE and AE and liver
    enzymes"), Domain = 38. Do not split this rule's items across rows, even if the
    registry lists them in separate entries; combine those entries in one row.
    **Keep separate** (their own rows):
    - Events the registry labels as SAEs but defines as something else, e.g. SAE defined
      as acute rejection, borderline rejection or de novo DSA.
    - Specific clinical events listed under safety, e.g. wound-related infection, sepsis,
      hospitalisation, other wound complications, serious infections.
    - Tolerability, when the registry names it next to safety ("safety, tolerability and
      efficacy").
    - Disease-specific composite outcomes whose name contains "adverse", e.g. major
      adverse kidney events (MAKE); these are efficacy outcomes, not safety.

### Study-level columns (one value per study, repeated on each outcome row)

ID (study number, same for every row of a study) · Reviewer 1 · Record ID · Title ·
Source · Registry ID(s) (CTG + ICTRP merged) · Registry URL(s) (merged) · Conditions ·
**Treatment / Prevention** · Intervention · Control · Study type · Study design · Phase ·
**Population** (Adults / Children / Adults and children) · **Population details** (exact
population, e.g. "adults on maintenance haemodialysis with uraemic pruritus") · Age range ·
Sample size (target for protocols, actual for completed; say which) · Countries ·
**Country income group** · Year started · Year completed · Results published · Author (PI) · PI email · Sponsor ·
Funder · Funder category · Funder notes.

- **Treatment / Prevention:** the study's purpose — Treatment, Prevention or Other. Use
  the registry's primary purpose unless the design clearly contradicts it (e.g. "to
  prevent hypocalcaemia" registered as Treatment → Prevention); note overrides.
- **Country income group:** classify with the World Bank historical classification file
  (`assets/OGHIST_2026_10_08.xlsx`, sheet "Country Analytical
  History"; codes L, LM, UM, H).
  - **Year:** use the column whose "Data for calendar year" equals the study's start year
    (e.g. start 2023 → data 2023 = FY25; start 2021 → FY23). If the start year is newer
    than the latest data year, use the latest column.
  - **Per country:** L, LM or UM → LMIC; H → HIC.
  - **Study value:** all countries in one group → that group (LMIC or HIC); countries in
    different groups → Mixed.
  - Match country names to the World Bank spelling (e.g. Russia → Russian Federation,
    Turkey → Türkiye, Korea → Korea, Rep., Iran → Iran, Islamic Rep.). If a country has no
    code for that year, flag it for review; do not guess.
- **Population:** Children = all participants <18 years; Adults = all ≥18; any trial
  enrolling under 18 together with adults = Adults and children.
- **Sponsor ≠ Funder.** Sponsor = registry primary/lead sponsor. Funder = source of
  money (ICTRP "source of monetary support"; CTG lead sponsor + collaborators).
- **Funder category:** 1 Universities and research institutes · 2 Hospitals and private
  clinics · 3 Industry · 4 Foundations and private individuals · 5 Other · 6 Missing data ·
  7 Governmental · 8 No funder · 9 Mixed · 10 Not sure.

Outcome-level column order: Outcome type · ★ Verbatim outcome · Outcome ·
Definition / criteria · Domain (Dodd) · OMI · OMI type · Metric · Time frame ·
Confidence · Confidence rationale · Needs review · Human decision · Reviewer notes.

### Duplicates and full texts (after protocol extraction)

Tools in `scripts/fulltext_tools/` (run with an isolated Python that has
`pypdf` and `openpyxl`; PDFs are untrusted input — keep their text in a separate folder).

1. **PDF text.** `pdf2txt.py <pdf folder> <txt folder>`. List PDFs that cannot be read
   (e.g. scanned) for manual handling.
2. **Duplicate check — all included protocols.** `fulltext_match.py` flags pairs that
   (a) share any recognised registry ID (own ID or "Secondary IDs"), (b) have public or
   scientific titles ≥85% similar, or (c) share an acronym (>3 characters). Flags are
   candidates only: give each group a verdict with a reason (Likely duplicate / Possible
   duplicate — check / Probably different / Different trials), based on sponsor, start
   date and exact title wording. The reviewer confirms in Human decision.
3. **Full-text match.** The same script finds registry IDs in each PDF's text and links the
   paper to every protocol whose own or secondary ID it names. Match strength:
   - **Strong** — the protocol ID is the only registry ID in the paper; or it appears on
     the first pages, or ≥2 times, and at least as often as any other ID.
   - **Weak — check** — named once, outside the first pages, with other IDs present
     (often only a citation).
   Record each paper's title and DOI (`doi_lookup.py`: DOI from the first page, title
   from Crossref, accepted only if that title appears at the start of the PDF).
   Papers with no matching protocol are listed with the registry IDs they contain; papers
   with no registry ID at all need manual matching (title, drug, population).
4. **Merge protocol and full text** ("Merged protocols-studies" sheet; the protocol leaves
   the Extraction sheet):
   - **Strong match** → merge. **Weak match** → merge only after the reviewer confirms in
     Human decision that the paper reports that trial.
   - Extract outcomes from the full text first, with the same extraction rules; verbatim
     = exact excerpt of the paper.
   - Each row gets an **Outcome source**: `Full text + protocol` (state in Comparison with
     protocol how it differs, e.g. "DEFINITION CHANGED: protocol target ≤6.0; full text
     3.5–6.0"), `Full text only`, or `Protocol only (missing in full text)` — every
     registered outcome the paper does not report is added from the protocol.
   - Study-level column **Protocol outcomes missing in full text** = number of
     `Protocol only` rows.
5. **Summary sheet** — one row per protocol: ID · Record ID · Registry ID(s) · Protocol
   title · Registry link · Possible duplicate registrations · Full text (author year. title.
   journal) · Full text DOI · Sheet where extracted · Reviewer 1.

## Controlled vocabularies

Use the dropdowns already wired into the template; full lists live in
[reference.md](reference.md):
- **Outcome domain (Dodd):** the 38-domain Dodd et al. (2018) taxonomy — the single
  classification layer for every outcome (sheet `Ref_Dodd`).
- **OMI type:** PROM / ClinROM / ObsROM / PerfO / OOM / Composite / Not specified.
- **Metric:** proportion/incidence · time-to-event · change from baseline ·
  mean/GM value · absolute value · AUC · categorical · binary · score change · not stated.

## Scripts

- **scripts/dedupe.py** — de-duplicate CTG + ICTRP, emit the screening table + PRISMA counts. *Execute.*
- **scripts/screen_to_excel.py** — apply AI screening rules and write a two-sheet Excel workbook:
  `1. Screening` (all source fields + AI decisions, amber-highlighted trigger cells, evidence snippets)
  and `Legend & PRISMA` (E1–E4 definitions, PRISMA counts, column guide). *Execute.*
- **scripts/extract_included.py** — read the **human-reviewed** Excel, collect every row where
  `decision == Include` (AI or human), and write `included_studies.csv` for Part 2. *Execute after review.*
- **scripts/parse_outcomes.py** — explode outcomes into rows, fill the grey columns. Preferred mode: `--included included_studies.csv`. Legacy mode: `--ctg` / `--ictrp`. *Execute.*
- **scripts/decompose.py** — AI decomposition step: reads `outcomes_raw.csv` + `included_studies.csv`, fills Outcome / Description / Domain (Dodd) / OMI / OMI type / Metric / Confidence / Needs Review, writes `extraction_results.xlsx` with two sheets. *Execute.*
- **scripts/build_template.py** — regenerate the blank template (dropdowns, codebook, ref tabs). *Execute only to rebuild.*

### Folder structure

```
scratch/Outcome-extraction/
  phase1-screening/          ← all Part 1 files live here
    ctg-studies.csv
    IctrpResults_example.csv
    screening.csv            ← dedupe output (intermediate)
    screening_results.xlsx   ← AI decisions + human_decision / justification columns
                               Reviewer fills in the green columns, does not touch the blue ones.

  phase2-extraction/         ← all Part 2 files live here
    included_studies.csv     ← written by extract_included.py (bridge between phases)
    outcomes_raw.csv         ← parse_outcomes.py output
    extraction_results.xlsx  ← final Part 2 table
```

### Command sequence

```bash
P1=scratch/Outcome-extraction/phase1-screening
P2=scratch/Outcome-extraction/phase2-extraction

# ── Part 1 ──────────────────────────────────────────────────────────────────

# Step 1 — de-duplicate
python scripts/dedupe.py --ctg $P1/CTG.csv --ictrp $P1/ICTRP.csv --out $P1/screening.csv

# Step 2 — AI screening → Excel  (blue columns = AI, green columns = reviewer)
python scripts/screen_to_excel.py --screening $P1/screening.csv \
    --out $P1/screening_results.xlsx --ctg-n 94 --ictrp-n 181 --dup-n 90

# ── Reviewer opens $P1/screening_results.xlsx ────────────────────────────────
# ── Fills human_decision / justification in green columns where needed ───────
# ── Saves file, does not rename or move it ──────────────────────────────────

# Step 3 — extract included (bridge: reads phase1 xlsx → writes phase2 csv)
python scripts/extract_included.py --xlsx $P1/screening_results.xlsx \
    --out $P2/included_studies.csv

# ── Part 2 ──────────────────────────────────────────────────────────────────

# Step 4 — explode outcomes (reads included_studies.csv)
python scripts/parse_outcomes.py --included $P2/included_studies.csv \
    --out $P2/outcomes_raw.csv

# Step 5 — AI decomposition → extraction Excel
python scripts/decompose.py \
    --raw  $P2/outcomes_raw.csv \
    --meta $P2/included_studies.csv \
    --out  $P2/extraction_results.xlsx
```

**Merge rule in extract_included.py:**
`human_decision` filled → use it · blank → use AI `decision`.
Output column `decision_source` = "AI" or "Human" for every row.

Requires Python 3.9+, `openpyxl`, and `pypdf` for the full-text tools. Install: `pip install -r requirements.txt`.

## Quality checks

- PRISMA counts reconcile: identified − duplicates = screened = include + exclude + unsure.
- No fuzzy-flagged duplicate removed without a human tick.
- Every Exclude row cites a criterion ID; every AI row has a confidence.
- No named measurement scale left in the Outcome column.
- Domain values come only from the dropdowns (no free text).

## Additional resources

- [reference.md](reference.md) — full Dodd taxonomy, OMI-type definitions, exact
  CTG/ICTRP field mappings, and registry parsing quirks.
