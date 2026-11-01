"""Stage 2 · Propose: edits from deterministic rules and from the Meta LLM.

Rule-based edits come straight out of the Analyze report and need no model:

- add:    promote an inline helper the player keeps writing itself (defined in
          >= `promote_min_episodes` episodes, or called >= `promote_min_calls`
          times) into a skill, so later players get it for free.
- delete: drop a skill that has never been called in >= `delete_min_episodes`
          evaluated episodes carrying that exact source.
- merge:  collapse skills whose bodies are identical up to the name.

The Meta LLM (optional; on for this run) sees the report and the full current
harness and returns semantic edits on skills, prompts and steps. Every edit is
tagged with its source, so the report can split rule-based from Meta LLM edits.
Nothing is applied here: Validate decides what survives.
"""

from __future__ import annotations

import ast
import json
import re
from typing import Any

from evolve.edits import RESERVED_NAMES
from evolve.harness import API_DOC, CORE_PROMPTS, Harness
from evolve.sandbox import ALLOWED_IMPORTS, function_key


# ---------------------------------------------------------------------------
# Rule-based
# ---------------------------------------------------------------------------


def _with_docstring(source: str, note: str) -> str:
    tree = ast.parse(source)
    node = tree.body[0]
    if isinstance(node, ast.FunctionDef) and ast.get_docstring(node) is None:
        node.body.insert(0, ast.Expr(ast.Constant(note)))
    return ast.unparse(ast.fix_missing_locations(tree))


def rule_edits(report: dict[str, Any], parent: Harness, cfg: dict[str, Any]) -> list[dict[str, Any]]:
    rules = cfg["rules"]
    edits: list[dict[str, Any]] = []

    promoted = 0
    for helper in report["inline_helpers"]:
        if promoted >= int(rules["max_promotions"]):
            break
        often = (
            helper["episodes_defined"] >= int(rules["promote_min_episodes"])
            or helper["calls"] >= int(rules["promote_min_calls"])
        )
        name = helper["name"]
        if not often or name in parent.skills or name in RESERVED_NAMES:
            continue
        names = [name] + helper["other_names"]
        edits.append(
            {
                "op": "add",
                "target": "skill",
                "name": name,
                "content": _with_docstring(
                    helper["source"],
                    f"Promoted from the player's own inline helper "
                    f"(defined in {helper['episodes_defined']} episodes, called "
                    f"{helper['calls']} times).",
                ),
                "rationale": (
                    f"inline helper defined in {helper['episodes_defined']} episode(s), "
                    f"{helper['turns_defined']} turn(s), called {helper['calls']} times"
                ),
                "source": "rule",
                # Validate replays the parent's episodes with these inline
                # definitions removed, so the promoted skill is what runs.
                "replay_strip": [[n, helper["key"]] for n in names],
                "replay_rename": {other: name for other in helper["other_names"]},
            }
        )
        promoted += 1

    for name, stats in report["skill_stats"].items():
        if (
            stats["calls"] == 0
            and stats["lifetime_calls"] == 0
            and stats["lifetime_episodes"] >= int(rules["delete_min_episodes"])
        ):
            edits.append(
                {
                    "op": "delete",
                    "target": "skill",
                    "name": name,
                    "rationale": f"never called in {stats['lifetime_episodes']} evaluated episodes",
                    "source": "rule",
                }
            )

    by_key: dict[str, list[str]] = {}
    for name, source in parent.skills.items():
        try:
            node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef))
        except (SyntaxError, StopIteration):
            continue
        by_key.setdefault(function_key(node), []).append(name)
    for names in by_key.values():
        if len(names) < 2:
            continue
        keep = max(names, key=lambda n: report["skill_stats"].get(n, {}).get("calls", 0))
        edits.append(
            {
                "op": "merge",
                "target": "skill",
                "names": sorted(names),
                "name": keep,
                "content": parent.skills[keep],
                "rationale": f"identical bodies: {', '.join(sorted(names))}",
                "source": "rule",
                "replay_rename": {n: keep for n in names if n != keep},
            }
        )
    return edits


# ---------------------------------------------------------------------------
# Meta LLM
# ---------------------------------------------------------------------------

