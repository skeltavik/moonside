"""Constants for the Moonside integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "moonside"

# Nordic UART Service UUIDs
UART_SERVICE_UUID: Final = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
UART_RX_CHAR_UUID: Final = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
UART_TX_CHAR_UUID: Final = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"

# Configuration keys
CONF_MAC: Final = "mac"
CONF_NAME: Final = "name"
CONF_BLE_NAME: Final = "ble_name"
CONF_CLOUD_EMAIL: Final = "cloud_email"
CONF_CLOUD_PASSWORD: Final = "cloud_password"
CONF_CLOUD_DEVICE_ID: Final = "cloud_device_id"
CONF_CLOUD_WRITE_GRACE_SECONDS: Final = "cloud_write_grace_seconds"

# Default values
DEFAULT_NAME: Final = "Moonside Light"
DEFAULT_BRIGHTNESS: Final = 255
DEFAULT_CLOUD_WRITE_GRACE_SECONDS: Final = 10

# Moonside cloud API
FIREBASE_API_KEY: Final = "AIzaSyCC-qQZqcZhxqsbO7GB0nXZShab9gV06Bk"
FIREBASE_IDENTITY_URL: Final = (
    "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"
)
FIREBASE_SIGN_UP_URL: Final = (
    "https://identitytoolkit.googleapis.com/v1/accounts:signUp"
)
FIREBASE_OOB_URL: Final = (
    "https://identitytoolkit.googleapis.com/v1/accounts:sendOobCode"
)
FIREBASE_TOKEN_REFRESH_URL: Final = "https://securetoken.googleapis.com/v1/token"
REALTIME_DATABASE_URL: Final = "https://moonside-501a1.firebaseio.com"

# Moonside protocol constants
MAX_BRIGHTNESS: Final = 120  # Moonside max brightness is 120
NUM_PIXELS: Final = 90  # Number of pixels on Moonside Lighthouse

# Commands (from reverse engineering)
CMD_LED_ON: Final = "LEDON"
CMD_LED_OFF: Final = "LEDOFF"
CMD_BRIGHTNESS: Final = "BRIGH"
CMD_COLOR: Final = "COLOR"
CMD_PIXEL: Final = "PIXEL"
CMD_MODE_PIXEL: Final = "MODEPIXEL"

# Theme keywords (from reverse engineering blog)
THEME_KEYWORDS = [
    "THEME1",
    "THEME2",
    "THEME3",
    "THEME4",
    "THEME5",
    "WAVE1",
    "WAVE2",
    "BEAT1",
    "BEAT2",
    "BEAT3",
    "GRADIENT1",
    "GRADIENT2",
    "RAINBOW1",
    "RAINBOW2",
    "RAINBOW3",
    "TWINKLE1",
    "FIRE1",
    "FIRE2",
    "COLORDROP1",
    "LAVA1",
    "PULSING1",
    "PALETTE1",
    "PALETTE2",
]

# Built-in themes with their configurations
# Format: name -> (display_name, theme_keyword, color_args)
THEMES = {
    # Rainbow themes
    "rainbow_one": ("Rainbow One", "RAINBOW1", "20,"),
    "rising_rainbow": ("Rising Rainbow", "RAINBOW2", "20,"),
    "blending_rainbow": ("Blending Rainbow", "RAINBOW3", "0,"),
    "color_wheel": ("Color Wheel", "PALETTE1", "0,"),
    # Fire themes
    "night_fire": ("Night Fire", "FIRE1", "20,"),
    "green_fire": ("Green Fire", "FIRE2", "0,0,0,0,255,0,200,0,0,255,0,0,"),
    "ghost_fire": ("Ghost Fire", "FIRE2", "0,0,0,255,0,0,0,0,255,255,255,255,"),
    "rainbow_fire": ("Rainbow Fire", "FIRE2", "0,0,0,255,0,0,0,255,0,0,0,255,"),
    "magic_fire": ("Magic Fire", "FIRE2", "0,0,0,255,0,0,0,0,255,255,255,255,"),
    "glowing_lava": ("Glowing Lava", "LAVA1", "255,25,0,100,30,0,255,150,0,"),
    "blue_lava": ("Blue Lava", "LAVA1", "200,0,0,50,0,0,0,0,255,"),
    "macmac": ("MacMac", "LAVA1", "20,255,2,255,100,0,255,0,60,"),
    "cool_sky": ("Cool Sky", "LAVA1", "0,183,255,0,0,0,255,255,255,"),
    "christmas_snow": ("Christmas Snow", "LAVA1", "255,0,0,60,60,60,0,255,0,"),
    # Gradient themes
    "green_land": ("Green Land", "GRADIENT2", "0,255,0,20,65,20,200,200,200,"),
    "christmas_blend": ("Christmas Blend", "GRADIENT1", "0,255,0,255,0,0,"),
    "purple_cake": ("Purple Cake", "GRADIENT2", "145,3,245,255,25,194,191,176,187,"),
    "purple_dream": ("Purple Dream", "GRADIENT1", "150,0,255,255,214,243,"),
    "late_oj": ("Late OJ", "GRADIENT1", "255,80,0,0,0,0,"),
    "margo": ("Margo", "GRADIENT1", "255,208,50,100,100,100,"),
    "pink_dawn": ("Pink Dawn", "GRADIENT1", "255,0,0,200,200,200,"),
    "galaxy_purple": ("Galaxy Purple", "GRADIENT1", "147,71,255,255,102,50,"),
    "nemo_green": ("Nemo Green", "GRADIENT2", "255,0,0,50,190,10,0,160,200,"),
    "volcano_ice_cream": (
        "Volcano Ice Cream",
        "GRADIENT2",
        "255,0,0,80,20,0,200,200,200,",
    ),
    "megatron": ("Megatron", "GRADIENT1", "198,255,221,247,45,50,"),
    "blue_raspberry": ("Blue Raspberry", "GRADIENT1", "255,0,0,0,50,200,"),
    "wizard": ("Wizard", "GRADIENT1", "0,255,0,200,200,200,"),
    "orange_ocean": ("Orange Ocean", "GRADIENT1", "255,50,0,0,90,220,"),
    "jingle_bell": ("Jingle Bell", "GRADIENT2", "0,255,0,255,0,0,100,0,0,"),
    "celebration_candy": (
        "Celebration Candy",
        "GRADIENT2",
        "59,250,229,255,85,0,255,0,20,",
    ),
    "ice_mountain": ("Ice Mountain", "GRADIENT2", "0,0,255,30,102,128,255,255,255,"),
    "magic_blend": ("Magic Blend", "GRADIENT1", "86,255,119,98,38,210,"),
    "martini": ("Martini", "GRADIENT1", "255,255,30,36,255,65,"),
    "petrol": ("Petrol", "GRADIENT1", "195,255,210,2,9,19,"),
    "aqua_wave": ("Aqua Wave", "GRADIENT1", "0,150,255,200,200,200,"),
    "watershine": ("WaterShine", "GRADIENT2", "8,175,212,178,37,247,242,12,188,"),
    # Beat themes
    "dancing_beat": ("Dancing Beat", "BEAT1", "255,0,0,0,255,0,0,0,255,"),
    "bouncing_stars": ("Bouncing Stars", "BEAT2", "255,255,0,0,0,255,"),
    "shining_beat": ("Shining Beat", "BEAT1", "255,190,100,255,190,100,"),
    "dancing_ocean": ("Dancing Ocean", "BEAT2", "7,200,249,13,34,135,"),
    "vibe_beat": ("Vibe Beat", "BEAT1", "0,255,0,200,200,200,"),
    # Theme patterns
    "blue_raspberry_theme": ("Blue Raspberry", "THEME1", "162,255,174,255,85,90,"),
    "my_moon": ("My Moon", "THEME1", "255,0,0,0,0,255,"),
    "wire_tap": ("Wire Tap", "THEME2", "138,35,135,242,113,33,"),
    "raining_blue": ("Raining Blue", "COLORDROP1", "10,100,255,200,200,200,"),
    "twinkle_star": ("Twinkle Star", "TWINKLE1", "255,0,0,0,0,255,"),
    "twinkle_christmas": ("Twinkle Christmas", "TWINKLE1", "255,0,0,0,180,0,"),
    "summer_glow": ("Summer Glow", "THEME1", "168,255,120,120,255,214,"),
    "colorful_swinging": (
        "Colorful Swinging",
        "PALETTE2",
        "0,0,200,0,100,200,100,0,200,200,0,0,200,0,100,120,200,0,",
    ),
    "rose_drop": ("Rose Drop", "COLORDROP1", "0,255,0,255,8,130,"),
    "super_pulsing": ("Super Pulsing", "PULSING1", "255,0,20,20,20,255,"),
    "super_limeade": ("Super Limeade", "PULSING1", "115,255,182,250,255,204,"),
    "distant_night": ("Distant Night", "THEME1", "0,0,255,255,0,255,"),
    "wild_watermelon": ("Wild Watermelon", "THEME1", "255,0,0,0,255,0,"),
    "ali": ("Ali", "THEME4", "255,66,20,255,66,20,8,217,255,"),
    "vibrant_city": ("Vibrant City", "THEME5", "200,20,150,0,60,255,"),
    # Wave themes
    "pink_ball": ("Pink Ball", "WAVE1", "255,0,0,255,0,255,"),
}


# List of effect names for UI
def get_effect_list() -> list[str]:
    """Return list of effect names for UI display."""
    return [theme[0] for theme in THEMES.values()]


def get_effect_display_name(effect_key: str) -> str:
    """Get display name for an effect key."""
    if effect_key in THEMES:
        return THEMES[effect_key][0]
    return effect_key


def get_theme_command(effect_key: str) -> str | None:
    """Generate the full theme command for a given effect key."""
    if effect_key not in THEMES:
        return None

    _, keyword, args = THEMES[effect_key]
    return f"THEME.{keyword}.{args}"


# Effect mapping for LightEntity
def get_effect_key_from_name(effect_name: str) -> str | None:
    """Find effect key from display name."""
    if effect_name in THEMES:
        return effect_name

    for key, (name, _, _) in THEMES.items():
        if name == effect_name:
            return key
    return None


def get_effect_key_from_command(command: str) -> str | None:
    """Find effect key from a full THEME command string."""
    normalized_command = command.strip().upper()
    for key in THEMES:
        if get_theme_command(key) == normalized_command:
            return key
    return None
