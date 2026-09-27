# Submission text

Portal fields, measured against their limits. No addresses, hashes, ids or shell
commands appear in any field: the contract address goes only in the validated
contract-link field, and the repository goes in the evidence rows.

## One-liner (180 characters)

A relief organisation as one intelligent contract: it declares what the sources
it watches add up to, then authorises the relief its charter promised before the
event.

## Description (1000 characters)

Relief is slow because people must first establish that an event happened and
how bad it is, then that a request belongs to that event. SUCCOUR makes both a
matter of record.

A charter is published while nothing is happening: the sources the organisation
watches, what each severity band requires in words, how many sources must
corroborate it, and what relief each band promises per category. An event is
then assessed in one consensus round: validators retrieve every watched source,
read whether the hazard, the place and each band's conditions are met, and code
derives the band, counting corroboration from the sources the quotes actually
ground in. Relief requests are filed against the band that stands and judged on
four things: is the need inside the declared area, is it established, is it tied
to this event, and what date does the evidence carry.

The model never sets an amount: the charter fixed it in advance, a qualifying
request reserves it, and settlement pays from a pull ledger.

## How to use it (seven steps, each with its heading)

1. **Connect a wallet** - open the contract in the explorer and connect the
   wallet you will sign with. The network is gasless, so a new wallet works.
2. **Publish a charter** - call the charter method with the watched sources,
   the severity bands and their conditions, what each band promises, and the
   windows. The contract hashes it; nothing about it can change afterwards.
3. **Fund the treasury** - as the charter's steward, send value with the funding
   method. Only the steward can fund, so everything unreserved is the steward's
   to reclaim once the charter is retired.
4. **Report a situation** - open an event against the charter, committing to the
   charter hash you read, with the situation and the area it affects.
5. **Assess it** - run the assessment. One consensus round reads every watched
   source and stores a declaration: the band, why, the onset date, which sources
   corroborated it, and what each validator compared.
6. **File a relief request** - against the band that stands, naming a category
   the band promises and one source that shows the need. The first request to
   cite a source holds it for that event.
7. **Adjudicate and claim** - run the adjudication; a qualifying request
   reserves the charter's fixed grant. After the recheck window, settle it and
   withdraw the credit.

## Verification outcome (500 characters)

<!-- VERIFY:START -->
Deployed on Studio, source byte-identical to the repository, thirty-five
methods. A live run drove the catalogue with real transactions: sixteen
assessments, a reassessment, twelve relief requests, thirteen settlements, four
grants paid, three withdrawals - every outcome as recorded, all nine refusals
refused. The watched sources came from three independent origins, one commit.
Afterwards pools and credits equal the balance. Offline: 233 tests and a sweep
pinning every guard.
<!-- VERIFY:END -->

## Evidence rows

| Type | What |
|---|---|
| repository | the GitHub repository (auto-badged) |
| contract link | the Studio explorer page for the deployment of record |

## Logo

`docs/assets/succour-mark.svg`, rasterised to a 512px PNG for the upload field.
