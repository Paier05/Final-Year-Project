#!/usr/bin/env python3
"""Verification pass over the literature corpus (workflow step 5b).

Three checks:

  1. TEMPLATE  - every entry carries every required field, none left blank.
  2. HANDLES   - every [Handle] cross-reference resolves to an entry that exists
                 (catches invented or renamed handles).
  3. NUMBERS   - every numeric token in a "Results that matter" line is checked
                 against the cached record for that paper. Unmatched numbers are
                 printed for manual review; they are not automatically errors
                 (a derived figure such as a ratio legitimately will not appear
                 verbatim in an abstract), but each one must be justified.

Usage: python checkcorpus.py            # run from anywhere; paths are resolved relative to tools/
"""
import io
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
LIT = os.path.normpath(os.path.join(HERE, ".."))
TOPICS = ["topic1-harness.md", "topic2-teacher-student.md", "topic3-frozen-weights.md"]

REQUIRED = ["Authors / Year / Venue", "Link", "Verified", "Type", "Problem", "Method",
            "Verification signal", "What changes", "Results that matter",
            "Limitations / criticisms", "Relevance to this FYP", "Reusable structure", "BibTeX"]


def entries(text):
    """Split a topic file into (handle, title, body) triples."""
    parts = re.split(r"\n(?=### \[)", text)
    out = []
    for p in parts:
        m = re.match(r"### \[([^\]]+)\]\s+—\s+(.*)", p)
        if m:
            out.append((m.group(1), m.group(2).strip(), p))
    return out


def main():
    problems, review = [], []
    defined, all_refs = set(), []
    corpus = {}

    for fn in TOPICS:
        text = io.open(os.path.join(LIT, fn), encoding="utf-8").read()
        es = entries(text)
        corpus[fn] = es
        for handle, _title, body in es:
            defined.add(handle)

    # extra handles that legitimately appear but are defined elsewhere
    defined |= {"non-archival", "unverified", "criteria", "survey", "narrow", "subsumed",
                "brackets", "Handle"}

    for fn, es in corpus.items():
        for handle, title, body in es:
            where = fn + " [" + handle + "]"

            # 1. template completeness
            for field in REQUIRED:
                m = re.search(r"^- \*\*" + re.escape(field) + r"[^*]*:\*\*(.*)$", body, re.M)
                if not m:
                    problems.append(where + ": MISSING field '" + field + "'")
                elif field != "BibTeX" and not m.group(1).strip():
                    problems.append(where + ": BLANK field '" + field + "'")
            if fn == TOPICS[2] and "- **Gain type:**" not in body:
                problems.append(where + ": MISSING 'Gain type' (required for topic 3)")
            if not re.search(r"^- \*\*Verified:\*\*\s*yes", body, re.M):
                problems.append(where + ": not marked Verified: yes")
            if "```bibtex" not in body:
                problems.append(where + ": no BibTeX block")

            # 2. handle references
            for ref in re.findall(r"\[([A-Z][A-Za-z0-9-]{2,})\]", body):
                all_refs.append((where, ref))

            # 3. numbers vs the cached record
            res = re.search(r"^- \*\*Results that matter:\*\*(.*)$", body, re.M)
            link = re.search(r"^- \*\*Link:\*\* arXiv:(\S+)", body, re.M)
            if not (res and link):
                continue
            aid = link.group(1).strip().rstrip(".")
            path = os.path.join(LIT, "refs", "arxiv",
                                re.sub(r"[^A-Za-z0-9._-]", "_", aid + ".json"))
            if not os.path.exists(path):
                problems.append(where + ": no cached record for " + aid)
                continue
            rec = json.load(io.open(path, encoding="utf-8"))
            hay = (rec.get("abstract", "") + " " + rec.get("comment", "") + " "
                   + rec.get("title", "") + " " + rec.get("journal_ref", ""))
            hay = hay.replace(",", "").replace("\\", "")
            claim = res.group(1)
            nums = re.findall(r"\d+(?:\.\d+)?", claim.replace(",", ""))
            unmatched = []
            for n in nums:
                if n in hay:
                    continue
                # tolerate 20 vs 20.0 and 92.1 vs 92.10
                alt = {n.rstrip("0").rstrip("."), n + ".0", n.split(".")[0]}
                if any(a and a in hay for a in alt):
                    continue
                unmatched.append(n)
            if unmatched:
                review.append(where + ": numbers not found verbatim in the cached record: "
                              + ", ".join(unmatched))

    for where, ref in all_refs:
        if ref not in defined:
            problems.append(where + ": dangling cross-reference [" + ref + "]")

    total = sum(len(v) for v in corpus.values())
    print("entries checked: " + str(total)
          + "  (" + ", ".join(fn.split("-")[0] + "=" + str(len(corpus[fn])) for fn in TOPICS) + ")")
    print("")
    if problems:
        print("PROBLEMS (" + str(len(problems)) + ") — must fix:")
        for p in problems:
            print("  - " + p)
    else:
        print("PROBLEMS: none. Template complete, all entries verified, no dangling handles.")
    print("")
    print("FOR MANUAL REVIEW (" + str(len(review)) + ") — numbers not verbatim in the cached record:")
    for r in review:
        print("  ? " + r)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
