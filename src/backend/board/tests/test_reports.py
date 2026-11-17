from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import OperationalError, close_old_connections
from django.urls import reverse
from rest_framework.test import APIClient

from board.models import Post, Report

pytestmark = pytest.mark.django_db


def test_reports_are_private_idempotent_and_retain_first_evidence(guest_client, draft):
    owner = guest_client()
    reporter = guest_client()
    post = owner.post("/board/posts", draft, format="json").data
    comment = owner.post(f"/board/posts/{post['id']}/comments", {"body": "Original comment"}).data
    post_path = f"/board/posts/{post['id']}/reports"
    comment_path = f"/board/comments/{comment['id']}/reports"
    first = reporter.post(post_path, {"reason": "  Private post report  "}, format="json")
    assert first.status_code == 201
    assert first.data == {"reported": True}
    assert reporter.post(comment_path, {"reason": "Private comment report"}).status_code == 201
    owner.patch(f"/board/posts/{post['id']}", {"title": "Edited title", "body": "Edited body"})
    owner.patch(f"/board/comments/{comment['id']}", {"body": "Edited comment"})
    assert reporter.post(post_path, {"reason": "Replacement reason"}).status_code == 200
    assert reporter.post(comment_path, {"reason": "Replacement reason"}).status_code == 200
    assert Report.objects.count() == 2
    post_report = Report.objects.get(target_kind="post", target_id=post["id"])
    assert post_report.reason == "Private post report"
    assert post_report.target_title == draft["title"]
    assert post_report.target_body == draft["body"]
    assert post_report.target_author_name == post["author"]["name"]
    assert post_report.target_author_kind == "guest"
    comment_report = Report.objects.get(target_kind="comment", target_id=comment["id"])
    assert comment_report.target_body == "Original comment"
    assert comment_report.reason == "Private comment report"
    for path in [post_path, comment_path, "/board/reports"]:
        assert reporter.get(path).status_code in {404, 405}
    for path in [
        "/board/posts",
        f"/board/posts/{post['id']}",
        f"/board/posts/{post['id']}/comments",
        "/board/tags",
    ]:
        public = owner.get(path)
        assert public.status_code == 200
        assert "Private post report" not in str(public.data)
        assert "Private comment report" not in str(public.data)
        assert "reporter" not in str(public.data)
        assert reporter.session["community_guest_id"] not in str(public.data)
    assert owner.delete(f"/board/posts/{post['id']}").status_code == 204
    assert not Post.objects.filter(pk=post["id"]).exists()
    post_report.refresh_from_db()
    comment_report.refresh_from_db()
    assert post_report.target_body == draft["body"]
    assert comment_report.target_body == "Original comment"
    assert Report.objects.count() == 2
    assert reporter.post(post_path, {"reason": "After deletion"}).status_code == 404


def test_different_reporters_create_independent_private_reports(guest_client, draft):
    owner = guest_client()
    first = guest_client()
    second = guest_client()
    post = owner.post("/board/posts", draft, format="json").data
    path = f"/board/posts/{post['id']}/reports"
    assert first.post(path, {"reason": "First"}).status_code == 201
    assert second.post(path, {"reason": "Second"}).status_code == 201
    assert first.post(path, {"reason": "Again"}).status_code == 200
    assert Report.objects.count() == 2


def test_account_report_evidence_survives_reporter_account_deletion(account_client, draft):
    owner, _ = account_client()
    reporter, account = account_client()
    post = owner.post("/board/posts", draft, format="json").data
    path = f"/board/posts/{post['id']}/reports"
    assert reporter.post(path, {"reason": "Evidence"}).status_code == 201
    account.account_type = "business"
    account.business_name = "New business name"
    account.save(update_fields=["account_type", "business_name"])
    assert reporter.post(path, {"reason": "Again"}).status_code == 200
    account.user.delete()
    report = Report.objects.get()
    assert report.reporter_account_id is None
    assert report.reporter_kind == "student"
    assert report.reporter_guest_id == ""
    assert report.reason == "Evidence"


