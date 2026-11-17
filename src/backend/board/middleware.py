from django.utils.cache import patch_vary_headers


class BoardNoStoreMiddleware:
    """Include errors and middleware-generated responses in the privacy boundary."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path == "/board" or request.path.startswith("/board/"):
            response["Cache-Control"] = "private, no-store"
            patch_vary_headers(response, ("Cookie", "Authorization"))
        return response