META_SYSTEM = """\
You improve the harness that a game-playing language model (the "player") uses
on Level 1 of an ARC-AGI-3 game. You never play. You read evidence from the
player's last episodes and propose edits to its harness.

HOW THE PLAYER WORKS
Each turn the player gets a system prompt rendered from its harness, plus the
current observation, the result of its last code cell, recent actions and its
notes. It replies with a short line of reasoning per step of the turn
procedure, then one Python code block, which runs in a sandbox and acts on the
game through action(). At most {cap} actions per turn; {max_actions} actions
per episode.

THE HARNESS (what you may edit)
- prompts: named texts placed in the system prompt. "system" (the rules) and
  "format" (the reply format) are core: you may edit them but not delete them.
  Other prompts are rendered between them in order.
- steps: the numbered turn procedure (between {min_steps} and {max_steps} steps).
  "{{cap}}" inside a step is replaced by the per-turn action cap.
- skills: Python functions preloaded into the sandbox and documented to the
  player by signature + docstring. A skill may call the sandbox API (including
  action(), which counts against the player's caps) and other skills.

The sandbox API is fixed and NOT editable:
{api}

SANDBOX RULES (a skill that breaks them is rejected)
- imports only from: {imports}; no attribute starting with "_"; no open, exec,
  eval, getattr, setattr, globals, randomness, time, or bare `except:`.
- Exactly one top-level function per skill, named as the skill, with a
  docstring. At most {max_skill_lines} lines.

SCORE (what you are optimising)
Per episode: a Level-1 clear scores 0.5 + 0.5 * min(1, 22 / actions)^2.
Otherwise 0.5 * progress, where progress in [0, 1] is a graded measure of how
close the episode came to completing the level (computed by the evaluator; you
see its value per episode). A version is accepted only if its mean score over 3
episodes beats its parent's and its worst episode is at most {delta} below the
parent's worst.

VALIDATION (edits that fail are dropped)
- every skill you add, edit or merge needs a "test": a short Python snippet
  that calls it and asserts something true. It runs in the sandbox on real
  recorded game states (start, middle, late).
- your edits are replayed against the recorded episodes; a skill that raises
  where the old one did not, or a merge that changes behaviour, is dropped.
- prompts must stay under {max_prompt_chars} characters each and the whole
  system prompt under {max_system_chars}; steps under {max_step_chars} each.

EDIT FORMAT
Reply with one JSON object and nothing else:
{{"analysis": "<2-4 sentences: what is limiting the score, citing evidence>",
 "edits": [<at most {max_edits} edits>]}}
Each edit is one of:
 {{"op":"add","target":"skill","name":N,"content":SOURCE,"test":CODE,"rationale":R}}
 {{"op":"edit","target":"skill","name":N,"content":SOURCE,"test":CODE,"rationale":R}}
 {{"op":"delete","target":"skill","name":N,"rationale":R}}
 {{"op":"merge","target":"skill","names":[A,B],"name":N,"content":SOURCE,"test":CODE,"rationale":R}}
 {{"op":"add","target":"prompt","name":KEY,"content":TEXT,"rationale":R}}
 {{"op":"edit","target":"prompt","name":KEY,"content":FULL_NEW_TEXT,"rationale":R}}
 {{"op":"delete","target":"prompt","name":KEY,"rationale":R}}
 {{"op":"add","target":"step","index":I,"content":TEXT,"rationale":R}}   (inserted before current step I; use n+1 to append)
 {{"op":"edit","target":"step","index":I,"content":TEXT,"rationale":R}}
 {{"op":"delete","target":"step","index":I,"rationale":R}}
 {{"op":"merge","target":"step","indices":[I,J],"content":TEXT,"rationale":R}}
Step indices always refer to the CURRENT numbering shown below, even if an
earlier edit in your list adds or removes a step.

GUIDANCE
- Base every edit on evidence in the analysis. Say which evidence in "rationale".
- Fewer, well-aimed edits beat many: each round is judged as a whole.
- Do not re-propose an edit that was already tried and rejected unless you
  change it in a way that addresses why it failed.
- Facts about this game that the evidence establishes (what an action does,
  where things are) are fair to write down; guesses presented as facts are not.
"""


