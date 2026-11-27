#!/usr/bin/env python3
"""Extract final included studies from the reviewed screening workbook (Step 3).

Reads '1. Screening' sheet of screening_results.xlsx.
For each Unique record applies the merge rule:

    final = human_decision  (if filled by reviewer)
            else  decision  (AI)

Rows where final == 'Include' go into included_studies.csv for Part 2.
The output carries both AI and human columns so the audit trail is clear.

Usage:
  python scripts/extract_included.py --xlsx screening_results.xlsx --out included_studies.csv
"""
import argparse, csv, sys
from openpyxl import load_workbook

PART2_COLS = [
    "record_id", "source",
    "ctg_id", "ctg_url", "ictrp_id", "ictrp_url",
    "title", "sponsor", "cond", "phase", "status",
    "enrollment", "sex", "age", "locations",
    "primary_outcomes", "secondary_outcomes", "other_outcomes",
    "inclusion_criteria", "exclusion_criteria",
    "results_available",
    # audit trail
    "ai_decision", "ai_criterion", "ai_evidence", "ai_confidence",
    "human_decision", "justification",
    "decision_source",   # "AI" or "Human"
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xlsx",  required=True, help="reviewed screening_results.xlsx")
    ap.add_argument("--out",   default="included_studies.csv")
    ap.add_argument("--sheet", default="1. Screening")
    a = ap.parse_args()

    wb = load_workbook(a.xlsx, read_only=True, data_only=True)
    if a.sheet not in wb.sheetnames:
        print(f"[error] sheet '{a.sheet}' not found. Available: {wb.sheetnames}", file=sys.stderr)
        sys.exit(1)

    ws     = wb[a.sheet]
    it     = ws.values
    header = [str(c).strip() if c is not None else "" for c in next(it)]
    idx    = {col: i for i, col in enumerate(header)}

    for required in ("decision", "dup"):
        if required not in idx:
            print(f"[error] required column '{required}' missing from sheet.", file=sys.stderr)
            sys.exit(1)

    def get(row, col, default=""):
        i = idx.get(col)
        return str(row[i]).strip() if i is not None and row[i] is not None else default

    included = []
    n_ai = n_human = 0

    for row in it:
        if get(row, "dup") != "Unique":
            continue

        ai_dec     = get(row, "decision")
        human_dec  = get(row, "human_decision")
        final_dec  = human_dec if human_dec else ai_dec
        source     = "Human" if human_dec else "AI"

        if final_dec.lower() != "include":
            continue

        rec = {
            "record_id":          get(row, "record_id"),
            "source":             get(row, "source"),
            "ctg_id":             get(row, "ctg_id"),
            "ctg_url":            get(row, "ctg_url"),
            "ictrp_id":           get(row, "ictrp_id"),
            "ictrp_url":          get(row, "ictrp_url"),
            "title":              get(row, "title"),
            "sponsor":            get(row, "sponsor"),
            "cond":               get(row, "cond"),
            "phase":              get(row, "phase"),
            "status":             get(row, "status"),
            "enrollment":         get(row, "enrollment"),
            "sex":                get(row, "sex"),
            "age":                get(row, "age"),
            "locations":          get(row, "locations"),
            "primary_outcomes":   get(row, "primary_outcomes"),
            "secondary_outcomes": get(row, "secondary_outcomes"),
            "other_outcomes":     get(row, "other_outcomes"),
            "inclusion_criteria": get(row, "inclusion_criteria"),
            "exclusion_criteria": get(row, "exclusion_criteria"),
            "results_available":  get(row, "results_available"),
            "ai_decision":        ai_dec,
            "ai_criterion":       get(row, "criterion"),
            "ai_evidence":        get(row, "evidence"),
            "ai_confidence":      get(row, "confidence"),
            "human_decision":     human_dec,
            "justification":      get(row, "justification"),
            "decision_source":    source,
        }
        included.append(rec)
        if source == "Human": n_human += 1
        else: n_ai += 1

    with open(a.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=PART2_COLS, extrasaction="ignore")
        w.writeheader()
        w.writerows(included)

    print(f"[ok] {len(included)} included → {a.out}", file=sys.stderr)
    print(f"     AI-decided: {n_ai}  |  Human-added/overridden: {n_human}", file=sys.stderr)
    for r in included:
        tag = "[H]" if r["decision_source"] == "Human" else "[A]"
        rid = r.get("ctg_id") or r.get("ictrp_id","")
        print(f"  {tag} {r['record_id']} | {rid} | {r['title'][:55]}")


if __name__ == "__main__":
    main()
