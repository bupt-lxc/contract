import os

from sc_gr_app.identity import get_7_digit_id, get_machine_id


def test_get_7_digit_id_prefers_stripped_os_getlogin(monkeypatch):
    monkeypatch.setattr(os, "getlogin", lambda: "  abc1234  ")
    monkeypatch.setenv("USERNAME", "fallback")

    assert get_7_digit_id() == "abc1234"
    assert get_machine_id() == "abc1234"


def test_get_7_digit_id_falls_back_to_username_when_getlogin_raises(monkeypatch):
    def raise_getlogin():
        raise OSError("no login")

    monkeypatch.setattr(os, "getlogin", raise_getlogin)
    monkeypatch.setenv("USERNAME", "  fallback  ")

    assert get_7_digit_id() == "fallback"


def test_get_7_digit_id_returns_empty_string_when_both_unavailable(monkeypatch):
    def raise_getlogin():
        raise OSError("no login")

    monkeypatch.setattr(os, "getlogin", raise_getlogin)
    monkeypatch.delenv("USERNAME", raising=False)

    assert get_7_digit_id() == ""
