#!/usr/bin/env python3
"""AI decomposition step — Part 2 of the COS extraction pipeline.

Reads outcomes_raw.csv (from parse_outcomes.py --included) and
included_studies.csv (for study metadata), applies AI decomposition of each
outcome into Outcome / OMI / OMI type / Metric / Domain (Dodd), and writes
extraction_results.xlsx with:

  Sheet "2. Extraction"   — one row per outcome, colour-coded columns
  Sheet "Legend & Dodd"  — Dodd taxonomy, OMI type, metric definitions

Colour scheme (mirrors Phase 1):
  Grey  (D9D9D9) — deterministic fields (scripts)
  Blue  (BDD7EE) — AI-filled fields
  Green (EBF5EB) — human review columns (blank for reviewer to fill)
  Red   (FFD0D0) — rows flagged needs_review = Y

Usage:
  python scripts/decompose.py \\
      --raw  phase2-extraction/outcomes_raw.csv \\
      --meta phase2-extraction/included_studies.csv \\
      --out  phase2-extraction/extraction_results.xlsx
"""
import argparse, csv, sys
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# ── AI decompositions — keyed by (record_id, type_of_outcome, verbatim prefix) ─

# Each entry: (outcome, description, domain_dodd, omi, omi_type, metric, confidence, needs_review)
# Domain strings follow the Dodd et al. (2018) numbering convention.

