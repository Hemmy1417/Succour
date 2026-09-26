"""The lifecycle, the declarations, the relief and the views.

Each test drives the contract the way a caller would - publish a charter, fund
it, open an event, assess it, file a request, adjudicate, settle - and checks
what the contract stored, not what the harness said.
"""

from tests.direct import support as s

LATER = "2026-09-26T14:00:00Z"
MUCH_LATER = "2026-09-27T14:00:00Z"


# -- the charter ---------------------------------------------------------------

def test_a_charter_is_published_with_its_hash(court, direct_vm, direct_alice):
    charter_id = s.published(court, direct_vm, direct_alice)
    info = court.get_charter(charter_id)
    assert info["found"] and charter_id == "CH-000001"
    assert info["steward"] == direct_alice.as_hex.lower()
    assert info["status"] == "ACTIVE"
    assert len(info["charter_hash"]) == 64
    assert info["charter"]["hazard"] == "FLOOD"
    assert info["pool_atto"] == "0" and info["paid_atto"] == "0"


def test_the_stored_charter_is_the_canonical_form_not_the_text_sent(court, direct_vm,
                                                                   direct_alice, mod):
    charter_id = s.published(court, direct_vm, direct_alice)
    info = court.get_charter(charter_id)
    assert info["charter_hash"] == mod._sha256_hex(mod._canonical(info["charter"]))


def test_a_monitor_url_is_stored_canonicalised(court, direct_vm, direct_alice):
    charter_id = s.published(court, direct_vm, direct_alice,
                             monitors=[{"source_id": "M1",
                                        "url": "https://Alerts.Example.Gov/basin/"
                                               "flood-bulletin",
                                        "stability": "STABLE",
                                        "description": "The provincial flood bulletin"}],
                             bands=[s.band("watch", "Watch", "A flood warning is in force.",
                                           1, [s.relief("SHELTER", s.GEN, 5)])])
    monitors = court.get_charter(charter_id)["charter"]["monitors"]
    assert monitors[0]["url"] == s.M1_URL


def test_charter_ids_run_in_order(court, direct_vm, direct_alice):
    first = s.published(court, direct_vm, direct_alice)
    second = s.published(court, direct_vm, direct_alice)
    assert (first, second) == ("CH-000001", "CH-000002")
    assert court.list_charters(0, 10)["ids"] == [first, second]


def test_retiring_a_charter_stops_new_events(court, direct_vm, direct_alice):
    charter_id = s.published(court, direct_vm, direct_alice)
    charter_hash = court.get_charter(charter_id)["charter_hash"]
    assert court.retire_charter(charter_id) == "RETIRED"
    with direct_vm.expect_revert("the charter is retired"):
        court.open_event(charter_id, charter_hash, "Flooding reported", "Eastfield")


def test_get_config_reports_the_vocabularies(court):
    config = court.get_config()
    assert config["contract_version"] == "0.1.0"
    assert "FLOOD" in config["hazards"] and "SHELTER" in config["categories"]
    assert "BAND_DECLARED" in config["assess_reasons"]
    assert "QUALIFIED" in config["request_reasons"]
    assert config["caps"]["monitors"] == 3


# -- the treasury --------------------------------------------------------------

def test_funding_a_charter_fills_its_pool(court, direct_vm, direct_alice):
    charter_id = s.published(court, direct_vm, direct_alice)
    assert s.funded(court, direct_vm, direct_alice, charter_id, 4 * s.GEN) == str(4 * s.GEN)
    assert court.get_charter(charter_id)["pool_atto"] == str(4 * s.GEN)
    assert court.get_treasury()["pools_atto"] == str(4 * s.GEN)


def test_the_steward_reclaims_only_after_retiring(court, direct_vm, direct_alice):
    charter_id = s.published(court, direct_vm, direct_alice)
    s.funded(court, direct_vm, direct_alice, charter_id, 4 * s.GEN)
    with direct_vm.expect_revert("retire the charter first"):
        court.reclaim_unreserved(charter_id)
    court.retire_charter(charter_id)
    assert court.reclaim_unreserved(charter_id) == str(4 * s.GEN)
    assert court.get_charter(charter_id)["pool_atto"] == "0"
    assert court.get_credit(direct_alice.as_hex.lower())["credit_atto"] == str(4 * s.GEN)


def test_withdraw_pays_once(court, direct_vm, direct_alice):
    charter_id = s.published(court, direct_vm, direct_alice)
    s.funded(court, direct_vm, direct_alice, charter_id, s.GEN)
    court.retire_charter(charter_id)
    court.reclaim_unreserved(charter_id)
    assert court.withdraw() == str(s.GEN)
    with direct_vm.expect_revert("nothing to withdraw"):
        court.withdraw()


def test_a_refused_deposit_is_credited_back_never_raised(court, direct_vm, direct_alice,
                                                         direct_bob):
    charter_id = s.published(court, direct_vm, direct_alice)
    direct_vm.sender = direct_bob
    direct_vm.value = 2 * s.GEN
    try:
        answer = court.fund_charter(charter_id)
    finally:
        direct_vm.value = 0
    assert answer.startswith("RETURNED: only the charter's steward")
    assert court.get_credit(direct_bob.as_hex.lower())["credit_atto"] == str(2 * s.GEN)
    assert court.get_charter(charter_id)["pool_atto"] == "0"
    entries = court.get_returned_deposits(0, 10)["entries"]
    assert entries[0]["method"] == "fund_charter"


# -- opening and assessing an event -------------------------------------------

