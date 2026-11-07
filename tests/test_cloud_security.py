"""Cloud failures must remain safe to share in diagnostics and logs."""

import logging
import time
import traceback
from types import SimpleNamespace

import pytest
from aiohttp import (
    ClientConnectionError,
    ClientResponseError,
    ContentTypeError,
    RequestInfo,
)
from multidict import CIMultiDict, CIMultiDictProxy
from yarl import URL

from custom_components.moonside.cloud import (
    MoonsideCloudAuthError,
    MoonsideCloudClient,
    MoonsideCloudError,
)
from custom_components.moonside.config_flow import _map_cloud_auth_error
from custom_components.moonside.moonside import MoonsideInstance


@pytest.mark.parametrize(
    "failure", ["content_type", "connection", "provider_body", "json", "timeout"]
)
async def test_cloud_failures_do_not_expose_credentials(failure, caplog):
    """Untrusted HTTP exceptions and bodies cannot copy secrets into logs."""
    token = "private-cloud-token"
    email = "private-user@example.invalid"
    password = "private-cloud-password"
    url = URL(f"https://example.invalid/device.json?auth={token}")
    request = RequestInfo(url, "GET", CIMultiDictProxy(CIMultiDict()), url)
    secret_text = f"{token} {email} {password}"

    class Response:
        status = 500 if failure == "provider_body" else 200

        def raise_for_status(self):
            if self.status == 500:
                raise ClientResponseError(request, (), status=500, message=secret_text)

        async def json(self):
            if failure == "content_type":
                raise ContentTypeError(request, (), message=secret_text)
            if failure == "json":
                raise ValueError(secret_text)
            return {"error": {"message": secret_text}}

    class Session:
        async def get(self, *args, **kwargs):
            if failure == "connection":
                raise ClientConnectionError(secret_text)
            if failure == "timeout":
                raise TimeoutError(secret_text)
            return Response()

    client = MoonsideCloudClient(Session(), email, password)
    with pytest.raises(MoonsideCloudError) as caught:
        await client._async_request_json("get", str(url))
    formatted = "".join(traceback.format_exception(caught.value))
    for secret in (token, email, password):
        assert secret not in str(caught.value)
        assert secret not in formatted

    client._id_token = token
    client._local_id = "test-user"
    client._token_expiry = time.monotonic() + 1000
    instance = MoonsideInstance(
        "AA:BB:CC:DD:EE:FF",
        "Lamp",
        hass=SimpleNamespace(),
        cloud_email=email,
        cloud_password=password,
        cloud_device_id="test-device",
    )
    instance._cloud_client = client
    instance._update_advertisement_state = lambda: False
    with caplog.at_level(logging.DEBUG, logger="custom_components.moonside.moonside"):
        await instance.update()
    for secret in (token, email, password):
        assert secret not in caplog.text


@pytest.mark.parametrize(
    ("provider_message", "expected_error"),
    [
        ("EMAIL_EXISTS", "email_already_exists"),
        ("EMAIL-ALREADY-IN-USE", "email_already_exists"),
        ("EMAIL_NOT_FOUND", "email_not_found"),
        ("INVALID_LOGIN_CREDENTIALS", "invalid_auth"),
        ("INVALID_PASSWORD", "invalid_auth"),
        ("INVALID_EMAIL", "invalid_email"),
        ("INVALID_PASSWORD : private-provider-detail", "invalid_auth"),
        ("INVALID_EMAIL private-provider-detail", "invalid_auth"),
        ("private-provider-detail", "invalid_auth"),
    ],
)
async def test_auth_rejections_preserve_only_known_categories(
    provider_message, expected_error, caplog
):
    """Provider details stay private while config-flow errors remain useful."""
    secret = "private-provider-detail"
    url = URL(f"https://example.invalid/login?key={secret}")
    request = RequestInfo(url, "POST", CIMultiDictProxy(CIMultiDict()), url)

    class Response:
        status = 400

        def raise_for_status(self):
            raise ClientResponseError(request, (), status=400, message=secret)

        async def json(self):
            return {"error": {"message": provider_message}}

    class Session:
        async def post(self, *args, **kwargs):
            return Response()

    client = MoonsideCloudClient(Session(), secret, secret, api_key=secret)
    with pytest.raises(MoonsideCloudAuthError) as caught:
        await client.async_create_account()

    assert _map_cloud_auth_error(str(caught.value)) == expected_error
    assert secret not in str(caught.value)
    assert secret not in "".join(traceback.format_exception(caught.value))
    logging.getLogger(__name__).warning(
        "Cloud authentication failed: %s", caught.value, exc_info=caught.value
    )
    assert secret not in caplog.text


@pytest.mark.parametrize(
    "payload",
    [
        None,
        "private-provider-detail",
        {"error": "private-provider-detail"},
        {"error": {"message": ["private-provider-detail"]}},
        ValueError("private-provider-detail"),
    ],
)
async def test_malformed_auth_errors_do_not_expose_response_body(payload):
    """Malformed Firebase error bodies must not become diagnostic strings."""

    class Response:
        status = 400

        def raise_for_status(self):
            raise ValueError("private-provider-detail")

        async def json(self):
            if isinstance(payload, Exception):
                raise payload
            return payload

    class Session:
        async def post(self, *args, **kwargs):
            return Response()

    client = MoonsideCloudClient(Session(), "user@example.invalid", "password")
    with pytest.raises(MoonsideCloudAuthError) as caught:
        await client.async_send_password_reset_email()

    assert _map_cloud_auth_error(str(caught.value)) == "invalid_auth"
    assert "private-provider-detail" not in "".join(
        traceback.format_exception(caught.value)
    )


async def test_invalid_auth_expiry_does_not_expose_response_value(caplog):
    """Token-expiry conversion errors must not reveal the provider's value."""
    secret = "private-provider-detail"

    class Response:
        def raise_for_status(self):
            pass

        async def json(self):
            return {
                "idToken": "id-token",
                "refreshToken": "refresh-token",
                "localId": "local-id",
                "expiresIn": secret,
            }

    class Session:
        async def post(self, *args, **kwargs):
            return Response()

    client = MoonsideCloudClient(Session(), "user@example.invalid", "password")
    with pytest.raises(MoonsideCloudError) as caught:
        await client.async_create_account()

    assert "authentication response" in str(caught.value)
    assert secret not in "".join(traceback.format_exception(caught.value))
    logging.getLogger(__name__).warning(
        "Cloud response failed: %s", caught.value, exc_info=caught.value
    )
    assert secret not in caplog.text