DECOMP = [
    # ── R0077 ─────────────────────────────────────────────────────────────────
    {
        "record_id": "R0077", "type_of_outcome": "Primary",
        "outcome": "Fever clearance",
        "description": "Proportion of participants achieving body temperature < 38 °C assessed daily over 7 days; also expressed as time to fever clearance",
        "domain_dodd": "9 General",
        "omi": "Body temperature measurement (thermometry)",
        "omi_type": "OOM",
        "metric": "time-to-event",
        "confidence": "Medium",
        "needs_review": "Y",  # verbatim conflates time-to-event and proportion; reviewer to confirm metric
    },
    {
        "record_id": "R0077", "type_of_outcome": "Secondary",
        "outcome": "Virological clearance",
        "description": "Time to clearance of chikungunya virus from blood assessed by daily virological testing",
        "domain_dodd": "12 Infection and infestation",
        "omi": "Virological blood test (PCR or equivalent CHIKV assay)",
        "omi_type": "OOM",
        "metric": "time-to-event",
        "confidence": "High",
        "needs_review": "N",
    },
    # ── R0080 ─────────────────────────────────────────────────────────────────
    {
        "record_id": "R0080", "type_of_outcome": "Primary",
        "outcome": "Disease activity (chronic CHIKV arthritis)",
        "description": "Improvement in DAS-28 response (composite of 28-joint tender/swollen count, patient global assessment, CRP) at up to 6 months",
        "domain_dodd": "15 Musculoskeletal and connective tissue",
        "omi": "DAS-28 (Disease Activity Score 28)",
        "omi_type": "Composite",
        "metric": "change from baseline",
        "confidence": "High",
        "needs_review": "N",
    },
    {
        "record_id": "R0080", "type_of_outcome": "Secondary",
        "outcome": "Synovial inflammation",
        "description": "Synovial macrophage and T-cell infiltration measured by immunohistochemistry of synovial biopsy tissue",
        "domain_dodd": "15 Musculoskeletal and connective tissue",
        "omi": "Synovial biopsy / immunohistochemistry",
        "omi_type": "OOM",
        "metric": "mean / geometric-mean value",
        "confidence": "High",
        "needs_review": "N",
    },
    {
        "record_id": "R0080", "type_of_outcome": "Secondary",
        "outcome": "Inflammatory cytokine levels",
        "description": "TNF, IL-6, and MCP-1 concentrations in synovial tissue",
        "domain_dodd": "11 Immune system",
        "omi": "Cytokine assay (ELISA or equivalent) in synovial tissue",
        "omi_type": "OOM",
        "metric": "mean / geometric-mean value",
        "confidence": "High",
        "needs_review": "N",
    },
    # ── R0096 ─────────────────────────────────────────────────────────────────
    {
        "record_id": "R0096", "type_of_outcome": "Primary",
        "outcome": "Chikungunya symptom severity",
        "description": "Change in multidimensional symptom burden (physical function, pain, fatigue) assessed with MDHAQ from baseline to 4 weeks",
        "domain_dodd": "25 Physical functioning",
        "omi": "MDHAQ (Multi-Dimensional Health Assessment Questionnaire)",
        "omi_type": "PROM",
        "metric": "change from baseline",
        "confidence": "High",
        "needs_review": "N",
    },
    {
        "record_id": "R0096", "type_of_outcome": "Secondary",
        "outcome": "Pain intensity",
        "description": "Change in pain intensity measured on a visual analogue scale assessed weekly to 4 weeks",
        "domain_dodd": "15 Musculoskeletal and connective tissue",
        "omi": "VAS — Visual Analogue Scale (pain)",
        "omi_type": "PROM",
        "metric": "change from baseline",
        "confidence": "High",
        "needs_review": "N",
    },
    # ── R0147 ─────────────────────────────────────────────────────────────────
    {
        "record_id": "R0147", "type_of_outcome": "Primary",
        "outcome": "Inflammation and pain (pCHIK-CIR)",
        "description": "Reduction of inflammation and pain in post-chikungunya chronic inflammatory rheumatism; no measurement instrument specified in registry",
        "domain_dodd": "15 Musculoskeletal and connective tissue",
        "omi": "Not specified",
        "omi_type": "Not specified",
        "metric": "not stated",
        "confidence": "Low",
        "needs_review": "Y",
    },
    {
        "record_id": "R0147", "type_of_outcome": "Secondary",
        "outcome": "Quality of life",
        "description": "Health-related quality of life in pCHIK-CIR patients; instrument not specified",
        "domain_dodd": "30 Global quality of life",
        "omi": "Not specified",
        "omi_type": "Not specified",
        "metric": "not stated",
        "confidence": "Low",
        "needs_review": "Y",
    },
    # ── R0156 ─────────────────────────────────────────────────────────────────
    {
        "record_id": "R0156", "type_of_outcome": "Primary",
        "outcome": "Pain (pCHIK-CIR)",
        "description": "Pain management in post-chikungunya chronic inflammatory rheumatism; instrument not specified",
        "domain_dodd": "15 Musculoskeletal and connective tissue",
        "omi": "Not specified",
        "omi_type": "Not specified",
        "metric": "not stated",
        "confidence": "Low",
        "needs_review": "Y",
    },
    {
        "record_id": "R0156", "type_of_outcome": "Secondary",
        "outcome": "Signs and symptoms (pCHIK-CIR)",
        "description": "Relief in clinical signs and symptoms of pCHIK-CIR; instrument not specified",
        "domain_dodd": "15 Musculoskeletal and connective tissue",
        "omi": "Not specified",
        "omi_type": "Not specified",
        "metric": "not stated",
        "confidence": "Low",
        "needs_review": "Y",
    },
    # ── R0163 ─────────────────────────────────────────────────────────────────
    {
        "record_id": "R0163", "type_of_outcome": "Primary",
        "outcome": "Inflammation and pain (pCHIK-CIR)",
        "description": "Reduction of inflammation and pain in post-chikungunya chronic inflammatory rheumatism; instrument not specified",
        "domain_dodd": "15 Musculoskeletal and connective tissue",
        "omi": "Not specified",
        "omi_type": "Not specified",
        "metric": "not stated",
        "confidence": "Low",
        "needs_review": "Y",
    },
    {
        "record_id": "R0163", "type_of_outcome": "Secondary",
        "outcome": "Quality of life",
        "description": "Health-related quality of life in chikungunya patients; instrument not specified",
        "domain_dodd": "30 Global quality of life",
        "omi": "Not specified",
        "omi_type": "Not specified",
        "metric": "not stated",
        "confidence": "Low",
        "needs_review": "Y",
    },
    # ── R0168 ─────────────────────────────────────────────────────────────────
    {
        "record_id": "R0168", "type_of_outcome": "Primary",
        "outcome": "Efficacy (not further specified)",
        "description": "General efficacy — single-word registry entry with no instrument or endpoint defined",
        "domain_dodd": "9 General",
        "omi": "Not specified",
        "omi_type": "Not specified",
        "metric": "not stated",
        "confidence": "Low",
        "needs_review": "Y",
    },
    {
        "record_id": "R0168", "type_of_outcome": "Secondary",
        "outcome": "Safety",
        "description": "General safety — single-word registry entry; likely adverse events but no detail provided",
        "domain_dodd": "38 Adverse events/effects",
        "omi": "Not specified",
        "omi_type": "Not specified",
        "metric": "not stated",
        "confidence": "Medium",
        "needs_review": "Y",
    },
    # ── R0169 ─────────────────────────────────────────────────────────────────
    {
        "record_id": "R0169", "type_of_outcome": "Primary",
        "outcome": "Efficacy (not further specified)",
        "description": "General efficacy — single-word registry entry with no instrument or endpoint defined",
        "domain_dodd": "9 General",
        "omi": "Not specified",
        "omi_type": "Not specified",
        "metric": "not stated",
        "confidence": "Low",
        "needs_review": "Y",
    },
    {
        "record_id": "R0169", "type_of_outcome": "Secondary",
        "outcome": "Safety",
        "description": "General safety — single-word registry entry; likely adverse events but no detail provided",
        "domain_dodd": "38 Adverse events/effects",
        "omi": "Not specified",
        "omi_type": "Not specified",
        "metric": "not stated",
        "confidence": "Medium",
        "needs_review": "Y",
    },
]