def test_an_event_commits_to_the_charter_it_was_opened_against(court, direct_vm,
                                                               direct_alice, direct_bob):
    charter_id = s.published(court, direct_vm, direct_alice)
    charter_hash = court.get_charter(charter_id)["charter_hash"]
    direct_vm.sender = direct_bob
    event_id = court.open_event(charter_id, charter_hash, "Flooding reported in the lower "
                                                          "town", "The lower town of "
                                                                  "Eastfield")
    event = court.get_event(event_id)
    assert event["charter_hash"] == charter_hash and event["status"] == "OPEN"
    assert event["opener"] == direct_bob.as_hex.lower()
    assert event["declared_band"] == "" and event["window_ends"] == "2026-09-26T13:00:00Z"


def test_an_event_refuses_a_charter_hash_that_does_not_match(court, direct_vm, direct_alice):
    charter_id = s.published(court, direct_vm, direct_alice)
    with direct_vm.expect_revert("charter_hash does not match"):
        court.open_event(charter_id, "00" * 32, "Flooding reported", "Eastfield")


def test_two_corroborating_sources_declare_the_band_they_support(court, direct_vm,
                                                                direct_alice, direct_bob):
    charter_id = s.published(court, direct_vm, direct_alice)
    charter_hash = court.get_charter(charter_id)["charter_hash"]
    s.serve_all(direct_vm)
    event_id, declaration_id = s.declared(court, direct_vm, direct_bob, charter_id,
                                          charter_hash)
    receipt = court.get_declaration(declaration_id)["declaration"]
    assert receipt["declared_band"] == "declared"
    assert receipt["band_label"] == "Declared"
    assert receipt["reason_code"] == "BAND_DECLARED"
    assert receipt["onset"] == s.ONSET_DATE
    assert receipt["onset_outcome"] == "CURRENT"
    assert receipt["min_corroboration"] == 2
    assert receipt["corroborating_sources"] == ["M1", "M2"]
    assert receipt["corroboration_compared"] is False
    assert court.get_event(event_id)["declared_band"] == "declared"


def test_a_band_met_by_one_source_when_two_are_required_falls_short(court, direct_vm,
                                                                    direct_alice,
                                                                    direct_bob):
    charter_id = s.published(court, direct_vm, direct_alice)
    charter_hash = court.get_charter(charter_id)["charter_hash"]
    s.serve_all(direct_vm)
    said = s.assessment_said(watch=("NOT_MET", ""), declared=("MET", "M1"))
    _event_id, declaration_id = s.declared(court, direct_vm, direct_bob, charter_id,
                                           charter_hash, subjects=said)
    receipt = court.get_declaration(declaration_id)["declaration"]
    assert receipt["declared_band"] == "NONE"
    assert receipt["reason_code"] == "CORROBORATION_SHORT"
    assert receipt["short_band"] == "declared"


def test_a_milder_band_is_declared_when_the_stronger_one_falls_short(court, direct_vm,
                                                                     direct_alice,
                                                                     direct_bob):
    charter_id = s.published(court, direct_vm, direct_alice)
    charter_hash = court.get_charter(charter_id)["charter_hash"]
    s.serve_all(direct_vm)
    said = s.assessment_said(watch=("MET", "M1"), declared=("MET", "M1"))
    _event_id, declaration_id = s.declared(court, direct_vm, direct_bob, charter_id,
                                           charter_hash, subjects=said)
    receipt = court.get_declaration(declaration_id)["declaration"]
    assert receipt["declared_band"] == "watch"
    assert receipt["reason_code"] == "BAND_DECLARED"
    assert receipt["relief"][0]["category"] == "SHELTER"


def test_the_severest_band_met_with_corroboration_wins(court, direct_vm, direct_alice,
                                                       direct_bob):
    charter_id = s.published(court, direct_vm, direct_alice)
    charter_hash = court.get_charter(charter_id)["charter_hash"]
    s.serve_all(direct_vm)
    said = s.assessment_said(severe=("MET", "M1M2"))
    _event_id, declaration_id = s.declared(court, direct_vm, direct_bob, charter_id,
                                           charter_hash, subjects=said)
    assert court.get_declaration(declaration_id)["declaration"]["declared_band"] == "severe"


def test_a_band_the_panel_could_not_read_does_not_block_a_milder_one(court, direct_vm,
                                                                     direct_alice,
                                                                     direct_bob):
    charter_id = s.published(court, direct_vm, direct_alice)
    charter_hash = court.get_charter(charter_id)["charter_hash"]
    s.serve_all(direct_vm)
    said = s.assessment_said(severe=("UNCLEAR", ""))
    _event_id, declaration_id = s.declared(court, direct_vm, direct_bob, charter_id,
                                           charter_hash, subjects=said)
    assert court.get_declaration(declaration_id)["declaration"]["declared_band"] == "declared"


def test_no_band_met_declares_nothing(court, direct_vm, direct_alice, direct_bob):
    charter_id = s.published(court, direct_vm, direct_alice)
    charter_hash = court.get_charter(charter_id)["charter_hash"]
    s.serve_all(direct_vm)
    said = s.assessment_said(watch=("NOT_MET", ""), declared=("NOT_MET", ""))
    _event_id, declaration_id = s.declared(court, direct_vm, direct_bob, charter_id,
                                           charter_hash, subjects=said)
    receipt = court.get_declaration(declaration_id)["declaration"]
    assert receipt["declared_band"] == "NONE" and receipt["reason_code"] == "NO_BAND_MET"
    assert receipt["relief"] == []


