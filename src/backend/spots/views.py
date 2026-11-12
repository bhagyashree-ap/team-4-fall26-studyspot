"""Study-spot routes: the public read routes and a business owner's listings."""

from __future__ import annotations

import uuid
from typing import Any

from django.db.models import Count, Expression, F, IntegerField, Q, QuerySet, Value
from django.db.models.functions import ASin, Cast, Cos, Least, Power, Radians, Round, Sin, Sqrt
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.authentication import Auth0Authentication
from accounts.models import Account, AccountType

from .models import StudySpot
from .search import expanded_words, search
from .serializers import (
    Coordinates,
    ListingSerializer,
    NearbySpotSerializer,
    SpotFacetsQuerySerializer,
    SpotQuerySerializer,
    SpotSearchQuerySerializer,
    StudySpotSerializer,
)

#: Mean Earth radius, the same figure ``data/ingest.py`` measures
#: ``subway_metres`` and ``nearby_spots`` with, so every distance the API
#: reports is on one scale.
EARTH_RADIUS_METRES = 6_371_000.0


def distance_from(origin: Coordinates) -> Expression:
    """Straight-line metres from ``origin`` to each row, by the haversine formula.

    Computed in SQL rather than in Python so that ordering and paging stay in
    the database: sorting in Python would mean loading every matching row to
    serve twenty. Plain Postgres has no geography type here, and a few thousand
    rows do not justify adding PostGIS.

    ``Least`` caps the haversine term at 1. Rounding can push it a hair past 1
    for a point near the antipode, and ``asin`` raises on anything above 1
    rather than returning pi/2.
    """
    latitude = Radians(F("latitude"))
    origin_latitude = Radians(Value(origin.latitude))
    half_latitude = (latitude - origin_latitude) / Value(2.0)
    half_longitude = (Radians(F("longitude")) - Radians(Value(origin.longitude))) / Value(2.0)

    haversine = Power(Sin(half_latitude), 2) + Cos(origin_latitude) * Cos(latitude) * Power(
        Sin(half_longitude), 2
    )
    return Value(2.0 * EARTH_RADIUS_METRES) * ASin(Sqrt(Least(haversine, Value(1.0))))


#: Maps a validated query parameter to the lookup it filters with. Substring for
#: the name, exact for the rest, all case-insensitive. A `neighborhood` filter
#: therefore excludes rows where the column is NULL, which is the documented
#: behaviour.
#:
#: `university` is not here: it is the one filter a reader types instead of
#: picking, so :func:`campus` decides its lookup per value.
LOOKUPS = {
    "name": "name__icontains",
    "category": "category__iexact",
    "neighborhood": "neighborhood__iexact",
    "borough": "borough__iexact",
    "free_public_wifi": "free_public_wifi",
    "no_purchase_needed": "no_purchase_needed",
    # Three-state, and the plain lookup is what makes it behave correctly:
    # `indoor_seating=True` and `indoor_seating=False` each compile to an
    # equality test, which SQL does not satisfy for NULL. So each value selects
    # the rows recorded as that answer and the unrecorded majority falls out of
    # both, which is the only honest reading of a filter on this field.
    "indoor_seating": "indoor_seating",
}


def campus(value: str) -> Q:
    """How to match ``value`` against the campus column.

    The field is a text box with a 126-entry datalist behind it, so a reader
    can pick a whole name or type part of one, and the two need different
    lookups. Exact matching alone answered a half-typed name with zero
    results, which reads as "there are none" rather than "keep typing":

        New York University  ->  11
        New York             ->   0
        NYU                  ->   0

    So: exact when the value names a campus, substring when it does not. That
    way picking "New York University" from the list still means that campus
    alone, and does not quietly also return the spots near
    "LIU-New York University Campus", which a plain substring match would.

    The initialism table from search gets a turn too, because "NYU" is what
    people type and it is a substring of nothing.

    Checked against every row rather than against the rows the other filters
    left, so that what "New York University" means does not depend on whether
    a borough was also chosen.
    """
    candidates = [value]
    expanded = " ".join(expanded_words(value))
    if expanded.casefold() != value.casefold():
        candidates.append(expanded)

    for candidate in candidates:
        if StudySpot.objects.filter(university__iexact=candidate).exists():
            return Q(university__iexact=candidate)

    partial = Q()
    for candidate in candidates:
        partial |= Q(university__icontains=candidate)
    return partial