@pytest.mark.parametrize("reason", ["", " ", "x" * 2001, None, 123])
def test_report_reason_is_required_trimmed_bounded_text(guest_client, draft, reason):
    owner = guest_client()
    post = owner.post("/board/posts", draft, format="json").data
    response = owner.post(f"/board/posts/{post['id']}/reports", {"reason": reason}, format="json")
    assert response.status_code == 422
    assert response.data["error"]["code"] == "validation_error"
    assert not Report.objects.exists()


def test_reports_reject_client_identity_and_allow_maximum_reason(guest_client, draft):
    owner = guest_client()
    post = owner.post("/board/posts", draft, format="json").data
    path = f"/board/posts/{post['id']}/reports"
    assert (
        owner.post(path, {"reason": "No", "reporter_account": 1}, format="json").status_code == 422
    )
    assert owner.post(path, {"reason": "x" * 2000}, format="json").status_code == 201
    assert len(Report.objects.get().reason) == 2000
    assert owner.post("/board/comments/999999/reports", {"reason": "Missing"}).status_code == 404


@pytest.mark.django_db(transaction=True)
def test_concurrent_duplicate_reports_converge(guest_client, draft):
    owner = guest_client()
    reporter = guest_client()
    post = owner.post("/board/posts", draft, format="json").data
    path = f"/board/posts/{post['id']}/reports"
    cookies = deepcopy(reporter.cookies)
    token = reporter.cookies["csrftoken"].value

    def submit(reason):
        close_old_connections()
        try:
            client = APIClient(enforce_csrf_checks=True)
            client.cookies = deepcopy(cookies)
            response = client.post(path, {"reason": reason}, format="json", HTTP_X_CSRFTOKEN=token)
            return response.status_code, response.data
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(submit, ["First request", "Second request"]))
    assert sorted(status for status, _ in results) == [200, 201]
    assert all(body == {"reported": True} for _, body in results)
    assert Report.objects.count() == 1
    assert Report.objects.get().reason in {"First request", "Second request"}


def test_report_queue_requires_staff_and_permissions_and_preserves_readonly_evidence(
    guest_client, draft
):
    owner = guest_client()
    post = owner.post("/board/posts", draft, format="json").data
    owner.post(f"/board/posts/{post['id']}/reports", {"reason": "Staff-only evidence"})
    report = Report.objects.get()
    queue_url = reverse("admin:board_report_changelist")
    detail_url = reverse("admin:board_report_change", args=[report.pk])
    anonymous = APIClient()
    assert anonymous.get(queue_url).status_code == 302
    users = get_user_model().objects
    nonstaff = users.create_user(username="board-nonstaff")
    anonymous.force_login(nonstaff)
    assert anonymous.get(queue_url).status_code == 302
    staff = users.create_user(username="board-moderator", is_staff=True)
    moderator = APIClient()
    moderator.force_login(staff)
    assert moderator.get(queue_url).status_code == 403
    staff.user_permissions.add(
        *Permission.objects.filter(
            content_type__app_label="board", codename__in=["view_report", "change_report"]
        )
    )
    queue = moderator.get(queue_url)
    assert queue.status_code == 200
    assert moderator.get(detail_url).status_code == 200
    moderator.post(detail_url, {"reason": "Tampered", "target_body": "Tampered", "_save": "Save"})
    report.refresh_from_db()
    assert report.reason == "Staff-only evidence"
    assert report.target_body == draft["body"]
    moderator.post(queue_url, {"action": "mark_reviewed", "_selected_action": [str(report.pk)]})
    report.refresh_from_db()
    assert report.reviewed_at is not None
    assert report.reviewed_by_id == staff.pk
    assert moderator.get(reverse("admin:board_report_delete", args=[report.pk])).status_code == 403
    assert Report.objects.filter(pk=report.pk).exists()


def test_board_error_responses_are_private_even_outside_drf(guest_client, monkeypatch):
    client = guest_client()

    def unavailable():
        raise OperationalError("Test database outage")

    monkeypatch.setattr("board.views.readable_posts", unavailable)
    response = client.get("/board/posts")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "database_unavailable"
    assert response["Cache-Control"] == "private, no-store"
    assert client.get("/board/not-a-route")["Cache-Control"] == "private, no-store"
    malformed = client.post("/board/posts", data="{bad", content_type="application/json")
    assert malformed.status_code == 400
    assert malformed["Cache-Control"] == "private, no-store"
