"""Async client for the Capa Connect / GDHV IoT cloud (Azure AD B2C auth)."""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
import secrets
import time
from typing import Any

import aiohttp

from .const import (
    API_BASE,
    AUTHORIZE_URL,
    CLIENT_ID,
    CONFIRMED_URL,
    DEVICE_HEADERS,
    REDIRECT_URI,
    SCOPE,
    SELFASSERTED_URL,
    TEMP_NONE,
    TOKEN_URL,
)

_LOGGER = logging.getLogger(__name__)


class CapaAuthError(Exception):
    """Authentication failed (bad credentials or broken auth flow)."""


class CapaApiError(Exception):
    """A device-API call failed."""


async def _read_json(resp: aiohttp.ClientResponse, what: str) -> dict[str, Any]:
    """Parse a JSON body, turning a non-JSON reply into a clean CapaApiError
    instead of a raw JSONDecodeError (which HA would surface as "Unknown error").
    """
    text = await resp.text()
    try:
        return json.loads(text) if text.strip() else {}
    except json.JSONDecodeError as err:
        raise CapaApiError(
            f"{what}: unexpected non-JSON reply (HTTP {resp.status})"
        ) from err


def _pkce() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) for PKCE S256."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    return verifier, challenge


class CapaAuth:
    """Owns the OAuth tokens and knows how to (re)acquire them.

    Two entry points:
      * ``login(email, password)`` — full Azure B2C auth-code flow via the hosted
        SelfAsserted (username/password) endpoint. Use once, from the config flow.
      * ``async_get_token()`` — returns a valid access token, transparently
        refreshing with the stored refresh token when it is near expiry.
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        refresh_token: str | None = None,
    ) -> None:
        self._session = session
        self._refresh_token = refresh_token
        self._access_token: str | None = None
        self._expires_at = 0.0

    @property
    def refresh_token(self) -> str | None:
        return self._refresh_token

    async def async_get_token(self) -> str:
        if self._access_token and time.time() < self._expires_at - 60:
            return self._access_token
        if not self._refresh_token:
            raise CapaAuthError("No refresh token; login() required first")
        await self._refresh()
        return self._access_token  # type: ignore[return-value]

    async def _refresh(self) -> None:
        data = {
            "grant_type": "refresh_token",
            "client_id": CLIENT_ID,
            "scope": SCOPE,
            "refresh_token": self._refresh_token,
        }
        async with self._session.post(TOKEN_URL, data=data) as resp:
            body = await _read_json(resp, "token refresh")
        if resp.status != 200 or "access_token" not in body:
            raise CapaAuthError(f"Token refresh failed ({resp.status}): {body}")
        self._store(body)

    def _store(self, tok: dict[str, Any]) -> None:
        self._access_token = tok["access_token"]
        self._expires_at = time.time() + int(tok.get("expires_in", 3600))
        if tok.get("refresh_token"):
            self._refresh_token = tok["refresh_token"]

    async def login(self, email: str, password: str) -> str:
        """Run the full B2C auth-code flow; return the refresh token."""
        verifier, challenge = _pkce()
        state = secrets.token_urlsafe(16)
        # 1) Load the hosted login page (sets the CSRF cookie; embeds SETTINGS).
        authorize_params = {
            "client_id": CLIENT_ID,
            "response_type": "code",
            "redirect_uri": REDIRECT_URI,
            "scope": SCOPE,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "response_mode": "query",
        }
        async with self._session.get(AUTHORIZE_URL, params=authorize_params) as resp:
            html = await resp.text()
        m = re.search(r'"csrf":"([^"]+)"', html)
        t = re.search(r'"transId":"([^"]+)"', html)
        if not m or not t:
            raise CapaAuthError("Could not parse B2C login page (csrf/transId)")
        csrf, trans_id = m.group(1), t.group(1)

        # 2) Submit credentials to SelfAsserted. B2C's AJAX endpoint requires
        # both the CSRF token and the XMLHttpRequest marker, else it 403s / returns
        # HTML instead of the {"status": ...} JSON.
        sa_params = {"tx": trans_id, "p": _policy()}
        sa_headers = {
            "X-CSRF-TOKEN": csrf,
            "X-Requested-With": "XMLHttpRequest",
        }
        sa_data = {
            "request_type": "RESPONSE",
            "email": email,
            "password": password,
        }
        async with self._session.post(
            SELFASSERTED_URL, params=sa_params, data=sa_data, headers=sa_headers
        ) as resp:
            sa_body = await _read_json(resp, "sign-in")
        if str(sa_body.get("status")) != "200":
            raise CapaAuthError(f"Login rejected: {sa_body}")

        # 3) Fetch the auth code (do NOT follow the redirect to the app scheme).
        conf_params = {
            "rememberMe": "false",
            "csrf_token": csrf,
            "tx": trans_id,
            "p": _policy(),
        }
        async with self._session.get(
            CONFIRMED_URL, params=conf_params, allow_redirects=False
        ) as resp:
            location = resp.headers.get("Location", "")
        code_m = re.search(r"[?&]code=([^&]+)", location)
        if not code_m:
            raise CapaAuthError(f"No auth code in redirect: {location[:120]}")
        code = code_m.group(1)

        # 4) Exchange the code for tokens.
        data = {
            "client_id": CLIENT_ID,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "scope": SCOPE,
            "code_verifier": verifier,
        }
        async with self._session.post(TOKEN_URL, data=data) as resp:
            body = await _read_json(resp, "token exchange")
        if resp.status != 200 or "access_token" not in body:
            raise CapaAuthError(f"Code exchange failed ({resp.status}): {body}")
        self._store(body)
        if not self._refresh_token:
            raise CapaAuthError("Login succeeded but no refresh token returned")
        return self._refresh_token


def _policy() -> str:
    from .const import B2C_POLICY

    return B2C_POLICY


class CapaClient:
    """Thin wrapper over the GDHV device API. All methods auto-authenticate."""

    def __init__(self, session: aiohttp.ClientSession, auth: CapaAuth) -> None:
        self._session = session
        self._auth = auth

    async def _headers(self) -> dict[str, str]:
        token = await self._auth.async_get_token()
        return {**DEVICE_HEADERS, "Authorization": f"Bearer {token}"}

    async def _get(self, path: str) -> Any:
        async with self._session.get(
            f"{API_BASE}{path}", headers=await self._headers()
        ) as resp:
            if resp.status != 200:
                raise CapaApiError(f"GET {path} -> {resp.status}: {await resp.text()}")
            return await resp.json(content_type=None)

    async def _post(self, path: str, body: dict[str, Any]) -> Any:
        headers = {**await self._headers(), "Content-Type": "application/json"}
        async with self._session.post(
            f"{API_BASE}{path}", data=json.dumps(body), headers=headers
        ) as resp:
            if resp.status != 200:
                raise CapaApiError(f"POST {path} -> {resp.status}: {await resp.text()}")
            text = await resp.text()
            return json.loads(text) if text.strip() else None

    # --- reads ---
    async def get_sites(self) -> list[dict[str, Any]]:
        return await self._get("/api/DirectSite/GetUserSites")

    async def get_zones(self, site_id: str) -> list[dict[str, Any]]:
        return await self._get(
            f"/api/DirectZones/GetZonesAndAppliancesForSiteId?SiteId={site_id}"
        )

    async def get_room_temps(self, site_id: str) -> dict[str, int]:
        return await self._get(
            f"/api/DirectSite/GetApplianceRoomTemperatures?siteId={site_id}"
        )

    async def get_zone(self, zone_id: str, site_id: str) -> dict[str, Any]:
        return await self._post(
            "/api/DirectZones/GetZone", {"ZoneId": zone_id, "SiteId": site_id}
        )

    # --- writes ---
    async def set_mode(
        self, site_id: str, zone_id: str, mode: int, temperature: int = TEMP_NONE
    ) -> Any:
        return await self._post(
            "/api/DirectZones/UpdateZoneMode",
            {
                "SiteId": site_id,
                "ZoneId": zone_id,
                "Mode": mode,
                "OverrideDateTo": None,
                "Temperature": temperature,
                "IsValidationEnabled": True,
                "Errors": {"Errors": {}, "IsValidationEnabled": True},
            },
        )

    async def set_setpoint(
        self, site_id: str, zone_id: str, temperature: int
    ) -> Any:
        return await self._post(
            "/api/DirectZones/UpdateZoneSetpointTemperature",
            {
                "SiteId": site_id,
                "ZoneId": zone_id,
                "NewTemperature": temperature,
                "IsValidationEnabled": True,
                "Errors": {"Errors": {}, "IsValidationEnabled": True},
            },
        )
