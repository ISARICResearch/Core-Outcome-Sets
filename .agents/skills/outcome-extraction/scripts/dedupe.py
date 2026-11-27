#!/usr/bin/env python3
"""De-duplicate ClinicalTrials.gov + WHO ICTRP downloads (Part 1 core).

Merge order (most reliable first):
  1. Exact registry-ID match across primary + secondary IDs
  2. ICTRP bridge flag / shared secondary ID
  3. Fuzzy fallback: title similarity ≥ 0.90 + same registration year +
     outcome word-overlap ≥ 0.25 (when outcome text available in both).
     Always flagged — CONFIRM — never silent.

Outputs a unified record table matching the '1. Screening' sheet, with a
match_basis for every removed duplicate, plus PRISMA counts to stderr.

Usage:
  python scripts/dedupe.py --ctg ctg-studies.csv --ictrp IctrpResults_example.csv --out screening.csv
"""
import argparse, csv, re, sys
from difflib import SequenceMatcher

def norm_id(s):
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())

# Recognise only REAL trial-registry IDs as merge keys. Free-text secondary-ID
# fields ("Nil", "No", sponsor codes) must never become merge keys.
REG = [re.compile(p, re.I) for p in [
    r"\bNCT\d{8}\b", r"\bISRCTN\d{8}\b", r"\bACTRN\d{14}\b", r"\bDRKS\d{8}\b",
    r"\bChiCTR[-A-Za-z]*\d{6,}\b", r"\bCTRI/\d{4}/\d{2,3}/\d{6}\b",
    r"\bEUCTR\d{4}-\d{6}-\d{2}\b", r"\b\d{4}-\d{6}-\d{2}\b",   # EudraCT
    r"\bIRCT\w{6,}\b", r"\bUMIN\d{9}\b", r"\bjRCTs?\d{6,}\b",
    r"\bPACTR\d{12,}\b", r"\bRBR-\w{5,}\b", r"\bKCT\d{7}\b", r"\bNTR\d{3,}\b",
    r"\bTCTR\d{8,}\b", r"\bSLCTR/\d{4}/\d{3}\b", r"\bPER-\d+\b", r"\bCHICTR\w*\d{6,}\b",
]]

def reg_ids(*fields):
    out = set()
    for s in fields:
        if not s: continue
        for rx in REG:
            for m in rx.findall(s):
                out.add(norm_id(m))
    return out

def norm_text(s):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", (s or "").lower())).strip()

norm_title = norm_text  # alias kept for clarity

_STOP = frozenset(
    "a an the of in and or to at by for with on is are was were be been "
    "as this that it its from which will was were has have had".split()
)

def outcome_overlap(a, b):
    """Jaccard similarity on content words. Returns None when either string is empty."""
    wa = {w for w in norm_text(a).split() if w not in _STOP and len(w) > 2}
    wb = {w for w in norm_text(b).split() if w not in _STOP and len(w) > 2}
    if not wa or not wb:
        return None
    return len(wa & wb) / len(wa | wb)

def year(s):
    m = re.search(r"(19|20)\d{2}", s or "")
    return m.group(0) if m else ""

def ctg_url(nct_id, study_url=""):
    if study_url:
        return study_url.strip()
    nct = (nct_id or "").strip()
    return f"https://clinicaltrials.gov/study/{nct}" if nct.upper().startswith("NCT") else ""

def read_ctg(path):
    out = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            nct = r.get("NCT Number","").strip()
            ids = {norm_id(nct)} | reg_ids(r.get("Other IDs"))
            primary_out   = r.get("Primary Outcome Measures","").strip()
            secondary_out = r.get("Secondary Outcome Measures","").strip()
            other_out     = r.get("Other Outcome Measures","").strip()
            outcomes = " | ".join(filter(None, [primary_out, secondary_out]))
            out.append(dict(source="ClinicalTrials.gov", primary_id=nct,
                url=ctg_url(nct, r.get("Study URL","")),
                ids={i for i in ids if i}, sec=r.get("Other IDs","").strip(),
                title=r.get("Study Title","").strip(),
                summary=r.get("Brief Summary","").strip(),
                sponsor=r.get("Sponsor","").strip(),
                collaborators=r.get("Collaborators","").strip(),
                cond=r.get("Conditions","").strip(),
                intv=r.get("Interventions","").strip(),
                stype=r.get("Study Type","").strip(),
                study_design=r.get("Study Design","").strip(),
                phase=r.get("Phases","").strip(),
                status=r.get("Study Status","").strip(),
                enrollment=r.get("Enrollment","").strip(),
                sex=r.get("Sex","").strip(),
                age=r.get("Age","").strip(),
                funder_type=r.get("Funder Type","").strip(),
                date=r.get("Start Date","").strip(),
                completion_date=r.get("Completion Date","").strip(),
                locations=r.get("Locations","").strip(),
                primary_outcomes=primary_out,
                secondary_outcomes=secondary_out,
                other_outcomes=other_out,
                inclusion_criteria="",
                exclusion_criteria="",
                results_available=r.get("Study Results","").strip(),
                outcomes=outcomes, bridge=""))
    return out

