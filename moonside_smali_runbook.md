# Moonside Smali Runbook

## Goal
Switch the reverse-engineering path from recovered symbol analysis to an actual apktool smali workspace, while keeping the BLE live-state investigation focused on the same read/update chain.

## Confirmed inputs
- Base APK: `.playwright-mcp/moonside-xapk/com.moonside.moonside.apk`
- XAPK manifest: `.playwright-mcp/moonside-xapk/manifest.json`
- Package: `com.moonside.moonside`

## Decode command
```bash
apktool d ".playwright-mcp/moonside-xapk/com.moonside.moonside.apk" -o ".playwright-mcp/moonside-smali" -f
```

## Decode output
- `.playwright-mcp/moonside-smali/AndroidManifest.xml`
- `.playwright-mcp/moonside-smali/apktool.yml`
- `.playwright-mcp/moonside-smali/smali/`
- `.playwright-mcp/moonside-smali/smali_classes2/`

## What smali gives us immediately
The flutter_reactive_ble plugin layer survives the smali decode with readable package/class names. This is the first reliable anchor for the BLE state path.

### Plugin-side smali targets
- `.playwright-mcp/moonside-smali/smali/com/signify/hue/flutterreactiveble/PluginController.smali`
- `.playwright-mcp/moonside-smali/smali/com/signify/hue/flutterreactiveble/ble/ReactiveBleClient.smali`
- `.playwright-mcp/moonside-smali/smali/com/signify/hue/flutterreactiveble/channelhandlers/CharNotificationHandler.smali`
- `.playwright-mcp/moonside-smali/smali/com/signify/hue/flutterreactiveble/channelhandlers/DeviceConnectionHandler.smali`

### Exact first smali slices
These are the highest-value method bodies to inspect first inside the decoded tree.

#### Read path
- `PluginController.smali`
  - private `readCharacteristic(Lw6/o;Lw6/q;)V`
  - parse request → call `BleClient.readCharacteristic(deviceId, uuid, instanceId)`
- `ReactiveBleClient.smali`
  - public `readCharacteristic(Ljava/lang/String;Ljava/util/UUID;I)Ld7/q;`
- `ReactiveBleClient$readCharacteristic$1$1$2.smali`
  - `invoke([B)Lcom/signify/hue/flutterreactiveble/ble/CharOperationSuccessful;`
  - this is the key point where raw inbound bytes become a `CharOperationSuccessful`

#### Notify path
- `CharNotificationHandler.smali`
  - `subscribeToNotifications(Lcom/signify/hue/flutterreactiveble/ProtobufModel$NotifyCharacteristicRequest;)V`
  - private `handleNotificationValue(Lcom/signify/hue/flutterreactiveble/ProtobufModel$CharacteristicAddress;[B)V`
- `CharNotificationHandler$subscribeToNotifications$subscription$1.smali`
  - `invoke([B)V`
  - this is the raw notification callback before conversion to protobuf output

#### Write path
- `PluginController.smali`
  - private `writeCharacteristicWithResponse(Lw6/o;Lw6/q;)V`
  - private `writeCharacteristicWithoutResponse(Lw6/o;Lw6/q;)V`
- `PluginController$writeCharacteristicWithResponse$1.smali`
  - forwards to `BleClient.writeCharacteristicWithResponse(...)`
- `PluginController$writeCharacteristicWithoutResponse$1.smali`
  - forwards to `BleClient.writeCharacteristicWithoutResponse(...)`
- `ReactiveBleClient$writeCharacteristicWithResponse$1.smali`
  - `invoke(LI5/v;Landroid/bluetooth/BluetoothGattCharacteristic;[B)Ld7/q;`
  - calls `RxBleConnectionExtensionKt.writeCharWithResponse(...)`
- `ReactiveBleClient$writeCharacteristicWithoutResponse$1.smali`
  - `invoke(LI5/v;Landroid/bluetooth/BluetoothGattCharacteristic;[B)Ld7/q;`
  - calls `RxBleConnectionExtensionKt.writeCharWithoutResponse(...)`

#### Connection/state fan-out
- `DeviceConnectionHandler.smali`
  - private `handleDeviceConnectionUpdateResult(Lcom/signify/hue/flutterreactiveble/ProtobufModel$DeviceInfo;)V`
  - this is where connection/device updates are emitted to the Flutter channel after protobuf conversion

These correspond to the same live trace/hook points already used in `moonside_state_trace.js`:
- `readCharacteristic`
- `readNotifications`
- `writeCharacteristicWithResponse`
- `writeCharacteristicWithoutResponse`
- `setupNotification`
- notification/value handling
- device connection update fan-out

## What smali does NOT give cleanly by itself
The app-side `BleDeviceConnector` path is still effectively obfuscated in smali, so the authoritative cross-reference for those methods remains the unflutter outputs.

### App-side cross-reference layer
- `.playwright-mcp/moonside-unflutter/functions.jsonl`
- `.playwright-mcp/moonside-unflutter/string_refs.jsonl`

Key recovered targets:
- `BleDeviceConnector.connectionChecker_2a5c6c`
- `BleDeviceConnector.updateDeviceInfo_2a5f1c`
- `BleDeviceConnector.readA1DeviceBleInfo_2a90f4`
- `BleDeviceConnector.readBLEData_593630`

Recovered string evidence tied to that path:
- `A1`
- `ON`
- `OFF`
- `charCodes`

## Best combined workflow
1. Use smali for the plugin-side transport and callback flow.
2. Use unflutter cross-references to keep the obfuscated app-side state path navigable.
3. Use `moonside_state_trace.js` to correlate runtime writes/reads/notifications with the recovered app-side path.

