from dataclasses import dataclass
from typing import Literal

from django.conf import settings
from django.contrib.auth import SESSION_KEY, get_user_model
from rest_framework.exceptions import NotAuthenticated, PermissionDenied
from rest_framework.request import Request

from accounts.models import Account, AccountType
from communities.guest_names import guest_name
from communities.views import ensure_guest_id, guest_id

from .models import Authored, AuthorKind, PostKind


@dataclass(frozen=True)
class AccountWriter:
    account: Account

    @property
    def kind(self) -> str:
        return str(self.account.account_type)

    @property
    def name(self) -> str:
        if self.kind == AccountType.BUSINESS:
            return str(self.account.business_name)
        return str(self.account.username or "Student")


@dataclass(frozen=True)
class GuestWriter:
    identity: str

    @property
    def kind(self) -> str:
        return AuthorKind.GUEST

    @property
    def name(self) -> str:
        return guest_name(self.identity)


Writer = AccountWriter | GuestWriter
ViewerKind = Literal["visitor", "guest", "student", "business", "unfinished", "inactive"]


@dataclass(frozen=True)
class Viewer:
    kind: ViewerKind
    writer: Writer | None

    @property
    def create_kinds(self) -> list[str]:
        if self.kind not in {"guest", "student", "business"}:
            return []
        kinds: list[str] = [PostKind.QUESTION, PostKind.INFORMATION]
        if self.kind == "business":
            kinds.append(PostKind.ANNOUNCEMENT)
        return kinds

    def require_writer(self) -> Writer:
        if self.writer is None:
            if self.kind in {"visitor", "guest"}:
                raise NotAuthenticated("Sign in to publish on the board.")
            raise PermissionDenied(
                "Complete sign-up with an active account to publish on the board."
            )
        return self.writer


def viewer_for(request: Request, *, establish_guest: bool = False) -> Viewer:
    user = request.user
    # SessionAuthentication declines inactive users. They must not become guests.
    if not getattr(user, "is_authenticated", False):
        user = getattr(request, "board_session_user", request._request.user)
    if getattr(user, "is_authenticated", False):
        if not user.is_active:
            return Viewer("inactive", None)
        account = Account.objects.filter(user_id=user.pk).first()
        if account is None or account.account_type not in AccountType.values:
            return Viewer("unfinished", None)
        kind: ViewerKind = "business" if account.account_type == AccountType.BUSINESS else "student"
        return Viewer(kind, AccountWriter(account))
    session_user_id = request.session.get(SESSION_KEY)
    if (
        session_user_id is not None
        and get_user_model().objects.filter(pk=session_user_id, is_active=False).exists()
    ):
        return Viewer("inactive", None)
    if settings.CHAT_GUEST_ACCESS:
        identity = ensure_guest_id(request) if establish_guest else guest_id(request)
        return Viewer("guest", GuestWriter(identity) if identity else None)
    return Viewer("visitor", None)


def owns(writer: Writer | None, authored: Authored) -> bool:
    match writer:
        case AccountWriter(account):
            return authored.author_account_id == account.pk
        case GuestWriter(identity):
            return (
                authored.author_kind == AuthorKind.GUEST
                and authored.author_account_id is None
                and bool(identity)
                and authored.author_guest_id == identity
            )
        case None:
            return False


def author_stamp(writer: Writer) -> dict:
    return {
        "author_account": writer.account if isinstance(writer, AccountWriter) else None,
        "author_guest_id": writer.identity if isinstance(writer, GuestWriter) else "",
        "author_kind": writer.kind,
        "author_name": writer.name,
    }


def reporter_stamp(writer: Writer) -> dict:
    return {
        "reporter_account": writer.account if isinstance(writer, AccountWriter) else None,
        "reporter_guest_id": writer.identity if isinstance(writer, GuestWriter) else "",
        "reporter_kind": writer.kind,
        "reporter_name": writer.name,
    }