def read_ictrp(path):
    out = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            trial_id = r.get("TrialID","").strip()
            ids = {norm_id(trial_id)} | reg_ids(r.get("Secondary ID"), r.get("other records"))
            reg = (r.get("Source Register") or r.get("Source Name") or "ICTRP").strip()
            primary_out   = r.get("Primary outcome","").strip()
            secondary_out = r.get("Secondary outcome","").strip()
            outcomes = " | ".join(filter(None, [primary_out, secondary_out]))
            age_min = r.get("Inclusion agemin","").strip()
            age_max = r.get("Inclusion agemax","").strip()
            age = f"{age_min}–{age_max}" if age_min or age_max else ""
            out.append(dict(source=f"ICTRP: {reg}", primary_id=trial_id,
                url=(r.get("web address") or "").strip(),
                ids={i for i in ids if i}, sec=r.get("Secondary ID","").strip(),
                title=(r.get("Public title") or r.get("Scientific title","")).strip(),
                summary=r.get("Scientific title","").strip(),
                sponsor=r.get("Primary sponsor","").strip(),
                collaborators=r.get("Secondary Sponsor","").strip(),
                cond=r.get("Condition","").strip(),
                intv=r.get("Intervention","").strip(),
                stype=r.get("Study type","").strip(),
                study_design=r.get("Study design","").strip(),
                phase=r.get("Phase","").strip(),
                status=r.get("Recruitment Status","").strip(),
                enrollment=r.get("Target size","").strip(),
                sex=r.get("Inclusion gender","").strip(),
                age=age,
                funder_type="",
                date=r.get("Date registration","").strip(),
                completion_date=r.get("Date enrollement","").strip(),
                locations=r.get("Countries","").strip(),
                primary_outcomes=primary_out,
                secondary_outcomes=secondary_out,
                other_outcomes="",
                inclusion_criteria=r.get("Inclusion Criteria","").strip(),
                exclusion_criteria=r.get("Exclusion Criteria","").strip(),
                results_available=r.get("results yes no","").strip(),
                outcomes=outcomes, bridge=(r.get("Bridging flag truefalse","") or "").strip()))
    return out

