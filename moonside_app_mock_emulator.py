"""Minimal local semantic emulator for the strongest supported Moonside app mock model.

This deliberately treats the upstream A1 response as decoded text and emits a
DeviceInfo-like structure without claiming exact wire format or protocol fidelity.
"""

from __future__ import annotations

import json
from pathlib import Path


DEVICE_ID = "26A3BB99-5EA4-05A2-69D8-42149F79C51D"


def emulate_device_info(decoded_payload: str, device_id: str = DEVICE_ID) -> dict:
    """Map a decoded A1 payload into the strongest supported mock DeviceInfo."""
    payload = decoded_payload.upper()

    device_info: dict = {
        "id": device_id,
        "connectionState": 1,
    }

    if "OFF" in payload:
        device_info["powerSemantic"] = "OFF"
    elif "ON" in payload:
        device_info["powerSemantic"] = "ON"
    else:
        device_info["powerSemantic"] = "UNKNOWN"

    if "ERROR" in payload or "FAIL" in payload:
        device_info["connectionState"] = 0
        device_info["failure"] = {
            "code": 1,
            "message": "mock failure",
        }

    return device_info


def main() -> None:
    fixture_path = Path(__file__).with_name("moonside_app_mock_fixture.json")
    fixture_data = json.loads(fixture_path.read_text())

    print("== Moonside mock emulator ==")
    print(f"fixture: {fixture_path}")

    for entry in fixture_data["fixtures"]:
        result = emulate_device_info(entry["payload"])
        print(f"[{entry['name']}]")
        print(
            json.dumps({"payload": entry["payload"], "device_info": result}, indent=2)
        )


if __name__ == "__main__":
    main()
