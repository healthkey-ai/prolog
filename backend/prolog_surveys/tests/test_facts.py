"""Facts about the participant, supplied by the host (DEF-14, RUN-23).

The engine and validator tests run in every profile; the API tests need a
signed-in participant, so they run in the integrated profile only (as
test_integrated.py does).
"""

from __future__ import annotations

import copy

import pytest
from django.contrib.auth import get_user_model

from prolog_surveys import conf
from prolog_surveys.definitions.loader import load_definition
from prolog_surveys.definitions.normalize import normalize
from prolog_surveys.definitions.schema import read_json
from prolog_surveys.definitions.validate import validate_semantics
from prolog_surveys.engine.facts import known_facts, resolve_facts
from prolog_surveys.engine.visibility import pending_keys, visible_keys
from prolog_surveys.models import SurveyResponse
from prolog_surveys.tests.conftest import EXAMPLES_DIR

integrated = pytest.mark.skipif(not conf.is_integrated(), reason="integrated profile only")

SLUG = "sample-recheck"


def recheck() -> dict:
    return read_json(EXAMPLES_DIR / "sample-recheck.json")


def codes(definition: dict) -> list[str]:
    return [i.code for i in validate_semantics(normalize(definition)) if i.level == "error"]


# --- engine -------------------------------------------------------------------


def test_known_facts_keeps_only_declared_facts_with_declared_values():
    d = recheck()
    supplied = {"last_result": "awaited", "enrolled": "maybe", "other": "x", "number": 3}
    assert known_facts(d, supplied) == {"last_result": "awaited"}


def test_resolving_facts_never_changes_the_shared_definition():
    d = normalize(recheck())
    before = copy.deepcopy(d)
    resolved = resolve_facts(d, {"last_result": "awaited"})
    assert d == before
    assert resolved["sections"][0]["questions"][1]["visible_if"] == [{"const": True}]
    assert resolved["sections"][0]["questions"][2]["visible_if"] == [
        {"any": [{"const": False}, {"question": "feeling", "op": "eq", "value": "worse"}]}
    ]
    assert resolved["sections"][1]["visible_if"] == [{"const": False}]


def test_a_definition_without_facts_is_returned_as_it_is():
    d = {"facts": [], "sections": []}
    assert resolve_facts(d, {"anything": "x"}) is d


def test_a_question_closed_by_a_fact_is_settled_not_pending():
    resolved = resolve_facts(normalize(recheck()), {"last_result": "normal", "enrolled": "no"})
    assert visible_keys(resolved, {}) == ["feeling"]
    # worse_details still waits on "feeling"; the others are decided by facts.
    assert pending_keys(resolved, {}) == ["worse_details"]


# --- validator ----------------------------------------------------------------


def test_the_example_with_facts_is_valid():
    assert codes(recheck()) == []


def test_a_condition_on_an_undeclared_fact_is_refused():
    d = recheck()
    d["sections"][0]["questions"][1]["visible_if"] = [{"fact": "unknown", "op": "eq", "value": "x"}]
    assert codes(d) == ["fact_unknown"]


def test_a_value_the_fact_does_not_declare_is_refused():
    d = recheck()
    d["sections"][1]["visible_if"] = [
        {"fact": "enrolled", "op": "in", "values": ["yes", "perhaps"]}
    ]
    assert codes(d) == ["condition_value"]


def test_a_fact_declared_twice_is_refused():
    d = recheck()
    d["facts"].append({"key": "enrolled", "values": ["yes"]})
    assert codes(d) == ["fact_duplicate"]


def test_an_anonymous_survey_cannot_declare_facts():
    d = recheck()
    d["participation"] = {"anonymous": True, "resume": "browser_token"}
    assert "facts_anonymous" in codes(d)


def test_a_question_behind_a_fact_is_not_reported_unreachable():
    issues = validate_semantics(normalize(recheck()))
    assert not [i for i in issues if i.code == "unreachable"]


# --- API (integrated profile) ---------------------------------------------------


def provide(participant, definition):
    """The test host's PROLOG_FACTS_PROVIDER: whatever ``FACTS`` holds."""
    assert definition["slug"] == SLUG
    return dict(FACTS)