def test_a_hazard_mismatch_is_decided_before_any_band(court, direct_vm, direct_alice,
                                                      direct_bob):
    charter_id = s.published(court, direct_vm, direct_alice)
    charter_hash = court.get_charter(charter_id)["charter_hash"]
    s.serve_all(direct_vm)
    said = s.assessment_said(hazard="MISMATCH")
    _event_id, declaration_id = s.declared(court, direct_vm, direct_bob, charter_id,
                                           charter_hash, subjects=said)
    receipt = court.get_declaration(declaration_id)["declaration"]
    assert receipt["reason_code"] == "HAZARD_MISMATCH"
    assert receipt["declared_band"] == "NONE" and receipt["onset"] == ""


def test_an_undated_signal_declares_nothing(court, direct_vm, direct_alice, direct_bob):
    charter_id = s.published(court, direct_vm, direct_alice)
    charter_hash = court.get_charter(charter_id)["charter_hash"]
    s.serve_all(direct_vm)
    said = s.assessment_said(onset="")
    _event_id, declaration_id = s.declared(court, direct_vm, direct_bob, charter_id,
                                           charter_hash, subjects=said)
    receipt = court.get_declaration(declaration_id)["declaration"]
    assert receipt["reason_code"] == "SIGNAL_UNDATED"
    assert receipt["onset"] == "" and receipt["onset_outcome"] == "UNDATED"


def test_a_stale_signal_declares_nothing(court, direct_vm, direct_alice, direct_bob):
    charter_id = s.published(court, direct_vm, direct_alice)
    charter_hash = court.get_charter(charter_id)["charter_hash"]
    s.serve_all(direct_vm, {s.M1_URL: s.bulletin("1 September 2026"),
                            s.M2_URL: s.GAUGES})
    said = s.assessment_said(onset="2026-09-01", onset_words="1 September 2026")
    _event_id, declaration_id = s.declared(court, direct_vm, direct_bob, charter_id,
                                           charter_hash, subjects=said)
    receipt = court.get_declaration(declaration_id)["declaration"]
    assert receipt["reason_code"] == "SIGNAL_STALE"
    assert receipt["onset_outcome"] == "STALE" and receipt["onset"] == "2026-09-01"


def test_an_onset_far_in_the_past_is_not_this_event(court, direct_vm, direct_alice,
                                                   direct_bob):
    charter_id = s.published(court, direct_vm, direct_alice, max_age_seconds=0)
    charter_hash = court.get_charter(charter_id)["charter_hash"]
    s.serve_all(direct_vm, {s.M1_URL: s.bulletin("2 January 2026")})
    said = s.assessment_said(onset="2026-01-02", onset_words="2 January 2026")
    _event_id, declaration_id = s.declared(court, direct_vm, direct_bob, charter_id,
                                           charter_hash, subjects=said)
    receipt = court.get_declaration(declaration_id)["declaration"]
    assert receipt["reason_code"] == "SIGNAL_PREDATES_WINDOW"


def test_no_readable_source_is_an_unavailability_not_a_refusal(court, direct_vm,
                                                               direct_alice, direct_bob):
    charter_id = s.published(court, direct_vm, direct_alice)
    charter_hash = court.get_charter(charter_id)["charter_hash"]
    s.serve_all(direct_vm, {s.M1_URL: None, s.M2_URL: None})
    _event_id, declaration_id = s.declared(court, direct_vm, direct_bob, charter_id,
                                           charter_hash, subjects={})
    receipt = court.get_declaration(declaration_id)["declaration"]
    assert receipt["reason_code"] == "SOURCES_UNAVAILABLE"
    assert receipt["panel_state"] == "SKIPPED"
    assert [x["status"] for x in receipt["sources"]] == ["NOT_FOUND", "NOT_FOUND"]


def test_one_unreadable_source_still_lets_the_others_speak(court, direct_vm, direct_alice,
                                                           direct_bob):
    charter_id = s.published(court, direct_vm, direct_alice,
                             bands=[s.band("watch", "Watch",
                                           "A flood warning is in force.", 1,
                                           [s.relief("SHELTER", s.GEN, 5)])])
    charter_hash = court.get_charter(charter_id)["charter_hash"]
    s.serve_all(direct_vm, {s.M2_URL: None})
    said = {"HAZARD_MATCH": s.said("MATCHES", [("M1", s.HAZARD_LINE)]),
            "ONSET": s.said("DATED", [("M1", s.ONSET_LINE)], date=s.ONSET_DATE),
            "BAND_WATCH": s.said("MET", [("M1", s.WATCH_LINE)])}
    _event_id, declaration_id = s.declared(court, direct_vm, direct_bob, charter_id,
                                           charter_hash, subjects=said)
    receipt = court.get_declaration(declaration_id)["declaration"]
    assert receipt["declared_band"] == "watch"
    assert [x["status"] for x in receipt["sources"]] == ["RETRIEVED", "NOT_FOUND"]


def test_an_unusable_model_answer_declares_nothing(court, direct_vm, direct_alice,
                                                   direct_bob):
    charter_id = s.published(court, direct_vm, direct_alice)
    charter_hash = court.get_charter(charter_id)["charter_hash"]
    s.serve_all(direct_vm)
    direct_vm.sender = direct_bob
    event_id = court.open_event(charter_id, charter_hash, "Flooding reported", "Eastfield")
    direct_vm.mock_llm("SUCCOUR assessment panel", "not json at all")
    declaration_id = court.assess(event_id)
    receipt = court.get_declaration(declaration_id)["declaration"]
    assert receipt["panel_state"] == "INVALID"
    assert receipt["reason_code"] == "PANEL_UNUSABLE"


# -- reassessment, finalisation, lapse ----------------------------------------

