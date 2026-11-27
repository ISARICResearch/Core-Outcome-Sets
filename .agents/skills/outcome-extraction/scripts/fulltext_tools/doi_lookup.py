import json, re, sys, time, pathlib, urllib.request, urllib.parse
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from ftnorm import norm
txtdir, matches, out = pathlib.Path(sys.argv[1]), sys.argv[2], pathlib.Path(sys.argv[3])
names = sorted(f.stem for f in txtdir.glob("*.txt")) if matches == "--all" else sorted({l["fulltext"] for l in json.load(open(matches))["links"]})
DOI = re.compile(r"10\.\d{4,9}/[^\s\"<>,;]+")
def words(t): return set(re.findall(r"[a-z]{4,}", t.lower()))
res = {}
for n in names:
    raw = (txtdir / f"{n}.txt").read_text(encoding="utf-8", errors="ignore")
    head = norm(raw[:8000]); head_w = words(head)
    cands = []
    for m in DOI.finditer(raw[:8000].replace("\n", " ")):
        d = re.sub(r"[©®™]+$", "", m.group(0)).rstrip(".)]:").rstrip(".")
        if d not in cands: cands.append(d)
    if not cands:  # DOI broken across a line: join lines and strip glued-on words
        for m in DOI.finditer(raw[:8000].replace(chr(10), "")):
            d = re.sub(r"[©®™]+.*$", "", m.group(0)).rstrip(".)]:").rstrip(".")
            if d not in cands: cands.append(d)
    hit = None
    for d in cands[:6]:
        try:
            req = urllib.request.Request("https://api.crossref.org/works/" + urllib.parse.quote(d),
                                         headers={"User-Agent": "cos-extraction-script"})
            msg = json.load(urllib.request.urlopen(req, timeout=20))["message"]
        except Exception:
            continue
        title = " ".join(msg.get("title") or [""])
        tw = words(title)
        overlap = len(tw & head_w) / max(len(tw), 1)
        if overlap >= 0.8:  # title of this DOI must appear on the first pages -> the paper itself, not a reference
            auth = (msg.get("author") or [{}])[0].get("family", "")
            year = (msg.get("issued", {}).get("date-parts") or [[None]])[0][0]
            jour = " ".join(msg.get("short-container-title") or msg.get("container-title") or [""])
            hit = dict(doi="https://doi.org/" + msg["DOI"], title=title, author=auth, year=year, journal=jour,
                       overlap=round(overlap, 2))
            break
        time.sleep(0.2)
    res[n] = hit
    print(("OK  " if hit else "MISS"), n[:50], "|", (hit or {}).get("doi", f"candidates: {cands[:3]}"))
old = json.loads(out.read_text()) if out.exists() else {}
old.update({k: v for k, v in res.items() if v or k not in old})
json.dump(old, out.open("w"), indent=1)
print("found", sum(1 for v in res.values() if v), "of", len(res))
