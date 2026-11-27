#!/usr/bin/env python3
"""AI screening + Excel output for Part 1 (COS Outcome Extraction).

Reads the dedupe.py output (screening.csv), applies AI screening rules,
and writes a two-sheet Excel workbook:
  • 1. Screening  — one row per record, all source fields + screening decision
                    The column that triggered the exclusion is highlighted in amber;
                    the matched evidence snippet is in the 'evidence' column.
  • Legend & PRISMA — exclusion criteria definitions, PRISMA flow counts, column guide.

Usage:
  python scripts/screen_to_excel.py --screening screening.csv --out screening_results.xlsx \\
      [--ctg-n 94] [--ictrp-n 181] [--dup-n 90]
"""
import argparse, csv, re, sys
from collections import Counter
from openpyxl import Workbook
from openpyxl.styles import (Font, PatternFill, Alignment, Border, Side)
from openpyxl.utils import get_column_letter

# ── Screening patterns ─────────────────────────────────────────────────────────

VACCINE_KW = re.compile(
    r"\bvaccin|immunogen|seroconvers|immuniz|vla1553|mxchik|pepgnp|hydrovax|adjuvant|antigen",
    re.I)
THERAPEUTIC_KW = re.compile(
    r"\bmonoclonal|antibod|antiviral|analges|nsaid|ibuprofen|naproxen|acetaminophen|"
    r"chloroquine|methotrexate|hydroxychloroquine|favipiravir|ribavirin|corticosteroid|"
    r"prednisone|homoeopath|homeopat|ayurved|herbal|plant|traditional|physiother|"
    r"rehabilit|exercise|acupunctur|curmeric|chloroq|ivermectin|mequitazin|reduning|"
    r"auriculother|tDCS|vagus nerve|yoga",
    re.I)
VECTOR_KW = re.compile(
    r"\bmosquito\b|wolbachia|indoor residual spray|insecticide coat|vector breed|"
    r"\binsect vector\b|aedes.born|mosquito.born|\bblood (sample|collect)\b|serological|"
    r"venous blood|xpert.*fever.*test|diagnostic.*test|incompatible mating|IIT.SIT|"
    r"sterile insect|trap[^e]",
    re.I)
DETECTION_KW = re.compile(
    r"\bdetection\b|\bdetect\b.*(virus|chikv|rna|antigen)|"
    r"(virus|chikv).*(detection|in semen|in urine|in blood)|"
    r"\bdiagnos|\bseroprevalence|\bsurveillance\b|\bepidemiolog|\bnatural history\b",
    re.I)
PROPHYLAXIS_KW = re.compile(
    r"prevention of (dengue|chikungunya|mosquito.borne|arbovirus|aedes.borne|infection)|"
    r"prevent.{0,40}\b(dengue|chikungunya|arbovirus)\b.{0,40}infect|\bprophyla[xis]+|"
    r"(dengue|chikungunya).{0,30}(prevention|prevent)\b|eupatorium|pre-exposure|"
    r"prevent.{0,30}neonatal|neonatal.{0,30}prevent|preventing.{0,30}occurrence|"
    r"against chikungunya.{0,40}neonatal|neonatal.{0,40}chikungunya",
    re.I)

# Columns checked per criterion for evidence extraction and cell highlighting
CRITERION_COLS = {
    "E1":  ["cond", "title"],
    "E2":  ["stype", "title", "intv"],
    "E3":  ["title", "intv", "primary_outcomes"],
    "E4":  ["phase"],
    "":    ["phase"],   # Include
}


def is_prophylaxis(row):
    # Search each field separately so the evidence snippet stays concise and labelled
    for field in ("title", "intv", "primary_outcomes"):
        text = row.get(field, "")
        if not text:
            continue
        if re.search(r"prevention of post.chikungunya|post.chikungunya.*prevention", text, re.I):
            continue  # secondary prevention of complications = treatment
        m = PROPHYLAXIS_KW.search(text)
        if m:
            snippet = m.group(0)[:80]
            return True, f"{field}: '{snippet}'"
    return False, ""