def test_a_reassessment_supersedes_and_becomes_the_band_that_stands(court, direct_vm,
                                                                     direct_alice,
                                                                     direct_bob):
    charter_id = s.published(court, direct_vm, direct_alice)
    charter_hash = court.get_charter(charter_id)["charter_hash"]
    s.serve_all(direct_vm)
    event_id, first = s.declared(court, direct_vm, direct_bob, charter_id, charter_hash)
    s.panel(direct_vm, s.assessment_said(severe=("MET", "M1M2")))
    second = court.reassess(event_id)
    assert court.get_event(event_id)["declared_band"] == "severe"
    history = court.get_event_history(event_id)["rounds"]
    assert [r["mode"] for r in history] == ["ASSESS", "REASSESS"]
    assert court.get_declaration(second)["declaration"]["supersedes"] == first
    assert court.get_latest_declaration(event_id)["declaration"]["declaration_id"] == second


def test_an_event_is_reassessed_only_once(court, direct_vm, direct_alice, direct_bob):
    charter_id = s.published(court, direct_vm, direct_alice)
    charter_hash = court.get_charter(charter_id)["charter_hash"]
    s.serve_all(direct_vm)
    event_id, _first = s.declared(court, direct_vm, direct_bob, charter_id, charter_hash)
    s.panel(direct_vm, s.assessment_said())
    court.reassess(event_id)
    s.panel(direct_vm, s.assessment_said())
    with direct_vm.expect_revert("reassessed once already"):
        court.reassess(event_id)


def test_an_event_finalizes_after_its_window(court, direct_vm, direct_alice, direct_bob):
    charter_id = s.published(court, direct_vm, direct_alice)
    charter_hash = court.get_charter(charter_id)["charter_hash"]
    s.serve_all(direct_vm)
    event_id, _d = s.declared(court, direct_vm, direct_bob, charter_id, charter_hash)
    with direct_vm.expect_revert("the reassessment window closes"):
        court.finalize_event(event_id)
    direct_vm.warp(LATER)
    assert court.finalize_event(event_id) == "FINALIZED"
    assert court.get_event(event_id)["finalized_at"] == LATER


def test_an_event_nobody_assessed_lapses(court, direct_vm, direct_alice, direct_bob):
    charter_id = s.published(court, direct_vm, direct_alice)
    charter_hash = court.get_charter(charter_id)["charter_hash"]
    direct_vm.sender = direct_bob
    event_id = court.open_event(charter_id, charter_hash, "Flooding reported", "Eastfield")
    with direct_vm.expect_revert("the assessment window closes"):
        court.expire_event(event_id)
    direct_vm.warp(LATER)
    assert court.get_event_status(event_id, LATER)["effective_status"] == "LAPSED"
    assert court.expire_event(event_id) == "LAPSED"
    s.serve_all(direct_vm)
    s.panel(direct_vm, s.assessment_said())
    with direct_vm.expect_revert("only an OPEN event is assessed"):
        court.assess(event_id)


def test_the_assessment_window_closes(court, direct_vm, direct_alice, direct_bob):
    charter_id = s.published(court, direct_vm, direct_alice)
    charter_hash = court.get_charter(charter_id)["charter_hash"]
    direct_vm.sender = direct_bob
    event_id = court.open_event(charter_id, charter_hash, "Flooding reported", "Eastfield")
    direct_vm.warp(LATER)
    s.serve_all(direct_vm)
    s.panel(direct_vm, s.assessment_said())
    with direct_vm.expect_revert("the assessment window closed"):
        court.assess(event_id)


# -- filing and adjudicating a relief request ---------------------------------

def test_a_request_is_filed_against_the_band_that_stands(court, direct_vm, direct_alice,
                                                         direct_bob, direct_charlie):
    charter_id = s.published(court, direct_vm, direct_alice)
    charter_hash = court.get_charter(charter_id)["charter_hash"]
    s.serve_all(direct_vm)
    event_id, _d = s.declared(court, direct_vm, direct_bob, charter_id, charter_hash)
    request_id = s.filed(court, direct_vm, direct_charlie, event_id, charter_hash)
    request = court.get_request(request_id)
    assert request["band_id"] == "declared" and request["status"] == "FILED"
    assert request["filer"] == direct_charlie.as_hex.lower()
    assert request["source_url"] == s.EVIDENCE_URL
    assert court.list_requests(event_id, 0, 10)["ids"] == [request_id]


def test_a_request_needs_a_declared_band(court, direct_vm, direct_alice, direct_bob):
    charter_id = s.published(court, direct_vm, direct_alice)
    charter_hash = court.get_charter(charter_id)["charter_hash"]
    s.serve_all(direct_vm)
    said = s.assessment_said(watch=("NOT_MET", ""), declared=("NOT_MET", ""))
    event_id, _d = s.declared(court, direct_vm, direct_bob, charter_id, charter_hash,
                              subjects=said)
    with direct_vm.expect_revert("no band was declared"):
        s.filed(court, direct_vm, direct_bob, event_id, charter_hash)


def test_a_category_the_band_does_not_promise_is_refused(court, direct_vm, direct_alice,
                                                         direct_bob):
    charter_id = s.published(court, direct_vm, direct_alice)
    charter_hash = court.get_charter(charter_id)["charter_hash"]
    s.serve_all(direct_vm)
    event_id, _d = s.declared(court, direct_vm, direct_bob, charter_id, charter_hash)
    with direct_vm.expect_revert("promises no relief in that category"):
        s.filed(court, direct_vm, direct_bob, event_id, charter_hash, category="WATER")


