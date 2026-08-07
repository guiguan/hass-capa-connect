"""DataUpdateCoordinator for Capa Connect: polls the cloud for zone state."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import CapaApiError, CapaAuth, CapaAuthError, CapaClient
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class CapaCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetches every zone's state across the account each poll.

    ``data`` is ``{"zones": {zone_id: {...}}}``. Because Azure B2C rotates the
    refresh token on every use, the freshest token is written back into the
    config entry after each successful poll.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: CapaClient,
        auth: CapaAuth,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.entry = entry
        self.client = client
        self.auth = auth

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            zones: dict[str, Any] = {}
            for site in await self.client.get_sites():
                site_id = site["Id"]
                temps = await self.client.get_room_temps(site_id)
                for z in await self.client.get_zones(site_id):
                    detail = await self.client.get_zone(z["Id"], site_id)
                    setting = detail.get("DirectZoneSetting") or {}
                    appliances = detail.get("DirectAppliances") or []
                    app = appliances[0] if appliances else {}
                    appliance_id = app.get("Id")
                    zones[z["Id"]] = {
                        "site_id": site_id,
                        "name": z.get("ZoneName") or app.get("FriendlyName"),
                        "mode": setting.get("CurrentMode"),
                        "setpoint": setting.get("CurrentTemperature"),
                        "comfort": setting.get("ComfortTemp"),
                        "eco": setting.get("EcoTemp"),
                        "room_temp": temps.get(appliance_id),
                        "connected": app.get("IsConnected", False),
                        "appliance_id": appliance_id,
                        "model": app.get("ProductModelName"),
                        "firmware": app.get("FirmwareVersion"),
                    }
        except CapaAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except CapaApiError as err:
            raise UpdateFailed(str(err)) from err

        self._persist_rotated_token()
        return {"zones": zones}

    def _persist_rotated_token(self) -> None:
        token = self.auth.refresh_token
        if token and token != self.entry.data.get("refresh_token"):
            self.hass.config_entries.async_update_entry(
                self.entry, data={**self.entry.data, "refresh_token": token}
            )
