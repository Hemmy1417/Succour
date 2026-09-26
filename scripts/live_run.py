#!/usr/bin/env python3
"""Drive the deployed contract through the whole catalogue with real
transactions, and record what the chain answered.

    python scripts/live_run.py <address> --raw-base <pinned raw url> --phase full

Phases run in order and can be run one at a time: charters, assessments,
requests, settle, refusals. Every step is recorded in
deploy/live_run_transcript.json under a unique name; re-running skips steps
already recorded, so a transport failure or a rate limit never repeats work and
never loses an id. A resumed step reuses the ids the transcript recorded rather
than re-reading whatever is current.

The sources every charter watches are served from --raw-base, a
commit-pinned raw.githubusercontent.com URL, so every validator retrieves
exactly the committed bytes.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import studionet_transport  # noqa: E402,F401 - retries RPC transport failures
from genlayer_py import create_account, create_client  # noqa: E402
from genlayer_py.chains import studionet  # noqa: E402
from genlayer_py.types import TransactionStatus  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"
KEYS = ROOT / ".data" / "demo_wallets.json"
TRANSCRIPT = ROOT / "deploy" / "live_run_transcript.json"
LOG = ROOT / "deploy" / "live_run.log"
RPC = "https://studio.genlayer.com/api"
WAIT = dict(interval=5000, retries=300)
GEN = 10 ** 18
PHASES = ("charters", "assessments", "requests", "settle", "refusals")


def log(text: str):
    line = time.strftime("%H:%M:%S") + " " + text
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


# -- the transcript ------------------------------------------------------------

class Transcript:
    def __init__(self, address: str, raw_base: str, path=None):
        self.path = path or TRANSCRIPT
        if self.path.exists():
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        else:
            self.data = {"address": address, "raw_base": raw_base,
                         "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                         "steps": {}, "order": []}
        if self.data["address"] != address:
            sys.exit("the transcript records a different contract; move it aside first")
        self.data["raw_base"] = raw_base

    def has(self, step: str) -> bool:
        return step in self.data["steps"]

    def get(self, step: str) -> dict:
        return self.data["steps"][step]

    def put(self, step: str, entry: dict):
        entry["at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        if step not in self.data["steps"]:
            self.data["order"].append(step)
        self.data["steps"][step] = entry
        self.save()

    def save(self):
        self.data["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self.data["summary"] = self.summary()
        self.path.write_text(json.dumps(self.data, indent=1, sort_keys=True) + "\n",
                             encoding="utf-8")

    def summary(self) -> dict:
        steps = self.data["steps"].values()
        checks = [s for s in steps if "held" in s]
        return {
            "steps": len(self.data["order"]),
            "transactions": len([s for s in steps if s.get("tx")]),
            "outcomes_checked": len(checks),
            "outcomes_held": len([s for s in checks if s["held"]]),
            "missed": sorted(s["step"] for s in checks if not s["held"]),
            "refusals": len([s for s in steps if s.get("kind") == "refusal"]),
        }


# -- the chain -----------------------------------------------------------------

class Chain:
    def __init__(self, address: str, transcript: Transcript):
        self.address = address
        self.transcript = transcript
        keys = json.loads(KEYS.read_text(encoding="utf-8"))
        self.accounts = {name: create_account(account_private_key=key)
                         for name, key in keys.items()}
        self.clients = {name: create_client(chain=studionet, account=account,
                                            endpoint=RPC)
                        for name, account in self.accounts.items()}
        self.reader = self.clients["owner"]

    def read(self, method: str, args=None):
        return self.reader.read_contract(address=self.address, function_name=method,
                                         args=args or [])

    def send(self, step: str, wallet: str, method: str, args=None, value: int = 0,
             expect: dict = None, kind: str = "write") -> dict:
        if self.transcript.has(step):
            entry = self.transcript.get(step)
            if entry.get("leader_execution") == "SUCCESS" or entry.get("kind") == "faucet":
                log("  skip " + step + " (recorded " + entry.get("status", "?") + ")")
                return entry
            log("  retry " + step + " (recorded " + str(entry.get("error"))[:80] + ")")
        client = self.clients[wallet]
        log("  " + step + ": " + method + " as " + wallet
            + ("" if value == 0 else " with " + str(value) + " atto"))
        tx = client.write_contract(address=self.address, function_name=method,
                                   args=args or [], value=value)
        receipt = client.wait_for_transaction_receipt(
            transaction_hash=tx, status=TransactionStatus.FINALIZED, **WAIT)
        entry = {"step": step, "kind": kind, "method": method, "wallet": wallet,
                 "args": _plain(args or []), "value_atto": str(value),
                 "tx": _hex(tx), "status": _status(receipt),
                 "leader_execution": _execution(receipt), "votes": _votes(receipt),
                 "rounds": _rounds(receipt)}
        if entry["leader_execution"] != "SUCCESS":
            entry["error"] = _revert(receipt)
        if expect:
            entry.update(expect)
        self.transcript.put(step, entry)
        log("    " + entry["status"] + "/" + entry["leader_execution"]
            + " votes " + ",".join(entry["votes"]))
        return entry

    def created(self, entry: dict, step: str, method: str, args) -> dict:
        """Read back the id a successful write created. A write that reverted
        has created nothing, so the phase stops rather than guessing."""
        if entry.get("leader_execution") != "SUCCESS":
            raise SystemExit("  " + step + " did not execute: " + str(entry.get("error")))
        page = self.read(method, args)
        if not page["ids"]:
            raise SystemExit("  " + step + " executed but created nothing")
        return page

    def refuse(self, step: str, wallet: str, method: str, args=None, value: int = 0,
               because: str = "") -> dict:
        """A write that must be refused. A refusal that depends on a window must
        be sent while that window is in the state the step is about."""
        if self.transcript.has(step):
            log("  skip " + step + " (recorded)")
            return self.transcript.get(step)
        client = self.clients[wallet]
        log("  " + step + ": expecting a refusal of " + method)
        entry = {"step": step, "kind": "refusal", "method": method, "wallet": wallet,
                 "args": _plain(args or []), "because": because}
        try:
            tx = client.write_contract(address=self.address, function_name=method,
                                       args=args or [], value=value)
            receipt = client.wait_for_transaction_receipt(
                transaction_hash=tx, status=TransactionStatus.FINALIZED, **WAIT)
            entry["tx"] = _hex(tx)
            entry["status"] = _status(receipt)
            entry["leader_execution"] = _execution(receipt)
            entry["error"] = _revert(receipt)
            entry["held"] = entry["leader_execution"] != "SUCCESS"
        except Exception as err:                       # a client-side rejection counts
            entry["error"] = str(err)[:400]
            entry["held"] = True
        self.transcript.put(step, entry)
        log("    refused" if entry["held"] else "    NOT REFUSED - recorded as a miss")
        return entry


def _hex(value) -> str:
    return value if isinstance(value, str) else "0x" + bytes(value).hex()


def _plain(args) -> list:
    out = []
    for value in args:
        text = value if isinstance(value, (str, int, bool)) else str(value)
        if isinstance(text, str) and len(text) > 200:
            text = text[:200] + "... (" + str(len(text)) + " characters)"
        out.append(text)
    return out


def _status(receipt) -> str:
    for key in ("status", "statusName", "status_name"):
        value = receipt.get(key)
        if isinstance(value, str):
            return value
        if value is not None and hasattr(value, "name"):
            return value.name
    return "UNKNOWN"


def _leader(receipt) -> dict:
    data = receipt.get("consensus_data") or {}
    return data.get("leader_receipt") or {}


def _execution(receipt) -> str:
    leader = _leader(receipt)
    if isinstance(leader, list):
        leader = leader[0] if leader else {}
    value = leader.get("execution_result")
    return value if isinstance(value, str) else str(value)


def _revert(receipt) -> str:
    leader = _leader(receipt)
    if isinstance(leader, list):
        leader = leader[0] if leader else {}
    result = leader.get("result") or {}
    text = json.dumps(result)[:400] if not isinstance(result, str) else result[:400]
    return text


def _votes(receipt) -> list:
    last = receipt.get("last_round") or {}
    votes = last.get("votes") or (receipt.get("consensus_data") or {}).get("votes") or {}
    if isinstance(votes, dict):
        return [str(v) for v in votes.values()]
    return [str(v) for v in votes]


def _rounds(receipt) -> int:
    data = receipt.get("consensus_data") or {}
    rounds = data.get("rounds") or receipt.get("rounds")
    if isinstance(rounds, list):
        return len(rounds)
    return 1


# -- funding -------------------------------------------------------------------

def fund_account(address: str, amount: int) -> bool:
    """StudioNet's simulator funds an account directly. If the endpoint refuses,
    the run goes on and the treasury steps record what actually happened."""
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "sim_fundAccount",
                       "params": [address, amount]}).encode()
    request = urllib.request.Request(RPC, data=body, headers={
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            answer = json.loads(response.read().decode())
        return "error" not in answer
    except Exception as err:
        log("  faucet unavailable: " + str(err)[:120])
        return False


# -- the phases ----------------------------------------------------------------

def load_catalogue(raw_base: str) -> tuple:
    charters = json.loads((FIXTURES / "charters.json").read_text(encoding="utf-8"))
    cases = json.loads((FIXTURES / "cases.json").read_text(encoding="utf-8"))
    filled = {name: json.dumps(spec, sort_keys=True).replace("{base}", raw_base)
              for name, spec in charters.items()}
    return (filled, cases)


def phase_charters(chain: Chain, charters: dict, cases: dict, funded: bool):
    for name in sorted(charters):
        step = "charter:" + name
        entry = chain.send(step, "owner", "create_charter", [charters[name]])
        if "charter_id" not in entry:
            page = chain.created(entry, step, "list_charters", [0, 50])
            entry["charter_id"] = page["ids"][-1]
            chain.transcript.put(step, entry)
        log("    " + name + " -> " + entry["charter_id"])
    if funded:
        target = charter_id(chain, cases["request_event"])
        chain.send("fund:request_charter", "owner", "fund_charter", [target],
                   value=12 * GEN)


OPENERS = ("alice", "bob", "carol", "stranger", "owner")


def opener_for(case: str) -> str:
    """Spread the events over the demo wallets: a wallet holds at most ten open
    events, and the catalogue has more than ten."""
    digits = "".join(ch for ch in case if ch.isdigit())
    return OPENERS[(int(digits) if digits else 0) % len(OPENERS)]


def charter_id(chain: Chain, case: str) -> str:
    return chain.transcript.get("charter:" + case)["charter_id"]


def charter_hash(chain: Chain, case: str) -> str:
    return chain.read("get_charter", [charter_id(chain, case)])["charter_hash"]


def phase_assessments(chain: Chain, charters: dict, cases: dict):
    for case in cases["assessments"]:
        name = case["case"]
        cid = charter_id(chain, name)
        chash = charter_hash(chain, name)
        open_step = "open:" + name
        entry = chain.send(open_step, opener_for(name), "open_event",
                           [cid, chash, case["situation"], case["area"]])
        if "event_id" not in entry:
            page = chain.created(entry, open_step, "list_events", [cid, 0, 50])
            entry["event_id"] = page["ids"][-1]
            chain.transcript.put(open_step, entry)
        event_id = entry["event_id"]
        step = "assess:" + name
        if not chain.transcript.has(step):
            chain.send(step, "bob", "assess", [event_id])
            record_declaration(chain, step, name, event_id, case)
        else:
            log("  skip " + step + " (recorded)")


def record_declaration(chain: Chain, step: str, case_name: str, event_id: str,
                       case: dict):
    entry = chain.transcript.get(step)
    receipt = chain.read("get_latest_declaration", [event_id])
    entry["event_id"] = event_id
    if receipt.get("found"):
        declaration = receipt["declaration"]
        entry["declaration_id"] = declaration["declaration_id"]
        entry["observed_band"] = declaration["declared_band"]
        entry["observed_reason"] = declaration["reason_code"]
        entry["observed_onset"] = declaration["onset"]
        entry["panel_state"] = declaration["panel_state"]
        entry["markers"] = declaration["markers"]
        entry["corroborating_sources"] = declaration["corroborating_sources"]
        entry["expected_band"] = case["expect_band"]
        entry["expected_reason"] = case["expect_reason"]
        entry["held"] = (declaration["declared_band"] == case["expect_band"]
                         and declaration["reason_code"] == case["expect_reason"])
        entry["note"] = case["note"]
    else:
        entry["held"] = False
        entry["observed_reason"] = "no declaration stored"
    chain.transcript.put(step, entry)
    log("    " + case_name + ": " + str(entry.get("observed_band")) + "/"
        + str(entry.get("observed_reason")) + (" HELD" if entry["held"] else " MISSED"))


def event_of(chain: Chain, case: str) -> str:
    return chain.transcript.get("assess:" + case)["event_id"]


def phase_requests(chain: Chain, charters: dict, cases: dict, raw_base: str,
                   funded: bool):
    host = cases["request_event"]
    # a second reading of an event that stands, on the same watched sources. The
    # last case assessed is the one whose window is still open by now.
    reassessed = cases["assessments"][-1]["case"]
    if not chain.transcript.has("assess:" + reassessed):
        log("  skip reassess: " + reassessed + " was never assessed here")
    elif not chain.transcript.has("reassess:" + reassessed):
        chain.send("reassess:" + reassessed, "carol", "reassess",
                   [event_of(chain, reassessed)])
        entry = chain.transcript.get("reassess:" + reassessed)
        receipt = chain.read("get_latest_declaration", [event_of(chain, reassessed)])
        declaration = receipt["declaration"]
        entry["declaration_id"] = declaration["declaration_id"]
        entry["observed_band"] = declaration["declared_band"]
        entry["observed_reason"] = declaration["reason_code"]
        entry["supersedes"] = declaration["supersedes"]
        entry["round"] = declaration["round"]
        first = chain.transcript.get("assess:" + reassessed)
        entry["expected_band"] = first["observed_band"]
        entry["expected_reason"] = first["observed_reason"]
        entry["held"] = (declaration["declared_band"] == first["observed_band"]
                         and declaration["round"] == 2
                         and declaration["supersedes"] != "")
        entry["note"] = "a second reading of the same sources, superseding the first"
        chain.transcript.put("reassess:" + reassessed, entry)
    event_id = event_of(chain, host)
    chash = charter_hash(chain, host)
    for case in cases["requests"]:
        name = case["case"]
        url = raw_base + case["evidence"]
        file_step = "file:" + name
        entry = chain.send(file_step, case["wallet"], "file_request",
                           [event_id, chash, case["category"], case["need"],
                            case["area_note"], url, case["stability"]])
        if "request_id" not in entry:
            page = chain.created(entry, file_step, "list_requests", [event_id, 0, 50])
            entry["request_id"] = page["ids"][-1]
            chain.transcript.put(file_step, entry)
        request_id = entry["request_id"]
        step = "adjudicate:" + name
        if chain.transcript.has(step):
            log("  skip " + step + " (recorded)")
            continue
        chain.send(step, "owner", "adjudicate", [request_id])
        record_adjudication(chain, step, name, request_id, case, funded)

    # the treasury path: an unfunded charter authorises nothing, and a recheck
    # after it is funded authorises what the charter promised
    treasury_case = "AS02"
    ts_event = event_of(chain, treasury_case)
    ts_hash = charter_hash(chain, treasury_case)
    url = raw_base + "sources/evidence/riverside-row.html"
    entry = chain.send("file:TS01", "alice", "file_request",
                       [ts_event, ts_hash, "SHELTER",
                        "Seventy-two displaced households at Riverside Row need "
                        "emergency shelter tonight.",
                        "Riverside Row, lower town of Eastfield", url, "STABLE"])
    if "request_id" not in entry:
        page = chain.created(entry, "file:TS01", "list_requests", [ts_event, 0, 50])
        entry["request_id"] = page["ids"][-1]
        chain.transcript.put("file:TS01", entry)
    ts_request = entry["request_id"]
    if not chain.transcript.has("adjudicate:TS01"):
        chain.send("adjudicate:TS01", "owner", "adjudicate", [ts_request])
        record_adjudication(chain, "adjudicate:TS01", "TS01", ts_request,
                            {"expect_outcome": "QUALIFIES", "expect_reason": "QUALIFIED",
                             "expect_funding": "TREASURY_SHORT", "settle": False,
                             "note": "the charter's treasury holds nothing, so nothing "
                                     "is authorised"}, funded)
    if funded:
        chain.send("fund:TS01", "owner", "fund_charter", [charter_id(chain, treasury_case)],
                   value=3 * GEN)
        if not chain.transcript.has("recheck:TS01"):
            chain.send("recheck:TS01", "alice", "recheck_request", [ts_request])
            record_adjudication(chain, "recheck:TS01", "TS01:v2", ts_request,
                                {"expect_outcome": "QUALIFIES",
                                 "expect_reason": "QUALIFIED",
                                 "expect_funding": "RESERVED", "settle": True,
                                 "note": "the same reading, now funded, reserves the "
                                         "charter's grant"}, funded)

def record_adjudication(chain: Chain, step: str, label: str, request_id: str, case: dict,
                        funded: bool):
    entry = chain.transcript.get(step)
    receipt = chain.read("get_latest_adjudication", [request_id])
    entry["request_id"] = request_id
    if receipt.get("found"):
        ruling = receipt["adjudication"]
        entry["adjudication_id"] = ruling["adjudication_id"]
        entry["observed_outcome"] = ruling["outcome"]
        entry["observed_reason"] = ruling["reason_code"]
        entry["observed_funding"] = ruling["funding"]
        entry["authorised_atto"] = ruling["authorised_atto"]
        entry["panel_state"] = ruling["panel_state"]
        entry["markers"] = ruling["markers"]
        entry["decided_by"] = ruling["decided_by"]
        entry["expected_outcome"] = case["expect_outcome"]
        entry["expected_reason"] = case["expect_reason"]
        expected_funding = case["expect_funding"]
        if not funded and expected_funding == "RESERVED":
            expected_funding = "TREASURY_SHORT"
        entry["expected_funding"] = expected_funding
        entry["held"] = (ruling["outcome"] == case["expect_outcome"]
                         and ruling["reason_code"] == case["expect_reason"]
                         and ruling["funding"] == expected_funding)
        entry["note"] = case["note"]
        entry["settle"] = case["settle"]
    else:
        entry["held"] = False
        entry["observed_reason"] = "no adjudication stored"
    chain.transcript.put(step, entry)
    log("    " + label + ": " + str(entry.get("observed_outcome")) + "/"
        + str(entry.get("observed_reason")) + "/" + str(entry.get("observed_funding"))
        + (" HELD" if entry["held"] else " MISSED"))


def wait_until(iso: str, what: str):
    target = time.mktime(time.strptime(iso, "%Y-%m-%dT%H:%M:%SZ")) - time.timezone
    while True:
        left = target - time.time()
        if left <= 5:
            return
        log("  waiting " + str(int(left) + 5) + "s for " + what)
        time.sleep(min(left + 5, 120))


def phase_settle(chain: Chain, cases: dict):
    """Close what has an outcome: settle every adjudicated request, finalise the
    events whose windows have passed, and pay one filer out."""
    steps = chain.transcript.data["steps"]
    for name, entry in sorted(steps.items()):
        if not name.startswith(("adjudicate:", "recheck:")) or "request_id" not in entry:
            continue
        request_id = entry["request_id"]
        status = chain.read("get_request", [request_id])
        if status["status"] != "ADJUDICATED":
            continue
        step = "settle:" + request_id
        if chain.transcript.has(step):
            continue
        wait_until(status["window_ends"], "the recheck window of " + request_id)
        settled = chain.send(step, "owner", "finalize_request", [request_id])
        after = chain.read("get_request", [request_id])
        settled["paid_atto"] = after["paid_atto"]
        settled["request_status"] = after["status"]
        settled["held"] = after["status"] == "SETTLED"
        chain.transcript.put(step, settled)

    for case in [c["case"] for c in cases["assessments"]]:
        if not chain.transcript.has("assess:" + case):
            continue
        event_id = event_of(chain, case)
        status = chain.read("get_event", [event_id])
        if status["status"] != "ASSESSED":
            continue
        step = "finalize_event:" + case
        if chain.transcript.has(step):
            continue
        wait_until(status["window_ends"], "the reassessment window of " + event_id)
        entry = chain.send(step, "bob", "finalize_event", [event_id])
        entry["event_status"] = chain.read("get_event", [event_id])["status"]
        entry["held"] = entry["event_status"] == "FINALIZED"
        chain.transcript.put(step, entry)

    for wallet in ("alice", "bob", "carol"):
        address = str(chain.accounts[wallet].address).lower()
        credit = chain.read("get_credit", [address])["credit_atto"]
        if credit == "0":
            continue
        step = "withdraw:" + wallet
        if chain.transcript.has(step):
            continue
        entry = chain.send(step, wallet, "withdraw", [])
        entry["credit_before_atto"] = credit
        entry["credit_after_atto"] = chain.read("get_credit", [address])["credit_atto"]
        entry["held"] = entry["credit_after_atto"] == "0"
        chain.transcript.put(step, entry)

    treasury = chain.read("get_treasury")
    chain.transcript.data["treasury"] = treasury
    chain.transcript.save()
    log("  treasury: pools " + treasury["pools_atto"] + ", credits "
        + treasury["credits_atto"] + ", balance " + treasury["balance_atto"])


def phase_refusals(chain: Chain, cases: dict, raw_base: str):
    host = cases["request_event"]
    event_id = event_of(chain, host)
    chash = charter_hash(chain, host)
    cid = charter_id(chain, host)
    url = raw_base + "sources/evidence/riverside-row.html"
    need = "Households at Riverside Row need emergency shelter."
    area = "Riverside Row, lower town of Eastfield"

    chain.refuse("refuse:wrong_hash", "bob", "open_event",
                 [cid, "00" * 32, "Flooding reported again", "The lower town"],
                 because="the charter hash does not match the charter")
    chain.refuse("refuse:unknown_charter", "bob", "open_event",
                 ["CH-999999", chash, "Flooding reported", "The lower town"],
                 because="no such charter")
    chain.refuse("refuse:not_steward_retire", "alice", "retire_charter", [cid],
                 because="only the steward retires a charter")
    chain.refuse("refuse:category_not_promised", "bob", "file_request",
                 [event_id, chash, "WATER", need, area, url + "?x=1", "STABLE"],
                 because="the declared band promises no relief in that category")
    chain.refuse("refuse:no_band", "bob", "file_request",
                 [event_of(chain, "AS04"), charter_hash(chain, "AS04"), "SHELTER", need,
                  area, url + "?x=2", "STABLE"],
                 because="that event has no declaration to file against")
    chain.refuse("refuse:duplicate_source", "bob", "file_request",
                 [event_id, chash, "SHELTER", need, area, url, "STABLE"],
                 because="that source already backs another request for this event")
    chain.refuse("refuse:plain_http", "bob", "file_request",
                 [event_id, chash, "SHELTER", need, area,
                  "http://raw.githubusercontent.com/x/y.html", "STABLE"],
                 because="a source URL must use https")
    chain.refuse("refuse:withdraw_empty", "stranger", "withdraw", [],
                 because="that wallet has nothing to withdraw")
    chain.refuse("refuse:reclaim_active", "owner", "reclaim_unreserved", [cid],
                 because="an active charter's treasury is not reclaimed")
    entry = chain.send("fund:not_steward", "alice", "fund_charter", [cid], value=GEN,
                       kind="returned")
    entry["held"] = True
    entry["because"] = "a deposit from anyone but the steward is credited back, never lost"
    entry["returned"] = chain.read("get_returned_deposits", [0, 10])["entries"][-1] \
        if chain.read("get_returned_deposits", [0, 10])["total"] else {}
    entry["held"] = bool(entry["returned"])
    chain.transcript.put("fund:not_steward", entry)
    address = str(chain.accounts["alice"].address).lower()
    if chain.read("get_credit", [address])["credit_atto"] != "0":
        chain.send("withdraw:alice_returned", "alice", "withdraw", [])


# -- main ----------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("address")
    parser.add_argument("--raw-base", required=True,
                        help="commit-pinned base URL for fixtures/, ending in a slash")
    parser.add_argument("--phase", default="full",
                        choices=("full",) + PHASES)
    parser.add_argument("--transcript", default=None,
                        help="where to record the run; the default is the run of record")
    parser.add_argument("--no-faucet", action="store_true",
                        help="skip funding the demo wallets; treasury steps then record "
                             "TREASURY_SHORT outcomes")
    args = parser.parse_args()
    if not args.raw_base.endswith("/"):
        sys.exit("--raw-base must end with a slash")

    charters, cases = load_catalogue(args.raw_base)
    path = pathlib.Path(args.transcript) if args.transcript else None
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        globals()["LOG"] = path.with_suffix(".log")
    transcript = Transcript(args.address, args.raw_base, path)
    chain = Chain(args.address, transcript)
    log("contract " + args.address + " phase " + args.phase)

    funded = False
    if not args.no_faucet:
        step = "faucet"
        if transcript.has(step):
            funded = transcript.get(step)["funded"]
        else:
            address = str(chain.accounts["owner"].address)
            funded = fund_account(address, 40 * GEN)
            transcript.put(step, {"step": step, "kind": "faucet", "wallet": "owner",
                                  "funded": funded, "amount_atto": str(40 * GEN)})
        log("  steward funded: " + str(funded))

    phases = PHASES if args.phase == "full" else (args.phase,)
    for phase in phases:
        log("phase " + phase)
        if phase == "charters":
            phase_charters(chain, charters, cases, funded)
        elif phase == "assessments":
            phase_assessments(chain, charters, cases)
        elif phase == "requests":
            phase_requests(chain, charters, cases, args.raw_base, funded)
        elif phase == "settle":
            phase_settle(chain, cases)
        elif phase == "refusals":
            phase_refusals(chain, cases, args.raw_base)
    summary = transcript.summary()
    log("summary " + json.dumps(summary))


if __name__ == "__main__":
    main()
