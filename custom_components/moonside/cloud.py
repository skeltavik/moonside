"""Moonside cloud API helpers."""

from __future__ import annotations

import asyncio
import time
from typing import Any
from urllib.parse import quote

from aiohttp import ClientError, ClientResponse, ClientSession, ClientTimeout

from .const import (
    FIREBASE_API_KEY,
    FIREBASE_IDENTITY_URL,
    FIREBASE_OOB_URL,
    FIREBASE_SIGN_UP_URL,
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
        payload = await self._async_request_json("get", self._build_devices_url())
        if payload is None:
            return {}
        if not isinstance(payload, dict) or not all(
            isinstance(device_id, str) and isinstance(state, dict)
            for device_id, state in payload.items()
        ):
            raise MoonsideCloudError("Cloud returned an invalid device list")
        return payload

    async def async_create_account(self) -> None:
        """Create a Firebase email/password account and cache the issued tokens."""
        payload = await self._async_request_json(
            "post",
            f"{FIREBASE_SIGN_UP_URL}?key={self._api_key}",
            json={
                "email": self._email,
                "password": self._password,
                "returnSecureToken": True,
            },
            auth_request=True,
        )
        self._validate_auth_payload(payload, ("idToken", "refreshToken", "localId"))
        self._id_token = payload["idToken"]
        self._refresh_token = payload["refreshToken"]
        self._local_id = payload["localId"]
        self._set_token_expiry(payload.get("expiresIn", "3600"))

    async def async_send_password_reset_email(self) -> None:
        """Send a Firebase password reset email."""
        await self._async_request_json(
            "post",
            f"{FIREBASE_OOB_URL}?key={self._api_key}",
            json={
                "requestType": "PASSWORD_RESET",
                "email": self._email,
            },
            auth_request=True,
        )

    async def async_get_device_state(self, device_id: str) -> dict[str, Any]:
        """Fetch state for a single device."""
        await self._ensure_authenticated()
        payload = await self._async_request_json(
            "get", self._build_device_url(device_id)
        )
        if payload is None:
            return {}
        if not isinstance(payload, dict):
            raise MoonsideCloudError("Cloud returned an invalid device state")
        return payload

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
        payload = await self._async_request_json(
            "post",
            f"{FIREBASE_IDENTITY_URL}?key={self._api_key}",
            json={
                "email": self._email,
                "password": self._password,
                "returnSecureToken": True,
            },
            auth_request=True,
        )
        self._validate_auth_payload(payload, ("idToken", "refreshToken", "localId"))
        self._id_token = payload["idToken"]
        self._refresh_token = payload["refreshToken"]
        self._local_id = payload["localId"]
        self._set_token_expiry(payload.get("expiresIn", "3600"))

    async def _refresh(self) -> None:
        payload = await self._async_request_json(
            "post",
            f"{FIREBASE_TOKEN_REFRESH_URL}?key={self._api_key}",
            data={
                "grant_type": "refresh_token",
                "refresh_token": self._refresh_token,
            },
            auth_request=True,
        )
        self._validate_auth_payload(payload, ("id_token", "refresh_token", "user_id"))
        self._id_token = payload["id_token"]
        self._refresh_token = payload["refresh_token"]
        self._local_id = payload["user_id"]
        self._set_token_expiry(payload.get("expires_in", "3600"))

    def _build_devices_url(self) -> str:
        if not self._local_id or not self._id_token:
            raise MoonsideCloudAuthError("Client is not authenticated")
        return f"{REALTIME_DATABASE_URL}/userDevices/{self._local_id}.json?auth={self._id_token}"

    def _build_device_url(self, device_id: str) -> str:
        if not self._local_id or not self._id_token:
            raise MoonsideCloudAuthError("Client is not authenticated")
        encoded_device = quote(device_id, safe="")
        return f"{REALTIME_DATABASE_URL}/userDevices/{self._local_id}/{encoded_device}.json?auth={self._id_token}"

    async def _async_request_json(
        self,
        method: str,
        url: str,
        *,
        auth_request: bool = False,
        json: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
    ) -> Any:
        """Execute a bounded cloud request and normalize transport failures."""
        request = getattr(self._session, method)
        try:
            response = await request(
                url,
                json=json,
                data=data,
                timeout=ClientTimeout(total=10),
            )
            await self._raise_for_status(response, auth_request=auth_request)
            return await response.json()
        except MoonsideCloudError:
            raise
        except (ClientError, asyncio.TimeoutError, ValueError, TypeError) as err:
            raise MoonsideCloudError(f"Cloud request failed: {err}") from err

    @staticmethod
    def _validate_auth_payload(payload: Any, required_fields: tuple[str, ...]) -> None:
        """Validate fields required from a Firebase authentication response."""
        if not isinstance(payload, dict) or any(
            not isinstance(payload.get(field), str) or not payload[field]
            for field in required_fields
        ):
            raise MoonsideCloudError(
                "Cloud returned an invalid authentication response"
            )

    def _set_token_expiry(self, raw_expiry: Any) -> None:
        """Validate and cache a Firebase token expiry value."""
        try:
            expires_in = int(raw_expiry)
        except (TypeError, ValueError) as err:
            raise MoonsideCloudError(
                "Cloud returned an invalid authentication response"
            ) from err
        if expires_in <= 0:
            raise MoonsideCloudError(
                "Cloud returned an invalid authentication response"
            )
        self._token_expiry = time.monotonic() + max(expires_in - 120, 60)

    @staticmethod
    async def _raise_for_status(
        response: ClientResponse, auth_request: bool = False
    ) -> None:
        try:
            response.raise_for_status()
        except Exception as err:  # pylint: disable=broad-except
            details = await _extract_error_details(response)
            if auth_request and response.status == 400:
                raise MoonsideCloudAuthError(details) from err
            raise MoonsideCloudError(details) from err


async def _extract_error_details(response: ClientResponse) -> str:
    """Return the most useful error string from a Firebase response."""
    try:
        payload = await response.json()
    except Exception:  # noqa: BLE001 - response decoders may raise arbitrary errors
        return await response.text()

    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            if isinstance(message, str) and message:
                return message

    return str(payload)


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
            return _scale_device_brightness(int(command[5:]))
        except ValueError:
            return None

    return None


def infer_rgb_color(device_state: dict[str, Any]) -> tuple[int, int, int] | None:
    """Infer RGB color from cloud data."""
    command = str(device_state.get("controlData", ""))
    if command.upper().startswith("COLOR") and len(command) >= 14:
        payload = command[5:14]
        if payload.isdigit():
            rgb_color = (
                int(payload[0:3]),
                int(payload[3:6]),
                int(payload[6:9]),
            )
            if all(0 <= channel <= 255 for channel in rgb_color):
                return rgb_color

    hex_value = device_state.get("colorHEXDecimal")
    if isinstance(hex_value, int) and 0 <= hex_value <= 0xFFFFFF:
        hex_string = f"{hex_value:06x}"
        return (
            int(hex_string[0:2], 16),
            int(hex_string[2:4], 16),
            int(hex_string[4:6], 16),
        )

    return None


def infer_effect(device_state: dict[str, Any]) -> str | None:
    """Infer the active effect key from cloud control data."""
    command = str(device_state.get("controlData", "")).strip()
    if not command.upper().startswith("THEME."):
        return None
    return get_effect_key_from_command(command)


def _scale_cloud_brightness(value: int) -> int:
    """Scale cloud brightness to Home Assistant's 0-255 range."""
    if value <= 100:
        return max(0, min(255, round((value / 100) * 255)))
    return _scale_device_brightness(value)


def _scale_device_brightness(value: int) -> int:
    """Scale device protocol brightness to Home Assistant's 0-255 range."""
    return max(0, min(255, round((value / 120) * 255)))
