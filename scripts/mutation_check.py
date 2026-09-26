#!/usr/bin/env python3
"""Mutation kill check: prove the Direct Mode suite pins each load-bearing
guard, not merely that the code passes today.

For each mutation the repository is copied to a scratch directory with ONE
guard in the contract mechanically broken, and the whole Direct Mode suite
runs against the copy. A mutation is KILLED when the suite fails and SURVIVED
when it passes (an unpinned guard). The run starts with an accept-control:
the unmodified copy must pass, or every kill would be vacuous.

Anchors are code TEXT, never line numbers. An anchor that is not found
exactly once is reported as ANCHOR MISSING - the guard moved or was deleted,
which is its own finding.

Run:  python scripts/mutation_check.py              (full sweep)
      python scripts/mutation_check.py --anchors    (anchor check only)
      python scripts/mutation_check.py --only gate  (names containing "gate";
                                                     separate several with |)
      python scripts/mutation_check.py --jobs 3     (three scratch copies)
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys
import tempfile
import threading

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONTRACT = "contracts/succour.py"
Q = '"'


def off(condition: str) -> tuple:
    """(anchor, replacement) turning one `if` line into `if False:`."""
    head = condition[:len(condition) - len(condition.lstrip())]
    keyword = condition.lstrip().split(" ", 1)[0]
    return (condition + "\n", head + keyword + " False:\n")


def m(name: str, anchor: str, replacement: str = None) -> tuple:
    if replacement is None:
        anchor, replacement = off(anchor)
    return (name, anchor, replacement)


MUTATIONS = [
    # -- retrieval ------------------------------------------------------------------------
    m("a redirect is read as a retrieved source", "    if 300 <= code < 400:"),
    m("a 404 is a generic failure", "    if code in (404, 410):"),
    m("a forbidden source is a generic failure", "    if code in (401, 403):"),
    m("a server error is a generic failure", "    if code >= 500:"),
    # an empty body with its guard removed still decodes to empty text and meets the
    # "no visible text" branch: the same INVALID_CONTENT record - an equivalent mutant
    m("a binary content type is read",
      '    if content_type != "" and not any(t in content_type for t in TEXT_TYPES):'),
    m("an undecodable body is read",
      '    if text is None:\n        return (_empty_source(INVALID_CONTENT',
      '    if False:\n        return (_empty_source(INVALID_CONTENT'),
    m("a page with no visible text is read", '    if normalized == "":'),
    m("scripts and styles count as text",
      "    if html:\n        text = _strip_markup(text)\n", ""),
    m("an oversized source is not marked partial",
      "    truncated = len(body) > BODY_BYTES_CAP or len(normalized) > TEXT_CAP\n",
      "    truncated = False\n"),
    # -- what code decides before any model --------------------------------------------------
    m("an unreadable source is judged anyway",
      "    if source[\"status\"] not in READABLE:\n        return \"SOURCE_\" + source[\"status\"]",
      "    if False:\n        return \"SOURCE_\" + source[\"status\"]"),
    m("a source addressing the verifier is judged anyway", "    if len(markers) > 0:"),
    m("text in the visible body is not scanned", "    if body_hit:"),
    m("markup and attributes are not scanned",
      '    if not body_hit and _evaluator_hits(_scan_form(raw_text)):'),
    m("the title is not scanned",
      '    if _evaluator_hits(_scan_form(source["title"])):'),
    m("a matching source type needs no quote",
      "        return state != MATCHES or len(quotes) > 0\n", "        return True\n"),
    m("a component finding needs no quote",
      "    if state in (EXPLICIT, IMPLIED, CONTRADICTED):\n        return len(quotes) > 0\n",
      "    if state in (EXPLICIT, IMPLIED, CONTRADICTED):\n        return True\n"),
    m("a stated date need not appear in its quote",
      "            return len(quotes) > 0 and _date_in_quotes(date, quotes)\n",
      "            return len(quotes) > 0\n"),
    m("a date's month is not checked",
      'any(t in words for t in _month_tokens(month)) and any(',
      'True and any('),
    m("a date's day is not checked",
      '                t in words for t in _day_tokens(day)):\n',
      '                True for t in _day_tokens(day)):\n'),
    m("a non-freshness finding may carry a date",
      '    if date != "":\n        return False\n', ""),
    # -- the derivation ------------------------------------------------------------------------
    m("an unusable model answer is judged anyway",
      "    if payload[\"panel_state\"] != PANEL_ASSESSED:\n        return (INCONCLUSIVE, INCONCLUSIVE, \"MODEL_OUTPUT_INVALID\")",
      "    if False:\n        return (INCONCLUSIVE, INCONCLUSIVE, \"MODEL_OUTPUT_INVALID\")"),
    m("the wrong kind of source is judged anyway", "    if shape == MISMATCH:"),
    m("an unclear source type is judged anyway", "    if shape == UNCLEAR:"),
    m("a contradicted component does not contradict", "    if CONTRADICTED in states:"),
    m("an undated source meets a freshness policy", "    if outcome == UNDATED:"),
    m("stale evidence is current", "    if outcome == STALE:"),
    m("the age limit is off by a day",
      '    if now - stated > policy["max_age_seconds"]:\n',
      '    if now - stated > policy["max_age_seconds"] + 86400:\n'),
    m("a future date vouches for freshness", "    if stated > now + 86400:"),
    m("an unclear component is support", "    if UNCLEAR in states:"),
    m("absent evidence is partial support", "    if all(s == ABSENT for s in states):"),
    m("a missing component is full support", "    if ABSENT in states:"),
    m("implied evidence is direct",
      "    level = DIRECT if all(s == EXPLICIT for s in states) else STRONG\n",
      "    level = DIRECT\n"),
    m("the minimum support level is ignored",
      '    if level == STRONG and ctx["policy"]["minimum_support_level"] == DIRECT:'),
    m("an optional component decides",
      '    return [c["component_id"] for c in ctx["policy"]["components"] if c["required"]]\n',
      '    return [c["component_id"] for c in ctx["policy"]["components"]]\n'),
    # -- audit round -----------------------------------------------------------------------------
    m("a spliced quote is accepted",
      '    return "..." in text or chr(0x2026) in text\n', "    return False\n"),
    m("a STABLE source's raw hash and title are not compared",
      '        keys = keys + ["byte_count", "content_digest", "raw_sha256", "title", "content_type"]\n',
      '        keys = keys + ["byte_count", "content_digest"]\n'),
    m("non-decisive component readings are stored",
      '        decisive = c["reason_code"] in COMPONENT_DECIDED\n', "        decisive = True\n"),
    m("a DYNAMIC source's uncompared record is stored",
      '        if ctx["stability"] == "DYNAMIC":\n            source.update(',
      '        if False:\n            source.update('),
    m("re-verification ignores the open-request limit",
      '        count = self.open_counts.get(str(req.submitted_by))\n        if count is not None and int(count) >= MAX_OPEN_PER_REQUESTER:\n',
      '        count = self.open_counts.get(str(req.submitted_by))\n        if False:\n'),
    m("max_age false passes",
      '    elif not _is_int(policy["max_age_seconds"]) or policy["max_age_seconds"] != 0:',
      '    elif policy["max_age_seconds"] != 0:'),
    m("the marker scan does not remove invisible word-splitters",
      '                   and ch not in (chr(0xFEFF), chr(0xAD), chr(0x200D)))',
      '                   and ch not in (chr(0xFEFF),))'),
    m("numeric entities are not decoded for the scan",
      "    text = _decode_numeric(text)\n    return", "    return"),
    m("tags that split a word are not joined for the scan",
      '    body_hit = _evaluator_hits(_scan_form(panel_text)) or _evaluator_hits(joined)\n',
      '    body_hit = _evaluator_hits(_scan_form(panel_text))\n'),
    m("every required component is compared under a contradiction",
      '    all_compared = reason in COMPONENT_DECIDED and reason != "COMPONENT_CONTRADICTED"\n',
      '    all_compared = reason in COMPONENT_DECIDED\n'),
    m("evidence found is compared when components were not",
      '        "evidence_found": all_compared and any(_collapse(s) == PRESENT\n',
      '        "evidence_found": any(_collapse(s) == PRESENT\n'),
    m("a contradiction keeps readings that are not contradicted",
      '                keep = comp["required"] and f["state"] == CONTRADICTED\n',
      '                keep = True\n'),
    m("a contradicted receipt stores no reading",
      '                keep = comp["required"] and f["state"] == CONTRADICTED\n',
      '                keep = False\n'),
    m("the consequence is not compared",
      '        if mine[key] != theirs[key]:\n            return key + " mine="',
      '        if False:\n            return key + " mine="'),
    m("what each node retrieved is not compared",
      "        difference = _evidence_difference(ctx, own, parsed)\n", '        difference = ""\n'),
    m("a stable source's digest is not compared",
      '        keys = keys + ["byte_count", "content_digest", "raw_sha256", "title", "content_type"]\n',
      '        keys = keys + ["raw_sha256", "title", "content_type"]\n'),
    m("a dynamic source's digest is compared",
      '    if ctx["stability"] == "STABLE":\n        keys = keys',
      '    if True:\n        keys = keys'),
    m("required components are compared after an earlier reason decided",
      '    all_compared = reason in COMPONENT_DECIDED and reason != "COMPONENT_CONTRADICTED"\n',
      '    all_compared = True\n'),
    m("the gate trusts the leader's code reason", '    if p["panel_reason"] != reason:'),
    m("the gate does not re-ground quotes",
      '        if q in seen or _spliced(q["text"]) or not _quote_grounded(q, eligible, texts):\n',
      '        if q in seen or _spliced(q["text"]):\n'),
    m("the gate accepts an inconsistent source record",
      "    if not _valid_source(p[\"source\"]):\n        return None\n", ""),
    m("a model failure is ratified",
      "    if leader_text.startswith(ERROR_LLM):\n        return False\n", ""),
    # -- policies, requests, lifecycle ------------------------------------------------------------
    m("a stale policy version is accepted",
      "        if policy_hash != str(policy.policy_hash):"),
    m("a retired policy takes requests",
      '        if str(policy.status) != POLICY_ACTIVE:\n            self._fail("the policy is retired and',
      '        if False:\n            self._fail("the policy is retired and'),
    m("a non-canonical URL is accepted", "        if canonical != source_url:"),
    m("authority domains are not enforced",
      '        if not _domain_allowed(host, spec["authority_domains"]):'),
    m("a lookalike domain passes",
      '    return any(host == d or host.endswith("." + d) for d in domains)\n',
      '    return any(d in host for d in domains)\n'),
    m("a duplicate request is accepted",
      '        if holder is not None and str(holder) != "":\n            self._fail("duplicate verification: request " + str(holder)\n                       + " already asks',
      '        if False:\n            self._fail("duplicate verification: request " + str(holder)\n                       + " already asks'),
    m("the open-request limit does not hold",
      '        if count is not None and int(count) >= MAX_OPEN_PER_REQUESTER:\n            self._fail("this requester already has "',
      '        if False:\n            self._fail("this requester already has "'),
    m("anyone may verify",
      "        if not self._may_act(req):\n            self._fail(\"only the requester or the policy owner runs a verification\")",
      "        if False:\n            self._fail(\"only the requester or the policy owner runs a verification\")"),
    m("a verification may run after its window",
      '        if _iso_epoch(now) > _iso_epoch(str(req.deadline)):\n            self._fail("the verification window closed',
      '        if False:\n            self._fail("the verification window closed'),
    m("a request may be rechecked twice",
      '        if str(req.status) != REQ_EVALUATED or bool(req.rechecked):',
      '        if str(req.status) != REQ_EVALUATED:'),
    m("a recheck may run after its window",
      "        if _iso_epoch(now) > _iso_epoch(str(req.settle_at)):"),
    m("a request may be finalized inside its recheck window",
      "        if _iso_epoch(now) <= _iso_epoch(str(req.settle_at)):"),
    m("a request may expire before its deadline",
      "        if _iso_epoch(now) <= _iso_epoch(str(req.deadline)):"),
    m("an expired re-verification loses the last final receipt",
      "            req.version = u32(int(req.version) - 1)\n            req.status = REQ_FINALIZED\n",
      "            req.status = REQ_EXPIRED\n"),
    m("a closed request keeps its duplicate key",
      "        if str(self.open_keys.get(key)) == str(req.request_id):"),
    m("a policy id may shadow a built-in subject",
      "    if text.upper() in BUILT_IN_SUBJECTS:"),
    m("applicant text may address the verifier",
      "    if _evaluator_hits(value) or _hidden_hits(value):"),
    m("an IP literal is a host", "    if all_numeric or labels[-1].isdigit():"),
    m("a superseding policy may keep the old version",
      '            if policy["policy_version"] <= self._definition(prior)["policy_version"]:'),
]


def run_suite(workdir: pathlib.Path) -> bool:
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/direct", "-q", "-x", "-p", "no:cacheprovider",
         "--no-header"], cwd=workdir, capture_output=True, text=True)
    return completed.returncode == 0


def check_anchors(source: str) -> int:
    missing = 0
    for name, old, _new in MUTATIONS:
        hits = source.count(old)
        if hits != 1:
            print(f"ANCHOR MISSING ({hits} hits): {name}")
            missing += 1
    return missing


def copy_repo(scratch: pathlib.Path, index: int) -> pathlib.Path:
    work = scratch / ("repo%d" % index)
    shutil.copytree(ROOT, work, ignore=shutil.ignore_patterns(
        ".git", "__pycache__", ".pytest_cache", "deploy", "artifacts", ".data", "docs"))
    return work


def main() -> None:
    source = (ROOT / CONTRACT).read_text(encoding="utf-8")
    missing = check_anchors(source)
    print(f"{len(MUTATIONS)} mutations, {missing} anchor problems")
    if "--anchors" in sys.argv:
        sys.exit(0 if missing == 0 else 1)
    only = ""
    if "--only" in sys.argv:
        only = sys.argv[sys.argv.index("--only") + 1].casefold()
    jobs = 1
    if "--jobs" in sys.argv:
        jobs = max(1, int(sys.argv[sys.argv.index("--jobs") + 1]))
    todo = [x for x in MUTATIONS if source.count(x[1]) == 1
            and (not only or any(part in x[0].casefold() for part in only.split("|")))]
    jobs = min(jobs, max(1, len(todo)))
    scratch = pathlib.Path(tempfile.mkdtemp(prefix="evidence-receipt-mut-"))
    copies = [copy_repo(scratch, i) for i in range(jobs)]
    print("accept-control: unmodified copy must pass ...", flush=True)
    if not run_suite(copies[0]):
        print("CONTROL FAILED: the unmodified suite does not pass; aborting")
        shutil.rmtree(scratch, ignore_errors=True)
        sys.exit(1)
    print(f"control green; {len(todo)} mutations over {jobs} job(s)\n", flush=True)
    results = [None] * len(todo)
    cursor = [0]
    done = [0]
    lock = threading.Lock()

    def worker(work: pathlib.Path) -> None:
        target = work / CONTRACT
        while True:
            with lock:
                i = cursor[0]
                if i >= len(todo):
                    return
                cursor[0] = i + 1
            name, old, new = todo[i]
            target.write_text(source.replace(old, new), encoding="utf-8", newline="\n")
            passed = run_suite(work)
            target.write_text(source, encoding="utf-8", newline="\n")
            with lock:
                results[i] = passed
                done[0] += 1
                print(f"  [{done[0]}/{len(todo)}] {'SURVIVED' if passed else 'killed  '}: "
                      f"{name}", flush=True)

    threads = [threading.Thread(target=worker, args=(w,)) for w in copies]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    shutil.rmtree(scratch, ignore_errors=True)
    print()
    killed = survived = 0
    for (name, _old, _new), passed in zip(todo, results):
        print(("SURVIVED: " if passed else "killed:   ") + name)
        survived += 1 if passed else 0
        killed += 0 if passed else 1
    print(f"\nmutations: {killed} killed, {survived} survived, {missing} anchor missing")
    sys.exit(0 if survived == 0 and missing == 0 else 1)


if __name__ == "__main__":
    main()
