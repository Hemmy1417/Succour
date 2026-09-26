# Decisions

Why this contract exists in this shape, what was deliberately left out, and how
it differs from the nearest things already built.

## The question the contract answers

Relief is slow because people have to establish three things before money can
move: that an event happened and how bad it is, that a particular request is
inside the scope of that event, and that the request is not already covered or
made up. Each of those is a judgement over sources written in prose, and each
one is auditable after the fact.

SUCCOUR splits that work in two and puts a receipt under each half:

1. **Has a band been reached?** A charter published before the event names the
   sources the organisation watches, what each severity band requires - in
   words - and how many sources must corroborate it. One consensus round reads
   the sources and code derives the band.
2. **Does this request qualify?** Against the band that stands, one round reads
   the requester's evidence for four things: is the need inside the declared
   area, is it established, is it tied to this event, and what date does the
   evidence carry.

The money is not a judgement at all. The charter fixes the amount for a band
and a category before any event exists; a qualifying request reserves exactly
that amount, and settlement moves it to a pull ledger.

## Why this needs consensus at all

The oracle test, asked at design time and again before submission: could a
conventional oracle, or plain code with one API, do this?

| Part of the work | Who does it | Why |
|---|---|---|
| "Was there a magnitude 6.5 quake at these coordinates?" | **not this contract** | a feed and a numeric comparison; an oracle is the right tool and no panel is needed |
| "Do the sources this charter watches report an event of its hazard in its region?" | consensus | several sources, different wording, different units, and a region described in prose |
| "Are this band's conditions met?" | consensus | the conditions are a sentence a charter author wrote, not a threshold: *a warning in force and a gauge past its danger level, or an evacuation ordered* |
| "How many independent sources support that?" | **code** | counted from which sources the panel's quotes actually ground in |
| "Is this need inside the declared area, established, and caused by this event?" | consensus | a field report in prose against an area and a cause |
| "How much is owed?" | **code** | the charter said so before the event |
| freshness, onset arithmetic, caps, duplicate evidence, reservations, the ledger | **code** | deterministic, and nothing a model should be asked |

The two consensus questions are exactly the ones a single trusted server would
have to be believed about. Everything a machine can settle is settled by code,
and the model never sees an amount.

## Scope, and what was left out

Lean ship, in the shape of the last two standalone contracts: one contract, a
Direct Mode suite, fixtures served from a pinned commit, a mutation sweep, a
disposable diagnostic deployment, a deployment of record and a live run.

Left out deliberately:

- **A frontend.** This is a standalone contract; reads and writes are shown
  through a client in [`docs/INTEGRATION.md`](docs/INTEGRATION.md).
- **Per-claimant identity.** A wallet is the only identity; the charter's
  per-wallet grant cap is the honest limit that follows from that. Real relief
  needs identity, and a contract that pretended to have it would be lying.
- **Proportional or partial grants.** A charter promises a fixed amount per
  band and category. A model that could set an amount would be the single most
  attackable thing in the design.
- **Bands that fall as well as rise.** A reassessment can name any band the
  sources support, including a milder one; there is no separate de-escalation
  machinery, and a request filed against a band that no longer stands is
  refused in code rather than silently repriced.
- **Automatic payment on adjudication.** A qualifying request reserves;
  settlement pays after the recheck window. Money that moves before anyone can
  contest the reading cannot be un-moved.
- **More than three watched sources or three bands.** Both caps are arbitrary
  and both are enforced; a charter that watched twenty sources would be a
  charter nobody could check.

## Against the nearest neighbours

| Build | What it decides | Why SUCCOUR is not it |
|---|---|---|
| **ClaimSense** | whether a crop's weather basis risk paid out | one policy, one insured, an index that is a number; no shared event and no treasury of predefined actions |
| **InsureShield** | whether one insurance claim's evidence supports it | claim by claim, with no declaration standing above the claims and no severity band that changes what is promised |
| **Triggera** | parametric insurance on a published trigger | the trigger is a measurement; here the trigger is a sentence, corroborated across sources |
| **Isobar** | a weather market's outcome | a market settles one question for traders; this authorises spending against a published charter |
| **EvidenceReceipt** | whether one source supports one claim under a policy | the ancestor of the request half - and only that half. It has no event, no severity, no corroboration count and no money |
| **GrantCourt** | whether a grant milestone's evidence meets a programme's rubric | one submission judged against a rubric; nothing above it declares that a situation exists |

What is new here, and is the reason the build is worth doing: **one declaration
that many requests are measured against**. The event is assessed once, at a
severity, from several sources that must agree enough; then every relief
request inherits that declaration - its band, its promised amounts, its area
and its onset date - and is judged only on whether it belongs to it. That is the
shape a relief organisation actually has, and neither half works alone: without
the declaration the requests have nothing to be inside of, and without the
requests the declaration pays nobody.

## Design decisions worth naming

**Corroboration is counted, not claimed.** The panel is asked to quote every
source that supports a band. Code counts the distinct sources whose text those
quotes actually ground in, and compares that against the charter's
`min_corroboration`. A leader that cites the same page twice under two names
gets one source, because the second quote does not ground in the second
source's text.

**A poisoned source stops the whole round.** If any watched page carries text
addressed to whoever adjudicates, the round is decided in code as
`SOURCE_ADDRESSES_ADJUDICATOR` - it is not dropped from the set. Dropping it
would let whoever poisoned it choose which sources count, and removing one
source can take a band below its corroboration floor.

**An unavailable source is never a refusal.** No readable source is
`SOURCES_UNAVAILABLE`; unreadable evidence is `INCONCLUSIVE`. Silence is not
evidence that relief is undeserved.

**A milder band is declared when a stronger one falls short.** If the severe
band's conditions are met by one source where two are required, and the watch
band's are met by one where one is required, the watch band is declared. The
conservative reading is the one that pays less, not the one that pays nothing.

**The onset is compared.** It is the one date every later request is measured
against (evidence dated before the onset does not qualify), so validators must
agree on it, and the panel has to quote the passage that carries it - year,
month and day - for it to count at all.

**Under a refusal, only the reading that refused is compared.** A granted
request rests on area, need and link together, so all three states are
compared. A refused one rests on the single subject its reason names; comparing
the others would split a round over readings that cannot change it. This is the
lesson the previous build paid for live.

**Receipts store only what was compared.** A source the charter declared
DYNAMIC stores its status and nothing about its bytes. Readings no outcome
rested on are stored with `compared: false`, and the corroborating source list
is marked as grounded-but-not-compared, because honest panels cite different
subsets of the same bulletins.

**Money leaves only by withdrawal.** Reservations are held inside the charter's
pool; settlement credits the filer; `withdraw` clears the credit before it
emits the transfer. A payable write that must be refused returns the deposit as
a credit instead of raising, because this network credits the value of a
raising payable transaction to the contract regardless.