def dedupe(records):
    n = len(records)
    parent = list(range(n))
    def find(x):
        while parent[x]!=x: parent[x]=parent[parent[x]]; x=parent[x]
        return x
    def union(a,b): parent[find(a)]=find(b)
    basis = {}
    # 1+2: shared ID (covers exact NCT, secondary IDs, ICTRP bridge records)
    idmap = {}
    for i,r in enumerate(records):
        for _id in r["ids"]:
            if _id in idmap:
                union(i, idmap[_id]); basis.setdefault(i,"Exact/shared registry ID")
            else:
                idmap[_id] = i
    # 3: fuzzy fallback for still-singleton records
    # Requires: title similarity ≥ 0.90 AND same registration year
    #           AND outcome word-overlap ≥ 0.25 (skipped only if neither record has outcomes)
    groups = {}
    for i in range(n): groups.setdefault(find(i),[]).append(i)
    singles = [i for i,r in enumerate(records) if len(groups[find(i)])==1]
    for a_i in range(len(singles)):
        for b_i in range(a_i+1, len(singles)):
            a, b = singles[a_i], singles[b_i]
            if find(a)==find(b): continue
            ra, rb = records[a], records[b]
            ta, tb = norm_title(ra["title"]), norm_title(rb["title"])
            if not ta or not tb: continue
            sim = SequenceMatcher(None, ta, tb).ratio()
            same_year = year(ra["date"]) and year(ra["date"])==year(rb["date"])
            if not (sim >= 0.90 and same_year): continue
            ov = outcome_overlap(ra.get("outcomes",""), rb.get("outcomes",""))
            if ov is not None and ov < 0.25:
                continue  # titles match but outcomes diverge → not the same study
            ov_str = f", outcomes_overlap={ov:.2f}" if ov is not None else ", outcomes unavailable"
            union(a, b)
            basis[max(a, b)] = f"Fuzzy title+date+outcomes (title_sim={sim:.2f}{ov_str}) — CONFIRM"
    # build output: keep CTG record as canonical, else lowest index
    groups = {}
    for i in range(n): groups.setdefault(find(i),[]).append(i)
    rows = []
    counts = dict(ctg=0, ictrp=0, dup=0)
    for r in records:
        if r["source"].startswith("ClinicalTrials"): counts["ctg"]+=1
        else: counts["ictrp"]+=1
    rid = 0
    for members in groups.values():
        members.sort(key=lambda i: (0 if records[i]["source"].startswith("ClinicalTrials") else 1, i))
        keep = members[0]; rid += 1
        kr = records[keep]
        all_src = " + ".join(sorted({records[m]["source"] for m in members}))
        all_ids = "; ".join(sorted({records[m]["primary_id"] for m in members if records[m]["primary_id"]}))

        ctg_ids  = "; ".join(r["primary_id"] for m in members
                             if (r := records[m])["source"].startswith("ClinicalTrials") and r["primary_id"])
        ctg_urls = "; ".join(r["url"] for m in members
                             if (r := records[m])["source"].startswith("ClinicalTrials") and r["url"])
        # ictrp_id/url: only non-CTG source registers (exclude ICTRP mirrors of CTG records)
        ictrp_ids  = "; ".join(r["primary_id"] for m in members
                               if "ClinicalTrials" not in (r := records[m])["source"] and r["primary_id"])
        ictrp_urls = "; ".join(r["url"] for m in members
                               if "ClinicalTrials" not in (r := records[m])["source"] and r["url"])

        extra = {k: kr[k] for k in (
            "summary","sponsor","collaborators","enrollment","sex","age","funder_type",
            "study_design","completion_date","locations",
            "primary_outcomes","secondary_outcomes","other_outcomes",
            "inclusion_criteria","exclusion_criteria","results_available")}
        rows.append(dict(record_id=f"R{rid:04d}", source=all_src,
            ctg_id=ctg_ids, ctg_url=ctg_urls, ictrp_id=ictrp_ids, ictrp_url=ictrp_urls,
            reg_id=all_ids, sec=kr["sec"],
            title=kr["title"], cond=kr["cond"], intv=kr["intv"], stype=kr["stype"], phase=kr["phase"],
            status=kr["status"], date=kr["date"], dup="Unique", dup_of="",
            match=("single record" if len(members)==1 else basis.get([m for m in members if m!=keep][0],"shared ID")),
            **extra))
        for m in members:
            if m==keep: continue
            counts["dup"]+=1
            rm = records[m]
            is_ctg = "ClinicalTrials" in rm["source"]
            rm_extra = {k: rm[k] for k in (
                "summary","sponsor","collaborators","enrollment","sex","age","funder_type",
                "study_design","completion_date","locations",
                "primary_outcomes","secondary_outcomes","other_outcomes",
                "inclusion_criteria","exclusion_criteria","results_available")}
            rows.append(dict(record_id=f"R{rid:04d}-d", source=rm["source"],
                ctg_id=rm["primary_id"] if is_ctg else "",
                ctg_url=rm["url"] if is_ctg else "",
                ictrp_id="" if is_ctg else rm["primary_id"],
                ictrp_url="" if is_ctg else rm["url"],
                reg_id=rm["primary_id"], sec=rm["sec"], title=rm["title"],
                cond=rm["cond"], intv=rm["intv"], stype=rm["stype"],
                phase=rm["phase"], status=rm["status"], date=rm["date"],
                dup="Duplicate – removed", dup_of=f"R{rid:04d}", match=basis.get(m,"shared ID"),
                **rm_extra))
    return rows, counts

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ctg"); ap.add_argument("--ictrp"); ap.add_argument("--out", default="screening.csv")
    a = ap.parse_args()
    recs = []
    if a.ctg: recs += read_ctg(a.ctg)
    if a.ictrp: recs += read_ictrp(a.ictrp)
    rows, c = dedupe(recs)
    cols = [
        "record_id","source","ctg_id","ctg_url","ictrp_id","ictrp_url","reg_id","sec",
        "title","summary","sponsor","collaborators","cond","intv",
        "stype","study_design","phase","status","enrollment","sex","age","funder_type",
        "date","completion_date","locations",
        "primary_outcomes","secondary_outcomes","other_outcomes",
        "inclusion_criteria","exclusion_criteria","results_available",
        "dup","dup_of","match",
    ]
    with open(a.out,"w",newline="",encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader()
        for r in rows: w.writerow(r)
    uniq = c["ctg"]+c["ictrp"]-c["dup"]
    print(f"[PRISMA] CTG={c['ctg']}  ICTRP={c['ictrp']}  total={c['ctg']+c['ictrp']}  "
          f"duplicates_removed={c['dup']}  screened={uniq}", file=sys.stderr)
    print(f"[ok] wrote {a.out} ({len(rows)} rows)", file=sys.stderr)

if __name__ == "__main__": main()