def apply_filters(queryset: QuerySet[StudySpot], parameters: dict[str, Any]) -> QuerySet[StudySpot]:
    """Narrow ``queryset`` by every filter the caller supplied.

    Django escapes the LIKE wildcards in an ``icontains`` value, so a search for
    ``100%`` is a search for a literal percent sign.
    """
    lookups = {
        lookup: parameters[parameter]
        for parameter, lookup in LOOKUPS.items()
        if parameters.get(parameter) is not None
    }
    narrowed = queryset.filter(**lookups) if lookups else queryset

    university = parameters.get("university")
    return narrowed.filter(campus(university)) if university is not None else narrowed


class SpotListView(APIView):
    """``GET /spots`` -- a filtered, paginated page of study spots.

    With ``near_lat`` and ``near_lng``, or with ``near_neighborhood``, the page
    is ordered nearest first and each item carries ``distance_metres``; without
    them it is alphabetical and the items are the plain summary. The query
    serializer turns either form into one point, so both share
    :func:`distance_from`.
    """

    def get(self, request: Request) -> Response:
        query = SpotQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        parameters = query.validated_data

        limit: int = parameters["limit"]
        offset: int = parameters["offset"]
        near: Coordinates | None = parameters["near"]

        matching = apply_filters(StudySpot.objects.all(), parameters)

        # Counted before ordering by distance and before slicing: the envelope
        # reports the size of the whole result set, and the count needs neither.
        total = matching.count()

        if near is None:
            items = StudySpotSerializer(matching[offset : offset + limit], many=True).data
        else:
            # Ordered by the exact distance and served rounded, so two spots a
            # few centimetres apart still come out in a fixed order. The id
            # breaks exact ties, which keeps paging total as it is without a
            # point.
            nearest = (
                matching.alias(distance=distance_from(near))
                .annotate(distance_metres=Cast(Round(F("distance")), IntegerField()))
                .order_by("distance", "id")
            )
            items = NearbySpotSerializer(nearest[offset : offset + limit], many=True).data

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


class SpotDetailView(APIView):
    """``GET /spots/{id}`` -- one study spot."""

    def get(self, request: Request, spot_id: str) -> Response:
        try:
            spot = StudySpot.objects.get(pk=spot_id)
        except StudySpot.DoesNotExist:
            raise NotFound(f"No study spot has the identifier {spot_id!r}.") from None
        return Response(StudySpotSerializer(spot).data)


class SpotSearchView(APIView):
    """``GET /spots/search`` -- study spots ranked by how well they match ``q``.

    The envelope is the one ``GET /spots`` uses, so a caller can swap between
    filtering and searching without handling two response shapes. The relevance
    score is not part of it: it exists to order the results and would be a
    number the contract has to keep stable for no one's benefit.
    """

    def get(self, request: Request) -> Response:
        query = SpotSearchQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        parameters = query.validated_data

        limit: int = parameters["limit"]
        offset: int = parameters["offset"]

        # Filter first, then rank. The other order would drop the best
        # matches out of a page rather than out of the result set.
        matching = search(parameters["q"], apply_filters(StudySpot.objects.all(), parameters))

        total = matching.count()
        items = StudySpotSerializer(matching[offset : offset + limit], many=True).data

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


#: The fields ``GET /spots/facets`` reports values for, mapped to the response
#: key that carries each one. Wi-Fi is absent deliberately: a boolean has no
#: list of values to offer, so it is reported as a single count instead.
FACET_FIELDS = {
    "borough": "boroughs",
    "category": "categories",
    "university": "universities",
}