# Build lookup: (record_id, type_of_outcome) → list of decomps (in order)
_DMAP: dict = {}
for d in DECOMP:
    key = (d["record_id"], d["type_of_outcome"])
    _DMAP.setdefault(key, []).append(d)
_DMAP_CURSOR: dict = {}


def lookup_decomp(record_id, type_of_outcome):
    key = (record_id, type_of_outcome)
    lst = _DMAP.get(key, [])
    idx = _DMAP_CURSOR.get(key, 0)
    if idx < len(lst):
        _DMAP_CURSOR[key] = idx + 1
        return lst[idx]
    return {}


# ── colour fills ──────────────────────────────────────────────────────────────

FILL_GREY  = PatternFill("solid", fgColor="D9D9D9")
FILL_BLUE  = PatternFill("solid", fgColor="BDD7EE")
FILL_GREEN = PatternFill("solid", fgColor="EBF5EB")
FILL_RED   = PatternFill("solid", fgColor="FFD0D0")
FILL_AMBER = PatternFill("solid", fgColor="FFE699")
FILL_TITLE = PatternFill("solid", fgColor="4472C4")

FONT_WHITE = Font(bold=True, color="FFFFFF")
FONT_BOLD  = Font(bold=True)

def thin_border():
    s = Side(style="thin")
    return Border(left=s, right=s, top=s, bottom=s)


# ── column definitions ─────────────────────────────────────────────────────────

GREY_COLS  = ["record_id", "title", "source", "ctg_id", "ctg_url",
              "ictrp_id", "ictrp_url", "phase", "sponsor",
              "type_of_outcome", "verbatim_outcome", "time_frame"]
BLUE_COLS  = ["outcome", "description", "domain_dodd",
              "omi", "omi_type", "metric", "confidence", "needs_review"]
GREEN_COLS = ["human_decision", "reviewer_notes"]

ALL_COLS   = GREY_COLS + BLUE_COLS + GREEN_COLS

