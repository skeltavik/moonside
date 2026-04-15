"""Moonside cloud API helpers."""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import quote

from aiohttp import ClientResponse, ClientSession

from .const import (
    FIREBASE_API_KEY,
    FIREBASE_IDENTITY_URL,
    FIREBASE_TOKEN_REFRESH_URL,
    REALTIME_DATABASE_URL,
    get_effect_key_from_command,
)


class MoonsideCloudError(Exception):
    """Base error for Moonside cloud failures."""


class MoonsideCloudAuthError(MoonsideCloudError):
    """Raised when cloud credentials are rejected."""


class MoonsideCloudClient:
    """Thin client for the Moonside Firebase backend."""

    def __init__(
        self,
        session: ClientSession,
        email: str,
        password: str,
        api_key: str = FIREBASE_API_KEY,
    ) -> None:
        self._session = session
        self._email = email
        self._password = password
        self._api_key = api_key
        self._id_token: str | None = None
        self._refresh_token: str | None = None
        self._local_id: str | None = None
        self._token_expiry = 0.0

    async def async_fetch_devices(self) -> dict[str, dict[str, Any]]:
        """Fetch all devices for the authenticated account."""
        await self._ensure_authenticated()
        response = await self._session.get(self._build_devices_url())
        await self._raise_for_status(response)
        payload: dict[str, dict[str, Any]] | None = await response.json()
        return payload or {}

    async def async_get_device_state(self, device_id: str) -> dict[str, Any]:
        """Fetch state for a single device."""
        await self._ensure_authenticated()
        response = await self._session.get(self._build_device_url(device_id))
        await self._raise_for_status(response)
        payload: dict[str, Any] | None = await response.json()
        return payload or {}

    async def _ensure_authenticated(self) -> None:
        now = time.monotonic()
        if self._id_token and now < self._token_expiry:
            return

        if self._refresh_token:
            try:
                await self._refresh()
                return
            except MoonsideCloudError:
                pass

        await self._login()

    async def _login(self) -> None:
        response = await self._session.post(
            f"{FIREBASE_IDENTITY_URL}?key={self._api_key}",
            json={
                "email": self._email,
                "password": self._password,
                "returnSecureToken": True,
            },
        )
        await self._raise_for_status(response, auth_request=True)
        payload = await response.json()
        self._id_token = payload["idToken"]
        self._refresh_token = payload["refreshToken"]
        self._local_id = payload["localId"]
        expires_in = int(payload.get("expiresIn", "3600"))
        self._token_expiry = time.monotonic() + max(expires_in - 120, 60)

    async def _refresh(self) -> None:
        response = await self._session.post(
            f"{FIREBASE_TOKEN_REFRESH_URL}?key={self._api_key}",
            json={
                "grant_type": "refresh_token",
                "refresh_token": self._refresh_token,
            },
        )
        await self._raise_for_status(response, auth_request=True)
        payload = await response.json()
        self._id_token = payload["id_token"]
        self._refresh_token = payload["refresh_token"]
        self._local_id = payload["user_id"]
        expires_in = int(payload.get("expires_in", "3600"))
        self._token_expiry = time.monotonic() + max(expires_in - 120, 60)

    def _build_devices_url(self) -> str:
        if not self._local_id or not self._id_token:
            raise MoonsideCloudAuthError("Client is not authenticated")
        return f"{REALTIME_DATABASE_URL}/userDevices/{self._local_id}.json?auth={self._id_token}"

    def _build_device_url(self, device_id: str) -> str:
        if not self._local_id or not self._id_token:
            raise MoonsideCloudAuthError("Client is not authenticated")
        encoded_device = quote(device_id, safe="")
        return f"{REALTIME_DATABASE_URL}/userDevices/{self._local_id}/{encoded_device}.json?auth={self._id_token}"

    @staticmethod
    async def _raise_for_status(
        response: ClientResponse, auth_request: bool = False
    ) -> None:
        try:
            response.raise_for_status()
        except Exception as err:  # pylint: disable=broad-except
            details = await response.text()
            if auth_request and response.status == 400:
                raise MoonsideCloudAuthError(details) from err
            raise MoonsideCloudError(details) from err


def infer_power_state(device_state: dict[str, Any]) -> bool | None:
    """Infer power state from the cloud payload."""
    command = str(device_state.get("controlData", "")).upper()
    if "LEDON" in command:
        return True
    if "LEDOFF" in command:
        return False
    if command.startswith(("THEME", "COLOR", "PIXEL", "BRIGH")):
        return True

    if isinstance(device_state.get("on"), bool):
        return bool(device_state["on"])

    return None


def infer_brightness(device_state: dict[str, Any]) -> int | None:
    """Infer Home Assistant brightness from cloud data."""
    raw_brightness = device_state.get("brightness")
    if isinstance(raw_brightness, (int, float)):
        return _scale_cloud_brightness(int(raw_brightness))

    command = str(device_state.get("controlData", ""))
    if command.upper().startswith("BRIGH"):
        try:
            return _scale_cloud_brightness(int(command[5:]))
        except ValueError:
            return None

    return None


def infer_rgb_color(device_state: dict[str, Any]) -> tuple[int, int, int] | None:
    """Infer RGB color from cloud data."""
    command = str(device_state.get("controlData", ""))
    if command.upper().startswith("COLOR") and len(command) >= 14:
        payload = command[5:14]
        if payload.isdigit():
            return (
                int(payload[0:3]),
                int(payload[3:6]),
                int(payload[6:9]),
            )

    hex_value = device_state.get("colorHEXDecimal")
    if isinstance(hex_value, int):
        hex_string = f"{hex_value:06x}"
        return (
            int(hex_string[0:2], 16),
            int(hex_string[2:4], 16),
            int(hex_string[4:6], 16),
        )

    return None


def infer_effect(device_state: dict[str, Any]) -> str | None:
    """Infer the active effect key from cloud control data."""
    command = str(device_state.get("controlData", ""))
    if not command.upper().startswith("THEME."):
        return None
    return get_effect_key_from_command(command)


def _scale_cloud_brightness(value: int) -> int:
    """Scale cloud brightness to Home Assistant's 0-255 range."""
    if value <= 100:
        return max(0, min(255, round((value / 100) * 255)))
    return max(0, min(255, round((value / 120) * 255)))
