<img src="custom_components/moonside/brand/logo.png" width="400" alt="Moonside logo">

# Home Assistant Integration - Moonside

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)

Home Assistant custom integration for Moonside smart lights using Bluetooth Low Energy (BLE) for local control, with optional Moonside cloud-backed state refresh.

## Features

- **Auto-discovery**: Automatically discovers Moonside devices via Bluetooth
- **Full RGB Control**: Set any color with brightness control
- **40+ Built-in Effects**: Rainbow, Fire, Wave, Beat, Gradient, Twinkle, Lava, and more
- **Local BLE Control**: Direct Bluetooth commands for on/off, brightness, color, and effects
- **Optional Cloud State**: Use Moonside cloud credentials to improve power/state readback in Home Assistant
- **Configurable Reconciliation Window**: Delay cloud state reconciliation briefly after local BLE writes
- **Automation Actions**: Set individual Lighthouse pixels, pulse, strobe, or cycle through RGB colors
- **Diagnostics**: Signal strength, Bluetooth availability, and the last command/cloud-state update

## Supported Devices

- Moonside Lamp One
- Moonside Halo Lamp
- Moonside Neon Lighthouse
- Other Moonside BLE lights using the same UART command set

Nordic UART Service alone does not establish compatibility: the device must
understand the Moonside commands described below. Effect support can vary by firmware.

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click on "Integrations"
3. Click the menu (⋮) and select "Custom repositories"
4. Add `https://github.com/skeltavik/moonside` as an Integration
5. Click "Install"
6. Restart Home Assistant

HACS downloads the versioned `moonside.zip` release asset rather than a snapshot
of the moving default branch. A published release is required for installation.

### Manual Installation

1. Copy the `custom_components/moonside` folder to your Home Assistant `config/custom_components` directory
2. Restart Home Assistant

## Configuration

1. Go to **Settings** → **Devices & Services** → **Add Integration**
2. Search for "Moonside"
3. Select your discovered device; if none are found, enter the Bluetooth device identifier manually
4. Leave the optional cloud email and password blank and submit to use local-only control
5. The light and three diagnostic sensors will appear as new entities

For manually configured devices, the integration learns the model from a real
Bluetooth advertisement or discovered BLE device and saves that metadata for
the next restart. Your chosen display name is unchanged. Until that information
is available, the model stays generic and Lighthouse-only pixel actions fail
rather than guessing the device type.

### Optional Cloud-Backed State

The integration works without any cloud configuration. If you want Home Assistant to use Moonside cloud data as the authoritative state source, open the integration options after setup:

1. Go to **Settings** → **Devices & Services**
2. Open the configured **Moonside** entry
3. Click **Configure** / **Options**
4. Select **Sign in to existing account** and enter:
   - **Cloud email** - your Moonside account email
   - **Cloud password** - your Moonside account password
   - **Cloud device ID** *(optional)* - only needed if auto-matching is not sufficient
   - **Cloud write grace seconds** *(optional, default: 10)* - how long Home Assistant should prefer fresh local BLE writes before accepting cloud reconciliation again

When cloud state is configured, the integration keeps using BLE for local control but refreshes power, brightness, color, and effect state from Moonside's cloud when available.

The cloud form is available during initial setup and in the integration options.
Its **Cloud action** selector also supports:

- **Create cloud account**: Enter an email and password. Creating an account does
  not bind a lamp; use the Moonside app to bind devices if needed.
- **Send password reset email**: Enter the account email; no password is required.
  After sending the email, the form stays open rather than finishing setup.

To disable cloud state later, select **Sign in to existing account**, clear both
email and password, and submit the options form.

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

`Blue Raspberry` is the gradient preset; `Blue Raspberry (Theme)` is the separate
two-color motion preset. Every preset has a distinct selectable name.