def phase_decision(phase):
    p = phase.strip()
    ph_up = p.upper().replace(" ", "").replace("/", "")
    if re.search(r"PHASE3$|PHASE4$|PHASE34|PHASE43", ph_up): return "include", "High"
    if re.search(r"phase\s*3", p, re.I) and not re.search(r"phase\s*[12]\b", p, re.I): return "include", "High"
    if re.search(r"phase\s*4", p, re.I) and not re.search(r"phase\s*[12]\b", p, re.I): return "include", "High"
    if re.search(r"phase\s*2", p, re.I) and re.search(r"phase\s*3", p, re.I): return "unsure", "Low"
    return "exclude", "High"


def vaccine_detect(row):
    text = " ".join([row.get("title",""), row.get("intv","")]).lower()
    if VACCINE_KW.search(text):
        m = VACCINE_KW.search(text)
        return True, "High", m.group(0) if m else ""
    if "BIOLOGICAL:" in row.get("intv","") and not THERAPEUTIC_KW.search(text):
        return True, "Medium", "BIOLOGICAL intervention without therapeutic keyword"
    return False, "High", ""


def extract_evidence(row, decision, criterion):
    """Return the specific snippet that justified the decision."""
    title = row.get("title","")
    intv  = row.get("intv","")
    cond  = row.get("cond","")
    phase = row.get("phase","")
    po    = row.get("primary_outcomes","")

    if criterion == "E1":
        return f"cond: '{cond[:80]}' | title: '{title[:80]}'"
    if criterion == "E2":
        stype = row.get("stype","")
        if "INTERVENTIONAL" not in stype.upper():
            return f"stype='{stype}'"
        m = VECTOR_KW.search(f"{title} {intv}")
        if m: return f"vector/diag keyword: '{m.group(0)}' in title/intv"
        m = DETECTION_KW.search(title)
        if m: return f"detection keyword: '{m.group(0)}' in title"
        return f"stype='{stype}'"
    if criterion == "E3":
        text = f"{title} {intv}"
        m = VACCINE_KW.search(text)
        if m: return f"vaccine keyword: '{m.group(0)}'"
        ok, snippet = is_prophylaxis(row)
        if snippet: return f"prophylaxis keyword: '{snippet}'"
        return "BIOLOGICAL intervention, no therapeutic keyword match"
    if criterion == "E4":
        return f"phase='{phase}'"
    if decision == "Include":
        return f"phase='{phase}'"
    if decision == "Unsure":
        return f"phase='{phase}' (Phase 2/3 combined)"
    return ""


def screen(unique_rows):
    results = []
    for r in unique_rows:
        cond_title = " ".join([r.get("cond",""), r.get("title","")]).lower()
        title_intv = " ".join([r.get("title",""), r.get("intv","")]).lower()

        def exc(criterion, reason, confidence="High", needs_review="N", evidence=""):
            results.append({**r, "decision": "Exclude", "criterion": criterion,
                "reason": reason, "confidence": confidence,
                "needs_review": needs_review,
                "evidence": evidence or extract_evidence(r, "Exclude", criterion)})

        # E1 – not chikungunya
        if not re.search(r"chikungunya|chikv", cond_title, re.I):
            exc("E1", "No chikungunya in condition/title"); continue

        # E2 – non-interventional
        if "INTERVENTIONAL" not in r.get("stype","").upper():
            exc("E2", f"Non-interventional ({r.get('stype','')})"); continue

        # E2b – vector / diagnostic (from intv/title keywords)
        if VECTOR_KW.search(title_intv) and not THERAPEUTIC_KW.search(title_intv):
            exc("E2", "Vector-control / diagnostic / epidemiological"); continue

        # E2c – detection / surveillance (from title)
        if DETECTION_KW.search(r.get("title","")) and not THERAPEUTIC_KW.search(title_intv):
            exc("E2", "Detection / surveillance / diagnostic study (title)"); continue

        # E4-early – Phase 1 or 2 (clear, before BIOLOGICAL check)
        phase = r.get("phase","")
        if re.search(r"phase\s*[12]\b", phase, re.I) and not re.search(r"phase\s*3|phase\s*4", phase, re.I):
            exc("E4", f"Phase 1 or 2 ({phase})"); continue

        # E3a – vaccine (High-confidence keyword match)
        is_vax, vax_conf, vax_snippet = vaccine_detect(r)
        if is_vax and vax_conf == "High":
            exc("E3", "Vaccine / immunogenicity trial", confidence="High",
                needs_review="N", evidence=vax_snippet); continue

        # E3b – prophylaxis (checked before Medium-confidence BIOLOGICAL fallback)
        is_prop, prop_snippet = is_prophylaxis(r)
        if is_prop:
            exc("E3", "Prophylaxis / primary prevention (not treatment)",
                evidence=prop_snippet); continue

        # E3c – BIOLOGICAL intervention with no therapeutic keyword (Medium confidence)
        if is_vax and vax_conf == "Medium":
            exc("E3", "Vaccine / immunogenicity trial", confidence="Medium",
                needs_review="Y", evidence=vax_snippet); continue

        # E4 – remaining phase cases
        phase_dec, phase_conf = phase_decision(phase)
        ev = extract_evidence(r, phase_dec, "E4" if phase_dec != "include" else "")
        if phase_dec == "include":
            results.append({**r, "decision": "Include", "criterion": "",
                "reason": "Chikungunya interventional therapeutic Phase 3/4",
                "confidence": phase_conf, "needs_review": "N",
                "evidence": ev})
        elif phase_dec == "unsure":
            results.append({**r, "decision": "Unsure", "criterion": "E4",
                "reason": f"Phase 2/3 combined ({phase}); confirm if Phase 3 component qualifies",
                "confidence": "Low", "needs_review": "Y", "evidence": ev})
        else:
            exc("E4", f"Not Phase 3 or 4 ({phase or 'not specified'})",
                confidence=phase_conf, evidence=ev)

    return results