COL_WIDTH  = {
    "record_id": 10, "title": 50, "source": 35, "ctg_id": 14,
    "ctg_url": 35, "ictrp_id": 24, "ictrp_url": 40,
    "phase": 10, "sponsor": 30,
    "type_of_outcome": 12, "verbatim_outcome": 60, "time_frame": 18,
    "outcome": 30, "description": 50, "domain_dodd": 35,
    "omi": 35, "omi_type": 14, "metric": 22,
    "confidence": 12, "needs_review": 14,
    "human_decision": 18, "reviewer_notes": 40,
}

HEADERS = {
    "record_id": "Record ID", "title": "Study Title", "source": "Source",
    "ctg_id": "CTG ID", "ctg_url": "CTG URL",
    "ictrp_id": "ICTRP ID", "ictrp_url": "ICTRP URL",
    "phase": "Phase", "sponsor": "Sponsor",
    "type_of_outcome": "Outcome Type", "verbatim_outcome": "★ Verbatim Outcome",
    "time_frame": "Time Frame",
    "outcome": "Outcome", "description": "Description",
    "domain_dodd": "Domain (Dodd)", "omi": "OMI", "omi_type": "OMI Type",
    "metric": "Metric", "confidence": "Confidence", "needs_review": "Needs Review",
    "human_decision": "Human Decision", "reviewer_notes": "Reviewer Notes",
}


# ── helpers ───────────────────────────────────────────────────────────────────

def read_meta(path):
    meta = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            meta[r["record_id"]] = r
    return meta

def read_raw(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))

def apply_decomp(raw_rows, meta):
    out = []
    for r in raw_rows:
        rid   = r["record_id"]
        m     = meta.get(rid, {})
        d     = lookup_decomp(rid, r["type_of_outcome"])
        needs = d.get("needs_review", "N")
        out.append({
            "record_id":       rid,
            "title":           m.get("title", ""),
            "source":          r["source"],
            "ctg_id":          m.get("ctg_id", ""),
            "ctg_url":         m.get("ctg_url", ""),
            "ictrp_id":        m.get("ictrp_id", ""),
            "ictrp_url":       m.get("ictrp_url", ""),
            "phase":           m.get("phase", ""),
            "sponsor":         m.get("sponsor", ""),
            "type_of_outcome": r["type_of_outcome"],
            "verbatim_outcome":r["verbatim_outcome"],
            "time_frame":      r["time_frame"],
            "outcome":         d.get("outcome", ""),
            "description":     d.get("description", ""),
            "domain_dodd":     d.get("domain_dodd", ""),
            "omi":             d.get("omi", ""),
            "omi_type":        d.get("omi_type", ""),
            "metric":          d.get("metric", ""),
            "confidence":      d.get("confidence", ""),
            "needs_review":    needs,
            "human_decision":  "",
            "reviewer_notes":  "",
        })
    return out


def add_no_outcomes_rows(rows, meta, raw_rids):
    """Add a placeholder row for studies with no registered outcomes."""
    for rid, m in meta.items():
        if rid not in raw_rids:
            rows.append({
                "record_id":       rid,
                "title":           m.get("title", ""),
                "source":          m.get("source", ""),
                "ctg_id":          m.get("ctg_id", ""),
                "ctg_url":         m.get("ctg_url", ""),
                "ictrp_id":        m.get("ictrp_id", ""),
                "ictrp_url":       m.get("ictrp_url", ""),
                "phase":           m.get("phase", ""),
                "sponsor":         m.get("sponsor", ""),
                "type_of_outcome": "—",
                "verbatim_outcome": "[No outcomes registered in registry]",
                "time_frame":      "",
                "outcome":         "",
                "description":     "",
                "domain_dodd":     "",
                "omi":             "",
                "omi_type":        "",
                "metric":          "",
                "confidence":      "",
                "needs_review":    "Y",
                "human_decision":  "",
                "reviewer_notes":  "",
            })
    return rows


# ── Excel writer ──────────────────────────────────────────────────────────────