Effect palettes follow the [published firmware format](https://developer.moonside.design/#themes).
`Ali` uses the three-color gradient family and `Orange Ocean` the two-color
`THEME4` family. `Shining Beat` and `Vibe Beat` include the required third RGB
color by repeating the last color in their existing palettes.

The BLE API has no lighting-command acknowledgement or live effect readback.
Home Assistant's local effect state records the last successful write, not
proof that the lamp is visibly rendering that effect. If an effect goes dark,
report its exact name and device model; a successful BLE write alone cannot
establish firmware compatibility.

### Automation Actions

Use these actions in scripts, automations, or **Developer Tools → Actions**.
Replace the example entity IDs with your Moonside light entity IDs. Pass
`entity_id` inside `data`, as shown; it can also be a list of Moonside lights.

Failed Bluetooth writes raise a Home Assistant error so a blocking action call
or automation can detect the failure. When targeting several lights, the custom
action attempts every selected Moonside light before reporting any failures.

| Action | Parameters and limits | Result |
|--------|-----------------------|--------|
| `moonside.set_pixel` | Required `pixel_id`: 0–89; required `brightness`: 0–120 | Sets and applies one pixel; only devices identified as **Neon Lighthouse** are accepted |
| `moonside.pulse` | Optional `duration`: 0.1–5 seconds, default 0.5 | Turns on once, then off; does not restore the previous power state |
| `moonside.strobe` | Optional `count`: 1–10, default 3; optional `duration`: 0.1–1 seconds per phase, default 0.2 | Repeats on/off and ends off |
| `moonside.color_cycle` | Required `colors`: a JSON string containing one or more RGB triplets, integer channels 0–255; optional `duration`: 0.5–10 seconds, default 2 | Runs once at the cached brightness, ends on the last color, and clears the selected effect |

Pixel brightness uses the device's 0–120 scale, not Home Assistant's 0–255
brightness scale. `color_cycle` distributes `duration` across the colors;
BLE command pacing and connection time add to the total elapsed time.
Strobe produces flashing light; avoid it where flashing is unsafe.

Set a Lighthouse pixel:

```yaml
action: moonside.set_pixel
data:
  entity_id: light.neon_lighthouse
  pixel_id: 0
  brightness: 60
```

Pulse once:

```yaml
action: moonside.pulse
data:
  entity_id: light.moonside
  duration: 0.5
```

Strobe three times:

```yaml
action: moonside.strobe
data:
  entity_id: light.moonside
  count: 3
  duration: 0.2
```

Cycle through three colors:

```yaml
action: moonside.color_cycle
data:
  entity_id: light.moonside
  colors: "[[255,0,0],[0,255,0],[0,0,255]]"
  duration: 2
```

### Diagnostic Sensors

Each configured device creates these sensors in addition to its light entity:

| Sensor | Meaning |
|--------|---------|
| **Signal Strength** | RSSI in dBm from the latest accepted Bluetooth advertisement; not a live signal measurement |
| **Connection Status** | `connected` while a BLE connection is held or an advertisement was seen within the last five minutes; otherwise `disconnected` |
| **Last Update** | Time the integration last updated its command/cloud-state cache; not the last Bluetooth advertisement or confirmation of the physical light state |

The sensors remain available when the lamp is unreachable so diagnostics stay
visible; readings can be unknown until data is received. In particular,
`connected` means Bluetooth availability, not necessarily an active connection.
The RSSI value is retained when advertisements stop.

The light's power state can initially be unknown, including after restoring
saved state. Its `power_state_source` attribute distinguishes `unknown`,
`restored`, `local`, and `cloud`; `power_state_cloud_derived` is true only for
cloud-derived power state.

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

### State Model

- **Writes**: sent locally over BLE
- **Reads**: Bluetooth availability plus optional Moonside cloud state
- **Cloud auth**: Firebase email/password login against the Moonside backend
- **Grace window**: after a successful local BLE write, cloud reconciliation is suppressed briefly to avoid stale cloud state immediately rolling back the UI
- **Dashboard updates**: local state is published after accepted writes without waiting for Bluetooth disconnect. Color or effect selections can include brightness in the same BLE batch; the combined state is published only after that batch succeeds.
- **Connection reuse**: successive commands reuse the Bluetooth connection. It is released after five seconds without commands so the phone app or another controller can reconnect; integration unload also releases it.
- **Cloud isolation**: cloud network requests do not hold the BLE command lock. A response fetched before a successful or partially accepted local write is discarded, even when the grace window is set to zero.
- **External changes**: BLE exposes no live power/color/effect readback. Changes made in the Moonside app cannot be synchronized through BLE polling alone; optional cloud state is needed for external state refresh.

### Requirements

- Home Assistant 2026.10.0 or newer
- Bluetooth adapter or Home Assistant Bluetooth proxy with BLE connection support
- Moonside device within Bluetooth range
- Moonside account credentials only if you want optional cloud-backed state

The supported minimum is the Home Assistant 2026.10.0 version exercised by the
locked test environment and CI. Older Home Assistant versions are not supported.

## Troubleshooting

### Device Not Discovered

1. Ensure your Moonside light is powered on and advertising over Bluetooth
2. Check that your Home Assistant host has a working Bluetooth adapter and that it is not ignored under **Settings** → **Devices & Services**
3. For Lamp One, set the Bluetooth adapter's scanning mode to **Active** if the device appears only as an unnamed address. Its `MOONSIDE-L1` name is returned in the scan response, which passive scanning does not request.
4. Try moving the device closer to your Home Assistant host
5. Use manual configuration with the Bluetooth device address if auto-discovery fails

### Connection Issues

1. Ensure no other device (phone app) is currently connected to the light
2. Check Home Assistant logs for BLE errors
3. Restart the Moonside light by unplugging and plugging it back in
4. If the device is not available through Home Assistant's Bluetooth adapters or proxies, restore Bluetooth discovery first. The integration does not bypass Home Assistant by connecting to a raw address on the local host.

### Cloud State Issues

1. Confirm your Moonside account email and password are correct in the integration options
2. If you have multiple Moonside devices on one account, set the **Cloud device ID** explicitly
3. If Home Assistant seems to revert too quickly or too slowly after local control, adjust **Cloud write grace seconds**
4. If cloud auth fails, local BLE control should still work; only cloud-backed state refresh will be affected

## Development

Development and CI use Python 3.14 with dependencies and tool settings managed
through `pyproject.toml` and the committed `uv.lock`:

```console
uv sync --locked --all-groups
PYTHONPATH=. uv run --locked pytest
uv run --locked ruff check custom_components/moonside scripts tests
uv run --locked ruff format --check custom_components/moonside scripts tests
```

### Releases

Set the same new version in `pyproject.toml` and
`custom_components/moonside/manifest.json`, add its section to
[CHANGELOG.md](CHANGELOG.md), and update `uv.lock`. Build locally from the
repository root before tagging:

```console
uv run --locked python scripts/build_release.py v1.1.0 /tmp/moonside.zip
```

The builder rejects mismatched project, manifest, and tag versions. The ZIP
contains the integration files at its root, including branding assets and no
Python caches. For manual installation, extract it into
`config/custom_components/moonside`, then restart Home Assistant.

After committing a tested version, push its matching `v<version>` tag to run the
release workflow. All validation jobs must pass before it creates a draft,
uploads `moonside.zip` and `SHA256SUMS`, and publishes the release. Keep GitHub's
repository **immutable releases** setting enabled: publication locks the release
assets and associated tag and generates a signed release attestation. The
workflow requires the published release to report `immutable: true` and verifies
its attestation. It uses the ordinary workflow token, not an administrator token.

Verify a published release with `gh release verify v1.1.0`. Checksums detect
changed downloads; immutable releases prevent replacing published assets or
retargeting their tag. They do not make unreviewed code or dependencies safe.
Corrections must be shipped as a new version, not by replacing an existing ZIP.

## Credits

- Reverse engineering research by [TheGreydiamond](https://thegreydiamond.de/blog/2022/10/10/reverse-engineering-moonside-lighthouse/)
- Built using [bleak](https://github.com/hbldh/bleak) for BLE communication

## License

MIT License

## Support

- [GitHub Issues](https://github.com/skeltavik/moonside/issues)