class SpotFacetsView(APIView):
    """``GET /spots/facets`` -- the values the filters can take, with counts.

    A filter control cannot be built from the contract alone: `borough` is five
    fixed names, but `category` belongs to the importer and the campuses are
    whatever the data happens to contain. Hard-coding either in the browser
    would mean a filter that silently stops matching when the snapshot changes.

    Counts come along because a filter offering a value that matches nothing is
    worse than not offering it. That is why this endpoint takes the request
    already in force: counted over the whole snapshot, every number stops
    describing what the caller would actually get the moment one filter is on,
    and the control goes on offering values that now match nothing.

    Each facet is counted with every *other* filter applied but not its own.
    Applying a facet's own filter to itself would leave one value standing --
    the one already chosen -- and no way to switch to another.
    """

    def get(self, request: Request) -> Response:
        query = SpotFacetsQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        parameters = query.validated_data

        base = StudySpot.objects.all()
        if parameters.get("q"):
            # Matched through a subquery rather than by counting the ranked
            # queryset directly. Grouping over it would pull search()'s
            # relevance expression and ordering into the GROUP BY, which counts
            # every row on its own; the subquery keeps the ranking where it
            # belongs and leaves a plain set of rows to aggregate.
            ranked = search(parameters["q"], base).order_by().values("pk")
            base = StudySpot.objects.filter(pk__in=ranked)

        def narrow(excluding: str) -> QuerySet[StudySpot]:
            """``base`` with every filter applied except ``excluding``."""
            others = {name: value for name, value in parameters.items() if name != excluding}
            return apply_filters(base, others)

        def counts(field: str) -> list[dict[str, Any]]:
            rows = (
                narrow(field)
                .exclude(**{f"{field}__isnull": True})
                # order_by() before grouping, because Django adds ordering
                # columns to the GROUP BY and the default Meta ordering would
                # otherwise split every value into one group per row.
                .order_by()
                .values(field)
                .annotate(count=Count("id"))
                .order_by("-count", field)
            )
            return [{"value": row[field], "count": row["count"]} for row in rows]

        body: dict[str, Any] = {key: counts(field) for field, key in FACET_FIELDS.items()}

        # One number rather than a list: the control is a checkbox, so the only
        # count worth having is how many spots are left when it is ticked.
        body["free_public_wifi"] = narrow("free_public_wifi").filter(free_public_wifi=True).count()
        body["no_purchase_needed"] = (
            narrow("no_purchase_needed").filter(no_purchase_needed=True).count()
        )
        # Counted as `=True` rather than as "not false", so the number is how
        # many spots somebody has actually recorded indoor seating for. It is
        # small -- around 112 citywide -- and that is the point: padding it
        # with the unrecorded majority would make the count a guess.
        body["indoor_seating"] = narrow("indoor_seating").filter(indoor_seating=True).count()

        return Response(body)


#: Prefix of the identifiers given to owner-created listings, in the same
#: ``source:key`` form as the importer's ``facdb:`` and ``dohmh:``, so that no
#: listing can take the identifier of an imported spot.
LISTING_ID_PREFIX = "listing"


def business_account(request: Request) -> Account:
    """The caller's account, provided it is a business account."""
    account: Account = request.user.account
    if account.account_type != AccountType.BUSINESS:
        raise PermissionDenied("Only a business account can manage listings.")
    return account


def owned_listing(request: Request, spot_id: str) -> StudySpot:
    """The listing ``spot_id``, provided the caller's business account owns it.

    Someone else's listing and an imported spot are both answered as not found:
    from here, the caller has no listing by that identifier.
    """
    account = business_account(request)
    try:
        return StudySpot.objects.get(pk=spot_id, owner=account)
    except StudySpot.DoesNotExist:
        raise NotFound(f"You have no listing with the identifier {spot_id!r}.") from None


class ListingListView(APIView):
    """``GET /listings`` and ``POST /listings`` -- the caller's own listings."""

    authentication_classes = [Auth0Authentication]
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        listings = StudySpot.objects.filter(owner=business_account(request))
        return Response({"items": StudySpotSerializer(listings, many=True).data})

    def post(self, request: Request) -> Response:
        account = business_account(request)
        serializer = ListingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        spot = serializer.save(id=f"{LISTING_ID_PREFIX}:{uuid.uuid4().hex}", owner=account)
        return Response(StudySpotSerializer(spot).data, status=status.HTTP_201_CREATED)


class ListingDetailView(APIView):
    """``PATCH`` and ``DELETE /listings/{id}`` -- one of the caller's own listings."""

    authentication_classes = [Auth0Authentication]
    permission_classes = [IsAuthenticated]

    def patch(self, request: Request, spot_id: str) -> Response:
        spot = owned_listing(request, spot_id)
        serializer = ListingSerializer(spot, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        return Response(StudySpotSerializer(serializer.save()).data)

    def delete(self, request: Request, spot_id: str) -> Response:
        owned_listing(request, spot_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
