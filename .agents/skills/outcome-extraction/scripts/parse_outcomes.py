#!/usr/bin/env python3
"""Explode each study's outcomes into one row per outcome (Part 2, deterministic).

Fills only the GREY columns (verbatim outcome + timepoint + type), leaving
Outcome / OMI / Metric / Domain blank for the AI step. No tokens spent here.

CTG CSV packs outcomes as:  measure, description, timeframe | next | ...
  -> NOTE: the ClinicalTrials.gov v2 JSON API returns measure/description/
     timeFrame as SEPARATE fields. Prefer the API; then measure & description
     are split for free and this script's CSV heuristic is unnecessary.
ICTRP packs outcomes as narrative split by ';' with 'Timepoint:' inline.

Usage (preferred — reads from included_studies.csv produced by extract_included.py):
  python scripts/parse_outcomes.py --included included_studies.csv --out outcomes_raw.csv

Usage (legacy — reads raw registry downloads directly):
  python scripts/parse_outcomes.py --ctg ctg-studies.csv --ictrp IctrpResults_example.csv --out outcomes.csv
"""
import argparse, csv, re, sys

TIME_HINT = re.compile(r"(day|week|hour|month|year|baseline|post|pre|visit|follow|screening|h\b|hrs?)", re.I)
HTML_TAG  = re.compile(r"<[^>]+>")

def clean(s):
    return re.sub(r"\s+", " ", HTML_TAG.sub(" ", s or "")).strip()

def split_ctg_field(blob):
    """One CTG outcome chunk -> (verbatim, timeframe_guess)."""
    parts = [p.strip() for p in blob.split(",")]
    tf = ""
    if len(parts) >= 2 and TIME_HINT.search(parts[-1]):
        tf = parts[-1]
    return blob.strip(), tf

# ── legacy readers (raw CTG / ICTRP CSV) ─────────────────────────────────────

def ctg_rows(path):
    rows=[]
    with open(path, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            rid = r.get("NCT Number","").strip()
            for col,typ in [("Primary Outcome Measures","Primary"),
                            ("Secondary Outcome Measures","Secondary"),
                            ("Other Outcome Measures","Other")]:
                val = (r.get(col) or "").strip()
                if not val or val.lower()=="nan": continue
                for chunk in val.split("|"):
                    chunk=chunk.strip()
                    if not chunk: continue
                    verb, tf = split_ctg_field(chunk)
                    rows.append((rid,"ClinicalTrials.gov",typ,verb,tf))
    return rows

def ictrp_rows(path):
    rows=[]
    with open(path, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            rid = r.get("TrialID","").strip()
            for col,typ in [("Primary outcome","Primary"),("Secondary outcome","Secondary")]:
                val=(r.get(col) or "").strip()
                if not val or val.lower()=="nan": continue
                for chunk in re.split(r";", val):
                    chunk=chunk.strip()
                    if not chunk: continue
                    tf=""
                    m=re.search(r"Timepoint\s*:\s*(.+)$", chunk, re.I)
                    if m:
                        tf=m.group(1).strip()
                        chunk=chunk[:m.start()].strip()
                    rows.append((rid,f"ICTRP",typ,chunk,tf))
    return rows

# ── preferred reader (from included_studies.csv) ─────────────────────────────

def included_rows(path):
    """Read from included_studies.csv (already has parsed outcome columns)."""
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            record_id = r.get("record_id","").strip()
            source    = r.get("source","").strip()
            is_ctg    = "ClinicalTrials.gov" in source

            for col, typ in [("primary_outcomes",   "Primary"),
                             ("secondary_outcomes", "Secondary"),
                             ("other_outcomes",     "Other")]:
                val = clean(r.get(col,""))
                if not val or val.lower() in ("nan","none",""): continue

                if is_ctg:
                    for chunk in val.split("|"):
                        chunk = chunk.strip()
                        if not chunk: continue
                        verb, tf = split_ctg_field(chunk)
                        rows.append((record_id, source, typ, verb, tf))
                else:
                    # ICTRP: split on ";" or numbered list "1." / "2." etc.
                    # Handle numeric list markers that some CTRI entries use
                    chunks = re.split(r";|\n(?=\s*\d+\.)", val)
                    for chunk in chunks:
                        chunk = chunk.strip()
                        if not chunk: continue
                        tf = ""
                        m = re.search(r"Timepoint\s*:\s*(.+)$", chunk, re.I)
                        if m:
                            tf = clean(m.group(1))
                            chunk = chunk[:m.start()].strip()
                        chunk = clean(chunk)
                        if not chunk: continue
                        rows.append((record_id, source, typ, chunk, tf))
    return rows

# ── main ─────────────────────────────────────────────────────────────────────

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--included", help="preferred: included_studies.csv from extract_included.py")
    ap.add_argument("--ctg",  help="legacy: raw ClinicalTrials.gov CSV")
    ap.add_argument("--ictrp",help="legacy: raw ICTRP CSV")
    ap.add_argument("--out", default="outcomes_raw.csv")
    a=ap.parse_args()

    rows=[]
    if a.included: rows += included_rows(a.included)
    if a.ctg:      rows += ctg_rows(a.ctg)
    if a.ictrp:    rows += ictrp_rows(a.ictrp)

    if not rows:
        print("[error] provide --included, --ctg, or --ictrp", file=sys.stderr)
        sys.exit(1)

    cols=["record_id","source","type_of_outcome","verbatim_outcome","time_frame",
          "outcome","description","domain_dodd","omi","omi_type","metric",
          "confidence","needs_review"]
    with open(a.out,"w",newline="",encoding="utf-8") as f:
        w=csv.writer(f); w.writerow(cols)
        for rid,src,typ,verb,tf in rows:
            w.writerow([rid,src,typ,verb,tf,"","","","","","","",""])
    print(f"[ok] wrote {a.out}: {len(rows)} outcome rows (AI columns left blank)", file=sys.stderr)

if __name__=="__main__": main()