def write_extraction_sheet(wb, rows):
    ws = wb.create_sheet("2. Extraction")

    # ── header row ──────────────────────────────────────────────────────────
    for ci, col in enumerate(ALL_COLS, 1):
        cell = ws.cell(row=1, column=ci, value=HEADERS.get(col, col))
        cell.font      = FONT_WHITE
        cell.fill      = FILL_TITLE
        cell.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
        ws.column_dimensions[get_column_letter(ci)].width = COL_WIDTH.get(col, 20)
    ws.row_dimensions[1].height = 36

    # ── data rows ──────────────────────────────────────────────────────────
    for ri, row in enumerate(rows, 2):
        is_flagged = row.get("needs_review") == "Y"
        for ci, col in enumerate(ALL_COLS, 1):
            val  = row.get(col, "")
            cell = ws.cell(row=ri, column=ci, value=val)
            cell.alignment = Alignment(wrap_text=True, vertical="top")

            if col in GREEN_COLS:
                cell.fill = FILL_GREEN
            elif col in BLUE_COLS:
                cell.fill = FILL_RED if (is_flagged and col == "needs_review") else FILL_BLUE
            else:
                cell.fill = FILL_AMBER if (row.get("verbatim_outcome","").startswith("[No outcomes")) else FILL_GREY

        ws.row_dimensions[ri].height = 45

    # freeze header + left study cols
    ws.freeze_panes = "K2"  # freeze up to verbatim_outcome
    ws.auto_filter.ref = f"A1:{get_column_letter(len(ALL_COLS))}1"


