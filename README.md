# Capa Connect for Home Assistant

A custom Home Assistant integration for WiFi panel heaters controlled by the
**Capa Connect** app (also sold as **Glen Dimplex Connect**) — the Glen Dimplex
Heating & Ventilation (GDHV) IoT cloud. Built for and tested against a **Noirot
"Spot Plus" (model DM73588TPRO FDFS, product type "Muller PH Wifi")**.

It talks to the same cloud API the app uses (`mobileapi.gdhv-iot.com`, behind
Azure AD B2C). There is no local API on these heaters, so this is a
`cloud_polling` integration.

## Features

Each heater zone becomes a `climate` entity:

- **HVAC modes:** `off`, `heat`
- **Presets:** `comfort` (zone Comfort setpoint), `eco` (zone Eco setpoint),
  `away` (frost protection, ~7 °C)
- **Current temperature** — the heater's room sensor
- **Target temperature** — whole-degree steps (the heater only accepts integers;
  half-degrees are rounded up)
- **Resume on turn-on** — turning the heater off and back on restores the
  *previous* mode and setpoint instead of defaulting to Comfort. The last heating
  state is remembered across Home Assistant restarts.
- **Instant feedback** — a change made in HA (or in the Home app via the HomeKit
  bridge) is reflected immediately; a background poll then reconciles it.
- **Diagnostic attributes** — `gdhv_mode` (the raw device mode) and `schedule`
  (the active schedule name).

The integration controls the heater using the cloud's four **permanent** modes:
Off (0), Away (2), Comfort (5), Eco (8).

## How it works

- **Polling:** the cloud has no push API, so state is polled every 60 s. This
  runs continuously in the background, so changes made elsewhere (the Capa app,
  the heater's own controls) are picked up within a minute.
- **Authentication:** you sign in once with your email and password; only the
  rotating OAuth refresh token is stored — never the password. The token
  auto-renews on each poll, so you should not need to sign in again. If it ever
  expires, HA prompts you to re-enter your password (reauth).

## Installation

### HACS (custom repository)

1. HACS → Integrations → ⋮ → Custom repositories.
2. Add `https://github.com/guiguan/hass-capa-connect` as an **Integration**.
3. Install "Capa Connect (Noirot / GDHV)" and restart Home Assistant.

### Manual

Copy `custom_components/capa_connect/` into your HA `config/custom_components/`
directory and restart.

## Configuration

Settings → Devices & Services → **Add Integration** → "Capa Connect", then enter
the email and password for your Capa Connect account.

## Known limitations

- **Schedule handling is partial.** When the heater runs its assigned schedule it
  reports mode 13. A schedule block that is off (no setpoint — e.g. the default
  "24 hour Off" schedule) is now shown as **off**; a block with a setpoint reads
  as heating at that temperature. Only the off case has been verified against real
  hardware — the heating-block path is inferred. The `until-next-block` modes
  (4/7) still show as generic `heat` without a preset. The `gdhv_mode` attribute
  exposes the raw device mode.
- **HomeKit temperature step.** Apple's Home app always offers a 0.5° slider for
  thermostats — HA's HomeKit bridge hardcodes the characteristic step and ignores
  the entity's step, and this can't be changed from an integration. The heater
  still lands on a whole degree, because half-degree values are rounded before
  being sent.
- **Out-of-band changes** (Capa app, physical controls) appear at the next 60 s
  poll, not instantly. HA is the single source of truth for the HomeKit bridge,
  so all Home app clients on it stay consistent with HA.
- The account's **first site** and all its zones are imported; typically one
  heater.
- This is **unofficial** and not affiliated with Glen Dimplex or Noirot. It
  relies on a private API that could change at any time.