# ── Excel helpers ──────────────────────────────────────────────────────────────

def _fill(hex_color):
    return PatternFill("solid", fgColor=hex_color)

def _font(bold=False, color="000000", size=11):
    return Font(bold=bold, color=color, size=size)

def _thin():
    s = Side(style="thin", color="CCCCCC")
    return Border(left=s, right=s, top=s, bottom=s)

DEC_FILL  = {"Include": "C6EFCE", "Exclude": "FFDDC1", "Unsure": "FFEB9C", "": "FFFFFF"}
CRIT_FILL = {"E1": "FFC7CE", "E2": "FFD966", "E3": "F4B183", "E4": "BDD7EE", "": "FFFFFF"}

# Which source columns to highlight (amber) for each criterion
HIGHLIGHT_COLS = {
    "E1": ["cond", "title"],
    "E2": ["stype", "title", "intv"],
    "E3": ["title", "intv", "primary_outcomes"],
    "E4": ["phase"],
    "":   ["phase"],
}


HUMAN_COLS = ["human_decision", "justification"]  # reviewer-editable columns

def write_screening_sheet(ws, screened, dups, src_cols):
    ai_cols     = ["decision", "criterion", "evidence", "reason", "confidence", "needs_review"]
    all_cols    = ai_cols + HUMAN_COLS + src_cols

    col_idx = {col: i + 1 for i, col in enumerate(all_cols)}

    # Header row — two visual zones: AI (dark blue) and Human (dark green)
    for col, ci in col_idx.items():
        is_human = col in HUMAN_COLS
        cell = ws.cell(row=1, column=ci, value=col)
        cell.font      = _font(bold=True, color="FFFFFF")
        cell.fill      = _fill("375623" if is_human else "2F5496")
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border    = _thin()
    ws.freeze_panes = "A2"
    ws.row_dimensions[1].height = 32

    def write_row(ws, row_idx, r, is_dup=False):
        dec     = r.get("decision", "")
        crit    = r.get("criterion", "")
        hi_cols = set(HIGHLIGHT_COLS.get(crit, []))

        for col, ci in col_idx.items():
            val  = r.get(col, "")
            cell = ws.cell(row=row_idx, column=ci, value=val)
            cell.border    = _thin()
            cell.alignment = Alignment(vertical="top", wrap_text=True)

            if is_dup:
                cell.fill = _fill("F2F2F2")
                continue

            # Human reviewer columns — light green, always editable-looking
            if col in HUMAN_COLS:
                cell.fill = _fill("EBF5EB")
                if col == "human_decision" and val:
                    cell.font = _font(bold=True, color="375623")
                continue

            # AI screening columns
            if col == "decision":
                cell.fill = _fill(DEC_FILL.get(dec, "FFFFFF"))
                cell.font = _font(bold=(dec == "Include"))
            elif col == "criterion":
                cell.fill = _fill(CRIT_FILL.get(crit, "FFFFFF"))
                cell.font = _font(bold=True)
            elif col == "needs_review" and val == "Y":
                cell.fill = _fill("FF0000")
                cell.font = _font(bold=True, color="FFFFFF")
            elif col == "evidence":
                cell.font = _font(bold=False, color="7030A0")
            elif col in hi_cols and dec in ("Exclude", "Unsure"):
                cell.fill = _fill("FFD700")
                cell.font = _font(bold=True)

    row_idx = 2
    for r in screened:
        write_row(ws, row_idx, r)
        row_idx += 1
    for r in dups:
        write_row(ws, row_idx, r, is_dup=True)
        row_idx += 1

    widths = {
        "decision": 11, "criterion": 10, "evidence": 40, "reason": 42,
        "confidence": 12, "needs_review": 12,
        "title": 50, "summary": 38, "primary_outcomes": 50, "secondary_outcomes": 45,
        "intv": 40, "cond": 30, "phase": 14, "stype": 18, "sponsor": 28,
        "ctg_url": 44, "ictrp_url": 44,
        "inclusion_criteria": 38, "exclusion_criteria": 38,
        "locations": 22, "enrollment": 12,
    }
    for col, ci in col_idx.items():
        ws.column_dimensions[get_column_letter(ci)].width = widths.get(col, 16)


