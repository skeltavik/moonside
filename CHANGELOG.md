# Changelog

## Unreleased

- Wait for asynchronous GitHub release attestations with bounded retries and a fail-closed verification result.

## 1.1.0

- Keep cloud credentials out of errors, tracebacks, and logs.
- Surface failed BLE light commands and services without reporting success.
- Apply requested effects and brightness together, updating state only on success.
- Keep cloud requests off the BLE command lock and discard stale cloud responses.
- Recover and persist Bluetooth model names from cached advertisements or devices.
- Align the supported Home Assistant minimum with the tested 2026.10.0 runtime.
- Build version-checked HACS ZIPs with SHA-256 checksums; validate before publishing immutable tagged releases with GitHub release attestations.