def test_a_qualifying_request_reserves_the_charters_grant(court, direct_vm, direct_alice,
                                                          direct_bob, direct_charlie):
    charter_id = s.published(court, direct_vm, direct_alice)
    charter_hash = court.get_charter(charter_id)["charter_hash"]
    s.funded(court, direct_vm, direct_alice, charter_id, 10 * s.GEN)
    s.serve_all(direct_vm)
    event_id, _d = s.declared(court, direct_vm, direct_bob, charter_id, charter_hash)
    request_id = s.filed(court, direct_vm, direct_charlie, event_id, charter_hash)
    s.panel(direct_vm, s.request_said(), header="relief")
    ruling = court.get_adjudication(court.adjudicate(request_id))["adjudication"]
    assert ruling["outcome"] == "QUALIFIES" and ruling["reason_code"] == "QUALIFIED"
    assert ruling["authorised_atto"] == str(2 * s.GEN) and ruling["funding"] == "RESERVED"
    assert ruling["decided_by"] == "PANEL"
    assert court.get_charter(charter_id)["reserved_atto"] == str(2 * s.GEN)
    assert court.get_request(request_id)["reserved_atto"] == str(2 * s.GEN)


def test_settling_turns_a_reservation_into_a_credit(court, direct_vm, direct_alice,
                                                    direct_bob, direct_charlie):
    charter_id = s.published(court, direct_vm, direct_alice)
    charter_hash = court.get_charter(charter_id)["charter_hash"]
    s.funded(court, direct_vm, direct_alice, charter_id, 10 * s.GEN)
    s.serve_all(direct_vm)
    event_id, _d = s.declared(court, direct_vm, direct_bob, charter_id, charter_hash)
    request_id = s.filed(court, direct_vm, direct_charlie, event_id, charter_hash)
    s.panel(direct_vm, s.request_said(), header="relief")
    court.adjudicate(request_id)
    direct_vm.warp(LATER)
    assert court.finalize_request(request_id) == str(2 * s.GEN)
    charter = court.get_charter(charter_id)
    assert charter["paid_atto"] == str(2 * s.GEN) and charter["reserved_atto"] == "0"
    assert charter["pool_atto"] == str(8 * s.GEN)
    assert court.get_credit(direct_charlie.as_hex.lower())["credit_atto"] == str(2 * s.GEN)
    direct_vm.sender = direct_charlie
    assert court.withdraw() == str(2 * s.GEN)
    assert court.get_treasury()["accounted_atto"] == str(8 * s.GEN)


def test_a_refused_request_releases_nothing_and_frees_its_source(court, direct_vm,
                                                                 direct_alice, direct_bob,
                                                                 direct_charlie):
    charter_id = s.published(court, direct_vm, direct_alice)
    charter_hash = court.get_charter(charter_id)["charter_hash"]
    s.funded(court, direct_vm, direct_alice, charter_id, 10 * s.GEN)
    s.serve_all(direct_vm)
    event_id, _d = s.declared(court, direct_vm, direct_bob, charter_id, charter_hash)
    request_id = s.filed(court, direct_vm, direct_charlie, event_id, charter_hash)
    s.panel(direct_vm, s.request_said(area="OUTSIDE"), header="relief")
    ruling = court.get_adjudication(court.adjudicate(request_id))["adjudication"]
    assert ruling["outcome"] == "DOES_NOT_QUALIFY" and ruling["reason_code"] == "OUT_OF_AREA"
    assert ruling["authorised_atto"] == "0" and ruling["funding"] == "NOT_AUTHORISED"
    direct_vm.warp(LATER)
    assert court.finalize_request(request_id) == "0"
    assert court.get_charter(charter_id)["pool_atto"] == str(10 * s.GEN)
    second = s.filed(court, direct_vm, direct_charlie, event_id, charter_hash)
    assert second != request_id


def test_each_refusal_reason_reaches_the_receipt(court, direct_vm, direct_alice, direct_bob,
                                                 direct_charlie):
    charter_id = s.published(court, direct_vm, direct_alice)
    charter_hash = court.get_charter(charter_id)["charter_hash"]
    s.funded(court, direct_vm, direct_alice, charter_id, 20 * s.GEN)
    s.serve_all(direct_vm)
    event_id, _d = s.declared(court, direct_vm, direct_bob, charter_id, charter_hash)
    cases = (
        ({"need": "ABSENT"}, "DOES_NOT_QUALIFY", "NEED_ABSENT"),
        ({"need": "CONTRADICTED"}, "DOES_NOT_QUALIFY", "NEED_CONTRADICTED"),
        ({"link": "UNLINKED"}, "DOES_NOT_QUALIFY", "NOT_LINKED"),
        ({"area": "UNCLEAR"}, "INCONCLUSIVE", "AREA_UNCLEAR"),
        ({"need": "UNCLEAR"}, "INCONCLUSIVE", "NEED_UNCLEAR"),
        ({"link": "UNCLEAR"}, "INCONCLUSIVE", "LINK_UNCLEAR"),
        ({"date": ""}, "INCONCLUSIVE", "EVIDENCE_UNDATED"),
    )
    for index, (overrides, outcome, reason) in enumerate(cases):
        url = s.EVIDENCE_URL + "?case=" + str(index)
        s.serve(direct_vm, url, s.ASSESSMENT)
        request_id = s.filed(court, direct_vm, direct_charlie, event_id, charter_hash,
                             url=url)
        s.panel(direct_vm, s.request_said(**overrides), header="relief")
        ruling = court.get_adjudication(court.adjudicate(request_id))["adjudication"]
        assert (ruling["outcome"], ruling["reason_code"]) == (outcome, reason)
        direct_vm.clear_mocks()
        s.serve_all(direct_vm)