def write_legend_sheet(ws, dec, crit, counts):

    def heading(ws, row, text, cols=2, bg="2F5496"):
        cell = ws.cell(row=row, column=1, value=text)
        cell.font      = _font(bold=True, color="FFFFFF", size=12)
        cell.fill      = _fill(bg)
        cell.alignment = Alignment(horizontal="left", vertical="center")
        cell.border    = _thin()
        if cols > 1:
            ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=cols)
        ws.row_dimensions[row].height = 22

    def kv(ws, row, key, value, fill_key="DDEEFF"):
        c1 = ws.cell(row=row, column=1, value=key)
        c1.font = _font(bold=True); c1.fill = _fill(fill_key)
        c1.alignment = Alignment(vertical="top", wrap_text=True); c1.border = _thin()
        c2 = ws.cell(row=row, column=2, value=value)
        c2.alignment = Alignment(vertical="top", wrap_text=True)
        c2.fill = _fill("FFFFFF"); c2.border = _thin()
        ws.row_dimensions[row].height = max(18, min(90, len(str(value)) // 3))

    row = 1

    # ── Exclusion Criteria ────────────────────────────────────────────────────
    heading(ws, row, "EXCLUSION CRITERIA"); row += 1
    criteria = [
        ("E1 — Not chikungunya",
         "The study condition or title does not mention chikungunya virus or CHIKV. "
         "Applies to records retrieved incidentally through broad search terms.",
         "FFC7CE"),
        ("E2 — Non-interventional / non-therapeutic",
         "Study type is observational, surveillance, epidemiological, diagnostic, or vector-control. "
         "Includes sample-collection studies, serology surveys, entomological interventions, and "
         "detection/diagnostic studies identified from the title.",
         "FFD966"),
        ("E3 — Vaccine or prophylaxis",
         "Intervention is a chikungunya vaccine or immunogenicity study, OR the primary aim is "
         "prevention of chikungunya infection in uninfected individuals (primary prophylaxis), "
         "including passive immunisation for neonatal infection prevention. "
         "Note: secondary prevention of post-CHIKV complications is classified as treatment and "
         "is NOT excluded under E3.",
         "F4B183"),
        ("E4 — Phase not 3 or 4",
         "Study phase is Phase 1, Phase 2, or not specified. Only Phase 3 and Phase 4 therapeutic "
         "trials are eligible. Phase not specified is excluded because the phase cannot be confirmed "
         "without manual registry lookup.",
         "BDD7EE"),
    ]
    for label, desc, fill in criteria:
        kv(ws, row, label, desc, fill_key=fill); row += 1

    row += 1

    # ── Evidence & Highlighting Guide ────────────────────────────────────────
    heading(ws, row, "HOW TO READ THE SCREENING SHEET", bg="4472C4"); row += 1
    highlights = [
        ("decision column (blue header)",
         "AI screening decision — Green = Include · Orange = Exclude · Amber = Unsure. "
         "Read-only reference; do not edit."),
        ("criterion column",
         "Colour-coded by exclusion criterion: E1 red · E2 yellow · E3 orange · E4 blue"),
        ("evidence column",
         "Purple text — the exact text snippet or field value that triggered the AI decision. "
         "Check this first when reviewing an exclusion."),
        ("amber source cells",
         "The source column(s) that caused the exclusion are highlighted in amber/gold. "
         "E.g. for E4 the 'phase' cell is amber; for E3 the 'title' or 'intv' cell is amber."),
        ("needs_review = Y",
         "Red cell — Medium-confidence AI decision, requires human check before finalising."),
        ("human_decision (green header) ← EDIT HERE",
         "Leave blank to accept the AI decision. "
         "Fill in 'Include' or 'Exclude' ONLY where you disagree with the AI. "
         "extract_included.py will use your value when present, AI value otherwise."),
        ("justification (green header) ← EDIT HERE",
         "Free-text reason for your override. Required when human_decision is filled. "
         "Examples: 'Phase 3 confirmed on registry — blank field in ICTRP export' / "
         "'Prevention trial, AI missed it'"),
        ("grey rows",
         "Duplicate records removed during de-duplication (dup_of shows the canonical record)."),
    ]
    for key, val in highlights:
        kv(ws, row, key, val, fill_key="EAF0FB"); row += 1

    row += 1

    # ── PRISMA Flow ───────────────────────────────────────────────────────────
    heading(ws, row, "PRISMA FLOW — Part 1 Screening"); row += 1

    n_ctg    = counts.get("ctg", 0)
    n_ictrp  = counts.get("ictrp", 0)
    n_total  = n_ctg + n_ictrp
    n_dup    = counts.get("dup", 0)
    n_screen = n_total - n_dup
    n_inc    = dec.get("Include", 0)
    n_exc    = dec.get("Exclude", 0)
    n_uns    = dec.get("Unsure", 0)
    n_nr     = counts.get("needs_review", 0)

    prisma = [
        ("Identified — ClinicalTrials.gov",  n_ctg,              "C6EFCE"),
        ("Identified — WHO ICTRP",           n_ictrp,            "C6EFCE"),
        ("Identified — total",               n_total,            "C6EFCE"),
        ("Duplicates removed",               n_dup,              "FFDDC1"),
        ("Screened (unique records)",        n_screen,           "FFFFFF"),
        ("Included",                         n_inc,              "C6EFCE"),
        ("Excluded — total",                 n_exc,              "FFDDC1"),
        ("  E1 — not chikungunya",           crit.get("E1", 0),  "FFC7CE"),
        ("  E2 — non-interventional",        crit.get("E2", 0),  "FFD966"),
        ("  E3 — vaccine / prophylaxis",     crit.get("E3", 0),  "F4B183"),
        ("  E4 — wrong / no phase",          crit.get("E4", 0),  "BDD7EE"),
        ("Unsure (needs Phase 2/3 review)",  n_uns,              "FFEB9C"),
        ("Flagged for human review",         n_nr,               "FF0000" if n_nr else "FFFFFF"),
    ]
    bold_rows = {"Identified — total", "Screened (unique records)", "Included", "Excluded — total"}
    for label, value, fill in prisma:
        c1 = ws.cell(row=row, column=1, value=label)
        c2 = ws.cell(row=row, column=2, value=value)
        is_bold = label.strip() in bold_rows
        c1.font = _font(bold=is_bold)
        c1.fill = _fill(fill); c1.border = _thin()
        c1.alignment = Alignment(vertical="center", indent=2 if label.startswith("  ") else 0)
        c2.fill = _fill(fill); c2.border = _thin()
        c2.alignment = Alignment(horizontal="center", vertical="center")
        c2.font = _font(bold=is_bold,
                        color="CC0000" if (label == "Flagged for human review" and n_nr) else "000000")
        ws.row_dimensions[row].height = 18
        row += 1

    row += 1

    # ── Column Guide ──────────────────────────────────────────────────────────
    heading(ws, row, "COLUMN GUIDE — Screening sheet", bg="4472C4"); row += 1
    col_guide = [
        ("decision",        "Include / Exclude / Unsure — AI screening decision"),
        ("criterion",       "Exclusion criterion applied (E1–E4); blank for Include"),
        ("evidence",        "The exact text or field value that triggered the decision — "
                            "use this to quickly verify without re-reading the full record"),
        ("reason",          "One-line plain-English explanation of the decision"),
        ("confidence",      "High = clear-cut; Low = borderline Phase 2/3; "
                            "Medium = BIOLOGICAL intervention without confirmed vaccine keyword"),
        ("needs_review",    "Y = human reviewer must check before finalising"),
        ("ctg_id/ctg_url",  "ClinicalTrials.gov NCT number and direct study link"),
        ("ictrp_id/ictrp_url", "Source-registry ID and link via WHO ICTRP — populated only for "
                               "non-CTG registries (CTRI, REBEC, ChiCTR, etc.)"),
        ("primary_outcomes / secondary_outcomes",
         "Verbatim outcome text from the registry — used in Part 2 extraction"),
        ("inclusion_criteria / exclusion_criteria",
         "Participant eligibility text (from ICTRP records; blank for CTG-only records)"),
        ("match",           "De-duplication basis: 'single record', 'Exact/shared registry ID', "
                            "or 'Fuzzy title+date+outcomes (title_sim=X, outcomes_overlap=Y) — CONFIRM'"),
    ]
    for col, desc in col_guide:
        kv(ws, row, col, desc, fill_key="EAF0FB"); row += 1

    ws.column_dimensions["A"].width = 40
    ws.column_dimensions["B"].width = 74
    ws.freeze_panes = None


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--screening", required=True, help="screening.csv from dedupe.py")
    ap.add_argument("--out", default="screening_results.xlsx")
    ap.add_argument("--ctg-n",   type=int, default=0)
    ap.add_argument("--ictrp-n", type=int, default=0)
    ap.add_argument("--dup-n",   type=int, default=0)
    a = ap.parse_args()

    rows = []
    with open(a.screening, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    src_cols = list(rows[0].keys())
    unique   = [r for r in rows if r["dup"] == "Unique"]
    dups     = [r for r in rows if r["dup"] != "Unique"]

    screened = screen(unique)

    dec  = Counter(r["decision"]  for r in screened)
    crit = Counter(r["criterion"] for r in screened if r["decision"] == "Exclude")
    n_nr = sum(1 for r in screened if r.get("needs_review") == "Y")

    counts = {
        "ctg":  a.ctg_n  or sum(1 for r in rows if "ClinicalTrials" in r.get("source","") and r["dup"]=="Unique"),
        "ictrp": a.ictrp_n or sum(1 for r in rows if "ClinicalTrials" not in r.get("source","") and r["dup"]=="Unique"),
        "dup":  a.dup_n  or len(dups),
        "needs_review": n_nr,
    }
    if a.ctg_n:   counts["ctg"]   = a.ctg_n
    if a.ictrp_n: counts["ictrp"] = a.ictrp_n
    if a.dup_n:   counts["dup"]   = a.dup_n

    wb = Workbook()
    ws_screen = wb.active
    ws_screen.title = "1. Screening"
    ws_legend = wb.create_sheet("Legend & PRISMA")

    write_screening_sheet(ws_screen, screened, dups, src_cols)
    write_legend_sheet(ws_legend, dec, crit, counts)

    wb.save(a.out)
    print(f"[ok] {a.out}", file=sys.stderr)
    print(f"     Include={dec['Include']}  Exclude={dec['Exclude']}  "
          f"Unsure={dec['Unsure']}  NeedsReview={n_nr}", file=sys.stderr)
    print(f"     E1={crit['E1']} E2={crit['E2']} E3={crit['E3']} E4={crit['E4']}", file=sys.stderr)


if __name__ == "__main__":
    main()