def fail(participant, definition):
    raise RuntimeError("the host's records are down")


FACTS: dict = {}


@pytest.fixture
def signed_in(settings, api_client):
    settings.PROLOG_FACTS_PROVIDER = f"{__name__}.provide"
    load_definition(recheck(), activate=True)
    user = get_user_model().objects.create_user("participant", "", "x")
    api_client.force_authenticate(user)
    FACTS.clear()
    return api_client


def start(client):
    r = client.post("/api/run/responses/", {"slug": SLUG, "language": "en"}, format="json")
    assert r.status_code == 201, r.content
    return r.json()["id"]


@integrated
@pytest.mark.django_db
def test_a_signed_in_participants_response_keeps_the_hosts_facts(signed_in):
    FACTS.update(last_result="awaited", enrolled="no", undeclared="x")
    rid = start(signed_in)
    assert SurveyResponse.objects.get(pk=rid).facts == {"last_result": "awaited", "enrolled": "no"}
    # The facts are taken once: what the host says later does not change the response.
    FACTS.update(last_result="normal")
    r = signed_in.post("/api/run/responses/", {"slug": SLUG, "language": "en"}, format="json")
    assert r.status_code == 200 and r.json()["id"] == rid
    assert SurveyResponse.objects.get(pk=rid).facts["last_result"] == "awaited"


@integrated
@pytest.mark.django_db
def test_the_runner_gets_the_definition_resolved_and_never_the_facts(signed_in):
    FACTS.update(last_result="awaited", enrolled="no")
    rid = start(signed_in)
    served = signed_in.get(f"/api/run/surveys/{SLUG}/?response={rid}").json()
    assert "facts" not in served
    now = served["sections"][0]["questions"]
    assert now[1]["visible_if"] == [{"const": True}]
    assert served["sections"][1]["visible_if"] == [{"const": False}]
    # Before a response exists the conditions stay as written, and still no facts.
    plain = signed_in.get(f"/api/run/surveys/{SLUG}/").json()
    assert "facts" not in plain and plain["sections"][1]["visible_if"][0]["fact"] == "enrolled"


@integrated
@pytest.mark.django_db
def test_the_server_enforces_what_the_facts_open(signed_in):
    FACTS.update(last_result="normal", enrolled="no")
    rid = start(signed_in)
    hidden = signed_in.put(
        f"/api/run/responses/{rid}/answers/earlier_result/",
        {"value": {"option": "normal"}},
        format="json",
    )
    assert hidden.status_code == 400
    FACTS.update(last_result="awaited")
    SurveyResponse.objects.filter(pk=rid).delete()
    rid = start(signed_in)
    shown = signed_in.put(
        f"/api/run/responses/{rid}/answers/earlier_result/",
        {"value": {"option": "normal"}},
        format="json",
    )
    assert shown.status_code == 200, shown.content


@integrated
@pytest.mark.django_db
def test_a_failing_provider_starts_the_response_with_no_facts(settings, signed_in):
    settings.PROLOG_FACTS_PROVIDER = f"{__name__}.fail"
    rid = start(signed_in)
    assert SurveyResponse.objects.get(pk=rid).facts == {}


def fail_in_the_database(participant, definition):
    """A host whose own query fails: Postgres aborts the transaction it ran in."""
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM no_such_host_table")


@integrated
@pytest.mark.django_db
def test_a_provider_failing_in_the_database_still_starts_the_response(settings, signed_in):
    settings.PROLOG_FACTS_PROVIDER = f"{__name__}.fail_in_the_database"
    rid = start(signed_in)
    assert SurveyResponse.objects.get(pk=rid).facts == {}


@integrated
@pytest.mark.django_db
def test_no_provider_means_every_fact_is_unknown(settings, signed_in):
    settings.PROLOG_FACTS_PROVIDER = None
    rid = start(signed_in)
    response = SurveyResponse.objects.get(pk=rid)
    assert response.facts == {}
    assert visible_keys(response.definition, {}) == ["feeling"]
