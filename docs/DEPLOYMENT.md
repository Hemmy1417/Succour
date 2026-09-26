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

Filled by `scripts/deploy_studionet.py` once the deployment of record is made.
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

Filled from `deploy/diagnostics/`.
<!-- DIAGNOSTIC:END -->

<!-- LIVERUN:START -->
## Live run

Filled from `deploy/live_run_transcript.json`.
<!-- LIVERUN:END -->
