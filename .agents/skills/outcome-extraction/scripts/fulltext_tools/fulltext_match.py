import re, sys, json, pathlib, collections, difflib, openpyxl
txtdir, protos, out = pathlib.Path(sys.argv[1]), sys.argv[2], pathlib.Path(sys.argv[3])
PAT = re.compile(r"""(NCT\s?\d{8}|ISRCTN\s?\d{8}|ACTRN\s?\d{14}|ChiCTR[-\s]?[A-Z]{0,4}-?\d{6,10}|CTRI/\d{4}/\d{2,3}/\d{5,6}|
 IRCT\s?\d{8,14}N\d{1,3}|jRCT\s?\d{10}|UMIN\s?\d{9}|DRKS\s?\d{8}|TCTR\s?\d{11}|KCT\s?\d{7}|PACTR\s?\d{15}|
 NTR\s?\d{3,5}|NL\s?\d{4,5}|EudraCT[\s:No.number]*\d{4}-\d{6}-\d{2}|\b20\d\d-\d{6}-\d{2}\b|RBR-\w{6,8}|
 CTIS\s?\d{4}-\d{6}-\d{2}-\d{2}|SLCTR/\d{4}/\d{3}|IRCT\d+)""", re.X)
def norm(x):
    x = re.sub(r"\s", "", x)
    m = re.search(r"(\d{4}-\d{6}-\d{2})", x)
    if m and not x.startswith("CTIS"): return "EUDRACT:" + m.group(1)
    x = x.replace("ChiCTR-", "ChiCTR").replace("jRCT", "jRCT")
    return x.upper().replace("CHICTR", "ChiCTR").replace("JRCT", "jRCT")
def ids_in(text):
    return [norm(m.group(0)) for m in PAT.finditer(text)]
# protocols
wb = openpyxl.load_workbook(protos, read_only=True); rows = list(wb.active.iter_rows(values_only=True)); h = rows[0]
P = []
for r in rows[1:]:
    d = dict(zip(h, r)); pid = d["Registration ID"]
    own = set(ids_in(pid.replace("EUCTR", "EudraCT ").replace("JPRN-", "")))
    own |= {norm(pid.replace("JPRN-", ""))} if not pid.startswith("EUCTR") else set()
    sec = set(ids_in(str(d.get("Secondary IDs") or "")))
    P.append(dict(id=pid, src=d["Registry / Source"], title=str(d["Study Title"] or ""), sci=str(d["Scientific / Official Title"] or ""),
                  acr=str(d.get("Acronym") or ""), own=own, sec=sec, start=str(d.get("Enrollment start date") or ""),
                  sponsor=str(d.get("Sponsor") or ""), url=d.get("URL")))
# duplicates among protocols
idx = collections.defaultdict(set)
for i, p in enumerate(P):
    for k in p["own"] | p["sec"]: idx[k].add(i)
dups = []
for k, s in idx.items():
    if len(s) > 1: dups.append(("shared registry ID " + k, sorted(P[i]["id"] for i in s)))
def nt(t): return re.sub(r"[^a-z0-9 ]", " ", t.lower())
for i in range(len(P)):
    for j in range(i + 1, len(P)):
        a, b = P[i], P[j]
        if (a["own"] | a["sec"]) & (b["own"] | b["sec"]): continue
        for ta in (a["title"], a["sci"]):
            for tb in (b["title"], b["sci"]):
                if len(ta) > 25 and len(tb) > 25 and difflib.SequenceMatcher(None, nt(ta), nt(tb)).ratio() >= 0.85:
                    dups.append((f"similar title ({difflib.SequenceMatcher(None, nt(ta), nt(tb)).ratio():.2f})", [a["id"], b["id"]])); break
            else: continue
            break
        if a["acr"] and a["acr"] == b["acr"] and len(a["acr"]) > 3:
            dups.append(("same acronym " + a["acr"], [a["id"], b["id"]]))
seen = set(); D = []
for why, ids in dups:
    k = tuple(sorted(set(ids)))
    if k not in seen: seen.add(k); D.append((why, list(k)))
# full texts
FT = {}
for f in sorted(txtdir.glob("*.txt")):
    t = f.read_text(encoding="utf-8", errors="ignore")
    c = collections.Counter(ids_in(t)); first = collections.Counter(ids_in(t[:6000]))
    FT[f.stem] = dict(ids=c, first=first, chars=len(t))
links = []
for name, ft in FT.items():
    hits = collections.defaultdict(lambda: [0, 0])
    for k, n in ft["ids"].items():
        for i in idx.get(k, ()):
            hits[i][0] += n; hits[i][1] += ft["first"].get(k, 0)
    for i, (n, nf) in hits.items():
        links.append(dict(fulltext=name, protocol=P[i]["id"], mentions=n, in_first_pages=nf,
                          n_ids_in_text=len(ft["ids"]), ids_in_text=dict(ft["ids"].most_common(6))))
nomatch = [n for n in FT if not any(l["fulltext"] == n for l in links)]
json.dump(dict(dups=D, links=links, nomatch=nomatch, ft_meta={k: dict(chars=v["chars"], ids=dict(v["ids"].most_common(5))) for k, v in FT.items()},
               protos=[{k: (sorted(v) if isinstance(v, set) else v) for k, v in p.items()} for p in P]),
          out.open("w"), indent=1, default=str)
print("protocols", len(P), "| dup groups", len(D), "| fulltexts", len(FT), "| links", len(links),
      "| fulltexts w/o match", len(nomatch), "| protocols with fulltext", len({l['protocol'] for l in links}))