def write_legend_sheet(wb):
    ws = wb.create_sheet("Legend & Dodd")

    def hdr(row, text, fill=FILL_TITLE):
        c = ws.cell(row=row, column=1, value=text)
        c.font = FONT_WHITE
        c.fill = fill
        c.alignment = Alignment(horizontal="left")
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=4)

    def row2(r, a, b="", c="", d=""):
        ws.cell(row=r, column=1, value=a).alignment = Alignment(wrap_text=True)
        ws.cell(row=r, column=2, value=b).alignment = Alignment(wrap_text=True)
        ws.cell(row=r, column=3, value=c).alignment = Alignment(wrap_text=True)
        ws.cell(row=r, column=4, value=d).alignment = Alignment(wrap_text=True)

    r = 1
    hdr(r, "Column colour guide")
    r += 1; row2(r, "Grey",  "D9D9D9", "Deterministic — populated by scripts (no AI)")
    r += 1; row2(r, "Blue",  "BDD7EE", "AI-filled — Outcome, OMI, Metric, Domain")
    r += 1; row2(r, "Green", "EBF5EB", "Human review columns (Human Decision, Reviewer Notes)")
    r += 1; row2(r, "Red",   "FFD0D0", "Needs review = Y — AI flag of low confidence or ambiguity")
    r += 1; row2(r, "Amber", "FFE699", "No outcomes registered in registry")

    r += 2; hdr(r, "OMI type definitions")
    for typ, defn in [
        ("PROM",         "Patient-reported outcome measure (symptom diaries, QoL questionnaires)"),
        ("ClinROM",      "Clinician-reported (clinical assessment, physician-rated scales)"),
        ("ObsROM",       "Observer-reported (carer/parent report, not the patient)"),
        ("PerfO",        "Performance outcome (standardised task the patient performs)"),
        ("OOM",          "Objective outcome measure (lab assay, imaging, viral culture, thermometry)"),
        ("Composite",    "Defined combination of multiple measure types (e.g., DAS-28)"),
        ("Not specified","Registry gives no instrument detail"),
    ]:
        r += 1; row2(r, typ, defn)

    r += 2; hdr(r, "Metric (analytic form)")
    for m in ["proportion / incidence", "time-to-event", "change from baseline",
              "mean / geometric-mean value", "absolute value or level",
              "AUC", "categorical", "binary presence/absence",
              "score / score change", "not stated"]:
        r += 1; row2(r, m)

    r += 2; hdr(r, "Dodd et al. (2018) — 38-domain taxonomy")
    r += 1; row2(r, "Area", "Domain #", "Domain name")
    domains = [
        ("Mortality/survival",         1,  "Mortality/survival"),
        ("Physiological/clinical",     2,  "Blood and lymphatic"),
        ("Physiological/clinical",     3,  "Cardiac"),
        ("Physiological/clinical",     4,  "Congenital, familial and genetic"),
        ("Physiological/clinical",     5,  "Endocrine"),
        ("Physiological/clinical",     6,  "Ear and labyrinth"),
        ("Physiological/clinical",     7,  "Eye"),
        ("Physiological/clinical",     8,  "Gastrointestinal"),
        ("Physiological/clinical",     9,  "General"),
        ("Physiological/clinical",     10, "Hepatobiliary"),
        ("Physiological/clinical",     11, "Immune system"),
        ("Physiological/clinical",     12, "Infection and infestation"),
        ("Physiological/clinical",     13, "Injury and poisoning"),
        ("Physiological/clinical",     14, "Metabolism and nutrition"),
        ("Physiological/clinical",     15, "Musculoskeletal and connective tissue"),
        ("Physiological/clinical",     16, "Neoplasms"),
        ("Physiological/clinical",     17, "Nervous system"),
        ("Physiological/clinical",     18, "Pregnancy, puerperium and perinatal"),
        ("Physiological/clinical",     19, "Renal and urinary"),
        ("Physiological/clinical",     20, "Reproductive system and breast"),
        ("Physiological/clinical",     21, "Psychiatric"),
        ("Physiological/clinical",     22, "Respiratory, thoracic and mediastinal"),
        ("Physiological/clinical",     23, "Skin and subcutaneous tissue"),
        ("Physiological/clinical",     24, "Vascular"),
        ("Life impact",                25, "Physical functioning"),
        ("Life impact",                26, "Social functioning"),
        ("Life impact",                27, "Role functioning"),
        ("Life impact",                28, "Emotional functioning/wellbeing"),
        ("Life impact",                29, "Cognitive functioning"),
        ("Life impact",                30, "Global quality of life"),
        ("Life impact",                31, "Perceived health status"),
        ("Resource use",               32, "Delivery of care"),
        ("Resource use",               33, "Personal circumstances"),
        ("Resource use",               34, "Economic"),
        ("Resource use",               35, "Hospital"),
        ("Resource use",               36, "Need for further intervention"),
        ("Resource use",               37, "Societal/carer burden"),
        ("Adverse events",             38, "Adverse events/effects"),
    ]
    for area, num, name in domains:
        r += 1; row2(r, area, str(num), name)

    for ci, w in [(1,20),(2,8),(3,40),(4,60)]:
        ws.column_dimensions[get_column_letter(ci)].width = w


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw",  required=True, help="outcomes_raw.csv from parse_outcomes.py")
    ap.add_argument("--meta", required=True, help="included_studies.csv from extract_included.py")
    ap.add_argument("--out",  default="extraction_results.xlsx")
    a  = ap.parse_args()

    meta     = read_meta(a.meta)
    raw_rows = read_raw(a.raw)
    rows     = apply_decomp(raw_rows, meta)

    raw_rids = {r["record_id"] for r in raw_rows}
    rows     = add_no_outcomes_rows(rows, meta, raw_rids)

    # sort: by record_id, then Primary before Secondary/Other
    order = {"Primary": 0, "Secondary": 1, "Other": 2}
    rows.sort(key=lambda r: (r["record_id"], order.get(r["type_of_outcome"], 9)))

    wb = Workbook()
    wb.remove(wb.active)       # remove default blank sheet
    write_extraction_sheet(wb, rows)
    write_legend_sheet(wb)
    wb.save(a.out)

    n_flag = sum(1 for r in rows if r.get("needs_review") == "Y")
    print(f"[ok] wrote {a.out}  ({len(rows)} outcome rows, {n_flag} flagged for review)",
          file=sys.stderr)
    print(f"     Studies in extraction: {sorted({r['record_id'] for r in rows})}", file=sys.stderr)


if __name__ == "__main__":
    main()
