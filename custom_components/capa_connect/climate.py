"""Climate entity for a Capa Connect heater zone."""
from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    MAX_TEMP,
    MIN_TEMP,
    MODE_COMFORT,
    MODE_ECO,
    MODE_OFF,
    MODE_TO_PRESET,
    PRESET_AWAY,
    PRESET_COMFORT,
    PRESET_ECO,
    PRESET_TO_MODE,
    TEMP_NONE,
)
from .coordinator import CapaCoordinator

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: CapaCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        CapaClimate(coordinator, zone_id) for zone_id in coordinator.data["zones"]
    )


class CapaClimate(CoordinatorEntity[CapaCoordinator], ClimateEntity):
    """One heater zone exposed as a HA climate entity."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]
    _attr_preset_modes = [PRESET_COMFORT, PRESET_ECO, PRESET_AWAY]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.PRESET_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    _attr_min_temp = MIN_TEMP
    _attr_max_temp = MAX_TEMP
    # The heater only accepts whole degrees (it rounds 17.5 -> 18), so step by 1
    # in HA. HA propagates this to HomeKit's TargetTemperature minStep too.
    _attr_target_temperature_step = 1
    _enable_turn_on_off_backwards_compatibility = False

    def __init__(self, coordinator: CapaCoordinator, zone_id: str) -> None:
        super().__init__(coordinator)
        self._zone_id = zone_id
        self._attr_unique_id = zone_id

    @property
    def _zone(self) -> dict[str, Any]:
        return self.coordinator.data["zones"].get(self._zone_id, {})

    @property
    def device_info(self) -> DeviceInfo:
        z = self._zone
        return DeviceInfo(
            identifiers={(DOMAIN, self._zone_id)},
            name=z.get("name"),
            manufacturer="Noirot / Muller (GDHV)",
            model=z.get("model"),
            sw_version=z.get("firmware"),
        )

    @property
    def available(self) -> bool:
        return super().available and bool(self._zone.get("connected"))

    @property
    def current_temperature(self) -> float | None:
        return self._zone.get("room_temp")

    @property
    def target_temperature(self) -> float | None:
        z = self._zone
        mode = z.get("mode")
        if mode == MODE_OFF:
            return None
        # CurrentTemperature is the live setpoint (a per-zone override written by
        # UpdateZoneSetpointTemperature); 255 means "none — use the mode's stored
        # temp". Prefer it, then fall back to the Comfort/Eco stored setpoint.
        setpoint = z.get("setpoint")
        if isinstance(setpoint, (int, float)) and setpoint != TEMP_NONE:
            return setpoint
        if mode == MODE_COMFORT:
            return z.get("comfort")
        if mode == MODE_ECO:
            return z.get("eco")
        return None

    @property
    def hvac_mode(self) -> HVACMode:
        return HVACMode.OFF if self._zone.get("mode") == MODE_OFF else HVACMode.HEAT

    @property
    def hvac_action(self) -> HVACAction:
        z = self._zone
        if z.get("mode") == MODE_OFF:
            return HVACAction.OFF
        current = z.get("room_temp")
        target = self.target_temperature
        if current is not None and target is not None and current < target:
            return HVACAction.HEATING
        return HVACAction.IDLE

    @property
    def preset_mode(self) -> str | None:
        return MODE_TO_PRESET.get(self._zone.get("mode"))

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is None:
            return
        z = self._zone
        await self.coordinator.client.set_setpoint(
            z["site_id"], self._zone_id, round(temp)
        )
        await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        # Turning "heat" on from off resumes the Comfort preset.
        mode = MODE_OFF if hvac_mode == HVACMode.OFF else MODE_COMFORT
        await self._set_mode(mode)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        mode = PRESET_TO_MODE.get(preset_mode)
        if mode is not None:
            await self._set_mode(mode)

    async def _set_mode(self, mode: int) -> None:
        z = self._zone
        # TEMP_NONE keeps the zone's stored Comfort/Eco setpoint.
        await self.coordinator.client.set_mode(
            z["site_id"], self._zone_id, mode, TEMP_NONE
        )
        await self.coordinator.async_request_refresh()
