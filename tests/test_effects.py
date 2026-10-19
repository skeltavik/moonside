"""Validate selectable effects against the published firmware palette format."""

from custom_components.moonside.const import (
    THEMES,
    get_effect_display_name,
    get_effect_key_from_command,
    get_effect_key_from_name,
    get_effect_list,
    get_theme_command,
)


def test_effect_commands_have_complete_firmware_palettes():
    """Missing RGB triplets must not silently become black in the firmware parser."""
    # https://developer.moonside.design/#themes
    color_counts = {
        "FIRE2": 4,
        "THEME1": 2,
        "THEME2": 2,
        "THEME3": 6,
        "THEME4": 2,
        "THEME5": 2,
        "COLORDROP1": 2,
        "GRADIENT1": 2,
        "GRADIENT2": 3,
        "GRADIENT3": 2,
        "TWINKLE1": 2,
        "PULSING1": 2,
        "PALETTE2": 6,
        "BEAT1": 3,
        "BEAT2": 2,
        "BEAT3": 3,
        "WAVE1": 2,
        "LAVA1": 3,
    }
    non_color_codes = {"RAINBOW1", "RAINBOW2", "RAINBOW3", "FIRE1", "PALETTE1"}
    for key in THEMES:
        command = get_theme_command(key)
        prefix, code, parameters = command.split(".")
        assert prefix == "THEME", key
        assert parameters.endswith(","), key
        channels = [int(value) for value in parameters[:-1].split(",")]
        if code in non_color_codes:
            assert len(channels) == 1, key
        else:
            assert len(channels) == color_counts[code] * 3, key
            assert all(0 <= value <= 255 for value in channels), key


def test_every_effect_can_be_selected_and_identified_unambiguously():
    """Different presets must not collapse to the first matching UI name or command."""
    names = get_effect_list()
    assert len(names) == len(set(names))
    for key in THEMES:
        assert get_effect_key_from_name(get_effect_display_name(key)) == key
        assert get_effect_key_from_command(get_theme_command(key)) == key
