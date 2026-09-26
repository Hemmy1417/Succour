<p align="center">
  <img src="docs/assets/succour-mark.svg" width="88" height="88" alt="SUCCOUR">
</p>

<h1 align="center">SUCCOUR</h1>

<p align="center">
  A relief organisation as one GenLayer Intelligent Contract: it declares what
  the sources it watches add up to, and authorises the relief its charter
  promised before the event.
</p>

---

Relief is slow because people have to establish three things before money can
move: that an event happened and how bad it is, that a request belongs to that
event, and that the request is real. SUCCOUR turns each of those into a record
anyone can check.

A **charter** is published first, while nothing is happening: the sources the
organisation watches, what each severity band requires in words, how many
sources must corroborate it, what relief each band promises for each category,
and what a relief request must show. Then:

- an **event** is opened against that charter and **assessed** - one consensus
  round reads every watched source and code derives the band;
- a **relief request** is filed against the band that stands and
  **adjudicated** - one round reads the requester's evidence for area, need,
  link to the event, and date;
- a qualifying request **reserves** the amount the charter fixed in advance, and
  **settles** into a pull ledger once its recheck window has passed.

The model never produces a band, an outcome or an amount. Code derives all
three from findings the validators agreed on, and every finding quotes the
source it rests on.

## What each side owns

| Deterministic code | GenLayer consensus |
|---|---|
| the charter, its hash, and what an event and a request commit to | whether the watched sources describe an event of the charter's hazard in its region |
| every field limit, URL admission, the authority-domain rule | which date the sources give for the onset |
| source status from the HTTP answer, normalisation, digests | whether each band's conditions - written in words - are met |
| where a source addresses the adjudicator | whether a need is inside the declared area |
| how many distinct sources a band's finding rests on | whether the evidence establishes that need |
| the onset and freshness arithmetic | whether the need is tied to this event or to something else |
| which band the findings add up to, and whether a request qualifies | what date the evidence carries |
| the amount, the caps, duplicate evidence, reservations, the ledger | |

## The lifecycle

```
  create_charter ─────────────────────────────── the charter is immutable and hashed
        │
        ├── fund_charter (payable, steward only)
        │
   open_event ── assess ──┬── reassess (once, in window) ──┐
        │                 │                               │
        │                 └───────────────────────────────┴── finalize_event
        │                                    the band that stands
   expire_event (never assessed)                       │
                                                       │
                                      file_request ── adjudicate ──┬── recheck_request
                                            │                      │      (once, in window)
                                     expire_request                │
                                     (never adjudicated)    finalize_request
                                                                   │
                                                              withdraw (pull)
```

## The declaration

An assessment reads every source the charter watches, in one round, and reaches
one of these:

| Reason | Meaning |
|---|---|
| `BAND_DECLARED` | the highest band whose conditions were met, with enough sources behind it |
| `CORROBORATION_SHORT` | a band's conditions were met by fewer sources than the charter requires, and no milder band was met |
| `NO_BAND_MET` | the sources report the situation but no band's conditions |
| `HAZARD_MISMATCH` / `HAZARD_UNCLEAR` | the sources describe another hazard or another place, or cannot be read that way |
| `SIGNAL_UNDATED` | no onset date the sources actually show, or one in the future |
| `SIGNAL_STALE` | the onset is older than the charter's freshness window |
| `SIGNAL_PREDATES_WINDOW` | the onset is too far in the past to be this event |
| `SOURCES_UNAVAILABLE` | no watched source could be read |
| `SOURCE_ADDRESSES_ADJUDICATOR` | a watched page carries text addressed to whoever adjudicates |
| `PANEL_UNUSABLE` | the model's answer could not be used |

## The relief decision

| Outcome | Reasons |
|---|---|
| `QUALIFIES` | `QUALIFIED` |
| `DOES_NOT_QUALIFY` | `OUT_OF_AREA`, `NEED_ABSENT`, `NEED_CONTRADICTED`, `NOT_LINKED`, `EVIDENCE_PREDATES_ONSET`, `BAND_WITHDRAWN`, `GRANT_CAP_REACHED`, `WALLET_CAP_REACHED` |
| `INCONCLUSIVE` | `AREA_UNCLEAR`, `NEED_UNCLEAR`, `LINK_UNCLEAR`, `EVIDENCE_UNDATED`, `EVIDENCE_STALE`, `EVIDENCE_UNAVAILABLE`, `SOURCE_ADDRESSES_ADJUDICATOR`, `PANEL_UNUSABLE` |

A qualifying request is `RESERVED` when the charter's treasury can cover the
promised grant and `TREASURY_SHORT` when it cannot - the outcome stands either
way, and a recheck after funding authorises it.

## What validators must agree on

Only the consequence. An assessment compares the declared band, the reason, the
onset and its outcome, the short band when corroboration fell short, and the
digest of every source the charter declared STABLE. A relief decision compares
the outcome, the reason, the evidence date where it bears on the result, and the
three readings **only when the request was granted** - a refusal rests on the
one subject its reason names.

Not compared: notes, which passages were quoted, how many sources a met band was
quoted from, optional readings, and everything about a DYNAMIC source beyond its
status. Details, and why each line is where it is:
[`docs/CONSENSUS.md`](docs/CONSENSUS.md).

## Verified

<!-- VERIFIED:START -->
Filled from the live run of record. Until then, what has been verified is the
offline gate:

| Check | Result |
|---|---|
| `genvm-lint check contracts/succour.py --json` | lint ok, 35 methods (20 view, 15 write) |
| `ruff check .` | clean |
| `python scripts/generate_fixtures.py --check` | 43 fixture files regenerate byte for byte |
| `python -m pytest tests/direct -q` | 225 passed |
<!-- VERIFIED:END -->

## Running it

```bash
pip install -r requirements-test.txt
```

```bash
python scripts/fetch_genvm_bundle.py
```

```bash
python -m pytest tests/direct -q
```

```bash
genvm-lint check contracts/succour.py --json
```

Deployment, the live run and the integration suite:
[`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

## Layout

| Path | What is in it |
|---|---|
| `contracts/succour.py` | the whole contract: one file, no runtime dependency outside GenVM |
| `tests/direct/` | the Direct Mode suite: lifecycle, hardening, adversarial, fixtures |
| `tests/integration/` | reads against the deployment of record |
| `fixtures/` | the charters, cases and source pages a live run serves from a pinned commit |
| `scripts/` | fixtures, deploy, live run, mutation check, preflight |
| `deploy/` | the deployment record, the live-run transcript and the diagnostic passes |
| `docs/` | consensus, the charter's policy language, security, adversarial testing, integration, deployment |

## Documents

- [`DECISION.md`](DECISION.md) - why this shape, what was left out, and how it differs from the nearest builds
- [`docs/CONSENSUS.md`](docs/CONSENSUS.md) - what each node does, what is compared, what may differ
- [`docs/CHARTER.md`](docs/CHARTER.md) - the charter's fields and how to write conditions a panel can read
- [`docs/SECURITY.md`](docs/SECURITY.md) - the boundaries, and what is out of scope
- [`docs/ADVERSARIAL_TESTING.md`](docs/ADVERSARIAL_TESTING.md) - the attacks the suite runs and the mutation sweep
- [`docs/INTEGRATION.md`](docs/INTEGRATION.md) - reading and writing from a client
- [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) - the deployment of record, the toolchain and the live run

## Licence

MIT. See [`LICENSE`](LICENSE).
