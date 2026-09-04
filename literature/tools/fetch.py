#!/usr/bin/env python3
"""Citation-verification helper for the issue #6 literature survey.

Every paper in literature/*.md is verified with this script: it retrieves the
canonical record (arXiv API, Semantic Scholar Graph API, or a raw page) and
caches it under literature/refs/ so the write-up can be re-checked later
without re-fetching. Nothing in the corpus is written from memory of a title.

Usage:
  python fetch.py arxiv 2505.03335 2507.14172 ...   # fetch + cache + print records
  python fetch.py find "exact-ish title words"      # arXiv title search
  python fetch.py search "all: keywords" [n]        # arXiv full search
  python fetch.py s2 arXiv:2505.03335               # Semantic Scholar record
  python fetch.py refs arXiv:2505.03335 [n]         # works this paper cites
  python fetch.py cites arXiv:2505.03335 [n]        # works citing this paper
  python fetch.py s2find "title or keywords" [n]    # Semantic Scholar search
  python fetch.py web <url> <cache-name>            # cache a web page as text
"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "refs")
UA = {"User-Agent": "FYP-lit-survey/1.0 (academic literature review; contact via GitHub Paier05)"}
ATOM = "{http://www.w3.org/2005/Atom}"
ARX = "{http://arxiv.org/schemas/atom}"


_LAST = {}


def _throttle(url, gap=10.0):
    """arXiv asks for >=3s between API hits; S2 rate-limits anonymous callers too."""
    host = urllib.parse.urlparse(url).netloc
    now = time.time()
    wait = gap - (now - _LAST.get(host, 0.0))
    if wait > 0:
        time.sleep(wait)
    _LAST[host] = time.time()


def get(url, tries=4, pause=8.0):
    for attempt in range(tries):
        _throttle(url)
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as exc:  # noqa: BLE001 - report and retry
            if attempt == tries - 1:
                print("!! FETCH FAILED " + url + "\n   " + str(exc))
                return None
            time.sleep(pause * (attempt + 1))
    return None


def cache(subdir, name, data):
    d = os.path.join(ROOT, subdir)
    os.makedirs(d, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", name)
    path = os.path.join(d, safe)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(data if isinstance(data, str) else json.dumps(data, indent=1, ensure_ascii=False))
    return path


def parse_atom(xml_text):
    feed = ET.fromstring(xml_text)
    out = []
    for e in feed.findall(ATOM + "entry"):
        def txt(tag):
            node = e.find(ATOM + tag)
            return " ".join(node.text.split()) if node is not None and node.text else ""

        def opt(ns, tag):
            node = e.find(ns + tag)
            return " ".join(node.text.split()) if node is not None and node.text else ""

        rec = {
            "id": txt("id"),
            "arxiv_id": txt("id").rsplit("/abs/", 1)[-1],
            "title": txt("title"),
            "abstract": txt("summary"),
            "published": txt("published"),
            "updated": txt("updated"),
            "authors": [" ".join(a.find(ATOM + "name").text.split())
                        for a in e.findall(ATOM + "author")
                        if a.find(ATOM + "name") is not None],
            "primary_category": (e.find(ARX + "primary_category").get("term")
                                 if e.find(ARX + "primary_category") is not None else ""),
            "categories": [c.get("term") for c in e.findall(ATOM + "category")],
            "doi": opt(ARX, "doi"),
            "journal_ref": opt(ARX, "journal_ref"),
            "comment": opt(ARX, "comment"),
        }
        out.append(rec)
    return out


def show(rec, abstract_chars=900):
    print("-" * 78)
    print("ID       : " + rec.get("arxiv_id", ""))
    print("TITLE    : " + rec.get("title", ""))
    au = rec.get("authors", [])
    tail = " et al." if len(au) > 8 else ""
    print("AUTHORS  : " + ", ".join(au[:8]) + tail + "  (n=" + str(len(au)) + ")")
    print("DATE     : published " + rec.get("published", "")[:10]
          + "  updated " + rec.get("updated", "")[:10])
    if rec.get("journal_ref"):
        print("JOURNAL  : " + rec["journal_ref"])
    if rec.get("doi"):
        print("DOI      : " + rec["doi"])
    if rec.get("comment"):
        print("COMMENT  : " + rec["comment"][:220])
    print("CATS     : " + ",".join(rec.get("categories", [])))
    ab = rec.get("abstract", "")
    more = "...[truncated]" if len(ab) > abstract_chars else ""
    print("ABSTRACT : " + ab[:abstract_chars] + more)


def cmd_arxiv(ids, quiet=False):
    joined = ",".join(ids)
    url = "https://export.arxiv.org/api/query?max_results=100&id_list=" + urllib.parse.quote(joined)
    xml_text = get(url)
    if xml_text is None:
        return
    recs = parse_atom(xml_text)
    found = set()
    for rec in recs:
        base = rec["arxiv_id"].split("v")[0]
        found.add(base)
        cache("arxiv", base + ".json", rec)
        if quiet:
            print("ok  " + base.ljust(12) + " " + rec.get("published", "")[:7]
                  + "  " + rec.get("title", "")[:88])
        else:
            show(rec)
    for want in ids:
        if want.split("v")[0] not in found:
            print("-" * 78)
            print("!! UNRESOLVED arXiv ID: " + want + "  (no record returned)")


def cmd_search(query, n=8, field=None):
    q = (field + ":" + query) if field else query
    url = ("https://export.arxiv.org/api/query?search_query=" + urllib.parse.quote(q)
           + "&start=0&max_results=" + str(n) + "&sortBy=relevance")
    xml_text = get(url)
    if xml_text is None:
        return
    recs = parse_atom(xml_text)
    if not recs:
        print("!! NO RESULTS for: " + q)
    for rec in recs:
        print(rec["arxiv_id"].ljust(18) + " " + rec["published"][:7] + "  " + rec["title"][:100])


S2 = "https://api.semanticscholar.org/graph/v1/paper/"
S2F = "title,year,venue,publicationVenue,externalIds,citationCount,authors,abstract,publicationTypes"


def cmd_s2(pid):
    url = S2 + urllib.parse.quote(pid, safe=":/") + "?fields=" + S2F
    raw = get(url)
    if raw is None:
        return
    try:
        rec = json.loads(raw)
    except json.JSONDecodeError:
        print("!! non-JSON reply: " + raw[:200])
        return
    cache("s2", pid.replace(":", "_") + ".json", rec)
    print("-" * 78)
    print("S2 TITLE : " + str(rec.get("title")))
    print("YEAR/VEN : " + str(rec.get("year")) + " | " + str(rec.get("venue"))
          + " | types=" + str(rec.get("publicationTypes")))
    print("CITED BY : " + str(rec.get("citationCount")))
    print("IDS      : " + str(rec.get("externalIds")))
    au = [a.get("name") for a in (rec.get("authors") or [])]
    print("AUTHORS  : " + ", ".join([str(x) for x in au[:10]]) + "  (n=" + str(len(au)) + ")")


def cmd_edges(pid, direction, n=30):
    fields = "title,year,venue,externalIds,citationCount"
    url = (S2 + urllib.parse.quote(pid, safe=":/") + "/" + direction
           + "?fields=" + fields + "&limit=" + str(n))
    raw = get(url)
    if raw is None:
        return
    try:
        data = json.loads(raw).get("data", [])
    except json.JSONDecodeError:
        print("!! non-JSON reply: " + raw[:200])
        return
    key = "citedPaper" if direction == "references" else "citingPaper"
    rows = [(item.get(key) or {}) for item in data]
    rows.sort(key=lambda p: -(p.get("citationCount") or 0))
    cache("s2", pid.replace(":", "_") + "." + direction + ".json", rows)
    for p in rows:
        ax = (p.get("externalIds") or {}).get("ArXiv", "") or ""
        cc = str(p.get("citationCount", 0)).rjust(5)
        print("[" + cc + "] " + str(p.get("year")) + " " + ax.ljust(12) + " " + str(p.get("title"))[:88])


def cmd_s2find(query, n=10):
    url = ("https://api.semanticscholar.org/graph/v1/paper/search?query="
           + urllib.parse.quote(query) + "&limit=" + str(n)
           + "&fields=title,year,venue,externalIds,citationCount")
    raw = get(url)
    if raw is None:
        return
    try:
        data = json.loads(raw).get("data", [])
    except json.JSONDecodeError:
        print("!! non-JSON reply: " + raw[:200])
        return
    for p in data:
        ax = (p.get("externalIds") or {}).get("ArXiv", "") or ""
        cc = str(p.get("citationCount", 0)).rjust(5)
        print("[" + cc + "] " + str(p.get("year")) + " " + ax.ljust(12) + " "
              + str(p.get("venue"))[:24].ljust(24) + " " + str(p.get("title"))[:80])


def cmd_web(url, name):
    raw = get(url)
    if raw is None:
        return
    text = re.sub(r"(?is)<(script|style|nav|footer|svg)[^>]*>.*?</\1>", " ", raw)
    text = re.sub(r"(?s)<!--.*?-->", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    for a, b in [("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&#39;", "'"),
                 ("&quot;", '"'), ("&nbsp;", " "), ("&mdash;", "-"), ("&rsquo;", "'")]:
        text = text.replace(a, b)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    header = "SOURCE: " + url + "\nFETCHED: " + time.strftime("%Y-%m-%d") + "\n\n"
    path = cache("web", name + ".txt", header + text.strip())
    print("cached -> " + path + "  (" + str(len(text)) + " chars)")
    print(text.strip()[:3000])


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    if cmd == "arxiv":
        cmd_arxiv(sys.argv[2:])
    elif cmd == "arxivq":
        cmd_arxiv(sys.argv[2:], quiet=True)
    elif cmd == "cat":
        # re-read cached records (no network) when writing up entries
        for i in sys.argv[2:]:
            p = os.path.join(ROOT, "arxiv", re.sub(r"[^A-Za-z0-9._-]", "_", i + ".json"))
            if not os.path.exists(p):
                print("!! NOT CACHED: " + i)
                continue
            with open(p, encoding="utf-8") as fh:
                show(json.load(fh), abstract_chars=4000)
    elif cmd == "find":
        cmd_search('"' + sys.argv[2] + '"', int(sys.argv[3]) if len(sys.argv) > 3 else 8, field="ti")
    elif cmd == "search":
        cmd_search(sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 8)
    elif cmd == "msearch":
        # multiple queries in one process so the arXiv throttle actually applies
        for q in sys.argv[3:]:
            print("### " + q)
            cmd_search(q, int(sys.argv[2]))
            print()
    elif cmd == "ms2find":
        for q in sys.argv[3:]:
            print("### " + q)
            cmd_s2find(q, int(sys.argv[2]))
            print()
    elif cmd == "s2":
        cmd_s2(sys.argv[2])
    elif cmd == "refs":
        cmd_edges(sys.argv[2], "references", int(sys.argv[3]) if len(sys.argv) > 3 else 30)
    elif cmd == "cites":
        cmd_edges(sys.argv[2], "citations", int(sys.argv[3]) if len(sys.argv) > 3 else 30)
    elif cmd == "s2find":
        cmd_s2find(sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 10)
    elif cmd == "web":
        cmd_web(sys.argv[2], sys.argv[3])
    else:
        print(__doc__)
