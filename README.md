<img src="custom_components/moonside/icon.png" width="128" height="128" alt="Moonside Icon">

# Home Assistant Integration - Moonside

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)

Home Assistant custom integration for Moonside smart lights (including Halo Lamp and Neon Lighthouse) using Bluetooth Low Energy (BLE).

## Features

- **Auto-discovery**: Automatically discovers Moonside devices via Bluetooth
- **Full RGB Control**: Set any color with brightness control
- **40+ Built-in Effects**: Rainbow, Fire, Wave, Beat, Gradient, Twinkle, Lava, and more
- **Local Control**: No cloud required - direct BLE communication

## Supported Devices

- Moonside Halo Lamp
- Moonside Neon Lighthouse
- Other Moonside BLE lights using the same UART command set
- Other Moonside devices using Nordic UART Service over BLE

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click on "Integrations"
3. Click the menu (⋮) and select "Custom repositories"
4. Add `https://github.com/skeltavik/moonside` as an Integration
5. Click "Install"
6. Restart Home Assistant

### Manual Installation

1. Copy the `custom_components/moonside` folder to your Home Assistant `config/custom_components` directory
2. Restart Home Assistant

## Configuration

1. Go to **Settings** → **Devices & Services** → **Add Integration**
2. Search for "Moonside"
3. Select your discovered device or enter the device identifier manually
4. The light will appear as a new entity

## Usage

### Basic Control

- **On/Off**: Toggle the light
- **Brightness**: 0-100%
- **Color**: Select any RGB color

### Effects

The integration includes 40+ built-in effects:

| Effect Category | Available Effects |
|----------------|------------------|
| Rainbow | Rainbow One, Rising Rainbow, Blending Rainbow, Color Wheel |
| Fire | Night Fire, Green Fire, Ghost Fire, Rainbow Fire, Magic Fire |
| Lava | Glowing Lava, Blue Lava, MacMac, Cool Sky, Christmas Snow |
| Gradient | Green Land, Christmas Blend, Purple Cake, Purple Dream, and more |
| Beat | Dancing Beat, Bouncing Stars, Shining Beat, Dancing Ocean, Vibe Beat |
| Theme Patterns | Blue Raspberry, My Moon, Wire Tap, Raining Blue, Twinkle Star, and more |

Select effects from the "Effect" dropdown in the light entity.

## Technical Details

### Communication Protocol

This integration uses the reverse-engineered BLE protocol for Moonside devices:

- **Service**: Nordic UART Service (UUID: `6e400001-b5a3-f393-e0a9-e50e24dcca9e`)
- **Commands** (text-based):
  - `LEDON` / `LEDOFF` - Power control
  - `BRIGHXXX` - Brightness (0-120)
  - `COLORRRRGGGBBB` - RGB color (set brightness separately)
  - `THEME.*` - Various animated effects
  - `PIXEL,ID,BRIGHTNESS` - Individual pixel control

### Requirements

- Home Assistant 2024.1.0 or newer
- Bluetooth adapter with BLE support
- Moonside device within Bluetooth range

## Troubleshooting

### Device Not Discovered

1. Ensure your Moonside light is powered on and advertising over Bluetooth
2. Check that your Home Assistant host has a working Bluetooth adapter
3. Try moving the device closer to your Home Assistant host
4. Use manual configuration with the device identifier if auto-discovery fails

### Connection Issues

1. Ensure no other device (phone app) is currently connected to the light
2. Check Home Assistant logs for BLE errors
3. Restart the Moonside light by unplugging and plugging it back in

## Credits

- Reverse engineering research by [TheGreydiamond](https://thegreydiamond.de/blog/2022/10/10/reverse-engineering-moonside-lighthouse/)
- Built using [bleak](https://github.com/hbldh/bleak) for BLE communication

## License

MIT License

## Support

- [GitHub Issues](https://github.com/skeltavik/moonside/issues)
