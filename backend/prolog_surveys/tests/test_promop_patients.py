"""Exercise the built-in adapter against a minimal host schema in PostgreSQL.

The fields and identity ownership relation mirror PRomop dev d7632df1. Fake
modules isolate the adapter from the host package; all lookup/locking and
creation queries execute against actual tables, including concurrent calls.
"""

# ruff: noqa: DJ001, DJ008 -- fixtures mirror nullable host email columns.

import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from types import ModuleType, SimpleNamespace

import pytest
from django.db import close_old_connections, connection, models, transaction

from prolog_surveys import conf
from prolog_surveys.patients import PatientLinkError, link_promop_patient


class HostPerson(models.Model):
    email = models.EmailField(null=True)

    class Meta:
        app_label = "prolog_patient_tests"
        db_table = "prolog_test_host_person"
        managed = False


class HostPatient(models.Model):
    person = models.OneToOneField(HostPerson, on_delete=models.CASCADE)
    email = models.EmailField(null=True)
    organization_id = models.IntegerField(null=True)
    user_edited_fields = models.JSONField(default=list)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "prolog_patient_tests"
        db_table = "prolog_test_host_patient"
        managed = False


class HostIdentity(models.Model):
    email = models.EmailField()

    class Meta:
        app_label = "prolog_patient_tests"
        db_table = "prolog_test_host_identity"
        managed = False


class HostPatientUser(models.Model):
    person = models.OneToOneField(HostPerson, on_delete=models.CASCADE)
    identity = models.OneToOneField(HostIdentity, on_delete=models.CASCADE)
    is_active = models.BooleanField(default=True)

    class Meta:
        app_label = "prolog_patient_tests"
        db_table = "prolog_test_host_user"
        managed = False


@pytest.fixture
def host(transactional_db, monkeypatch):
    classes = [HostPerson, HostPatient, HostIdentity, HostPatientUser]
    with connection.schema_editor() as editor:
        for model in classes:
            editor.create_model(model)
    omop = ModuleType("omop_core.models")
    omop.Person, omop.PatientRecord = HostPerson, HostPatient
    portal = ModuleType("patient_portal.models")
    portal.PatientUser = HostPatientUser
    monkeypatch.setitem(sys.modules, "omop_core", ModuleType("omop_core"))
    monkeypatch.setitem(sys.modules, "omop_core.models", omop)
    monkeypatch.setitem(sys.modules, "patient_portal", ModuleType("patient_portal"))
    monkeypatch.setitem(sys.modules, "patient_portal.models", portal)
    monkeypatch.setattr(conf, "patient_model", lambda: "omop_core.PatientRecord")
    monkeypatch.setattr(conf, "participant_model", lambda: "omop_core.Person")
    yield
    with connection.schema_editor() as editor:
        for model in reversed(classes):
            editor.delete_model(model)


def _attempt(org=7, email="respondent@example.org"):
    person = HostPerson.objects.create()
    source = HostPatient.objects.create(person=person, organization_id=org)
    return SimpleNamespace(participant_id_or_none=person.pk), SimpleNamespace(email=email), source


def _link(response, contact):
    with transaction.atomic():
        return link_promop_patient(response, contact)


def test_unknown_email_promotes_existing_minimal_record_and_preserves_source_identity(host):
    response, contact, source = _attempt()
    patient = _link(response, contact)
    assert patient.pk == source.pk
    assert patient.email == contact.email and "email" in patient.user_edited_fields
    assert patient.person.email is None  # No unverified identity assertion.
    assert not HostPatientUser.objects.exists()


def test_account_lookup_uses_email_case_insensitively_without_replacing_existing_email(host):
    response, contact, source = _attempt(email="OWNER@example.org")
    owner = HostPerson.objects.create(email="verified@example.org")
    patient = HostPatient.objects.create(
        person=owner, email="verified@example.org", organization_id=7
    )
    identity = HostIdentity.objects.create(email="owner@example.org")
    HostPatientUser.objects.create(person=owner, identity=identity)
    assert _link(response, contact).pk == patient.pk
    patient.refresh_from_db()
    assert patient.email == "verified@example.org"
    assert response.participant_id_or_none == source.person_id


def test_prior_contact_only_patient_is_reused_on_next_survey(host):
    first, contact, _ = _attempt()
    existing = _link(first, contact)
    second, contact, _ = _attempt(email=contact.email.upper())
    assert _link(second, contact).pk == existing.pk


def test_cross_organization_account_is_refused(host):
    response, contact, _ = _attempt()
    owner = HostPerson.objects.create()
    HostPatient.objects.create(person=owner, email=contact.email, organization_id=8)
    identity = HostIdentity.objects.create(email=contact.email)
    HostPatientUser.objects.create(person=owner, identity=identity)
    with pytest.raises(PatientLinkError):
        _link(response, contact)


def test_ambiguous_existing_patient_email_is_refused(host):
    response, contact, _ = _attempt()
    for _ in range(2):
        HostPatient.objects.create(
            person=HostPerson.objects.create(), email=contact.email, organization_id=7
        )
    with pytest.raises(PatientLinkError):
        _link(response, contact)


def test_missing_projection_is_created_for_existing_person(host):
    person = HostPerson.objects.create()
    response = SimpleNamespace(participant_id_or_none=person.pk)
    patient = _link(response, SimpleNamespace(email="minimal@example.org"))
    assert patient.person_id == person.pk
    assert patient.email == "minimal@example.org"


def test_simultaneous_first_submission_for_same_email_uses_one_patient(host):
    first, contact, _ = _attempt()
    second, _, _ = _attempt()
    barrier = threading.Barrier(2)

    def worker(response):
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            return _link(response, contact).pk
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(worker, [first, second]))
    assert ids[0] == ids[1]
    assert HostPatient.objects.filter(email__iexact=contact.email).count() == 1


def test_source_organization_change_during_lookup_is_refused(host, monkeypatch):
    response, contact, source = _attempt()
    original = HostPatient.objects.select_for_update

    def change_org_before_projection_lock(*args, **kwargs):
        HostPatient.objects.filter(pk=source.pk).update(organization_id=8)
        return original(*args, **kwargs)

    monkeypatch.setattr(HostPatient.objects, "select_for_update", change_org_before_projection_lock)
    with pytest.raises(PatientLinkError, match="source organization changed"):
        _link(response, contact)