def _compact_report(report: dict[str, Any]) -> dict[str, Any]:
    compact = dict(report)
    helpers = []
    for helper in report["inline_helpers"][:6]:
        item = {k: v for k, v in helper.items() if k != "key"}
        item["source"] = item["source"][:1500]
        helpers.append(item)
    compact["inline_helpers"] = helpers
    compact["skill_stats"] = {
        name: {k: v for k, v in stats.items() if k != "source_hash"}
        for name, stats in report["skill_stats"].items()
    }
    return compact


def meta_messages(report: dict[str, Any], parent: Harness, cfg: dict[str, Any]) -> list[dict[str, str]]:
    budget, limits, meta = cfg["budget"], cfg["validate"], cfg["meta"]
    system = META_SYSTEM.format(
        cap=budget["actions_per_turn"],
        max_actions=budget["max_actions"],
        min_steps=limits["min_steps"],
        max_steps=limits["max_steps"],
        api=API_DOC.format(cap=budget["actions_per_turn"]),
        imports=", ".join(sorted(ALLOWED_IMPORTS)),
        max_skill_lines=limits["max_skill_lines"],
        delta=cfg["gate"]["delta"],
        max_prompt_chars=limits["max_prompt_chars"],
        max_system_chars=limits["max_system_chars"],
        max_step_chars=limits["max_step_chars"],
        max_edits=meta["max_edits"],
    )
    steps = "\n".join(f"{i}. {s}" for i, s in enumerate(parent.steps, start=1))
    prompts = "\n\n".join(
        f'--- prompt "{key}"{" (core)" if key in CORE_PROMPTS else ""} ---\n{text}'
        for key, text in parent.prompts.items()
    )
    skills = "\n\n".join(
        f"--- skill {name} ---\n{source.rstrip()}" for name, source in sorted(parent.skills.items())
    )
    user = (
        f"CURRENT HARNESS {parent.version}\n\n"
        f"PROMPTS\n{prompts}\n\nSTEPS\n{steps}\n\nSKILLS\n{skills or '(none)'}\n\n"
        f"ANALYSIS OF {parent.version}'s EPISODES (JSON)\n"
        f"{json.dumps(_compact_report(report), indent=1, ensure_ascii=False)}\n\n"
        "Propose your edits now. JSON only."
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def parse_meta_reply(text: str) -> tuple[str, list[Any]]:
    """(analysis, raw edits) from the Meta LLM's reply. Raises ValueError."""
    cleaned = re.sub(r"<think>.*?</think>", "", text or "", flags=re.DOTALL).strip()
    fenced = re.findall(r"```(?:json)?\s*\n(.*?)```", cleaned, flags=re.DOTALL)
    candidates = fenced + [cleaned]
    for candidate in candidates:
        start, end = candidate.find("{"), candidate.rfind("}")
        if start < 0 or end <= start:
            continue
        try:
            payload = json.loads(candidate[start : end + 1])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and isinstance(payload.get("edits"), list):
            return str(payload.get("analysis", "")), payload["edits"]
    raise ValueError("no JSON object with an 'edits' list in the Meta LLM reply")


def meta_edits(
    report: dict[str, Any], parent: Harness, cfg: dict[str, Any], client: Any,
    feedback: str | None = None,
) -> dict[str, Any]:
    messages = meta_messages(report, parent, cfg)
    if feedback:
        messages[-1]["content"] += f"\n\nFEEDBACK ON YOUR PREVIOUS ATTEMPT THIS ROUND\n{feedback}"
    response = client.complete(messages, max_tokens=int(cfg["meta"]["max_tokens"]))
    out: dict[str, Any] = {
        "reply": response.text,
        "tokens_in": response.tokens_in,
        "tokens_out": response.tokens_out,
        "finish_reason": response.raw_finish_reason,
        "prompt_chars": sum(len(m["content"]) for m in messages),
    }
    try:
        analysis, edits = parse_meta_reply(response.text)
    except ValueError as error:
        out.update(analysis="", edits=[], parse_error=str(error))
        return out
    cap = int(cfg["meta"]["max_edits"])
    out["analysis"] = analysis
    out["edits"] = []
    out["over_cap"] = []
    for index, edit in enumerate(edits):
        tagged = dict(edit) if isinstance(edit, dict) else {"raw": edit}
        tagged["source"] = "meta"
        (out["edits"] if index < cap else out["over_cap"]).append(tagged)
    return out
