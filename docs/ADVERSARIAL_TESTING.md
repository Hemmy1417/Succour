# Adversarial testing

What is attacked, how, and how the suite proves it would notice.

## The suite

| File | What it covers |
|---|---|
| `tests/direct/test_succour.py` | the lifecycle: charters, treasury, events, declarations, requests, settlement, the views |
| `tests/direct/test_succour_hardening.py` | every refusal: the charter parser, access control, the state machine, the windows, the caps, the ledger arithmetic |
| `tests/direct/test_succour_adversarial.py` | hostile sources, fabricated support, and the validator's own judgement |
| `tests/direct/test_fixtures.py` | the live-run fixtures against the deployed code |

Everything runs the contract as deployed. Only the two nondeterministic calls
are mocked - the retrieval and the panel - and a mocked panel answer has to
ground its quotes in the text the harness actually serves, so a fabricated
quote is downgraded in the test exactly as it would be on chain.

## The attacks

**A watched source tells the adjudicator what to decide.** In the visible body,
in a `<meta>` tag a reader never sees, and in the title. Each one stops the
round with `SOURCE_ADDRESSES_ADJUDICATOR`, and the marker names where it was
found.

**The instruction hides from a naive scan.** A soft hyphen, a zero-width joiner,
a byte order mark, a numeric character reference, a `<span></span>` and an HTML
comment, each splitting the word the scan looks for. All six are caught, and a
separate test proves each string carries **exactly one** marker phrase - without
it, a test could pass because a second, untouched instruction sat in the same
line. That check is here because the previous build's evasion tests were
vacuous for precisely that reason.

**Only one of several watched sources is poisoned.** The round still stops. The
alternative - dropping the poisoned source and declaring on the rest - would let
whoever poisoned it remove the corroboration a band needs.

**A quote that is not in the source.** Dropped, the finding falls back to its
default, and the band is not declared.

**A quote attributed to a source it did not come from.** Re-attributed to the
source it actually grounds in, or dropped. Citing one page twice under two names
yields one source, so the corroboration floor still bites - and the test proves
the round falls back to the milder band rather than declaring the stronger one.

**A quote spliced with an ellipsis.** Dropped, both when the panel answers and
at the gate.

**A date that is not in its quote, and a date in the future.** Both become
`UNDATED`; nothing is declared and nothing qualifies on them.

**A state asserted without its quote, a state outside the vocabulary, a missing
subject.** All three fall back to the subject's default.

**A source that is a redirect, a 403, a 503, an image, or enormous.** Each is
reported as what it is; the enormous one is `PARTIAL` and still usable.

**A dishonest leader.** The captured validator closure is replayed against a
payload the test has tampered with: a forged band state, a forged quote, a
forged digest on a STABLE source, a forged marker list, a claim that the panel
was skipped, a payload about another record or another round, a payload missing
a key. Every one is refused, and the refusal prints why.

**An honest leader that differs.** Notes and quote choice may differ; the same
band from other quotes is ratified; a DYNAMIC source whose incidental content
changed is ratified; a STABLE source whose bytes changed is not; a validator
that reads a different band or a different onset disagrees.

**A leader that failed.** A transient failure meeting a transient one is
ratified; a model failure never is; a leader that failed where the validator
succeeded is refused.

**A claimant who edits the page after a refusal.** Refused on `NEED_ABSENT`,
the requester serves an improved page and asks for a second look. The recheck is
refused, the standing decision is left alone, and the same bytes can still be
re-judged - which is what a contested reading needs.

**A claimant who cites their own site.** Refused at filing: the charter named
its evidence authorities before the event.

**A steward who watches three pages of one agency.** The charter parser refuses a
band demanding more corroboration than the charter has origins, and a band whose
quotes come from two pages of one host is short of its floor.

**Money.** A deposit from anyone but the steward is credited back rather than
lost; a reserved grant cannot be reclaimed; a released reservation gives its
grant slot back; the same source cannot back two live requests; a paid source
stays spent; the books balance across a whole run, including reclaiming what is
unreserved.

## The mutation sweep

A passing suite proves the code works today. The sweep proves the suite would
notice if a guard were removed. `scripts/mutation_check.py` copies the
repository once per mutation, breaks exactly one guard in the contract - by
text, never by line number - and runs the whole Direct Mode suite against the
copy. A mutation is KILLED when the suite fails and SURVIVED when it passes.

The run starts with an accept-control: the unmodified copy must pass, or every
kill would be vacuous. An anchor that is not found exactly once is reported as
`ANCHOR MISSING`, which is its own finding - the guard moved or was deleted.

```bash
python scripts/mutation_check.py
```

```bash
python scripts/mutation_check.py --anchors
```

The 95 mutations cover the retrieval layer, the marker scan, what a finding must
show, the band derivation and its corroboration floor, the freshness and onset
arithmetic, every branch of the relief decision, what validators compare, the
charter parser, the state machine, the caps and the ledger.

<!-- SWEEP:START -->
**The sweep of record: 97 mutations, 97 killed, 0 survived, 0 anchors
missing** (`deploy/mutation_sweep_record.txt`), with the accept-control green.

An earlier sweep left seventeen survivors. Every one of them is now either pinned
by a test written for it - a body that does not decode, a page with nothing a
reader can see, a stray date at the gate, a splice that grounds because grounding
walks ellipsis-separated parts, two quotes from one source counting as one
source, freshness switched off, evidence that went stale between filing and
adjudication, a truncated reading, an address literal in a URL, settling inside
the recheck window, a deterministic failure meeting a transient one - or is named
below as one no test can kill, with the reason.
<!-- SWEEP:END -->

## What the sweep deliberately leaves alone

Comparisons that are implications rather than values are not mutated, because no
test could kill them: a reason already fixes the readings it rests on, so
removing the freshness outcome or the three relief states from the comparison
changes nothing that could ever differ. They were removed from the comparison
instead.
