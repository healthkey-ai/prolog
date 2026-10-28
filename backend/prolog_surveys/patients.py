"""Patient linkage for identified, linked-contact submissions.

The contact's patient is an analytics join only. It never changes the response's
participant, creates an account, or grants access to a clinical record.
"""

from __future__ import annotations

import logging

from django.apps import apps
from django.db import connection
from django.utils.module_loading import import_string
from django.views.decorators.debug import sensitive_variables

from . import conf

log = logging.getLogger(__name__)


class PatientLinkError(Exception):
    """Submission can be retried after the host's linkage service recovers."""


def patient_model():
    label = conf.patient_model()
    return apps.get_model(label) if label else None


@sensitive_variables()
def link_submitted_response(response):
    """Link only submitted responses carrying an explicitly linked contact.

    The caller holds the response lock and transaction. A failed link rolls
    submission back, so retries never strand a submitted response without its
    patient. No address or host exception text escapes into logs/error reports.
    """
    model = patient_model()
    if model is None or not response.is_submitted:
        return None
    from .models import SurveyLinkedContact

    contact = SurveyLinkedContact.objects.filter(response=response).first()
    if contact is None:
        return None
    if contact.patient_id:
        return contact.patient
    try:
        path = conf.get("PROLOG_PATIENT_LINKER")
        linker = import_string(path) if path else link_promop_patient
        patient = linker(response, contact)
        if not isinstance(patient, model) or patient.pk is None or patient._state.adding:
            raise PatientLinkError("linker must return a saved patient")
        contact.patient = patient
        contact.save(update_fields=["patient"])
        return patient
    except Exception as exc:
        log.error("patient linkage failed with %s for response %s", type(exc).__name__, response.pk)
        raise PatientLinkError from None


@sensitive_variables()
def link_promop_patient(response, contact):
    """PRomop adapter: resolve an account owner, or retain the minted person.

    An email here is a self-report, not a verified identity. The link does not
    re-parent answers or attach a PatientUser; in particular it never puts the
    unverified address on Person, which the host uses for identity matching.
    """
    if conf.patient_model() != "omop_core.PatientRecord":
        raise PatientLinkError("a custom patient model requires PROLOG_PATIENT_LINKER")
    from omop_core.models import PatientRecord, Person
    from patient_portal.models import PatientUser

    participant_id = response.participant_id_or_none
    if participant_id is None or conf.participant_model() != "omop_core.Person":
        raise PatientLinkError("PRomop linkage requires a Person participant")
    source = PatientRecord.objects.filter(person_id=participant_id).first()
    organization_id = source.organization_id if source else None
    # There is no row to lock on the first occurrence of an address. A stable,
    # salted PostgreSQL transaction lock serializes that gap across responses
    # and workers, without persisting or exposing the address in a lock key.
    lock_key = int(
        conf.salted_hash("patient-email", str(organization_id), contact.email.casefold())[:16], 16
    )
    if lock_key >= 2**63:
        lock_key -= 2**64
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [lock_key])
    holders = list(
        PatientUser.objects.filter(
            identity__email__iexact=contact.email, is_active=True
        ).select_related("person")[:2]
    )
    if len(holders) > 1:
        raise PatientLinkError("ambiguous account owner")
    target_person_id = holders[0].person_id if holders else participant_id
    if not holders:
        # A prior contact-only respondent has no account. Reuse the minimal
        # record from that submission rather than minting a patient per survey.
        matches = list(
            PatientRecord.objects.filter(
                email__iexact=contact.email, organization_id=organization_id
            ).values_list("person_id", flat=True)[:2]
        )
        if len(matches) > 1:
            raise PatientLinkError("ambiguous patient email")
        if matches:
            target_person_id = matches[0]
    # The host writer locks PatientRecord before Person. Follow that order,
    # sorting multiple projections so two reciprocal link requests cannot
    # deadlock. No clinical writes occur on the source or target person.
    locked = list(
        PatientRecord.objects.select_for_update()
        .filter(person_id__in={participant_id, target_person_id})
        .order_by("pk")
    )
    locked_source = next((p for p in locked if p.person_id == participant_id), None)
    current_organization_id = locked_source.organization_id if locked_source else None
    if current_organization_id != organization_id:
        raise PatientLinkError("source organization changed; retry submission")
    target = next((p for p in locked if p.person_id == target_person_id), None)
    if target and target.organization_id != organization_id:
        raise PatientLinkError("account owner belongs to another organization")
    person = Person.objects.select_for_update().get(pk=target_person_id)
    patient, _ = PatientRecord.objects.get_or_create(
        person=person,
        defaults={
            "email": contact.email,
            "organization_id": organization_id,
            "user_edited_fields": ["email"],
        },
    )
    # Do not replace a patient's existing or verified email. The self-reported
    # address is durable on the contact; the projection's pending edit marker
    # keeps a newly filled email through host refresh without touching Person.
    if not patient.email:
        patient.email = contact.email
        patient.user_edited_fields = sorted(set(patient.user_edited_fields or []) | {"email"})
        patient.save(update_fields=["email", "user_edited_fields", "updated_at"])
    return patient
