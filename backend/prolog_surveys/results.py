"""Who may read a survey's results, and how they say who they are.

PROlog holds no accounts and checks no passwords. A deployment names a
callable in ``PROLOG_RESULTS_AUTH``; it is handed an address and a password
and answers with a :class:`ResultsViewer` or ``None``. The host's own login
path — its hashing, its lockout, its audit trail — is the only one there is,
and it decides what "may read results" means. In PRomop that is exactly what
the Django admin requires of the same person, which is where these readers
already have accounts.

What PROlog keeps of a signed-in reader is a session entry: who they are, for
the report page to show, and the two permissions it asks about. No password,
no token of its own, nothing in the database.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.utils.module_loading import import_string

from . import conf

SESSION_KEY = "prolog_results_viewer"


class PasswordRefused(Exception):
    """The host declined a password change, with reasons a reader can act on.

    Its ``messages`` are the host's own: its policy (length, reuse, how common
    the word is) is the only policy there is, and its wording is what the
    reader is told.
    """

    def __init__(self, messages: list[str]):
        super().__init__("; ".join(messages))
        self.messages = messages


@dataclass(frozen=True)
class ResultsViewer:
    """A person the host has recognised, and what they may see.

    ``label`` is shown on the page so a reader can tell whose access they are
    using; make it something they recognise (their address), never an id.
    """

    label: str
    may_read_responses: bool = True
    may_read_contacts: bool = False

    def as_session(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "responses": self.may_read_responses,
            "contacts": self.may_read_contacts,
        }

    @classmethod
    def from_session(cls, data: dict[str, Any]) -> ResultsViewer:
        return cls(
            label=str(data.get("label", "")),
            may_read_responses=bool(data.get("responses")),
            may_read_contacts=bool(data.get("contacts")),
        )


def get_results_auth():
    """The configured authenticator: a callable, a class or a prebuilt instance."""
    path = conf.get("PROLOG_RESULTS_AUTH")
    if not path:
        return None
    target = import_string(path)
    return target


def authenticate(email: str, password: str) -> ResultsViewer | None:
    """Ask the host whether this is a reader. Any failure is "no".

    A host that raises is not a reason to say yes, and the exception must not
    reach a response: it would carry the credentials into error reporting.
    """
    auth = get_results_auth()
    if auth is None:
        return None
    viewer = auth(email, password)
    if viewer is None:
        return None
    if not isinstance(viewer, ResultsViewer):
        raise TypeError("PROLOG_RESULTS_AUTH must return a ResultsViewer or None")
    return viewer


def get_password_change():
    """The configured password-change hook, if the deployment offers one."""
    path = conf.get("PROLOG_RESULTS_PASSWORD_CHANGE")
    return import_string(path) if path else None


def change_password(email: str, current: str, new: str) -> None:
    """Ask the host to change a reader's password. Raises PasswordRefused with
    the host's reasons; anything else is the host failing, not a refusal."""
    hook = get_password_change()
    if hook is None:
        raise PasswordRefused(["this deployment does not offer a password change here"])
    hook(email, current, new)


def sign_in(request, viewer: ResultsViewer) -> None:
    request.session[SESSION_KEY] = viewer.as_session()
    request.session.cycle_key()


def sign_out(request) -> None:
    request.session.pop(SESSION_KEY, None)


def viewer_of(request) -> ResultsViewer | None:
    data = request.session.get(SESSION_KEY)
    return ResultsViewer.from_session(data) if isinstance(data, dict) else None