## Current best linkage from smali back to app-side semantics

### Concrete transport linkage
- `readA1DeviceBleInfo` → `PluginController.readCharacteristic(...)` → `ReactiveBleClient.readCharacteristic(...)`
- raw read bytes are wrapped at `ReactiveBleClient$readCharacteristic$1$1$2.invoke([B)` into `CharOperationSuccessful`
- notification bytes arrive at `CharNotificationHandler$subscribeToNotifications$subscription$1.invoke([B)` and flow into `handleNotificationValue(...)`
- writes leave through `PluginController.writeCharacteristicWith/WithoutResponse(...)` → `ReactiveBleClient.writeCharacteristicWith/WithoutResponse(...)`

### App-side semantic linkage
Use unflutter as the authoritative semantic index for the obfuscated app layer:
- `BleDeviceConnector.readBLEData_593630`
- `BleDeviceConnector.readA1DeviceBleInfo_2a90f4`
- `BleDeviceConnector.updateDeviceInfo_2a5f1c`
- `BleDeviceConnector.connectionChecker_2a5c6c`

Current evidence strength by function:
- `readBLEData` → actionable as upstream BLE read path
- `readA1DeviceBleInfo` → actionable as A1-specific state-read path
- `updateDeviceInfo` → strongest semantic target; recovered string refs include `ON`, `OFF`, `A1`, and `doResetTimer`
- `connectionChecker` → identified semantically in unflutter and tied to `A1`, but not yet directly re-identified as a stable app-side smali symbol

### Current semantic conclusion
Based on the recovered app-side asm:
- `updateDeviceInfo_2a5f1c` is currently the best place to answer where ON/OFF first becomes distinguishable at the app semantic layer.
- `readA1DeviceBleInfo_2a90f4` appears to be the device-specific read parser feeding that state update path; it references `charCodes`, `_ble`, and `_connectedDeviceOperator`.
- `connectionChecker_2a5c6c` currently looks more like an A1-specific gate/retry/connection-state step than the first clean ON/OFF semantic boundary.

More concretely:
- `updateDeviceInfo_2a5f1c` materially loads the recovered `ON` constant first, then later loads the recovered `OFF` constant and continues into additional device-update logic.
- That makes `updateDeviceInfo` the current best candidate for the first app-side point where raw/device-specific state has already been promoted into human-meaningful power semantics.
- `readA1DeviceBleInfo_2a90f4` shares the same `charCodes`, `_ble`, and `_connectedDeviceOperator` markers as `sendBLEData_4237c8`, which strongly suggests it is operating at the device command/read payload layer rather than the final ON/OFF semantic layer.
- `signal_cfg.dot` strengthens that interpretation: `readA1DeviceBleInfo_2a90f4` explicitly links to `StringBase.createFromCharCodes`, `Uint8List.sublist`, and the Flutter platform-message path, which is consistent with byte-oriented response parsing before semantic labeling.
- Safer wording: `readA1DeviceBleInfo_2a90f4` likely turns A1 BLE response material into higher-level string/list-like data, and `updateDeviceInfo_2a5f1c` likely performs the first explicit A1 status interpretation involving the literals `ON` and `OFF`.

### Deepest current repo-grounded conclusion
- Best current candidate for the **first semantic ON/OFF boundary**: `updateDeviceInfo_2a5f1c`
- Best current candidate for the **upstream byte/payload parser feeding that boundary**: `readA1DeviceBleInfo_2a90f4`
- Best current characterization of `connectionChecker_2a5c6c`: A1-specific gate/retry/connection-state layer, not yet the first clean ON/OFF semantic split

## Runtime tracing blocker in this environment
- The connected Android target is a **jailed** emulator (`emulator-5554`), not a rooted device.
- `frida -U -f com.moonside.moonside ...` fails with: `need Gadget to attach on jailed Android`.
- Attaching to the live PID also fails in this environment with: `unable to connect to remote frida-server: closed`.
- This means the repo now contains the trace assets (`moonside_state_trace.js`, `moonside_state_trace_runbook.md`), but proving the actual ON/OFF bytes still requires a working runtime hook environment (rooted device, gadget-based instrumentation, or a functioning attach path).

### Narrowest next slice
If continuing analysis from this runbook, prioritize:
1. unflutter `BleDeviceConnector.updateDeviceInfo_2a5f1c`
2. unflutter `BleDeviceConnector.readA1DeviceBleInfo_2a90f4`
3. unflutter `BleDeviceConnector.connectionChecker_2a5c6c`
4. `CharNotificationHandler$subscribeToNotifications$subscription$1.smali`
5. `ReactiveBleClient$readCharacteristic$1$1$2.smali`

That slice is the shortest path to answer whether ON/OFF first appears in app-side parsing, or whether you need to fall back to raw read/notification provenance.

## First actionable smali checks
When continuing from here, answer these in order:
1. Which plugin-side write/read methods are actually invoked during lamp toggle and refresh?
2. Which characteristic UUID and instance ID carry the state-bearing traffic?
3. Which app-side cross-referenced function first turns that traffic into `ON` / `OFF` semantics?
4. Does the first ON/OFF distinction appear in read bytes, notification bytes, or only after app-side parsing?

## Success condition
The smali path is considered useful once you can produce a small table linking:
- write UUID
- read/notify UUID
- raw payload bytes
- first app-side parsing function
- observed `ON` vs `OFF` distinction

At that point, the reverse-engineering output is strong enough to guide a truthful Home Assistant live-state implementation.