def test_evidence_dated_before_the_onset_does_not_qualify(court, direct_vm, direct_alice,
                                                          direct_bob, direct_charlie):
    charter_id = s.published(court, direct_vm, direct_alice)
    charter_hash = court.get_charter(charter_id)["charter_hash"]
    s.funded(court, direct_vm, direct_alice, charter_id, 10 * s.GEN)
    s.serve_all(direct_vm, {s.EVIDENCE_URL: s.evidence_page("20 September 2026")})
    event_id, _d = s.declared(court, direct_vm, direct_bob, charter_id, charter_hash)
    request_id = s.filed(court, direct_vm, direct_charlie, event_id, charter_hash)
    s.panel(direct_vm, s.request_said(date="2026-09-20", date_words="20 September 2026"),
            header="relief")
    ruling = court.get_adjudication(court.adjudicate(request_id))["adjudication"]
    assert ruling["reason_code"] == "EVIDENCE_PREDATES_ONSET"
    assert ruling["evidence_date"] == "2026-09-20"


def test_an_unreadable_evidence_source_is_inconclusive(court, direct_vm, direct_alice,
                                                       direct_bob, direct_charlie):
    charter_id = s.published(court, direct_vm, direct_alice)
    charter_hash = court.get_charter(charter_id)["charter_hash"]
    s.serve_all(direct_vm)
    event_id, _d = s.declared(court, direct_vm, direct_bob, charter_id, charter_hash)
    request_id = s.filed(court, direct_vm, direct_charlie, event_id, charter_hash)
    direct_vm.clear_mocks()
    s.serve_all(direct_vm, {s.EVIDENCE_URL: None})
    ruling = court.get_adjudication(court.adjudicate(request_id))["adjudication"]
    assert ruling["outcome"] == "INCONCLUSIVE"
    assert ruling["reason_code"] == "EVIDENCE_UNAVAILABLE"
    assert ruling["panel_state"] == "SKIPPED"


def test_a_treasury_that_cannot_cover_the_grant_authorises_nothing(court, direct_vm,
                                                                    direct_alice,
                                                                    direct_bob,
                                                                    direct_charlie):
    charter_id = s.published(court, direct_vm, direct_alice)
    charter_hash = court.get_charter(charter_id)["charter_hash"]
    s.serve_all(direct_vm)
    event_id, _d = s.declared(court, direct_vm, direct_bob, charter_id, charter_hash)
    request_id = s.filed(court, direct_vm, direct_charlie, event_id, charter_hash)
    s.panel(direct_vm, s.request_said(), header="relief")
    ruling = court.get_adjudication(court.adjudicate(request_id))["adjudication"]
    assert ruling["outcome"] == "QUALIFIES" and ruling["funding"] == "TREASURY_SHORT"
    assert ruling["authorised_atto"] == "0"
    assert court.get_request(request_id)["reserved_atto"] == "0"


def test_a_recheck_after_funding_reserves_what_the_charter_promised(court, direct_vm,
                                                                    direct_alice,
                                                                    direct_bob,
                                                                    direct_charlie):
    charter_id = s.published(court, direct_vm, direct_alice)
    charter_hash = court.get_charter(charter_id)["charter_hash"]
    s.serve_all(direct_vm)
    event_id, _d = s.declared(court, direct_vm, direct_bob, charter_id, charter_hash)
    request_id = s.filed(court, direct_vm, direct_charlie, event_id, charter_hash)
    s.panel(direct_vm, s.request_said(), header="relief")
    first = court.adjudicate(request_id)
    s.funded(court, direct_vm, direct_alice, charter_id, 5 * s.GEN)
    s.panel(direct_vm, s.request_said(), header="relief")
    direct_vm.sender = direct_charlie
    second = court.recheck_request(request_id)
    ruling = court.get_adjudication(second)["adjudication"]
    assert ruling["funding"] == "RESERVED" and ruling["supersedes"] == first
    assert ruling["mode"] == "RECHECK" and ruling["round"] == 2
    history = court.get_request_history(request_id)["rounds"]
    assert [r["funding"] for r in history] == ["TREASURY_SHORT", "RESERVED"]


def test_a_recheck_that_overturns_releases_the_reservation(court, direct_vm, direct_alice,
                                                           direct_bob, direct_charlie):
    charter_id = s.published(court, direct_vm, direct_alice)
    charter_hash = court.get_charter(charter_id)["charter_hash"]
    s.funded(court, direct_vm, direct_alice, charter_id, 10 * s.GEN)
    s.serve_all(direct_vm)
    event_id, _d = s.declared(court, direct_vm, direct_bob, charter_id, charter_hash)
    request_id = s.filed(court, direct_vm, direct_charlie, event_id, charter_hash)
    s.panel(direct_vm, s.request_said(), header="relief")
    court.adjudicate(request_id)
    s.panel(direct_vm, s.request_said(need="CONTRADICTED"), header="relief")
    court.recheck_request(request_id)
    assert court.get_charter(charter_id)["reserved_atto"] == "0"
    direct_vm.warp(LATER)
    assert court.finalize_request(request_id) == "0"
    assert court.get_charter(charter_id)["pool_atto"] == str(10 * s.GEN)


def test_a_band_withdrawn_under_a_filed_request_is_decided_in_code(court, direct_vm,
                                                                   direct_alice, direct_bob,
                                                                   direct_charlie):
    charter_id = s.published(court, direct_vm, direct_alice)
    charter_hash = court.get_charter(charter_id)["charter_hash"]
    s.funded(court, direct_vm, direct_alice, charter_id, 10 * s.GEN)
    s.serve_all(direct_vm)
    event_id, _d = s.declared(court, direct_vm, direct_bob, charter_id, charter_hash)
    request_id = s.filed(court, direct_vm, direct_charlie, event_id, charter_hash)
    s.panel(direct_vm, s.assessment_said(watch=("MET", "M1"), declared=("NOT_MET", "")))
    direct_vm.sender = direct_bob
    court.reassess(event_id)
    direct_vm.sender = direct_charlie
    ruling = court.get_adjudication(court.adjudicate(request_id))["adjudication"]
    assert ruling["reason_code"] == "BAND_WITHDRAWN"
    assert ruling["decided_by"] == "CODE" and ruling["sources"] == []
    assert court.get_charter(charter_id)["reserved_atto"] == "0"


