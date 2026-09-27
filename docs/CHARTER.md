# The charter

A charter is the whole policy of one relief organisation for one hazard in one
region. It is published before anything happens, it is immutable, and its
canonical JSON is hashed: every event and every relief request commits to that
hash, so nobody can argue afterwards about what was promised.

`create_charter(charter_json)` takes exactly these keys.

| Key | Type | Rule |
|---|---|---|
| `name` | string | 1-80 characters, one line |
| `hazard` | enum | `EARTHQUAKE`, `FLOOD`, `STORM`, `WILDFIRE`, `DROUGHT`, `OTHER` |
| `region` | string | 1-200 characters, one line: the area this charter covers |
| `authority_domains` | list | 1-4 lowercase host suffixes; every watched source must sit under one |
| `monitors` | list | 1-3 watched sources, numbered `M1`, `M2`, `M3` in order |
| `bands` | list | 1-3 severity bands, **mildest first** |
| `qualification` | string | 1-600 characters: what a relief request must show |
| `assessment_window` | int | 60 to 2,592,000 seconds |
| `request_window` | int | 60 to 2,592,000 seconds |
| `max_age_seconds` | int | 0 to turn freshness off, otherwise at least 60 and at most one year |
| `max_grants_per_wallet` | int | 1 to 10, per event |
| `budget_atto` | string | decimal atto, at least the largest grant the bands promise |

A monitor is `{source_id, url, stability, description}`: `url` must be https, on
a host inside `authority_domains`, with no credentials, no port but 443, no IP
literal, no fragment and no dot segments; `stability` is `STABLE` when every
validator must read identical bytes, `DYNAMIC` when the page changes under them.

A band is `{band_id, label, conditions, min_corroboration, relief}`:

- `band_id` is lowercase letters, digits and underscores, and may not shadow a
  built-in subject - `HAZARD_MATCH`, `ONSET`, `AREA`, `NEED`, `LINK` or
  `EVIDENCE_DATE` - in any case: the panel's keys are case-folded, so such an id
  would share a slot with a subject;
- `conditions` is up to 400 characters of prose, and is what the panel is asked
  to read;
- `min_corroboration` is 1 to the number of monitors: how many distinct watched
  sources a finding for this band must rest on;
- `relief` is 1-3 actions, each `{category, grant_atto, max_grants}`, one per
  category, from `SHELTER`, `MEDICAL`, `WATER`, `FOOD`, `EVACUATION`, `CASH`.

## Writing conditions a panel can read

The conditions are the heart of the charter; they are read by several
independent models that must reach the same answer. What works:

**Name observable facts, not conclusions.** *A flood warning is in force and a
gauge has passed its danger level* is readable from a bulletin. *The situation
is serious* is not.

**Put the alternatives in the sentence.** *...or an evacuation has been ordered
for part of the region* tells the panel that either route is enough, and tells
a reader afterwards which route was taken.

**Say what has happened, not what might.** A forecast is not a condition met;
the panel is told so in its instructions, and a charter that asks about
*expected* flooding will split its validators.

**Let the thresholds live in the sources.** *Above the warning level* is better
than *above 4.2 metres*, because the source states its own levels and the panel
can quote them. If a number has to be in the charter, keep it to one.

**Make the bands distinguishable.** If two bands can be true of the same
bulletin, the severer one is declared whenever it has the corroboration - which
is fine when that is what you meant, and confusing when it is not.

**Set `min_corroboration` to what you would insist on.** Two sources for a band
that spends real money; one for a watch band that only opens the smallest
grants. Remember that a missing source cannot corroborate: a charter with two
monitors and `min_corroboration: 2` declares nothing while either one is down.

## Writing the qualification rule

`qualification` is read by the relief panel alongside the request. It should
describe what the *evidence* must show, not what the requester must promise:
the place, the need in the category, and the tie to this event. The four
readings are fixed by the contract - area, need, link, date - so the rule's job
is to say what counts as establishing each of them for this kind of relief.

## Freshness and the onset

`max_age_seconds` bounds two things with one number: how old the onset the
watched sources give may be for a band to be declared, and how old the evidence
a relief request shows may be. Set it to 0 and neither is aged - useful for a
charter about a slow hazard like drought, where the onset is months back.
Evidence dated **before** the declared onset never qualifies, whatever this is
set to.

An onset further in the past than 90 days is `SIGNAL_PREDATES_WINDOW`: it is
read as a different event, not a stale reading of this one.

## What the charter cannot do

- It cannot be edited. Publish another one and retire this one; events already
  open keep the charter they committed to.
- It cannot set an amount per request. `grant_atto` is per band and category,
  fixed in advance, and identical for everyone.
- It cannot name a source outside its authority domains, so the organisation's
  own choice of authorities is on the record.
- It cannot promise more than its treasury holds: a qualifying request whose
  grant the pool cannot cover is recorded `TREASURY_SHORT` and authorises
  nothing until the treasury is funded and the request rechecked.

## A worked charter

`fixtures/charters.json` holds sixteen, one per live case. The shape of the
first, with its watched sources and three bands, is the one worth reading; it
covers a river basin, watches a hazards-agency bulletin and a gauge release,
and promises shelter at every band, medical relief from the middle band and
evacuation only at the severest.
