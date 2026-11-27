import re
def norm(t):
    t = t.replace("ﬁ", "fi").replace("ﬂ", "fl").replace("/C0", "−").replace("¼", "=")
    t = re.sub(r"(\w) ?-\s*\n\s*(\w)", r"\1\2", t)      # join hyphenated line breaks
    t = re.sub(r"\s+", " ", t)
    return t.strip()
