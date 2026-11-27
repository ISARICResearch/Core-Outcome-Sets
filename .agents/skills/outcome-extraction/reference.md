# COS Outcome Extraction — Reference

Detailed material kept out of SKILL.md for token economy. Read when you need the
full vocabularies or the exact registry field mappings.

## 1. Outcome domain taxonomy — Dodd et al. (2018)

The single outcome-classification layer — every outcome is classified to one of these 38 domains. Source: Dodd S, Clarke M, Becker L,
Mavergames C, Fish R, Williamson PR. *A taxonomy has been developed for outcomes in
medical research to help improve knowledge discovery.* J Clin Epidemiol. 2018;96:84-92.
38 domains in 5 core areas:

- **Mortality/survival:** 1. Mortality/survival
- **Physiological/clinical (2–24):** 2 Blood and lymphatic · 3 Cardiac · 4 Congenital,
  familial and genetic · 5 Endocrine · 6 Ear and labyrinth · 7 Eye · 8 Gastrointestinal ·
  9 General · 10 Hepatobiliary · 11 Immune system · 12 Infection and infestation ·
  13 Injury and poisoning · 14 Metabolism and nutrition · 15 Musculoskeletal and
  connective tissue · 16 Neoplasms · 17 Nervous system · 18 Pregnancy, puerperium and
  perinatal · 19 Renal and urinary · 20 Reproductive system and breast · 21 Psychiatric ·
  22 Respiratory, thoracic and mediastinal · 23 Skin and subcutaneous tissue · 24 Vascular
- **Life impact (25–31):** 25 Physical functioning · 26 Social functioning · 27 Role
  functioning · 28 Emotional functioning/wellbeing · 29 Cognitive functioning · 30 Global
  quality of life · 31 Perceived health status
- **Resource use (32–37):** 32 Delivery of care · 33 Personal circumstances · 34 Economic ·
  35 Hospital · 36 Need for further intervention · 37 Societal/carer burden
- **Adverse events:** 38 Adverse events/effects

The exact strings (with numbers) are in the `Ref_Dodd` sheet — classify to those verbatim.

## 2. OMI type (how the instrument reports)

- **PROM** — Patient-reported outcome measure (symptom diaries, QoL questionnaires).
- **ClinROM** — Clinician-reported (clinical assessment, physician-rated scales).
- **ObsROM** — Observer-reported (carer/parent report, not the patient).
- **PerfO** — Performance outcome (a standardised task the patient performs).
- **OOM** — Objective outcome measure (lab assay, imaging, viral culture, thermometry).
- **Composite OMI** — a defined combination (e.g. a symptom score over several items).
- **Not specified** — registry gives no instrument.

## 3. Metric (analytic form)

proportion / incidence · time-to-event · change from baseline · mean / geometric-mean
value · absolute value or level · AUC · categorical · binary presence/absence · score /
score change · not stated. Normalise capitalisation to the dropdown entry (avoid the
"time to event" / "Time-to-event" drift seen in earlier files).

## 4. ClinicalTrials.gov field mapping

CSV download columns → template:

| Template (grey) | CTG CSV column |
|---|---|
| Registry ID | `NCT Number` |
| Title | `Study Title` · Link `Study URL` |
| Sponsor / Funder | `Sponsor` · Funder type `Funder Type` |
| Condition / Intervention | `Conditions` / `Interventions` |
| Study type / Phase | `Study Type` / `Phases` |
| Age / Sex / Sample size | `Age` / `Sex` / `Enrollment` |
| Year | `Start Date` (or `First Posted`) |
| Verbatim outcome + Type | `Primary/Secondary/Other Outcome Measures` |

**CSV quirk:** each outcome packs `measure, description, timeframe` and the measure
often repeats at the start of the description. The v2 JSON API
(`protocolSection.outcomesModule.primaryOutcomes[].{measure,description,timeFrame}`)
returns them as clean separate fields — prefer it; then no heuristic splitting is needed.

## 5. WHO ICTRP field mapping

| Template (grey) | ICTRP CSV column |
|---|---|
| Registry ID | `TrialID` · Source `Source Register` |
| Secondary IDs | `Secondary ID`, `other records` |
| Title | `Public title` (fallback `Scientific title`) |
| Sponsor | `Primary sponsor` |
| Condition / Intervention | `Condition` / `Intervention` |
| Age / Sex / Sample size | `Inclusion agemin`/`agemax` / `Inclusion gender` / `Target size` |
| Status / Phase / Type | `Recruitment Status` / `Phase` / `Study type` |
| Verbatim outcome + timepoint | `Primary outcome` / `Secondary outcome` (split on `;`, timepoint after `Timepoint:`) |

ICTRP outcomes are narrative ("To evaluate the immunogenicity by ELISA…") and may
contain `<br>` HTML — strip tags, then the AI extracts the concept + instrument.

## 6. De-duplication detail

Merge precedence in `dedupe.py`:
1. **Exact / shared registry ID.** Only strings matching a known registry-ID format
   (NCT, ISRCTN, EUCTR/EudraCT, ChiCTR, CTRI, ACTRN, DRKS, IRCT, UMIN/jRCT, PACTR, etc.)
   are used as merge keys. Free-text secondary-ID values ("Nil", "No", sponsor codes)
   are ignored — they caused mass false-merges when treated as IDs.
2. **ICTRP bridge / shared secondary ID.** ICTRP's `Bridging flag`, `Bridged type` and
   `other records` link cross-registered records; recognised IDs inside them merge.
3. **Fuzzy fallback.** title similarity ≥ 0.90 AND same registration year → merge, but the
   `match` basis is tagged `… — CONFIRM` so a human signs it off. Never silent.

Because ICTRP ingests ClinicalTrials.gov, most real duplicates are exact NCT matches
that surface as a `ClinicalTrials.gov + ICTRP: ClinicalTrials.gov` merged source.
