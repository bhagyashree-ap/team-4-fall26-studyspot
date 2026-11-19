from __future__ import annotations

from typing import Any

from django.db import transaction
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework import status
from rest_framework.exceptions import APIException, NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from spots.models import StudySpot
from spots.serializers import (
    StrictQuerySerializer,
    StudySpotSerializer,
    limit_field,
    offset_field,
)

from .authentication import Auth0Authentication
from .models import AccountType, Favourite


class CompletedStudentRequired(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "A completed student account is required to use favourites."
    default_code = "conflict"


class FavouriteQuerySerializer(StrictQuerySerializer):
    limit = limit_field()
    offset = offset_field()


@method_decorator(never_cache, name="dispatch")
class FavouriteView(APIView):
    authentication_classes = [Auth0Authentication]
    permission_classes = [IsAuthenticated]

    def initial(self, request: Request, *args: Any, **kwargs: Any) -> None:
        super().initial(request, *args, **kwargs)
        if request.user.account.account_type != AccountType.STUDENT:
            raise CompletedStudentRequired()


class FavouriteListView(FavouriteView):
    def get(self, request: Request) -> Response:
        query = FavouriteQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        limit: int = query.validated_data["limit"]
        offset: int = query.validated_data["offset"]

        matching = Favourite.objects.filter(account=request.user.account).select_related("spot")
        total = matching.count()
        spots = [favourite.spot for favourite in matching[offset : offset + limit]]
        items = StudySpotSerializer(spots, many=True).data
        return Response(
            {
                "items": items,
                "pagination": {
                    "limit": limit,
                    "offset": offset,
                    "count": len(items),
                    "total": total,
                    "has_more": offset + len(items) < total,
                },
            }
        )


class FavouriteDetailView(FavouriteView):
    def put(self, request: Request, spot_id: str) -> Response:
        with transaction.atomic():
            try:
                # Serialize with refreshes before creating the foreign-key relationship.
                spot = StudySpot.objects.select_for_update().get(pk=spot_id)
            except StudySpot.DoesNotExist:
                raise NotFound(f"No study spot has the identifier {spot_id!r}.") from None
            Favourite.objects.get_or_create(account=request.user.account, spot=spot)
        return Response(status=status.HTTP_204_NO_CONTENT)

    def delete(self, request: Request, spot_id: str) -> Response:
        Favourite.objects.filter(account=request.user.account, spot_id=spot_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
