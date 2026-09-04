# Literature corpus — self-evolving harnesses, teacher–student training, and non-parametric capability gain

Built for [issue #6](https://github.com/Paier05/Final-Year-Project/issues/6). This is the
citation-verified evidence base for the FYP's literature-review chapter: 89 full-template entries
plus 25 one-line adjacent finds, organised so it can be written up directly.

**If you read three things:** `synthesis.md` §3 (where the literature actually conflicts),
`synthesis.md` §4.3 and §5 (what the 2026 ARC-AGI-3 results do to this project's framing), and
`taxonomy.md`'s empty cells (where the gap is).

**Headline finding.** The internal briefing notes describe an ARC-AGI-3 world where frontier systems
score ~0.5% and the best preview agent managed ~12.6%. That was true in March 2026 and is not true
now: frozen-weight harness agents reported **93.3%** ([Twin]) and **100.00 RHAE across all 183 public
levels** ([Tycho]) by August 2026 — while two other papers argue the public set is saturated and
cannot discriminate intelligent behaviour from trivial heuristics ([WMAblation],
[BenchmarkValidity]). The project's question has to move to the private set, to the no-internet
constraint, and to small models.

---

## Files

| File | What is in it |
|---|---|
| `topic1-harness.md` | **31 entries.** Harness engineering and self-modifying scaffolds: the Gödel-machine lineage, scaffold/prompt optimisation, tool/skill/experience accumulation, harness-vs-model ablation studies, failure modes. |
| `topic2-teacher-student.md` | **27 entries.** Proposer–solver structures: asymmetric self-play, learning-progress teachers, unsupervised environment design, open-endedness, the 2025–26 LLM self-play line, and its collapse literature. |
| `topic3-frozen-weights.md` | **31 entries.** Capability gain with frozen weights, each classified new-capability / elicitation / unclear; includes a clearly separated test-time-training sub-bucket where weights *do* change. |
| `taxonomy.md` | The filled two-axis table (what is optimised × where the signal comes from), with every entry placed, crowded cells explained and **empty cells discussed** — the gap falls out of these. |
| `synthesis.md` | Cross-topic analysis: taxonomy summary, 5 lineages, 3 disagreements, ARC-AGI-3 transfer per topic, the gap statement, and 18 evaluation-design notes. |
| `adjacent.md` | 25 relevant-but-out-of-scope finds, one line each, with the reason for exclusion. |
| `search-log.md` | Queries run, databases covered, dead ends, and **seven stated limitations** of this search. |
| `refs.bib` | 120 deduplicated entries, machine-generated from the cached records. |
| `refs/` | Cached source records — `arxiv/` (119 JSON), `s2/` (4 Semantic Scholar), `web/` (4 pages). The evidence base for every claim. |
| `tools/fetch.py` | Retrieval, caching and BibTeX generation. |
| `tools/checkbib.py` | Structural validator for `refs.bib`. |

## Coverage against the issue's acceptance criteria

| Criterion | Required | Delivered | Status |
|---|---|---|---|
| Topic 1 verified papers | ≥10, target ~20 | **31** | met |
| Topic 2 verified papers | ≥10, target ~20 | **27** | met |
| Topic 3 verified papers | ≥10, target ~20 | **31** | met |
| Full template, no blank fields | all entries | 89/89 | met |
| `Verified: yes` or explicit flag | all entries | 89/89 `yes` — none flagged | met |
| `refs.bib` compiles, no duplicates | — | 120 entries, 120 unique keys, validator clean | met (see caveat below) |
| Taxonomy filled, empty cells discussed | — | `taxonomy.md`, 6 empty-cell findings E1–E6 | met |
| `synthesis.md` has all six sections | — | §1–§6 present, plus §7 on chapter structure | met |
| `search-log.md` records queries/sources/dead ends | — | plus 7 stated limitations | met |
| Every Topic 3 entry classifies the gain | all | 31/31 | met |

**Caveat on "compiles clean".** No LaTeX toolchain exists in this environment, so `refs.bib` is
validated *structurally* by `tools/checkbib.py` — balanced braces, unique keys, well-formed headers,
required fields present, and no unescaped BibTeX specials. Run it with:

```
python literature/tools/checkbib.py literature/refs.bib
```

It should print `OK`. Please run a real `bibtex`/`biber` pass once the dissertation template exists.

## Topic 3 gain-type distribution

The elicitation-vs-acquisition classification required by the issue, tallied across all 31 entries:

| Classification | Count | Notes |
|---|---|---|
| (b) elicitation | 15 | The default finding. Includes the two strongest critical papers, [RLVR-Elicitation] and [ReasoningWithSampling]. |
| n/a — TTT sub-bucket or measurement study | 9 | Three entries update weights ([TTT-FewShot], [CompressARC], [TRM]); six are benchmarks or limitation studies. |
| (a) new capability | 4 | [AlgorithmDistillation] (model level), [AdA] (test-time, bought with prior training), [Twin] and [Tycho] (**system** level, model explicitly unchanged). |
| (c) unclear | 3 | [s1], [Self-Refine], [ExecWM] — each because the paper omits the control that would separate (a) from (b). |

The model/system distinction is argued in `synthesis.md` §3.1 rather than assumed; it is the reason
[Twin] can be (a) while its underlying model gains nothing.

## Benchmark and primary sources

These are cited in the review's background section rather than being part of the three topics. All
verified and cached; all in `refs.bib`.

- **On the Measure of Intelligence** — Chollet, 2019 — arXiv:1911.01547. Fluid intelligence,
  skill-acquisition efficiency and Core Knowledge priors: the framework the whole series rests on.
- **ARC-AGI-2: A New Challenge for Frontier AI Reasoning Systems** — 2025 — arXiv:2505.11831.
- **ARC-AGI-3: A New Challenge for Frontier Agentic Intelligence** — ARC Prize Foundation, 2026 —
  arXiv:2603.24621. The benchmark paper: interactive design, efficiency scoring against human action
  baselines, difficulty calibration; states that humans solve 100% of environments while frontier
  systems scored below 1% as of March 2026.
- **ARC Prize 2025: Technical Report** — arXiv:2601.10904. Written up as a full Topic 3 entry
  ([ARCPrize2025]) because its refinement-loop framing and contamination analysis are load-bearing.
- **ARC Prize 2026 competition page** — `refs/web/arcprize-competition-2026.txt` `[non-archival]`.
  Source of the evaluation constraints: Kaggle submission, **no internet access during evaluation**,
  mandatory open-sourcing for prize eligibility, $850K track total.
- **ARC-AGI-3 benchmark page** and **30-Day Preview learnings** — `refs/web/` `[non-archival]`.

## How to use this corpus

The review chapter structure recommended in the issue (2.1 scope → 2.2 background → 2.3 taxonomy by
locus of change → 2.4 learning signals → 2.5 failure modes → 2.6 synthesis and gap) is sound and this
corpus is organised to serve it; `synthesis.md` §7 argues for two evidence-driven adjustments to it.

- **§2.1 Scope and method** → `search-log.md` §1, §3, §4 and §7 (protocol, databases, limitations).
- **§2.2 Background** → the benchmark sources above, plus lineage L5 in `synthesis.md` §2. **Do not
  reuse the briefing notes' SOTA figures.**
- **§2.3.1 Improving the weights** → the `weights` row of `taxonomy.md`.
- **§2.3.2 Improving the task distribution** → `topic2-teacher-student.md`.
- **§2.3.3 Improving the harness** → `topic1-harness.md`.
- **§2.3.4 Gains at inference** → `topic3-frozen-weights.md`.
- **§2.4 Learning signals and verification** → the column axis of `taxonomy.md`; the verifier-gap
  failure mode is [BlindCurator], [LimitsResampling] and [VHG].
- **§2.5 Failure modes** → `topic1-harness.md` §5 and `topic2-teacher-student.md` §4.
- **§2.6 Synthesis and gap** → `synthesis.md` §5, grounded in `taxonomy.md` E1–E6.

## Three things to check before submission

1. **Confirm the ARC-AGI-3 set sizes.** The briefing says 135 environments at ~1:5 public:private;
   the papers describe 25 public games (183 levels) and a 55-game private evaluation. Marked
   `[unverified]` in `synthesis.md` §4 — resolve against `docs.arcprize.org`.
2. **Re-check the interactive state of the art.** It moved by two orders of magnitude between March
   and August 2026. Anything here is a September 2026 snapshot.
3. **Verify quoted figures against full PDFs** for any number that carries argumentative weight.
   Numbers here come from cached abstracts and records (limitation L6 in `search-log.md`); where an
   abstract reported no headline figure, the entry says so instead of supplying one.

---

*Corpus assembled 2026-09-04. Every citation was retrieved from a live record and cached under
`refs/` before being written up; no citation in this corpus was written from memory of a title.*
