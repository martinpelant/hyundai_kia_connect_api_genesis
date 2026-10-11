"""Unit tests for Genesis EU functionality in KiaUvoApiEU."""

import base64
import json
from unittest.mock import MagicMock, patch
import pytest

from hyundai_kia_connect_api import Token
from hyundai_kia_connect_api.KiaUvoApiEU import KiaUvoApiEU
from hyundai_kia_connect_api.const import BRAND_GENESIS, BRAND_HYUNDAI, ENGINE_TYPES
from hyundai_kia_connect_api.exceptions import AuthenticationError


def _make_genesis_api():
    return KiaUvoApiEU(region=1, brand=3, language="en")


def _make_genesis_token_b64(extra=None):
    data = {
        "a": "genesis_access_token",
        "r": "genesis_refresh_token",
        "ea": "genesis_exchangeable_access",
        "er": "genesis_exchangeable_refresh",
        "nc": "genesis_non_ccs_access",
        "nr": "genesis_non_ccs_refresh",
        "it": "genesis_id_token",
    }
    if extra:
        data.update(extra)
    return "G:" + base64.b64encode(json.dumps(data).encode()).decode()


def test_genesis_login_with_g_token():
    api = _make_genesis_api()
    encoded_token = _make_genesis_token_b64()

    with patch.object(api, "_exchange_ccs_token_genesis") as mock_exchange:
        token = api.login("user@example.com", encoded_token, pin="1234")

    assert token.username == "user@example.com"
    assert token.access_token == "Bearer genesis_access_token"
    assert token.refresh_token == "genesis_refresh_token"
    assert token.exchangeable_token == "genesis_exchangeable_access"
    assert token.exchangeable_refresh_token == "genesis_exchangeable_refresh"
    assert token.non_ccs_token == "genesis_non_ccs_access"
    assert token.non_ccs_refresh_token == "genesis_non_ccs_refresh"
    assert token.id_token == "genesis_id_token"
    assert token.pin == "1234"
    mock_exchange.assert_called_once_with(token)


def test_genesis_login_invalid_g_token_raises():
    api = _make_genesis_api()
    with pytest.raises(AuthenticationError):
        api.login("user@example.com", "G:not-valid-base64!@#$")


def test_genesis_refresh_access_token_strips_auth_and_rotates_connector():
    api = _make_genesis_api()
    token = Token(
        username="user@example.com",
        password="pwd",
        access_token="Bearer old_access",
        refresh_token="old_refresh",
        exchangeable_token="old_ea",
        exchangeable_refresh_token="old_er",
        non_ccs_token="old_nc",
        non_ccs_refresh_token="old_nr",
        id_token="old_it",
    )

    refresh_response_json = {
        "accessToken": "new_access_token",
        "refreshToken": "new_refresh_token",
        "tokenType": "Bearer",
        "expiresTime": 7200,
        "connector": {
            "hmgid1.0": {
                "accessToken": "rotated_ea",
                "refreshToken": "rotated_er",
            },
            "oneid": {
                "accessToken": "rotated_nc",
                "refreshToken": "rotated_nr",
            },
        },
        "idToken": "new_it",
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = refresh_response_json

    with (
        patch("requests.post", return_value=mock_resp) as mock_post,
        patch.object(api, "_exchange_ccs_token_genesis") as mock_exchange,
    ):
        updated_token = api.refresh_access_token(token)

        assert mock_post.called
        call_args = mock_post.call_args
        sent_headers = call_args[1]["headers"]
        # Must verify that authorization headers were stripped to prevent 401
        assert "authorization" not in sent_headers
        assert "Authorization" not in sent_headers
        assert sent_headers["authentication"] == "old_it"

        sent_payload = call_args[1]["json"]
        assert sent_payload["accessToken"] == "old_access"
        assert sent_payload["refreshToken"] == "old_refresh"
        assert sent_payload["exchangeableAccessToken"] == "old_ea"
        assert sent_payload["exchangeableRefreshToken"] == "old_er"
        assert sent_payload["nonCcsToken"] == "old_nc"
        assert sent_payload["nonCcsRefreshToken"] == "old_nr"

        # Check rotation
        assert updated_token.access_token == "Bearer new_access_token"
        assert updated_token.refresh_token == "new_refresh_token"
        assert updated_token.exchangeable_token == "rotated_ea"
        assert updated_token.exchangeable_refresh_token == "rotated_er"
        assert updated_token.non_ccs_token == "rotated_nc"
        assert updated_token.non_ccs_refresh_token == "rotated_nr"
        assert updated_token.id_token == "new_it"
        mock_exchange.assert_called_once_with(updated_token)


def test_genesis_test_token_handles_9030():
    api = _make_genesis_api()
    token = Token(username="u", password="p", access_token="Bearer tok")

    # Expired token 9030
    mock_resp_9030 = MagicMock()
    mock_resp_9030.status_code = 200
    mock_resp_9030.json.return_value = {"code": 9030, "message": "Token expired"}

    with patch("requests.get", return_value=mock_resp_9030):
        assert api.test_token(token) is False

    # Valid token
    mock_resp_valid = MagicMock()
    mock_resp_valid.status_code = 200
    mock_resp_valid.json.return_value = {"code": 0, "contents": []}

    with patch("requests.get", return_value=mock_resp_valid):
        assert api.test_token(token) is True


def test_genesis_get_vehicles_parsing():
    api = _make_genesis_api()
    token = Token(username="u", password="p", access_token="Bearer tok")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "contents": [
            {
                "ccspCarId": "car-123",
                "vehicleNameView": "GV60",
                "vehicleModelName": "GV60 Sport",
                "vin": "KMHG1234567890",
                "ccspVehicle": {
                    "carType": "EV",
                    "createdAt": "2024-01-01",
                    "detailInfo": {"saleSpecYearCd": "2024"},
                },
            }
        ]
    }

    with patch("requests.get", return_value=mock_resp):
        vehicles = api.get_vehicles(token)

    assert len(vehicles) == 1
    v = vehicles[0]
    assert v.id == "car-123"
    assert v.name == "GV60"
    assert v.model == "GV60 Sport"
    assert v.VIN == "KMHG1234567890"
    assert v.engine_type == ENGINE_TYPES.EV


def test_genesis_authenticated_headers_use_legacy_domain():
    api = _make_genesis_api()
    token = Token(
        username="u",
        password="p",
        access_token="Bearer oneapp_access",
        ccs_token="ccs_token_abc",
        device_id="dev-456",
    )

    with patch.object(api, "_get_stamp", return_value="stamp123"):
        headers = api._get_authenticated_headers(token)

    assert headers["Authorization"] == "Bearer ccs_token_abc"
    assert headers["ccsp-service-id"] == "3020afa2-30ff-412a-aa51-d28fbe901e10"
    assert headers["ccsp-application-id"] == "f11f2b86-e0e7-4851-90df-5600b01d8b70"
    assert headers["ccsp-device-id"] == "dev-456"
    assert headers["Host"] == "prd-eu-ccapi.genesis.com:443"
