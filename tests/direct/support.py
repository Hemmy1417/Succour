"""What the Direct Mode suite mocks, and what it does not.

Mocked: the two nondeterministic calls the contract makes - `gl.nondet.web.get`
(the sources a round retrieves) and `gl.nondet.exec_prompt` (the panel). Every
other line runs as deployed: the charter parser, URL admission, normalisation,
the marker scan, quote grounding, the structural gate, the band and
qualification derivations, the reservations, the ledger and every state
transition.

Not mocked and not faked: the panel's answers are shaped like a model's - keyed
by subject, quoting the page - and each quote has to ground in the text this
harness actually serves, or the contract downgrades the finding exactly as it
would on chain.
"""

import json

CONTRACT = "contracts/succour.py"
NOW = "2026-09-26T12:00:00Z"

GEN = 10 ** 18

# -- the sources the charter watches ------------------------------------------

M1_URL = "https://alerts.example.gov/basin/flood-bulletin"
M2_URL = "https://data.example.gov/gauges/lower-marrow"
M3_URL = "https://relief.example.gov/field/situation-report"
EVIDENCE_URL = "https://reports.example.org/eastfield/shelter-assessment"

HAZARD_LINE = "A flood warning is in force for the Lower Marrow river basin in " \
              "Eastfield province."
ONSET_WORDS = "24 September 2026"
ONSET_DATE = "2026-09-24"


def onset_line(words: str = ONSET_WORDS) -> str:
    return "The flooding began on " + words + " after three days of rainfall."


ONSET_LINE = onset_line()
WATCH_LINE = "River gauges across Eastfield stand above the warning level this morning."
DECLARED_LINE = "The gauge at Marrow Bridge has passed the danger level and an " \
                "evacuation of the lower town has been ordered."
SEVERE_LINE = "Widespread inundation is reported across the basin and four thousand " \
              "residents have been displaced from their homes."
GAUGE_LINE = "Marrow Bridge gauge reading: 6.4 metres, above the danger level of 5.9 metres."
FIELD_LINE = "Field teams report shelters at capacity and continued displacement in " \
             "Eastfield province."

AREA_LINE = "The assessed site is in the lower town of Eastfield, inside the Lower " \
            "Marrow river basin."
NEED_LINE = "Seventy displaced households at this site have no shelter tonight and " \
            "require emergency accommodation."
LINK_LINE = "The damage recorded here was caused by the flooding that began on " \
            "24 September 2026."
DATE_LINE = "Survey completed on 25 September 2026 by the district relief office."


def page(title: str, lines) -> str:
    body = "".join("<p>" + line + "</p>" for line in lines)
    return ("<html><head><title>" + title + "</title></head><body><h1>" + title
            + "</h1>" + body + "</body></html>")


def bulletin(onset_words: str = ONSET_WORDS, extra=()) -> str:
    return page("Lower Marrow flood bulletin",
                [HAZARD_LINE, onset_line(onset_words), WATCH_LINE, DECLARED_LINE,
                 SEVERE_LINE] + list(extra))


BULLETIN = bulletin()
GAUGES = page("Lower Marrow gauge readings",
              [HAZARD_LINE, ONSET_LINE, WATCH_LINE, GAUGE_LINE, SEVERE_LINE])
SITUATION = page("Eastfield situation report", [HAZARD_LINE, ONSET_LINE, FIELD_LINE])
ASSESSMENT = page("Eastfield shelter assessment",
                  [AREA_LINE, NEED_LINE, LINK_LINE, DATE_LINE])


# -- the charter ---------------------------------------------------------------

def band(band_id: str, label: str, conditions: str, min_corroboration: int, relief) -> dict:
    return {"band_id": band_id, "label": label, "conditions": conditions,
            "min_corroboration": min_corroboration, "relief": relief}


def relief(category: str, grant: int, max_grants: int) -> dict:
    return {"category": category, "grant_atto": str(grant), "max_grants": max_grants}


