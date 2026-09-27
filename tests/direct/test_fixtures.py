"""The fixtures a live run serves, checked against the deployed code.

The model's readings cannot be checked here - that is what the live run is for -
but everything around them can: each charter template parses, each source a
charter names is present unless the case is about it being missing, each
injected page is caught by the marker scan, and no honest page trips it.
"""

import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures"
BASE = "https://raw.githubusercontent.com/example/succour/0000000/fixtures/"
ORIGINS = {"{base}": BASE,
           "{mirror}": "https://cdn.jsdelivr.net/gh/example/succour@0000000/fixtures/",
           "{mirror2}": "https://rawcdn.githack.com/example/succour/0000000/fixtures/"}

CHARTERS = json.loads((FIXTURES / "charters.json").read_text(encoding="utf-8"))
CASES = json.loads((FIXTURES / "cases.json").read_text(encoding="utf-8"))
MISSING = ("AS09-missing-bulletin.html", "AS09-missing-gauges.html", "AS10-missing.html",
           "missing-survey.html")


def filled(template: dict) -> str:
    text = json.dumps(template)
    for placeholder, origin in ORIGINS.items():
        text = text.replace(placeholder, origin)
    return text


def served_path(url: str) -> str:
    for origin in ORIGINS.values():
        if url.startswith(origin):
            return url[len(origin):]
    return url


@pytest.mark.parametrize("name", sorted(CHARTERS))
def test_every_charter_template_parses(mod, name):
    error, spec = mod._parse_charter(filled(CHARTERS[name]))
    assert error == "", name
    assert spec["hazard"] in mod.HAZARDS
    hosts = []
    for entry in spec["monitors"]:
        assert served_path(entry["url"]) != entry["url"], entry["url"]
        hosts.append(mod._host_of(entry["url"]))
    assert len(set(hosts)) == len(hosts), (name, hosts)
    for band in spec["bands"]:
        assert band["min_corroboration"] <= len(set(hosts)), name


def test_the_catalogue_covers_every_charter(mod):
    assert sorted(c["charter"] for c in CASES["assessments"]) == sorted(CHARTERS)
    assert CASES["request_event"] in CHARTERS
    for case in CASES["assessments"]:
        assert case["expect_reason"] in mod.ASSESS_REASONS, case["case"]
        band = case["expect_band"]
        if band != "NONE":
            ids = [b["band_id"] for b in CHARTERS[case["charter"]]["bands"]]
            assert band in ids, case["case"]


def test_every_request_case_is_coherent(mod):
    charter = CHARTERS[CASES["request_event"]]
    categories = {a["category"] for b in charter["bands"] for a in b["relief"]}
    for case in CASES["requests"]:
        assert case["expect_outcome"] in mod.OUTCOMES, case["case"]
        assert case["expect_reason"] in mod.REQUEST_REASONS, case["case"]
        assert case["category"] in categories, case["case"]
        assert case["stability"] in mod.STABILITIES, case["case"]
        assert mod._text_error(case["need"], mod.NEED_CAP, "need", True) == "", case["case"]
        assert mod._text_error(case["area_note"], mod.AREA_CAP, "area", False) == "", \
            case["case"]


def test_every_named_source_exists_unless_the_case_is_about_its_absence():
    referenced = []
    for template in CHARTERS.values():
        for entry in template["monitors"]:
            referenced.append(entry["url"].split("}", 1)[-1])
    for case in CASES["requests"]:
        referenced.append(case["evidence"])
    for path in referenced:
        exists = (FIXTURES / path).exists()
        assert exists != path.endswith(MISSING), path


def test_no_fixture_page_is_unreferenced():
    served = {str(p.relative_to(FIXTURES)).replace("\\", "/")
              for p in FIXTURES.rglob("*.html")}
    referenced = set()
    for template in CHARTERS.values():
        for entry in template["monitors"]:
            referenced.add(entry["url"].split("}", 1)[-1])
    for case in CASES["requests"]:
        referenced.add(case["evidence"])
    assert served - referenced == set()


INJECTED = ("AS11-bulletin.html", "AS12-bulletin.html", "AS12-gauges.html",
            "AS13-bulletin.html", "injected.html")


@pytest.mark.parametrize("path", sorted(str(p.relative_to(FIXTURES)).replace("\\", "/")
                                       for p in FIXTURES.rglob("*.html")))
def test_the_marker_scan_agrees_with_what_each_page_is(mod, path):
    raw = (FIXTURES / path).read_text(encoding="utf-8")
    source = {"status": "RETRIEVED", "title": mod._title_of(raw, True)}
    normalized = mod._normalize(raw, True)
    found = mod._markers(source, normalized, raw)
    assert bool(found) == path.endswith(INJECTED), (path, found)


def test_the_onset_the_catalogue_states_is_shown_in_the_pages_that_carry_it(mod):
    onset = CASES["onset"]
    quote = [{"evidence_id": "M1",
              "text": "The flooding began on " + onset["words"] + " after three days"}]
    assert mod._date_in_quotes(onset["date"], quote)
    for name in ("AS01-bulletin.html", "AS01-gauges.html"):
        raw = (FIXTURES / "sources/monitors" / name).read_text(encoding="utf-8")
        assert onset["words"] in mod._normalize(raw, True), name
