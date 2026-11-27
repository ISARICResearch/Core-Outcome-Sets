import sys, pathlib, pypdf
src, out = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
ok = bad = 0
for f in sorted(src.iterdir()):
    if f.suffix.lower() != ".pdf":
        continue
    try:
        r = pypdf.PdfReader(str(f))
        txt = "\n".join((p.extract_text() or "") for p in r.pages)
        (out / (f.stem + ".txt")).write_text(txt, encoding="utf-8")
        ok += 1
    except Exception as e:
        print("FAIL", f.name, e); bad += 1
print("ok", ok, "failed", bad)