def charter(**overrides) -> dict:
    spec = {
        "name": "Lower Marrow flood relief",
        "hazard": "FLOOD",
        "region": "The Lower Marrow river basin, Eastfield province",
        "authority_domains": ["example.gov"],
        "evidence_domains": ["example.org", "example.gov"],
        "monitors": [
            {"source_id": "M1", "url": M1_URL, "stability": "STABLE",
             "description": "The provincial hazards agency flood bulletin"},
            {"source_id": "M2", "url": M2_URL, "stability": "STABLE",
             "description": "Published river gauge readings for the basin"},
        ],
        "bands": [
            band("watch", "Watch",
                 "A flood warning is in force for the region, or river gauges stand "
                 "above the warning level.", 1,
                 [relief("SHELTER", GEN, 5)]),
            band("declared", "Declared",
                 "A flood warning is in force and a gauge has passed the danger level, "
                 "or an evacuation has been ordered.", 2,
                 [relief("SHELTER", 2 * GEN, 5), relief("MEDICAL", GEN, 3)]),
            band("severe", "Severe",
                 "Widespread inundation is reported with residents displaced, or a "
                 "state of emergency has been declared for the region.", 2,
                 [relief("SHELTER", 5 * GEN, 2), relief("EVACUATION", 3 * GEN, 2)]),
        ],
        "qualification": "A request qualifies when the evidence places the need inside "
                         "the declared area, establishes the need in the category asked "
                         "for, and ties it to this event.",
        "assessment_window": 3600,
        "request_window": 3600,
        "max_age_seconds": 14 * 86400,
        "max_grants_per_wallet": 2,
        "budget_atto": str(20 * GEN),
    }
    spec.update(overrides)
    return spec


def charter_json(**overrides) -> str:
    return json.dumps(charter(**overrides))


# -- serving the sources -------------------------------------------------------

def serve(vm, url: str, body, status: int = 200,
          content_type: str = "text/html; charset=utf-8"):
    """Serve one URL. `body` may be text or bytes; headers carry the type."""
    if isinstance(body, str):
        body = body.encode("utf-8")
    vm.mock_web(_escape(url), {"response": {"status": status,
                                            "headers": {"content-type": content_type},
                                            "body": body}, "method": "GET"})


def serve_missing(vm, url: str, status: int = 404):
    serve(vm, url, "not found", status=status, content_type="text/plain")


def _escape(url: str) -> str:
    out = ""
    for ch in url:
        out = out + ("\\" + ch if ch in ".?*+()[]{}|^$\\" else ch)
    return out


def serve_all(vm, pages=None):
    """Serve every source the suite knows about, so a round never depends on an
    unmocked GET (which raises, and would read as a timeout rather than the 404
    a live host answers with)."""
    served = {M1_URL: BULLETIN, M2_URL: GAUGES, M3_URL: SITUATION,
              EVIDENCE_URL: ASSESSMENT}
    if pages:
        served.update(pages)
    for url, body in served.items():
        if body is None:
            serve_missing(vm, url)
        elif isinstance(body, dict):
            serve(vm, url, body.get("body", ""), body.get("status", 200),
                  body.get("content_type", "text/html; charset=utf-8"))
        else:
            serve(vm, url, body)


# -- the panel's answers -------------------------------------------------------

def said(state: str, quotes=(), date: str = "", note: str = "") -> dict:
    """One subject's answer, as the model would send it."""
    entry = {"state": state,
             "quotes": [{"evidence_id": sid, "text": text} for sid, text in quotes]}
    if date:
        entry["date"] = date
    if note:
        entry["note"] = note
    return entry


def panel(vm, subjects: dict, header: str = "assessment"):
    """Register the panel answer for the next round.

    The runner returns the FIRST registered mock whose pattern matches, so a
    second round with a different answer needs the earlier answers gone; the
    web mocks (the sources) are left alone."""
    vm._llm_mocks.clear()
    vm._llm_mocks_hit.clear()
    pattern = "SUCCOUR " + header + " panel"
    vm.mock_llm(pattern, json.dumps({"subjects": subjects}))


