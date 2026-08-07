"""Config + reauth flow for Capa Connect (email/password -> refresh token)."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD

from .api import CapaApiError, CapaAuth, CapaAuthError, CapaClient
from .const import DOMAIN


class CapaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Sign in once; store only the rotating refresh token, never the password."""

    VERSION = 1

    def __init__(self) -> None:
        self._reauth_entry: ConfigEntry | None = None

    async def _login(
        self, email: str, password: str
    ) -> tuple[str | None, list[dict], str]:
        """Return (refresh_token, sites-or-empty, error_key).

        Uses a dedicated session: the multi-step B2C flow depends on the
        ``x-ms-cpim-*`` cookies from the authorize call being carried forward,
        and this keeps them out of HA's shared cookie jar.

        quote_cookie=False is required: those cookie values contain ``+ / . =``,
        which aiohttp would otherwise wrap in double quotes on the way back out.
        B2C sends them raw and rejects the quoted form as "Bad Request", so the
        SelfAsserted POST fails before any credential check.
        """
        jar = aiohttp.CookieJar(quote_cookie=False)
        async with aiohttp.ClientSession(cookie_jar=jar) as session:
            auth = CapaAuth(session)
            try:
                refresh_token = await auth.login(email, password)
                sites = await CapaClient(session, auth).get_sites()
            except CapaAuthError:
                return None, [], "invalid_auth"
            except (CapaApiError, aiohttp.ClientError):
                return None, [], "cannot_connect"
        return refresh_token, sites, ""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            email = user_input[CONF_EMAIL]
            refresh_token, sites, error = await self._login(
                email, user_input[CONF_PASSWORD]
            )
            if error:
                errors["base"] = error
            else:
                await self.async_set_unique_id(email.lower())
                self._abort_if_unique_id_configured()
                title = sites[0]["Name"] if sites else "Capa Connect"
                return self.async_create_entry(
                    title=title,
                    data={"refresh_token": refresh_token, CONF_EMAIL: email},
                )
        schema = vol.Schema(
            {vol.Required(CONF_EMAIL): str, vol.Required(CONF_PASSWORD): str}
        )
        return self.async_show_form(
            step_id="user", data_schema=schema, errors=errors
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        assert self._reauth_entry is not None
        entry = self._reauth_entry
        if user_input is not None:
            refresh_token, _sites, error = await self._login(
                entry.data[CONF_EMAIL], user_input[CONF_PASSWORD]
            )
            if error:
                errors["base"] = error
            else:
                self.hass.config_entries.async_update_entry(
                    entry, data={**entry.data, "refresh_token": refresh_token}
                )
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="reauth_successful")
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            errors=errors,
            description_placeholders={"email": entry.data.get(CONF_EMAIL, "")},
        )
