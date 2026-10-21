"""Public study-spot routes."""

from __future__ import annotations

from typing import Any

from django.db.models import Count, Q, QuerySet
from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import StudySpot
from .search import expanded_words, search
from .serializers import (
    SpotFacetsQuerySerializer,
    SpotQuerySerializer,
    SpotSearchQuerySerializer,
    StudySpotSerializer,
)

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
    """``GET /spots`` -- a filtered, paginated page of study spots."""

    def get(self, request: Request) -> Response:
        query = SpotQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        parameters = query.validated_data

        limit: int = parameters["limit"]
        offset: int = parameters["offset"]

        matching = apply_filters(StudySpot.objects.all(), parameters)

        # Counted before slicing, because the envelope reports the size of the
        # whole result set rather than of this page.
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
