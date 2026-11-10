"""Study-spot routes.

No trailing slashes, and ``APPEND_SLASH`` is off in settings, because the
published contract is ``/spots`` and ``/spots/{id}``.

A spot identifier carries its source dataset as a prefix, as in
``facdb:eec118768e15a5e03d3354abda7b00da``. ``str`` matches that colon; it
matches anything except a slash.
"""

from django.urls import path

from .views import (
    ListingDetailView,
    ListingListView,
    SpotDetailView,
    SpotFacetsView,
    SpotListView,
    SpotSearchView,
)

urlpatterns = [
    # A business owner's own listings. Separate from /spots, which stays public
    # and read-only; a listing is read there like any other spot.
    path("listings", ListingListView.as_view(), name="listing-list"),
    path("listings/<str:spot_id>", ListingDetailView.as_view(), name="listing-detail"),
    path("spots", SpotListView.as_view(), name="spot-list"),
    # Before the detail route: Django matches in order, and <str:spot_id> would
    # otherwise capture "search" and look for a spot with that identifier.
    path("spots/search", SpotSearchView.as_view(), name="spot-search"),
    path("spots/facets", SpotFacetsView.as_view(), name="spot-facets"),
    path("spots/<str:spot_id>", SpotDetailView.as_view(), name="spot-detail"),
]
