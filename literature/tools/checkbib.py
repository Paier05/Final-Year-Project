#!/usr/bin/env python3
"""Structural validator for refs.bib.

No LaTeX toolchain is available in this environment, so "compiles clean" is checked
structurally instead of by running bibtex: balanced braces, unique keys, well-formed
entry headers, required fields present, no unescaped specials that break BibTeX,
and no stray non-ASCII that a pdflatex run would choke on without inputenc.

Usage: python checkbib.py ../refs.bib [--strict-ascii]
Exit code 0 = clean.
"""
import re
import sys

REQUIRED = {"title", "author", "year"}


def check(path, strict_ascii=False):
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    problems = []

    # strip comment lines before brace accounting
    body = "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("%"))

    if body.count("{") != body.count("}"):
        problems.append("unbalanced braces: {0} '{{' vs {1} '}}'".format(
            body.count("{"), body.count("}")))

    headers = re.findall(r"@(\w+)\s*\{\s*([^,\s]+)\s*,", body)
    keys = [k for _, k in headers]
    seen, dupes = set(), []
    for k in keys:
        if k in seen:
            dupes.append(k)
        seen.add(k)
    if dupes:
        problems.append("duplicate keys: " + ", ".join(sorted(set(dupes))))

    for k in keys:
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9:_.\-+/]*", k):
            problems.append("suspicious citation key: " + k)

    # split into entries and check required fields
    chunks = re.split(r"\n(?=@\w+\s*\{)", body)
    n = 0
    for chunk in chunks:
        if not chunk.lstrip().startswith("@"):
            continue
        n += 1
        m = re.match(r"@(\w+)\s*\{\s*([^,\s]+)", chunk.strip())
        key = m.group(2) if m else "<unparsed>"
        fields = set(f.lower() for f in re.findall(r"^\s*([A-Za-z]+)\s*=", chunk, re.M))
        missing = REQUIRED - fields
        if missing:
            problems.append(key + ": missing " + ", ".join(sorted(missing)))
        # a bare unescaped % or # inside a value breaks bibtex/latex
        for bad in ("\\%", "%"):
            pass
        for line in chunk.splitlines():
            if line.lstrip().startswith("%"):
                continue
            val = line.split("=", 1)[1] if "=" in line else ""
            for ch in ("%", "#", "&", "_", "$"):
                if ch in val and ("\\" + ch) not in val:
                    problems.append(key + ": unescaped '" + ch + "' in: " + line.strip()[:70])
                    break

    if strict_ascii:
        for i, line in enumerate(text.splitlines(), 1):
            if any(ord(c) > 127 for c in line):
                problems.append("non-ASCII on line " + str(i) + ": " + line.strip()[:60])

    print("entries: " + str(n) + "   unique keys: " + str(len(seen)))
    if problems:
        print("PROBLEMS (" + str(len(problems)) + "):")
        for p in problems:
            print("  - " + p)
        return 1
    print("OK: braces balanced, keys unique, required fields present, no unescaped specials.")
    return 0


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    sys.exit(check(args[0], strict_ascii="--strict-ascii" in sys.argv))
