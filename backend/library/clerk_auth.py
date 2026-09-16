"""Clerk JWT verification against a fixed issuer and verified Google identities."""

import functools
import json
import re
import time
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

import jwt
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from .accounts import provision_identity


class AuthenticationError(Exception):
    pass


@functools.lru_cache(maxsize=4)
def jwks_client(issuer):
    origin = urlsplit(issuer)
    if (
        origin.scheme != "https"
        or not origin.hostname
        or origin.path not in ("", "/")
        or origin.query
        or origin.fragment
        or origin.username
        or origin.password
    ):
        raise AuthenticationError("Invalid issuer configuration")
    return jwt.PyJWKClient(
        issuer + "/.well-known/jwks.json", cache_keys=True, lifespan=300, timeout=10, headers={"User-Agent": "Halekhoob/0.2"}
    )


def verify_token(token):
    if not settings.CLERK_ISSUER or not settings.CLERK_AUTHORIZED_PARTIES:
        raise AuthenticationError("Authentication is not configured")
    if len(token) > 16000:
        raise AuthenticationError("Invalid token")
    try:
        key = jwks_client(settings.CLERK_ISSUER).get_signing_key_from_jwt(token).key
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            issuer=settings.CLERK_ISSUER,
            options={
                "require": ["exp", "iat", "nbf", "iss", "sub", "sid", "azp"],
                "verify_aud": False,
            },
            leeway=5,
        )
        if claims["azp"] not in settings.CLERK_AUTHORIZED_PARTIES or claims.get("sts") == "pending":
            raise AuthenticationError("Invalid session origin or status")
        if not re.fullmatch(r"user_[A-Za-z0-9]+", claims["sub"]) or not str(
            claims["sid"]
        ).startswith("sess_"):
            raise AuthenticationError("Invalid subject")
        return claims
    except (jwt.PyJWTError, ValueError, TypeError, KeyError) as exc:
        raise AuthenticationError("Invalid or expired session") from exc


@functools.lru_cache(maxsize=512)
def google_identity(subject, bucket, secret):
    # The cache bucket bounds stale account status to one minute; tokens are independently verified.
    if not secret:
        raise AuthenticationError("Authentication is not configured")
    request = Request(
        "https://api.clerk.com/v1/users/" + subject, headers={"Authorization": "Bearer " + secret, "User-Agent": "Halekhoob/0.2"}
    )
    try:
        with urlopen(request, timeout=10) as response:
            user = json.load(response)
        if user.get("banned") or user.get("locked") or user.get("id") != subject:
            raise AuthenticationError("Account unavailable")
        primary = next(
            (
                e
                for e in user.get("email_addresses", [])
                if e["id"] == user.get("primary_email_address_id")
                and e.get("verification", {}).get("status") == "verified"
            ),
            None,
        )
        if not primary or not any(
            a.get("provider") in {"google", "oauth_google"}
            and a.get("email_address", "").lower() == primary["email_address"].lower()
            for a in user.get("external_accounts", [])
        ):
            raise AuthenticationError("A verified Google account is required")
        return {"email": primary["email_address"], "first_name": user.get("first_name") or ""}
    except AuthenticationError:
        raise
    except Exception as exc:
        raise AuthenticationError("Identity service unavailable") from exc


def clerk_required(view):
    @csrf_exempt  # Only explicit Bearer credentials are accepted; Django session cookies are ignored.
    @functools.wraps(view)
    def wrapped(request, *args, **kwargs):
        authorization = request.headers.get("Authorization", "")
        if not authorization.startswith("Bearer "):
            return JsonResponse(
                {"error": {"code": "authentication", "message": "برای ادامه با گوگل وارد شو."}},
                status=401,
            )
        try:
            claims = verify_token(authorization[7:])
            identity = google_identity(
                claims["sub"], int(time.time() // 60), settings.CLERK_SECRET_KEY
            )
            request.user = provision_identity(claims["sub"], identity)
            if not request.user.is_active:
                raise AuthenticationError("Account disabled")
        except (AuthenticationError, ValueError):
            return JsonResponse(
                {
                    "error": {
                        "code": "authentication",
                        "message": "ورود معتبر نیست؛ دوباره با گوگل وارد شو.",
                    }
                },
                status=401,
            )
        return view(request, *args, **kwargs)

    return wrapped
