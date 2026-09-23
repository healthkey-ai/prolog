"""The report page: who gets in, what they see, and what they may download."""

from __future__ import annotations

import csv
import io

import pytest

from prolog_surveys.definitions.loader import load_definition, publish_version
from prolog_surveys.models import SurveyContact
from prolog_surveys.results import ResultsViewer

REPORT = "/api/run/report/sample-wellbeing/"
LOGIN = REPORT + "login/"


def _viewer(email, password):
    """A stand-in host authenticator: one reader, one reader of addresses too."""
    if password != "right":
        return None
    if email == "reader@example.org":
        return ResultsViewer(label=email)
    if email == "everything@example.org":
        return ResultsViewer(label=email, may_read_contacts=True)
    return None


def _raises(email, password):
    raise RuntimeError("the host blew up while checking " + password)


def _not_a_viewer(email, password):
    return "yes"


@pytest.fixture
def survey(db, example):
    version = load_definition(example, activate=True).version
    publish_version(version)
    return version


@pytest.fixture
def host_auth(settings):
    settings.PROLOG_RESULTS_AUTH = f"{__name__}._viewer"
    return settings


def test_the_door_says_only_whether_there_is_a_way_in(api_client, survey, host_auth):
    """Nothing about a survey's results before anybody has proved who they are."""
    body = api_client.get(REPORT).json()
    assert body["survey"] == "sample-wellbeing"
    assert body["viewer"] is None and body["sign_in_available"] is True
    assert "stats" not in body


def test_a_deployment_with_no_authenticator_says_so(api_client, survey, settings):
    settings.PROLOG_RESULTS_AUTH = None
    assert api_client.get(REPORT).json()["sign_in_available"] is False
    # ...and there is no way in at all, rather than a password prompt that can never pass
    r = api_client.post(LOGIN, {"email": "reader@example.org", "password": "right"}, format="json")
    assert r.status_code == 404


def test_the_host_decides_who_reads_results(api_client, survey, host_auth):
    wrong = api_client.post(LOGIN, {"email": "reader@example.org", "password": "no"}, format="json")
    assert wrong.status_code == 403
    # a correct password for somebody the host does not call a reader looks the same
    stranger = api_client.post(
        LOGIN, {"email": "stranger@example.org", "password": "right"}, format="json"
    )
    assert stranger.status_code == 403
    r = api_client.post(LOGIN, {"email": "reader@example.org", "password": "right"}, format="json")
    assert r.status_code == 200
    assert r.json()["viewer"] == {
        "label": "reader@example.org",
        "may_read_responses": True,
        "may_read_contacts": False,
    }
    # the session carries it, so the page itself now has the numbers
    body = api_client.get(REPORT).json()
    assert body["stats"]["versions"][0]["respondents"] == 0


def test_a_host_that_raises_is_not_a_way_in(api_client, survey, settings, caplog):
    """A broken authenticator is a 500, never an admission — and the password
    must not reach the log."""
    settings.PROLOG_RESULTS_AUTH = f"{__name__}._raises"
    r = api_client.post(
        LOGIN, {"email": "reader@example.org", "password": "hunter2"}, format="json"
    )
    assert r.status_code == 500
    assert "hunter2" not in caplog.text and "RuntimeError" in caplog.text
    assert api_client.get(REPORT).json()["viewer"] is None


def test_a_host_that_answers_with_nonsense_is_not_a_way_in(api_client, survey, settings):
    settings.PROLOG_RESULTS_AUTH = f"{__name__}._not_a_viewer"
    r = api_client.post(LOGIN, {"email": "reader@example.org", "password": "right"}, format="json")
    assert r.status_code == 500
    assert api_client.get(REPORT).json()["viewer"] is None


def test_downloads_need_a_reader_and_the_right_permission(api_client, survey, host_auth):
    responses = REPORT + "export/responses.csv"
    contacts = REPORT + "export/contacts.csv"
    assert api_client.get(responses).status_code == 403
    assert api_client.get(contacts).status_code == 403

    api_client.post(LOGIN, {"email": "reader@example.org", "password": "right"}, format="json")
    assert api_client.get(responses).status_code == 200
    # ...but this reader may not see addresses, which are their own permission
    assert api_client.get(contacts).status_code == 403

    api_client.post(LOGIN, {"email": "everything@example.org", "password": "right"}, format="json")
    assert api_client.get(contacts).status_code == 200


def test_the_response_export_streams_the_version_asked_for(api_client, survey, host_auth, example):
    """Each version is its own file: an answer means what its own version says."""
    api_client.post(LOGIN, {"email": "reader@example.org", "password": "right"}, format="json")
    rid = api_client.post(
        "/api/run/responses/", {"slug": "sample-wellbeing", "language": "en"}, format="json"
    ).json()["id"]
    api_client.put(
        f"/api/run/responses/{rid}/answers/country/", {"value": {"option": "GB"}}, format="json"
    )
    r = api_client.get(REPORT + "export/responses.csv?include_in_progress=true")
    assert r.status_code == 200
    assert r["Content-Type"].startswith("text/csv")
    assert 'filename="sample-wellbeing-1.0-responses-' in r["Content-Disposition"]
    rows = list(csv.reader(io.StringIO(b"".join(r.streaming_content).decode())))
    assert len(rows) == 2 and rows[1][0] == rid
    # the submitted-only export is the default, and there are none
    r = api_client.get(REPORT + "export/responses.csv")
    assert len(list(csv.reader(io.StringIO(b"".join(r.streaming_content).decode())))) == 1
    # a version nobody loaded is a 404, not somebody else's data
    assert api_client.get(REPORT + "export/responses.csv?version=9.9").status_code == 404


def test_the_counts_are_of_the_rows_the_export_will_contain(api_client, survey, host_auth):
    """Contact capture keeps addresses in one table or the other; counting both
    would promise rows the file does not hold."""
    rid = api_client.post(
        "/api/run/responses/", {"slug": "sample-wellbeing", "language": "en"}, format="json"
    ).json()["id"]
    api_client.post(
        f"/api/run/responses/{rid}/contact/", {"email": "someone@example.org"}, format="json"
    )
    # a row in the table this version's capture mode does not read
    SurveyContact.objects.create(
        survey_version=survey, email="stranded@example.org", language="en", consent_text="x"
    )
    api_client.post(LOGIN, {"email": "everything@example.org", "password": "right"}, format="json")
    row = next(
        v for v in api_client.get(REPORT).json()["stats"]["versions"] if v["version"] == "1.0"
    )
    r = api_client.get(REPORT + "export/contacts.csv")
    rows = list(csv.reader(io.StringIO(b"".join(r.streaming_content).decode())))
    assert row["contacts"] == len(rows) - 1


def test_signing_out_closes_the_door_again(api_client, survey, host_auth):
    api_client.post(LOGIN, {"email": "reader@example.org", "password": "right"}, format="json")
    assert api_client.post(REPORT + "logout/").status_code == 204
    assert api_client.get(REPORT).json()["viewer"] is None
    assert api_client.get(REPORT + "export/responses.csv").status_code == 403