def test_a_request_nobody_adjudicated_lapses_and_frees_its_source(court, direct_vm,
                                                                  direct_alice, direct_bob,
                                                                  direct_charlie):
    charter_id = s.published(court, direct_vm, direct_alice)
    charter_hash = court.get_charter(charter_id)["charter_hash"]
    s.serve_all(direct_vm)
    event_id, _d = s.declared(court, direct_vm, direct_bob, charter_id, charter_hash)
    request_id = s.filed(court, direct_vm, direct_charlie, event_id, charter_hash)
    direct_vm.warp(LATER)
    assert court.expire_request(request_id) == "LAPSED"
    second = s.filed(court, direct_vm, direct_charlie, event_id, charter_hash)
    assert court.get_request(second)["status"] == "FILED"


def test_the_same_source_cannot_back_two_live_requests(court, direct_vm, direct_alice,
                                                       direct_bob, direct_charlie):
    charter_id = s.published(court, direct_vm, direct_alice)
    charter_hash = court.get_charter(charter_id)["charter_hash"]
    s.serve_all(direct_vm)
    event_id, _d = s.declared(court, direct_vm, direct_bob, charter_id, charter_hash)
    s.filed(court, direct_vm, direct_charlie, event_id, charter_hash)
    with direct_vm.expect_revert("already backs request"):
        s.filed(court, direct_vm, direct_bob, event_id, charter_hash)


def test_a_source_that_was_paid_stays_spent(court, direct_vm, direct_alice, direct_bob,
                                            direct_charlie):
    charter_id = s.published(court, direct_vm, direct_alice)
    charter_hash = court.get_charter(charter_id)["charter_hash"]
    s.funded(court, direct_vm, direct_alice, charter_id, 10 * s.GEN)
    s.serve_all(direct_vm)
    event_id, _d = s.declared(court, direct_vm, direct_bob, charter_id, charter_hash)
    request_id = s.filed(court, direct_vm, direct_charlie, event_id, charter_hash)
    s.panel(direct_vm, s.request_said(), header="relief")
    court.adjudicate(request_id)
    direct_vm.warp(LATER)
    court.finalize_request(request_id)
    with direct_vm.expect_revert("already backs request"):
        s.filed(court, direct_vm, direct_charlie, event_id, charter_hash)


# -- views ---------------------------------------------------------------------

def test_get_actions_reports_what_is_left(court, direct_vm, direct_alice, direct_bob,
                                          direct_charlie):
    charter_id = s.published(court, direct_vm, direct_alice)
    charter_hash = court.get_charter(charter_id)["charter_hash"]
    s.funded(court, direct_vm, direct_alice, charter_id, 10 * s.GEN)
    s.serve_all(direct_vm)
    event_id, _d = s.declared(court, direct_vm, direct_bob, charter_id, charter_hash)
    request_id = s.filed(court, direct_vm, direct_charlie, event_id, charter_hash)
    actions = court.get_actions(request_id, s.NOW)
    assert actions["may_adjudicate"] and not actions["may_finalize"]
    assert actions["band_stands"] and actions["grant_atto"] == str(2 * s.GEN)
    assert actions["grants_left"] == 5 and actions["wallet_grants_left"] == 2
    s.panel(direct_vm, s.request_said(), header="relief")
    court.adjudicate(request_id)
    actions = court.get_actions(request_id, s.NOW)
    assert actions["may_recheck"] and actions["grants_used"] == 1
    assert actions["unreserved_atto"] == str(8 * s.GEN)


def test_request_status_reports_the_window(court, direct_vm, direct_alice, direct_bob,
                                          direct_charlie):
    charter_id = s.published(court, direct_vm, direct_alice)
    charter_hash = court.get_charter(charter_id)["charter_hash"]
    s.serve_all(direct_vm)
    event_id, _d = s.declared(court, direct_vm, direct_bob, charter_id, charter_hash)
    request_id = s.filed(court, direct_vm, direct_charlie, event_id, charter_hash)
    assert court.get_request_status(request_id, s.NOW)["may_adjudicate"]
    assert court.get_request_status(request_id, LATER)["effective_status"] == "LAPSED"
    assert court.get_request_status("RQ-999999", s.NOW)["found"] is False


def test_event_status_reports_what_may_happen(court, direct_vm, direct_alice, direct_bob):
    charter_id = s.published(court, direct_vm, direct_alice)
    charter_hash = court.get_charter(charter_id)["charter_hash"]
    s.serve_all(direct_vm)
    event_id, _d = s.declared(court, direct_vm, direct_bob, charter_id, charter_hash)
    status = court.get_event_status(event_id, s.NOW)
    assert status["may_reassess"] and status["may_file_request"]
    assert not status["may_finalize"]
    assert court.get_event_status(event_id, LATER)["may_finalize"]


