"""Reads against the deployment of record.

These tests do not re-run consensus: they check that the contract on chain is
the contract in this repository, that it answers, and that what the live run
recorded is what the chain still holds. One write is opt-in
(`SUCCOUR_LIVE_WRITES=1`) because it sends a real transaction.

    python -m pytest tests/integration -q
"""

import base64
import hashlib
import json
import os
import pathlib
import sys
import urllib.request

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

RECORD = ROOT / "deploy" / "deployment.json"
TRANSCRIPT = ROOT / "deploy" / "live_run_transcript.json"
CONTRACT = ROOT / "contracts" / "succour.py"
RPC = "https://studio.genlayer.com/api"

pytestmark = pytest.mark.skipif(not RECORD.exists(),
                                reason="no deployment of record yet")


def rpc(method: str, params: list):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method,
                       "params": params}).encode()
    request = urllib.request.Request(RPC, data=body, headers={
        "Content-Type": "application/json", "User-Agent": "succour-integration"})
    for attempt in range(6):
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                answer = json.loads(response.read().decode())
            if "error" in answer and "-32029" in json.dumps(answer["error"]):
                raise RuntimeError("rate limited")
            return answer
        except Exception:
            if attempt == 5:
                raise
            import time
            time.sleep(5 * (attempt + 1))


@pytest.fixture(scope="module")
def record():
    return json.loads(RECORD.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def client(record):
    import studionet_transport  # noqa: F401 - retries RPC transport failures
    from genlayer_py import create_account, create_client
    from genlayer_py.chains import studionet
    key = json.loads((ROOT / ".data" / "demo_wallets.json").read_text(encoding="utf-8"))
    account = create_account(account_private_key=key["owner"])
    return create_client(chain=studionet, account=account, endpoint=RPC)


def read(client, record, method, args=None):
    return client.read_contract(address=record["contract_address"],
                                function_name=method, args=args or [])


def test_the_deployed_source_is_this_repository(record):
    answer = rpc("gen_getContractCode", [record["contract_address"]])
    raw = answer.get("result")
    deployed = base64.b64decode(raw) if isinstance(raw, str) and "\n" not in raw[:40] \
        else str(raw).encode()
    if hashlib.sha256(deployed).hexdigest() != record["source_sha256"]:
        deployed = str(raw).encode()
    assert hashlib.sha256(deployed).hexdigest() == record["source_sha256"]
    assert record["source_sha256"] == hashlib.sha256(CONTRACT.read_bytes()).hexdigest()
    assert record["byte_identical"] is True


def test_the_schema_has_every_method(record):
    schema = rpc("gen_getContractSchema", [record["contract_address"]]).get("result") or {}
    methods = schema.get("methods") or {}
    assert len(methods) == 35
    for name in ("create_charter", "assess", "file_request", "adjudicate",
                 "finalize_request", "withdraw", "get_latest_declaration"):
        assert name in methods


def test_the_config_on_chain_matches_the_contract(client, record):
    config = read(client, record, "get_config")
    assert config["contract_version"] == "0.1.0"
    assert config["hazards"] == ["EARTHQUAKE", "FLOOD", "STORM", "WILDFIRE", "DROUGHT",
                                 "OTHER"]
    assert "BAND_DECLARED" in config["assess_reasons"]
    assert config["caps"]["monitors"] == 3 and config["caps"]["bands"] == 3


def test_the_treasury_is_accounted_for(client, record):
    treasury = read(client, record, "get_treasury")
    assert int(treasury["accounted_atto"]) == int(treasury["pools_atto"]) \
        + int(treasury["credits_atto"])
    assert int(treasury["balance_atto"]) >= int(treasury["accounted_atto"])


@pytest.mark.skipif(not TRANSCRIPT.exists(), reason="no live run yet")
def test_every_declaration_the_run_recorded_is_still_on_chain(client, record):
    steps = json.loads(TRANSCRIPT.read_text(encoding="utf-8"))["steps"]
    checked = 0
    for name, entry in sorted(steps.items()):
        if not name.startswith("assess:") or "declaration_id" not in entry:
            continue
        receipt = read(client, record, "get_declaration", [entry["declaration_id"]])
        assert receipt["found"], name
        declaration = receipt["declaration"]
        assert declaration["declared_band"] == entry["observed_band"], name
        assert declaration["reason_code"] == entry["observed_reason"], name
        checked += 1
    assert checked > 0


@pytest.mark.skipif(not TRANSCRIPT.exists(), reason="no live run yet")
def test_every_adjudication_the_run_recorded_is_still_on_chain(client, record):
    steps = json.loads(TRANSCRIPT.read_text(encoding="utf-8"))["steps"]
    checked = 0
    for name, entry in sorted(steps.items()):
        if not name.startswith(("adjudicate:", "recheck:")) or "adjudication_id" not in entry:
            continue
        receipt = read(client, record, "get_adjudication", [entry["adjudication_id"]])
        assert receipt["found"], name
        ruling = receipt["adjudication"]
        assert ruling["outcome"] == entry["observed_outcome"], name
        assert ruling["reason_code"] == entry["observed_reason"], name
        assert ruling["authorised_atto"] == entry["authorised_atto"], name
        checked += 1
    assert checked > 0


@pytest.mark.skipif(os.environ.get("SUCCOUR_LIVE_WRITES") != "1",
                    reason="set SUCCOUR_LIVE_WRITES=1 to send one transaction")
def test_a_charter_can_still_be_published(client, record):
    from genlayer_py.types import TransactionStatus
    charter = json.loads((ROOT / "fixtures" / "charters.json").read_text(encoding="utf-8"))
    text = json.dumps(charter["AS01"], sort_keys=True).replace(
        "{base}", "https://raw.githubusercontent.com/Hemmy1417/Succour/main/fixtures/")
    before = read(client, record, "get_stats")["charters"]
    tx = client.write_contract(address=record["contract_address"],
                              function_name="create_charter", args=[text])
    client.wait_for_transaction_receipt(transaction_hash=tx,
                                       status=TransactionStatus.FINALIZED,
                                       interval=5000, retries=240)
    assert read(client, record, "get_stats")["charters"] == before + 1
