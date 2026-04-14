# Moonside State Trace Runbook

## Goal
Capture the exact BLE write, read, notification, and app-side state-update sequence while toggling the lamp, so the on/off payload bytes can be mapped with evidence instead of inference.

## Prerequisites
- Android device with the Moonside app installed
- USB debugging enabled
- Frida server running on the device and `frida` CLI available on the host
- This repo checked out locally with `moonside_state_trace.js` present

## Launch
```bash
frida -U -f <package.name> -l moonside_state_trace.js
```

If the package name is unknown, list candidates first:
```bash
frida-ps -Uai | grep -i moonside
```

## Capture sequence
Run these as separate observations so you can correlate cause and effect clearly.

### 1. Baseline refresh
- Start the app fresh under Frida
- Open the device screen
- Trigger the app action that refreshes device info without changing power state
- Save the full trace output

### 2. Toggle ON
- With tracing still active, turn the lamp ON from inside the app
- Wait for the app UI to settle
- Save the trace output for that action window

### 3. Toggle OFF
- Turn the lamp OFF from inside the app
- Wait for the app UI to settle
- Save the trace output for that action window

## What to look for

### Write correlation
Find the nearest write event before each visible state change:
- `[plugin.writeWithResponse]` / `[plugin.writeWithoutResponse]`
- `[ble.writeWithResponse]` / `[ble.writeWithoutResponse]`

Record:
- device ID
- characteristic UUID
- instance ID
- raw payload bytes

### Read / notification evidence
Find the next state-bearing inbound event after the write or refresh:
- `[plugin.readCharacteristic]`
- `[ble.readCharacteristic]`
- `[notify.subscribe]`
- `[notify.value.bytes]`

Record:
- read target UUID / instance ID
- raw notification bytes
- whether the same bytes differ between ON and OFF runs

### App-side parsing proof
Correlate the inbound bytes with:
- `[app.readA1DeviceBleInfo]`
- `[app.connectionChecker]`
- `[app.updateDeviceInfo]`
- `[connection.update]`

The objective is to identify the first point where ON and OFF become distinguishable in raw data, and then the point where the app turns that into structured state.

## Success criteria
This run is successful if you can answer all of the following with trace evidence:
- Which characteristic UUID carries the relevant state bytes?
- Does the app learn state from explicit reads, notifications, or both?
- Which payload bytes or field positions differ between ON and OFF?
- Which app-side function first reflects that difference?

## If the trace is incomplete
- If writes appear but no inbound state arrives, keep the refresh action separate from toggles and repeat.
- If notifications subscribe but no values appear, the app may rely on reads only.
- If app-side `BleDeviceConnector` hooks do not fire, keep the plugin/notification traces and narrow the next hook from the observed UUIDs.

## Expected next output
After one successful ON trace and one successful OFF trace, create a minimal table:

| Action | Write UUID | Read/Notify UUID | Raw bytes | Parsed app state |
|---|---|---|---|---|
| ON | ... | ... | ... | ... |
| OFF | ... | ... | ... | ... |

That table is the bridge from reverse-engineering evidence to a truthful Home Assistant live-state implementation.