def test_the_stats_and_paging_hold(court, direct_vm, direct_alice, direct_bob):
    charter_id = s.published(court, direct_vm, direct_alice)
    charter_hash = court.get_charter(charter_id)["charter_hash"]
    s.serve_all(direct_vm)
    s.declared(court, direct_vm, direct_bob, charter_id, charter_hash)
    s.panel(direct_vm, s.assessment_said())
    direct_vm.sender = direct_bob
    second = court.open_event(charter_id, charter_hash, "Further flooding reported",
                             "Upper Eastfield")
    court.assess(second)
    stats = court.get_stats()
    assert stats["charters"] == 1 and stats["events"] == 2 and stats["declarations"] == 2
    page = court.list_events(charter_id, 1, 1)
    assert page == {"total": 2, "offset": 1, "ids": [second]}
    assert court.list_events("", 0, 50)["total"] == 2
    assert court.list_events("CH-999999", 0, 10)["ids"] == []


def test_unknown_records_answer_not_found(court):
    assert court.get_charter("CH-999999")["found"] is False
    assert court.get_event("EV-999999")["found"] is False
    assert court.get_request("RQ-999999")["found"] is False
    assert court.get_declaration("DE-999999")["found"] is False
    assert court.get_adjudication("AD-999999")["found"] is False
    assert court.get_latest_declaration("EV-999999")["found"] is False
    assert court.get_latest_adjudication("RQ-999999")["found"] is False
    assert court.get_event_history("EV-999999")["found"] is False
    assert court.get_request_history("RQ-999999")["found"] is False
    assert court.get_actions("RQ-999999", s.NOW)["found"] is False


# -- three watched sources, and a DYNAMIC declared source ----------------------

def test_a_charter_may_watch_three_sources_and_need_two(court, direct_vm, direct_alice,
                                                        direct_bob):
    monitors = [{"source_id": "M1", "url": s.M1_URL, "stability": "STABLE",
                 "description": "The provincial flood bulletin"},
                {"source_id": "M2", "url": s.M2_URL, "stability": "STABLE",
                 "description": "The published gauge readings"},
                {"source_id": "M3", "url": s.M3_URL, "stability": "STABLE",
                 "description": "The district situation report"}]
    bands = [s.band("declared", "Declared", "A flood warning is in force.", 2,
                    [s.relief("SHELTER", 2 * s.GEN, 4)])]
    charter_id = s.published(court, direct_vm, direct_alice, monitors=monitors, bands=bands)
    charter_hash = court.get_charter(charter_id)["charter_hash"]
    s.serve_all(direct_vm)
    said = {"HAZARD_MATCH": s.said("MATCHES", [("M1", s.HAZARD_LINE)]),
            "ONSET": s.said("DATED", [("M1", s.ONSET_LINE)], date=s.ONSET_DATE),
            "BAND_DECLARED": s.said("MET", [("M1", s.HAZARD_LINE),
                                            ("M3", s.FIELD_LINE)])}
    _event_id, declaration_id = s.declared(court, direct_vm, direct_bob, charter_id,
                                           charter_hash, subjects=said)
    receipt = court.get_declaration(declaration_id)["declaration"]
    assert receipt["declared_band"] == "declared"
    assert receipt["corroborating_sources"] == ["M1", "M3"]
    assert [x["source_id"] for x in receipt["sources"]] == ["M1", "M2", "M3"]


def test_a_request_may_declare_its_evidence_dynamic(court, direct_vm, direct_alice,
                                                    direct_bob, direct_charlie):
    charter_id = s.published(court, direct_vm, direct_alice)
    charter_hash = court.get_charter(charter_id)["charter_hash"]
    s.funded(court, direct_vm, direct_alice, charter_id, 10 * s.GEN)
    s.serve_all(direct_vm)
    event_id, _d = s.declared(court, direct_vm, direct_bob, charter_id, charter_hash)
    request_id = s.filed(court, direct_vm, direct_charlie, event_id, charter_hash,
                         stability="DYNAMIC")
    s.panel(direct_vm, s.request_said(), header="relief")
    ruling = court.get_adjudication(court.adjudicate(request_id))["adjudication"]
    assert ruling["outcome"] == "QUALIFIES"
    record = ruling["sources"][0]
    assert record["compared"] is False and "content_digest" not in record


def test_a_reassessment_records_the_onset_it_read(court, direct_vm, direct_alice,
                                                 direct_bob):
    charter_id = s.published(court, direct_vm, direct_alice)
    charter_hash = court.get_charter(charter_id)["charter_hash"]
    s.serve_all(direct_vm, {s.M1_URL: s.page(
        "Lower Marrow flood bulletin",
        [s.HAZARD_LINE, s.onset_line(), s.onset_line("23 September 2026"), s.WATCH_LINE,
         s.DECLARED_LINE])})
    event_id, _first = s.declared(court, direct_vm, direct_bob, charter_id, charter_hash)
    assert court.get_event(event_id)["onset"] == "2026-09-24"
    said = s.assessment_said(onset="2026-09-23", onset_words="23 September 2026")
    s.panel(direct_vm, said)
    court.reassess(event_id)
    assert court.get_event(event_id)["onset"] == "2026-09-23"
    rounds = court.get_event_history(event_id)["rounds"]
    assert [r["onset"] for r in rounds] == ["2026-09-24", "2026-09-23"]


def test_an_expired_event_frees_the_openers_slot(court, direct_vm, direct_alice,
                                                direct_bob):
    charter_id = s.published(court, direct_vm, direct_alice)
    charter_hash = court.get_charter(charter_id)["charter_hash"]
    direct_vm.sender = direct_bob
    event_id = court.open_event(charter_id, charter_hash, "Flooding reported", "Eastfield")
    direct_vm.warp(LATER)
    court.expire_event(event_id)
    assert court.open_event(charter_id, charter_hash, "A further report",
                           "Eastfield") == "EV-000002"
