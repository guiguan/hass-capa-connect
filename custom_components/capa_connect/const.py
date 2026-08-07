"""Constants for the Capa Connect (Glen Dimplex / GDHV IoT) integration."""

DOMAIN = "capa_connect"

# --- GDHV IoT device API ---
API_BASE = "https://mobileapi.gdhv-iot.com"

# Headers the device API expects (captured from the app). app_name identifies
# the white-label; api_version gates the endpoint contract.
DEVICE_HEADERS = {
    "app_name": "CapaConnect",
    "app_version": "3.24.0",
    "api_version": "1.0",
    "app_device_os": "iOS",
    "lang_code": "en",
    "logging_required_flag": "0",
    "Accept": "*/*",
}

# --- Azure AD B2C auth ---
B2C_BASE = "https://gdhvb2c.b2clogin.com"
B2C_TENANT = "gdhvb2c.onmicrosoft.com"
B2C_POLICY = "B2C_1A_CapaConnectSignupSignIn"
CLIENT_ID = "fc527388-5067-4934-8e38-27d927457e01"
SCOPE = "https://gdhvb2c.onmicrosoft.com/Mobile/read offline_access openid profile"
REDIRECT_URI = "msalfc527388-5067-4934-8e38-27d927457e01://auth"

AUTHORIZE_URL = f"{B2C_BASE}/tfp/{B2C_TENANT}/{B2C_POLICY}/oauth2/v2.0/authorize"
TOKEN_URL = f"{B2C_BASE}/tfp/{B2C_TENANT}/{B2C_POLICY}/oauth2/v2.0/token"
SELFASSERTED_URL = f"{B2C_BASE}/{B2C_TENANT}/{B2C_POLICY}/SelfAsserted"
CONFIRMED_URL = (
    f"{B2C_BASE}/{B2C_TENANT}/{B2C_POLICY}/api/CombinedSigninAndSignup/confirmed"
)

# --- Zone operating modes (PERMANENT variants only; the +1 "until next schedule
# block" overrides and the schedule-only modes 3/6 are deliberately not used). ---
MODE_OFF = 0
MODE_AWAY = 2  # frost/away, holds ~7 C
MODE_COMFORT = 5  # permanent, uses the zone's ComfortTemp
MODE_ECO = 8  # permanent, uses the zone's EcoTemp
# The device is following its assigned schedule. The active block's effective
# setpoint is reflected in CurrentTemperature; 255 means the block is off (as in
# the default "24 hour Off" schedule), any other value means it is heating.
MODE_SCHEDULE = 13

# "No setpoint" sentinel the API uses for modes without a target temperature.
TEMP_NONE = 255

PRESET_AWAY = "away"
PRESET_ECO = "eco"
PRESET_COMFORT = "comfort"

PRESET_TO_MODE = {
    PRESET_AWAY: MODE_AWAY,
    PRESET_ECO: MODE_ECO,
    PRESET_COMFORT: MODE_COMFORT,
}
MODE_TO_PRESET = {v: k for k, v in PRESET_TO_MODE.items()}
# Any of these mode values means the heater is actively heating (HVAC "heat").
HEATING_MODES = set(PRESET_TO_MODE.values())

# Setpoint bounds for the HA climate entity.
MIN_TEMP = 5
MAX_TEMP = 30

DEFAULT_SCAN_INTERVAL = 60  # seconds
