from django.conf import settings


class PrivateCacheMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if not request.path.startswith("/static/"):
            response["Cache-Control"] = "private, no-store"
        response["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; media-src 'self'; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'self'"
        )
        if settings.MEDIA_BACKEND == "r2":
            origin = settings.R2_ENDPOINT_URL
            policy = response["Content-Security-Policy"]
            for directive in ["img-src", "media-src", "connect-src"]:
                policy = policy.replace(f"{directive} 'self'", f"{directive} 'self' {origin}")
            response["Content-Security-Policy"] = policy
        response["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return response
