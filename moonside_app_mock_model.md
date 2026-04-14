# Moonside App Mock Emulation Model

## Goal
Capture the strongest supportable app-side mock model for the A1 read/update path without inventing unsupported bytes or field indices.

## Strongest current data-flow model

### 1. Upstream A1 read output
Best current interpretation from local artifacts:

```text
BLE bytes
  -> readA1DeviceBleInfo(...)
  -> byte slicing / charCodes / UTF-8-ish decode
  -> text-like payload
  -> updateDeviceInfo(...)
```

### Evidence
- `readA1DeviceBleInfo_2a90f4` references:
  - `charCodes`
  - `_ble`
  - `_connectedDeviceOperator`
- `signal_cfg.dot` ties the A1 read path to:
  - `readCharacteristic`
  - `Uint8List.sublist`
  - `StringBase.createFromCharCodes`
- `updateDeviceInfo_2a5f1c` explicitly loads:
  - `ON`
  - `OFF`
  - `A1`
  - `doResetTimer`

## Safest mockable upstream payload hypothesis

The safest app-like mock input is **decoded text**, not raw bytes and not a fully specified JSON/list schema.

```ts
type A1ReadPayload = string;
```

### Supported semantic content
The payload should be treated as containing app-meaningful tokens such as:
- `A1`
- `ON`
- `OFF`

### Not yet supported by evidence
Do **not** assume:
- exact delimiters
- exact field order
- exact byte offsets
- exact list index for power state
- exact framing (`\n`, `|`, `,`, etc.)

## Safest downstream app-state model

The strongest explicit structured object found in the plugin/app boundary is `ProtobufModel.DeviceInfo`.

```ts
type GenericFailure = {
  code: number;
  message: string;
};

type DeviceInfo = {
  id: string;
  connectionState: number;
  failure?: GenericFailure;
};
```

### Evidence
- `ProtobufModel$DeviceInfo.smali`
  - field 1 = `id`
  - field 2 = `connectionState`
  - field 3 = `failure`
- `ConnectionUpdateSuccess.smali`
  - explicit intermediate object with `deviceId` + `connectionState`
- `GenericFailure.smali`
  - field 1 = `code`
  - field 2 = `message`

## Concrete mock-emulation sketch

### Minimal ON mock
```ts
const mockA1PayloadOn = "A1 ... ON ...";

const mockDeviceInfoOn: DeviceInfo = {
  id: "26A3BB99-5EA4-05A2-69D8-42149F79C51D",
  connectionState: 1,
};
```

### Minimal OFF mock
```ts
const mockA1PayloadOff = "A1 ... OFF ...";

const mockDeviceInfoOff: DeviceInfo = {
  id: "26A3BB99-5EA4-05A2-69D8-42149F79C51D",
  connectionState: 1,
};
```

### Failure mock
```ts
const mockDeviceInfoFailure: DeviceInfo = {
  id: "26A3BB99-5EA4-05A2-69D8-42149F79C51D",
  connectionState: 0,
  failure: {
    code: 1,
    message: "mock failure",
  },
};
```

## Exact remaining unknowns
- The exact raw BLE request payload that causes the lamp to emit the A1 response
- The exact raw BLE response bytes for ON vs OFF
- The exact string format produced by `readA1DeviceBleInfo`
- The exact branch/comparison operation inside `updateDeviceInfo` that turns parsed data into `ON` vs `OFF`
- Whether `connectionState` should differ between ON and OFF, or only between reachable/unreachable states

## Strongest current conclusion
If you want to "pretend to be the app" safely, emulate the A1 path as:

```text
decoded text payload carrying A1 + ON/OFF semantics
        ->
structured DeviceInfo state object
```

That is the deepest supportable mock model from the current artifacts.
