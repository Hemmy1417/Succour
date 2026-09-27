# Deployment

The workflow, then only facts a receipt, a read or a command output shows. Every
recorded value is in `deploy/deployment.json`, written by
`scripts/deploy_studionet.py`.

## Assumptions

| Item | Value |
|---|---|
| Network | GenLayer StudioNet, chain id 61999, RPC `https://studio.genlayer.com/api`, explorer `https://explorer-studio.genlayer.com` |
| Gas | StudioNet is gasless; `fund_charter` is the one payable method, and its value is a real transfer |
| Wallets | the deployer key is created on first use in `.data/deployer.json`; the demo wallets' keys are in `.data/demo_wallets.json` (`scripts/make_wallets.py`); `.data/` is gitignored and no key is ever printed |
| Environment variables | none are required. `GENVM_VERSION=v0.3.0-rc7` pins the linter and the test runner when other GenVM bundles are cached; `SUCCOUR_LIVE_WRITES=1` opts the integration suite into one write |
| Runner | `py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6` |
| Sources | a live run serves `fixtures/sources/` from a commit-pinned `raw.githubusercontent.com` URL, so every validator retrieves exactly the committed bytes |
| Treasury | the steward wallet is funded through the simulator's `sim_fundAccount`, so the money path runs with real value |

## Workflow

Build and validate (the contract is one Python file; there is no build step
beyond the checks):

```bash
pip install -r requirements-test.txt
```

```bash
python scripts/fetch_genvm_bundle.py
```

```bash
genvm-lint check contracts/succour.py --json
```

```bash
python scripts/generate_fixtures.py --check
```

```bash
python -m pytest tests/direct -q
```

```bash
python scripts/mutation_check.py
```

Deploy and capture the address - the script refuses an uncommitted, non-ASCII or
CR-bearing contract, waits for FINALIZED, requires leader execution SUCCESS,
reads the deployed source back with `gen_getContractCode` and writes
`deploy/deployment.json` only after the byte comparison:

```bash
python scripts/deploy_studionet.py
```

Post-deployment check:

```bash
python scripts/deploy_studionet.py --verify
```

```bash
python -m pytest tests/integration -q
```

The live run walks the whole catalogue with real transactions, in phases, and
can be resumed:

```bash
python scripts/live_run.py <address> --raw-base https://raw.githubusercontent.com/<owner>/<repo>/<commit>/fixtures/ --phase full
```

By hand, with any GenLayer client: `create_charter(charter_json)` with a charter
from `fixtures/charters.json` (its `{base}` replaced by a pinned raw URL);
`fund_charter(charter_id)` with a value; `open_event(charter_id, charter_hash,
situation, area)`; `assess(event_id)`; `get_latest_declaration(event_id)`;
`file_request(event_id, charter_hash, category, need, area_note, evidence_url,
stability)`; `adjudicate(request_id)`; after the window `finalize_request` and
`withdraw`.

<!-- RECORD:START -->
## Deployment of record

| Item | Value |
|---|---|
| Network | GenLayer StudioNet, chain id 61999 |
| RPC | `https://studio.genlayer.com/api` |
| Contract | `0xBddAFAbb7Cc99FbAb694e0eF3e393D984A376B44` |
| Explorer | https://explorer-studio.genlayer.com/address/0xBddAFAbb7Cc99FbAb694e0eF3e393D984A376B44 |
| Deployment transaction | `0xa493597e2f97607cbd863165d57d61fcc2a8075dd694b99c5a4980098aefca72` |
| Deployed at | 2026-09-26T18:50:30Z |
| Receipt | status FINALIZED, leader execution SUCCESS, votes AGREE, AGREE, AGREE, AGREE, AGREE |
| Source commit | `267ce7d37bcd399e10acef5a504d805298f8175a` |
| Source blob | `3e8b5027e98ce98b3cc5bc3118ccf9391dda9196` |
| Source sha256 | `fed1c89a2626cb7d412a3e8ec2624bf93c53fdbc3c8fd1e673ffdd106557bad3` |
| Deployed source sha256 (`gen_getContractCode`) | `fed1c89a2626cb7d412a3e8ec2624bf93c53fdbc3c8fd1e673ffdd106557bad3` - byte-identical |
| Deployer (public address) | `0xEBE55542f6073A307E7E633DE28f852CA5670aeF` |
| Runner | `py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6` |

`python scripts/deploy_studionet.py --verify`: deployed and repository sha256
equal, byte-identical, 35 schema methods.
<!-- RECORD:END -->

## Toolchain

| Tool | Version |
|---|---|
| Python | 3.12.2 |
| genlayer-py | 0.16.3 |
| genlayer-test (Direct Mode) | 0.29.2 |
| genvm-linter | 0.11.0, GenVM bundle v0.3.0-rc7 |

`GENVM_VERSION=v0.3.0-rc7` matters on a machine where another project has
cached a newer GenVM manager: the linter and the direct runner resolve the
runner this contract pins from that bundle, and a newer manager that no longer
publishes it fails with `E101 Failed to load SDK`. CI's cache is keyed to the
same bundle.

