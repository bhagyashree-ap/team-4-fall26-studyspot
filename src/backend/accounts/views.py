"""Account routes.

``GET /auth/config`` is public: it tells the browser which Auth0 tenant to log
in with, so that the frontend build carries no environment of its own.
``/account`` needs a valid access token.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.db import IntegrityError, models, transaction
from django.db.models import TextField
from django.db.models.functions import Cast
from rest_framework import status
from rest_framework.exceptions import APIException, NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .authentication import Auth0Authentication, configured
from .models import Account, AccountType, StudentProfile
from .serializers import (
    AccountSerializer,
    CompleteSignUpSerializer,
    StudentProfileSerializer,
    public_student_profile,
    username_problem,
)


def require_student(request: Request) -> Account:
    account = getattr(request.user, "account", None)
    if not request.user.is_active or account is None or account.account_type != AccountType.STUDENT:
        raise PermissionDenied("An active student account is required.")
    return account


def spot_summary(spot_id: str) -> dict[str, str] | None:
    from spots.models import StudySpot

    spot = StudySpot.objects.filter(pk=spot_id).first()
    return {"id": spot.pk, "name": spot.name} if spot else None


def profile_payload(profile: StudentProfile) -> dict[str, Any]:
    data = public_student_profile(profile)
    if data.get("study_spot_id"):
        data["study_spot"] = spot_summary(data["study_spot_id"])
    return data


class StudentProfileView(APIView):
    authentication_classes = [Auth0Authentication]
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        account = require_student(request)
        profile, _ = StudentProfile.objects.get_or_create(account=account)
        return Response(
            {
                **StudentProfileSerializer(profile).data,
                "username": account.username,
                "study_spot": spot_summary(profile.study_spot_id)
                if profile.study_spot_id
                else None,
            }
        )

    def put(self, request: Request) -> Response:
        account = require_student(request)
        profile, _ = StudentProfile.objects.get_or_create(account=account)
        serializer = StudentProfileSerializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        spot_id = serializer.validated_data.get("study_spot_id")
        if spot_id:
            from spots.models import StudySpot

            if not StudySpot.objects.filter(pk=spot_id).exists():
                raise ValidationError({"study_spot_id": "Choose a study spot from StudySpot."})
        profile = serializer.save()
        return Response(
            {
                **StudentProfileSerializer(profile).data,
                "username": account.username,
                "study_spot": spot_summary(profile.study_spot_id)
                if profile.study_spot_id
                else None,
            }
        )


class StudentDirectoryView(APIView):
    authentication_classes = [Auth0Authentication]
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        require_student(request)
        from spots.models import StudySpot

        query = request.query_params.get("q", "").strip()
        course = request.query_params.get("course", "").strip()
        topic = request.query_params.get("topic", "").strip()
        spot_id = request.query_params.get("spot", "").strip()
        if len(spot_id) > 255:
            raise ValidationError({"spot": "Study spot identifier must be at most 255 characters."})
        try:
            offset = int(request.query_params.get("offset", "0"))
        except ValueError as error:
            raise ValidationError({"offset": "Offset must be a non-negative integer."}) from error
        if offset < 0:
            raise ValidationError({"offset": "Offset must be a non-negative integer."})
        if max(map(len, (query, course, topic))) > 100:
            raise ValidationError("Search terms must be at most 100 characters.")
        profiles = (
            StudentProfile.objects.filter(
                discoverable=True,
                account__account_type=AccountType.STUDENT,
                account__user__is_active=True,
            )
            .select_related("account")
            .exclude(account__user=request.user)
            .annotate(
                courses_text=Cast("courses", output_field=TextField()),
                topics_text=Cast("topics", output_field=TextField()),
            )
        )
        if course:
            profiles = profiles.filter(
                visible_fields__contains=["courses"], courses_text__icontains=course
            )
        if topic:
            profiles = profiles.filter(
                visible_fields__contains=["topics"], topics_text__icontains=topic
            )
        if spot_id:
            profiles = profiles.filter(
                visible_fields__contains=["study_spot_id"], study_spot_id=spot_id
            )
        if query:
            profiles = profiles.filter(
                models.Q(account__username__icontains=query)
                | (
                    models.Q(visible_fields__contains=["school"])
                    & models.Q(school__icontains=query)
                )
                | (
                    models.Q(visible_fields__contains=["courses"])
                    & models.Q(courses_text__icontains=query)
                )
                | (
                    models.Q(visible_fields__contains=["topics"])
                    & models.Q(topics_text__icontains=query)
                )
            )
        latitude, longitude = (
            request.query_params.get("latitude"),
            request.query_params.get("longitude"),
        )
        distances: dict[str, int] = {}
        if (latitude is None) != (longitude is None):
            raise ValidationError("Provide both latitude and longitude.")
        if latitude is not None:
            try:
                lat, lon = float(latitude), float(longitude)
                radius = int(request.query_params.get("radius", "25000"))
            except ValueError as error:
                raise ValidationError("Location and radius must be numeric.") from error
            if not (-90 <= lat <= 90 and -180 <= lon <= 180 and 1 <= radius <= 100000):
                raise ValidationError("Location or radius is outside the allowed range.")
            profiles = profiles.filter(visible_fields__contains=["study_spot_id"])
            spots = {
                spot.pk: spot
                for spot in StudySpot.objects.filter(pk__in=[p.study_spot_id for p in profiles])
            }
            found = []
            from math import asin, cos, radians, sin, sqrt

            for profile in profiles:
                place = spots.get(profile.study_spot_id)
                if not place:
                    continue
                distance = (
                    6371000
                    * 2
                    * asin(
                        sqrt(
                            sin(radians(place.latitude - lat) / 2) ** 2
                            + cos(radians(lat))
                            * cos(radians(place.latitude))
                            * sin(radians(place.longitude - lon) / 2) ** 2
                        )
                    )
                )
                if distance <= radius:
                    found.append(profile)
                    distances[profile.account.username] = round(distance)
            profiles = found
        if isinstance(profiles, list):
            ordered = sorted(profiles, key=lambda profile: profile.account.username.casefold())
            page = ordered[offset : offset + 51]
        else:
            page = list(profiles.order_by("account__username")[offset : offset + 51])
        items = [profile_payload(profile) for profile in page[:50]]
        for item in items:
            if item["username"] in distances:
                item["distance_metres"] = distances[item["username"]]
        return Response({"items": items, "has_more": len(page) > 50})


class PublicStudentProfileView(APIView):
    authentication_classes = [Auth0Authentication]
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, username: str) -> Response:
        require_student(request)
        try:
            profile = StudentProfile.objects.select_related("account").get(
                account__username__iexact=username,
                account__account_type=AccountType.STUDENT,
                account__user__is_active=True,
                discoverable=True,
            )
        except StudentProfile.DoesNotExist as error:
            raise NotFound("Student profile not found.") from error
        return Response(profile_payload(profile))


class StudentDirectMessageView(APIView):
    authentication_classes = [Auth0Authentication]
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, username: str) -> Response:
        require_student(request)
        try:
            target = Account.objects.select_related("user").get(
                username__iexact=username,
                account_type=AccountType.STUDENT,
                user__is_active=True,
                student_profile__discoverable=True,
            )
        except Account.DoesNotExist as error:
            raise NotFound("Student profile not found.") from error
        from communities.dm_views import start

        return start(request, f"u:{target.user_id}", target.username)


class SignUpAlreadyComplete(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "This account has already finished signing up."
    default_code = "conflict"


class AuthConfigView(APIView):
    """The public Auth0 settings the browser needs to start a log-in."""

    authentication_classes: list[type] = []
    permission_classes: list[type] = []

    def get(self, request: Request) -> Response:
        if not configured():
            return Response({"enabled": False})
        return Response(
            {
                "enabled": True,
                "domain": settings.AUTH0_DOMAIN,
                "client_id": settings.AUTH0_CLIENT_ID,
                "audience": settings.AUTH0_AUDIENCE,
            }
        )


class AccountView(APIView):
    """The logged-in person's own account.

    ``GET`` creates it on the first request after an Auth0 sign-up, so there is
    no separate registration call to forget. ``POST`` finishes sign-up by
    choosing student or business, once.
    """

    authentication_classes = [Auth0Authentication]
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        return Response(AccountSerializer(self._account(request)).data)

    def post(self, request: Request) -> Response:
        account = self._account(request)
        if account.account_type:
            raise SignUpAlreadyComplete()

        serializer = CompleteSignUpSerializer(data=request.data, context={"account": account})
        serializer.is_valid(raise_exception=True)
        data: dict[str, Any] = serializer.validated_data

        account.account_type = data["account_type"]
        account.business_name = data["business_name"]
        account.username = data["username"]
        try:
            with transaction.atomic():
                account.save(
                    update_fields=["account_type", "business_name", "username", "updated_at"]
                )
                if account.account_type == AccountType.STUDENT:
                    StudentProfile.objects.get_or_create(account=account)
        except IntegrityError as error:
            # Someone else took the name between the check and the save.
            raise ValidationError(
                {"username": "That username is taken."}, code="username_taken"
            ) from error
        return Response(AccountSerializer(account).data, status=status.HTTP_201_CREATED)

    @staticmethod
    def _account(request: Request) -> Account:
        return request.user.account


class UsernameView(APIView):
    """Whether a username can still be chosen, for the sign-up form to say so.

    Public, like the sign-up form that asks: it answers before anyone has an
    account. It says only whether a name is free, which submitting the form
    would reveal anyway.
    """

    authentication_classes: list[type] = []
    permission_classes: list[type] = []

    def get(self, request: Request, username: str) -> Response:
        problem = username_problem(username.strip())
        code, message = problem if problem is not None else (None, None)
        return Response(
            {
                "username": username,
                "available": problem is None,
                "reason": code,
                "message": message,
            }
        )
