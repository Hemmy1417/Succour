# Security

What this contract defends against, how, and what it does not pretend to
defend against.

## The boundaries

| Boundary | Who is on the other side | What holds |
|---|---|---|
| the charter | the steward who publishes it | immutable, hashed, and every event and request commits to the hash; a retired charter opens no new events |
| the watched sources | whoever publishes them, and whoever can influence them | https-only admission, an authority-domain rule the charter fixes in advance, status from the HTTP answer, normalisation, a marker scan, and a corroboration floor across distinct sources |
| a relief request's evidence | the requester | one declared source, retrieved by every validator, quoted by the panel and re-grounded by each validator in its own bytes |
| the panel | the models | the model never sees an amount and never returns a band or an outcome; every state that bears on the result must carry a quote |
| the leader | whoever is leading the round | a structural gate on its payload, then a comparison of what was retrieved and what it leads to, both reproduced independently |
| the treasury | everyone | only the steward funds, only reservations pay, and money leaves only through `withdraw` |

## Prompt injection

Every source is data. The panel header says so, and the contract does not rely
on the panel obeying it:

- `_markers` scans each readable source in code for text addressed to whoever
  adjudicates - in the visible text, in markup and attributes a reader never
  sees, and in the title;
- the scan undoes the tricks that hide such text from a naive `in` test: soft
  hyphens, zero-width joiners, bidirectional controls, byte order marks,
  numeric character references, and tags or comments splitting a word;
- a source that carries such text decides the round in code as
  `SOURCE_ADDRESSES_ADJUDICATOR`. The panel is not convened at all;
- the marker list is part of what validators compare, and the gate recomputes it
  from the source records, so a leader cannot hide or invent one;
- the charter's own texts are checked for the same markers at publication, so a
  steward cannot smuggle instructions into a band's conditions.

**A poisoned source is not dropped.** Ignoring it and declaring on the rest
would let whoever poisoned it choose which sources count - and with a
corroboration floor, removing one source can change the band. The whole round
stops.

## Fabricated support

- A quote is only a quote if it grounds in the text that node retrieved, as a
  contiguous run of words. Splices joined by an ellipsis are dropped.
- A quote attributed to a source it does not appear in is re-attributed to the
  source it actually grounds in, or dropped. Citing one page twice under two
  names yields one source, so a band's corroboration cannot be manufactured.
- A date counts only when a quote carries its year, month and day. A date in the
  future is `UNDATED`.
- A state that bears on the result without a quote is downgraded to the
  subject's default, and the downgrade is printed.

## Money

- Only the charter's steward funds it, so every unit in a pool is the steward's
  to reclaim once the charter is retired and nothing is reserved.
- A payable write that must be refused **returns the deposit as a claimable
  credit** and records the refusal. This network credits the value of a payable
  transaction to the contract even when the transaction raises, so refusing by
  raising would strand the sender's money.
- A qualifying request reserves inside the pool; nothing is paid until the
  recheck window has passed and `finalize_request` runs. A reading that is
  overturned within the window releases its reservation.
- `withdraw` clears the ledger entry before emitting the transfer, so a repeat
  pays nothing.
- At every moment the contract's accounted balance is the sum of the charter
  pools and the claimable credits; `get_treasury` shows both against the actual
  balance.

## Double-spending relief

- The first request to cite a source holds it for that event. A second request
  citing the same URL is refused at filing; a request that lapses or settles
  without a grant frees it; one that was paid keeps it forever.
- `max_grants` per band and category, and `max_grants_per_wallet` per event, are
  counted against grants that are reserved as well as paid, so two requests
  cannot both take the last grant.
- A request filed against a band that a reassessment has replaced is refused in
  code as `BAND_WITHDRAWN`, never silently repriced.

## Time

- Every window is measured against the transaction's own time
  (`gl.message_raw["datetime"]`), not a clock a caller passes. Views take an
  `as_of` argument because a view has no clock, and say so.
- A clock that cannot be read raises `[TRANSIENT]` rather than assuming a time.
- Windows bound both directions: an event must be assessed before its window
  closes and finalised after it, and the same for a request.

## Identity

Every recorded account is the signer (`gl.message.sender_address`), lowercased
into a hex string. No method takes an address for someone else, so a record can
never name a wallet that did not sign for it. Assessment, adjudication and
settlement are deliberately public: a keeper who is nobody's agent can move a
record forward, and none of them can change an outcome.

## Out of scope

- **SSRF.** URL admission is hygiene, not a network boundary; the validators'
  runtime egress controls are the real one.
- **Identity of claimants.** A wallet is the only identity. The per-wallet grant
  cap is the honest limit that follows; a determined person with many wallets and
  many genuine-looking sources is a problem this contract cannot solve, and the
  charter's caps bound the damage rather than preventing it.
- **Whether a watched source tells the truth.** The charter names its
  authorities in advance and the contract requires corroboration across them.
  If every authority a charter trusts is wrong together, the declaration is
  wrong together with them.
- **Model quality.** Where honest models split on a reading, the round does not
  reach consensus and nothing is stored. That is the correct failure, not a
  defence.
- **Griefing by volume.** Anyone can open events and file requests up to the
  per-wallet caps; on a gasless network that is a nuisance the caps bound, not
  an attack the contract prevents.