<!-- DIAGNOSTIC:START -->
## Disposable diagnostic deployment

| Address | Purpose | Record |
|---|---|---|
| `0xB04C0D6C185b68b0AFd7645E28D9bBEE420a3301` | the diagnostic pass: sixteen charters, fourteen assessments and every relief request run once, with the per-node readings recorded | `deploy/diagnostics/deployment_0xb04c0d6c.json`, `pass1_0xb04c0d6c.json`, `.log` |

It is never the deployment of record. 72 transactions, 27 outcomes checked, 25
held; what the two misses showed and what changed in response:
[`CONSENSUS.md`](CONSENSUS.md#live-findings).
<!-- DIAGNOSTIC:END -->

<!-- LIVERUN:START -->
## Live run

| Item | Value |
|---|---|
| Transcript | `deploy/live_run_transcript.json`, log `deploy/live_run.log` |
| Transactions | 121 in 122 steps, no rejected round |
| Window | 2026-09-26T18:50:56Z to 2026-09-26T20:32:53Z |
| Sources served from | `https://raw.githubusercontent.com/Hemmy1417/Succour/4396a67/fixtures/` |
| Outcomes held | **73 of 73** |
| Refusals | 9 of 9 refused |
| Treasury after the run | pools 9000000000000000000 atto, credits 0 atto, balance 9000000000000000000 atto |

What ran, and what each case answered:

| Case | Reading | Outcome |
|---|---|---|
| AS01 | two watched sources report the warning, the onset and a gauge past danger | band `declared`, corroborated by M1 and M2 |
| AS02 | only the bulletin reports the evacuation | `declared` falls short of two sources, so `watch` is declared |
| AS03 | both sources report widespread inundation and displacement | band `severe` |
| AS04 | routine seasonal readings | `NO_BAND_MET` |
| AS05 | the second watched source is a road closure notice, bearing on nothing | `CORROBORATION_SHORT`, short band `declared` |
| AS06 | the sources report a heat advisory | `HAZARD_MISMATCH` |
| AS07 | the flood is reported with no onset date | `SIGNAL_UNDATED` |
| AS08 | the onset is older than the charter's freshness window | `SIGNAL_STALE` |
| AS09 | neither watched source is published | `SOURCES_UNAVAILABLE` |
| AS10 | one source is missing, the other carries the warning | band `watch`, corroborated by M1 alone |
| AS11 | a watched page addresses the adjudicator in its visible text | `SOURCE_ADDRESSES_ADJUDICATOR` |
| AS12 | the instruction is in a title and in a `meta` element | `SOURCE_ADDRESSES_ADJUDICATOR` |
| AS13 | the instruction hides a soft hyphen inside the word | `SOURCE_ADDRESSES_ADJUDICATOR` |
| AS14 | one source is a live feed the charter declares DYNAMIC | band `declared`; nothing about its bytes compared or stored |
| AS15 | the onset the sources give is in the future | `SIGNAL_UNDATED` |
| AS16 | three watched sources, two of which report the gauge past danger | band `declared` |
| AS16 again | the same sources read a second time | round 2 supersedes round 1, same band |
| RQ01 | the need is inside the area, established, and tied to this event | `QUALIFIES`, the charter's grant `RESERVED` |
| RQ02 | the site is two hundred kilometres outside the basin | `OUT_OF_AREA` |
| RQ03 | the shelter at the site is open and below capacity | `NEED_CONTRADICTED` |
| RQ04 | a road survey does not establish a shelter need | `NEED_ABSENT` |
| RQ05 | the damage is tied to a fire in 2025 | `NOT_LINKED` |
| RQ06 | a pre-season survey of the same households | `NOT_LINKED` - see the note below |
| RQ07 | the evidence carries no date | `EVIDENCE_UNDATED` |
| RQ08 | the declared evidence is not published | `EVIDENCE_UNAVAILABLE` |
| RQ09 | the evidence addresses the adjudicator | `SOURCE_ADDRESSES_ADJUDICATOR` |
| RQ10 | a clinic's supply report, in a second category the band promises | `QUALIFIES` at that category's own amount |
| RQ11 | evidence the filer declares DYNAMIC | `QUALIFIES`; its quotes grounded, its bytes not compared |
| RQ12 | a survey that blames this event and is dated before it began | `EVIDENCE_PREDATES_ONSET` |
| TS01 | a qualifying request against an unfunded charter | `QUALIFIES` / `TREASURY_SHORT`, nothing authorised |
| TS01 again | the same reading after the treasury was funded | `QUALIFIES` / `RESERVED` |

Then: thirteen requests settled, four grants paid, sixteen events finalised,
three filers withdrew their credits to zero, and nine refusals were refused -
a charter hash that does not match, an unknown charter, retiring somebody
else's charter, a category the band does not promise, filing against an event
with no declaration, a second request citing a source another request holds, a
source URL that is not https, withdrawing nothing, and reclaiming an active
charter's treasury. A deposit from someone who is not the steward was credited
back rather than lost, and withdrawn.

Integration against the deployment (`python -m pytest tests/integration -q`):
6 passed, 1 skipped (the opt-in live write).
<!-- LIVERUN:END -->