def assessment_said(onset: str = ONSET_DATE, hazard: str = "MATCHES",
                    watch=("MET", "M1"), declared=("MET", "M1M2"),
                    severe=("NOT_MET", ""), onset_words: str = ONSET_WORDS) -> dict:
    """The usual shape of an assessment answer, quoting the served bulletins."""
    subjects = {
        "HAZARD_MATCH": said(hazard, [("M1", HAZARD_LINE)] if hazard == "MATCHES" else []),
        "ONSET": said("DATED" if onset else "UNDATED",
                      [("M1", onset_line(onset_words))] if onset else [], date=onset),
    }
    for name, (state, sources) in (("WATCH", watch), ("DECLARED", declared),
                                   ("SEVERE", severe)):
        quotes = []
        if state == "MET":
            if "M1" in sources:
                quotes.append(("M1", {"WATCH": WATCH_LINE, "DECLARED": DECLARED_LINE,
                                      "SEVERE": SEVERE_LINE}[name]))
            if "M2" in sources:
                quotes.append(("M2", {"WATCH": WATCH_LINE, "DECLARED": GAUGE_LINE,
                                      "SEVERE": SEVERE_LINE}[name]))
        subjects["BAND_" + name] = said(state, quotes)
    return subjects


def evidence_page(date_words: str = "25 September 2026") -> str:
    return page("Eastfield shelter assessment",
                [AREA_LINE, NEED_LINE, LINK_LINE,
                 "Survey completed on " + date_words
                 + " by the district relief office."])


def request_said(area: str = "INSIDE", need: str = "ESTABLISHED", link: str = "LINKED",
                 date: str = "2026-09-25", date_words: str = "25 September 2026") -> dict:
    return {
        "AREA": said(area, [("E1", AREA_LINE)] if area in ("INSIDE", "OUTSIDE") else []),
        "NEED": said(need, [("E1", NEED_LINE)]
                     if need in ("ESTABLISHED", "CONTRADICTED") else []),
        "LINK": said(link, [("E1", LINK_LINE)] if link in ("LINKED", "UNLINKED") else []),
        "EVIDENCE_DATE": said(
            "DATED" if date else "UNDATED",
            [("E1", "Survey completed on " + date_words
              + " by the district relief office.")] if date else [], date=date),
    }


# -- driving the lifecycle -----------------------------------------------------

def published(court, vm, sender, **overrides) -> str:
    vm.sender = sender
    return court.create_charter(charter_json(**overrides))


def funded(court, vm, sender, charter_id: str, amount: int) -> str:
    vm.sender = sender
    vm.value = amount
    try:
        return court.fund_charter(charter_id)
    finally:
        vm.value = 0


def declared(court, vm, sender, charter_id: str, charter_hash: str, subjects=None,
             situation: str = "Flooding reported across the lower town of Eastfield",
             area: str = "The lower town of Eastfield") -> tuple:
    """Open an event and assess it once. Returns (event_id, declaration_id)."""
    vm.sender = sender
    event_id = court.open_event(charter_id, charter_hash, situation, area)
    panel(vm, subjects if subjects is not None else assessment_said())
    return (event_id, court.assess(event_id))


def filed(court, vm, sender, event_id: str, charter_hash: str, category: str = "SHELTER",
          url: str = EVIDENCE_URL, stability: str = "STABLE") -> str:
    vm.sender = sender
    return court.file_request(
        event_id, charter_hash, category,
        "Seventy displaced households need emergency shelter tonight",
        "The lower town of Eastfield", url, stability)


# -- replaying a validator -----------------------------------------------------

def leader_payload(vm, index: int = -1) -> dict:
    """The payload the leader returned in the last consensus round, as the
    runner captured it - the starting point for a tampered one."""
    return json.loads(vm._captured_validators[index][0])


def replay(vm, payload=None, error=None, index: int = -1) -> bool:
    """Run the captured validator closure against a leader result. With no
    payload the leader's own is replayed, which is the agreement case."""
    if error is not None:
        return vm.run_validator(leader_error=error, index=index)
    if payload is None:
        return vm.run_validator(index=index)
    return vm.run_validator(leader_result=json.dumps(payload, sort_keys=True), index=index)


def finding_in(payload: dict, subject_id: str) -> dict:
    for finding in payload["findings"]:
        if finding["id"] == subject_id:
            return finding
    raise AssertionError("no finding for " + subject_id)


def source_in(payload: dict, source_id: str) -> dict:
    for source in payload["sources"]:
        if source["source_id"] == source_id:
            return source
    raise AssertionError("no source " + source_id)
