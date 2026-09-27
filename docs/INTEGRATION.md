# Integration

Every method, and what a client does with it. Reads are plain contract reads;
writes are signed transactions that go through consensus.

## Writes

| Method | Who | What it does |
|---|---|---|
| `create_charter(charter_json)` | anyone | publishes a charter and returns its id (`CH-000001`). The sender becomes its steward. Fields: [`CHARTER.md`](CHARTER.md) |
| `retire_charter(charter_id)` | steward | stops new events; open events and filed requests continue under the same charter |
| `fund_charter(charter_id)` **payable** | steward | adds the transaction's value to the charter's relief treasury and returns the new pool. A refusal returns the deposit as a credit and answers `RETURNED: <reason>` |
| `reclaim_unreserved(charter_id)` | steward | after retiring, credits back everything no reservation holds |
| `open_event(charter_id, charter_hash, situation, area)` | anyone | opens an event for assessment and returns its id (`EV-000001`). `charter_hash` pins the charter the opener read |
| `assess(event_id)` | anyone | one consensus round over the watched sources; returns the declaration id (`DE-000001`) |
| `reassess(event_id)` | anyone | one more round while the window is open, at most once; the new declaration supersedes the first and becomes the band that stands |
| `finalize_event(event_id)` | anyone | closes the declaration after its window |
| `expire_event(event_id)` | anyone | lapses an event nobody assessed in time |
| `file_request(event_id, charter_hash, category, need, area_note, evidence_url, stability)` | claimant | files a relief request against the band that stands and returns its id (`RQ-000001`) |
| `adjudicate(request_id)` | anyone | decides the request; a qualifying one reserves the charter's grant. Returns the adjudication id (`AD-000001`) |
| `recheck_request(request_id)` | the filer or the charter's steward | one more decision while the window is open, at most once, **on the same bytes** - a round whose retrieval differs from the bound digest is refused, and evidence declared DYNAMIC is not rechecked at all |
| `finalize_request(request_id)` | anyone | settles: a reservation becomes a claimable credit, anything else is released. Returns the amount |
| `expire_request(request_id)` | anyone | lapses a request nobody adjudicated in time, freeing its source |
| `withdraw()` | anyone with a credit | pays the caller's whole credit and returns the amount |

Amounts cross the boundary as decimal strings in atto (1 GEN = 10^18 atto),
because a u256 does not survive a JSON number.

## Reads

| Method | Returns |
|---|---|
| `get_charter(charter_id)` | the charter as published, its hash, steward, status and treasury |
| `get_event(event_id)` | the event, its status, its windows, the band that stands, the onset, and the latest declaration id |
| `get_event_status(event_id, as_of)` | what may happen at that time: reassess, finalise, file a request; and the effective status of an event whose window has passed |
| `get_declaration(declaration_id)` | one declaration receipt in full |
| `get_latest_declaration(event_id)` | the declaration that stands |
| `get_event_history(event_id)` | one line per round: mode, band, reason, onset |
| `get_request(request_id)` | the request as filed, its status, its outcome, its reserved and paid amounts, and the evidence digest the first adjudication bound |
| `get_request_status(request_id, as_of)` | what may happen at that time |
| `get_adjudication(adjudication_id)` | one adjudication receipt in full |
| `get_latest_adjudication(request_id)` | the decision that stands |
| `get_request_history(request_id)` | one line per round: mode, outcome, reason, who decided it, amount, funding |
| `get_actions(request_id, as_of)` | what the filer can do next, whether its band still stands, and what the caps and treasury leave |
| `list_charters(offset, limit)` / `list_events(charter_id, offset, limit)` / `list_requests(event_id, offset, limit)` | paged ids; an empty id lists everything |
| `get_treasury()` | pools, credits, their sum, and the contract's actual balance |
| `get_credit(wallet)` | one wallet's claimable balance |
| `get_returned_deposits(offset, limit)` | deposits that were credited back, with the reason |
| `get_stats()` | counts of charters, events, requests, declarations and adjudications |
| `get_config()` | every limit and vocabulary, read from the contract rather than copied from these documents |

A view has no clock, which is why `get_event_status`, `get_request_status` and
`get_actions` take `as_of`. Every write checks its own transaction time.

## A whole run, with a client

```python
from genlayer_py import create_account, create_client
from genlayer_py.chains import studionet
from genlayer_py.types import TransactionStatus

account = create_account(account_private_key=key)
client = create_client(chain=studionet, account=account,
                       endpoint="https://studio.genlayer.com/api")
ADDRESS = "0x..."


def write(method, args=None, value=0):
    tx = client.write_contract(address=ADDRESS, function_name=method,
                               args=args or [], value=value)
    return client.wait_for_transaction_receipt(
        transaction_hash=tx, status=TransactionStatus.FINALIZED,
        interval=5000, retries=300)


def read(method, args=None):
    return client.read_contract(address=ADDRESS, function_name=method, args=args or [])
```

Publish a charter, fund it, and read back its hash:

```python
write("create_charter", [charter_json])
charter_id = read("list_charters", [0, 50])["ids"][-1]
charter_hash = read("get_charter", [charter_id])["charter_hash"]
write("fund_charter", [charter_id], value=12 * 10 ** 18)
```

Open and assess an event, then read what was declared:

```python
write("open_event", [charter_id, charter_hash, situation, area])
event_id = read("list_events", [charter_id, 0, 50])["ids"][-1]
write("assess", [event_id])
declaration = read("get_latest_declaration", [event_id])["declaration"]
declaration["declared_band"], declaration["reason_code"], declaration["onset"]
```

File a relief request and adjudicate it:

```python
write("file_request", [event_id, charter_hash, "SHELTER", need, area_note,
                       evidence_url, "STABLE"])
request_id = read("list_requests", [event_id, 0, 50])["ids"][-1]
write("adjudicate", [request_id])
ruling = read("get_latest_adjudication", [request_id])["adjudication"]
ruling["outcome"], ruling["reason_code"], ruling["authorised_atto"], ruling["funding"]
```

Settle after the recheck window, then withdraw:

```python
status = read("get_request_status", [request_id, now_iso])
if status["may_finalize"]:
    write("finalize_request", [request_id])
write("withdraw")
```

## Reading a receipt

A declaration carries the charter and event it belongs to, the band and its
label, the reason, the onset and its outcome, the relief that band promises,
`min_corroboration` and the sources the quotes grounded in, one record per
watched source, the markers, the panel state, one finding per subject with a
`compared` flag, and a short excerpt of the decisive passages.

An adjudication carries the request, its band and category, the outcome and
reason, the evidence date where it bore on the result, the authorised amount and
its funding state, the source record, the markers, the panel state, the four
findings with their `compared` flags, and the excerpt. A code-decided refusal
carries `decided_by: "CODE"`, no sources and no findings.

What `compared` means, and why a field may be absent:
[`CONSENSUS.md`](CONSENSUS.md).

## Failures a client should expect

| Symptom | Meaning |
|---|---|
| leader execution `ERROR` with `[EXPECTED] ...` | the contract refused: a bad field, a closed window, a cap, a state that does not allow the call. The message says which |
| leader execution `ERROR` with `[TRANSIENT] ...` | the model call or the clock failed on that node; send it again |
| `RETURNED: <reason>` from a payable write | the deposit was credited back rather than lost; read `get_returned_deposits` |
| the transaction finalises but nothing changed | the round did not reach a majority. Nothing is stored; read the record and try again |
| `INCONCLUSIVE` with `EVIDENCE_UNAVAILABLE` | the declared source could not be retrieved, not a judgement about the need |
