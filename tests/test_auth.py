from unittest.mock import MagicMock, patch

import pytest

import robinhood_mcp.auth as auth
from robinhood_mcp.errors import BrokerError


@pytest.fixture(autouse=True)
def reset_login_state():
    auth._logged_in = False
    yield
    auth._logged_in = False


def test_raises_without_credentials(monkeypatch):
    monkeypatch.delenv("ROBINHOOD_USERNAME", raising=False)
    monkeypatch.delenv("ROBINHOOD_PASSWORD", raising=False)

    with pytest.raises(BrokerError, match="ROBINHOOD_USERNAME"):
        auth.ensure_login()


def test_raises_when_login_fails(monkeypatch):
    monkeypatch.setenv("ROBINHOOD_USERNAME", "user@example.com")
    monkeypatch.setenv("ROBINHOOD_PASSWORD", "hunter2")

    with patch.object(auth, "rh", MagicMock(login=MagicMock(return_value=None))):
        with pytest.raises(BrokerError, match="no access token"):
            auth.ensure_login()


def test_successful_login_sets_memoized_flag(monkeypatch):
    monkeypatch.setenv("ROBINHOOD_USERNAME", "user@example.com")
    monkeypatch.setenv("ROBINHOOD_PASSWORD", "hunter2")
    mock_rh = MagicMock(login=MagicMock(return_value={"access_token": "abc"}))

    with patch.object(auth, "rh", mock_rh):
        auth.ensure_login()

    assert auth._logged_in is True
    mock_rh.login.assert_called_once()


def test_second_call_does_not_login_again(monkeypatch):
    monkeypatch.setenv("ROBINHOOD_USERNAME", "user@example.com")
    monkeypatch.setenv("ROBINHOOD_PASSWORD", "hunter2")
    mock_rh = MagicMock(login=MagicMock(return_value={"access_token": "abc"}))

    with patch.object(auth, "rh", mock_rh):
        auth.ensure_login()
        auth.ensure_login()

    mock_rh.login.assert_called_once()


def test_mfa_code_is_passed_through(monkeypatch):
    monkeypatch.setenv("ROBINHOOD_USERNAME", "user@example.com")
    monkeypatch.setenv("ROBINHOOD_PASSWORD", "hunter2")
    monkeypatch.setenv("ROBINHOOD_MFA_CODE", "123456")
    mock_rh = MagicMock(login=MagicMock(return_value={"access_token": "abc"}))

    with patch.object(auth, "rh", mock_rh):
        auth.ensure_login()

    mock_rh.login.assert_called_once_with(
        username="user@example.com", password="hunter2", store_session=True, mfa_code="123456"
    )
