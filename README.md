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
- **Presets** (permanent modes only — no schedules):
  - `comfort` — holds the zone's Comfort setpoint
  - `eco` — holds the zone's Eco setpoint
  - `away` — frost protection (~7 °C)
- **Current temperature** — the heater's room sensor
- **Target temperature** — adjusts the active preset's setpoint

> The heater's built-in schedule feature is intentionally not exposed. Modes map
> to the cloud's *permanent* variants (Off=0, Away=2, Comfort=5, Eco=8); the
> "until next schedule block" and schedule-only modes are not used.

## Installation

### HACS (custom repository)

1. HACS → Integrations → ⋮ → Custom repositories.
2. Add `https://github.com/guiguan/hass-capa-connect` as an **Integration**.
3. Install "Capa Connect (Noirot / GDHV)" and restart Home Assistant.

### Manual

Copy `custom_components/capa_connect/` into your HA `config/custom_components/`
directory and restart.

## Configuration

Settings → Devices & Services → **Add Integration** → "Capa Connect".

Enter the email and password for your Capa Connect account. The password is used
**once** to obtain an OAuth refresh token and is **not stored** — only the
rotating refresh token is kept. If the token ever expires, HA will prompt you to
re-enter your password (reauth).

## Notes / limitations

- Cloud polling only (default 60 s). State changes made in the app appear at the
  next poll.
- The account's first site and all its zones are imported; typically one heater.
- This is unofficial and not affiliated with Glen Dimplex or Noirot. It relies
  on a private API that could change at any time.
