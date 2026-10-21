"""Tests for caption dedupe, the translation stub and proxy-header handling."""
import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def fresh_dedupe_db(tmp_path, monkeypatch):
    import dedupe_store

    monkeypatch.setattr(dedupe_store, "DB_PATH", tmp_path / "dedupe.sqlite")
    dedupe_store._ensure_schema()
    return dedupe_store


def test_dedupe_store_detects_exact_and_fuzzy_duplicates(fresh_dedupe_db):
    store = fresh_dedupe_db
    store.save_caption("Crystal clear water after a storm clean-up and filter rinse today.")
    assert store.is_duplicate_caption("Crystal clear water after a storm clean-up and filter rinse today.")[0]
    assert store.is_duplicate_caption("Crystal clear water after a storm clean-up and filter rinse today!")[0]
    assert not store.is_duplicate_caption("Quick tip: test your pH weekly during summer heat.")[0]


def test_poster_regenerates_duplicate_captions(fresh_dedupe_db, monkeypatch):
    import poster

    fresh_dedupe_db.save_caption("Same old caption about a sparkling clean pool on a sunny day.")
    outputs = iter([
        ("Same old caption about a sparkling clean pool on a sunny day.", True),
        ("Brand new caption: algae prevention starts with steady chlorine levels.", True),
    ])
    monkeypatch.setattr(poster, "_generate_caption", lambda c, w: next(outputs))

    caption, used_llm, duplicate_of = poster._generate_unique_caption("realistic", "")
    assert caption.startswith("Brand new caption")
    assert used_llm is True
    assert duplicate_of is None


def test_poster_flags_caption_when_all_attempts_are_duplicates(fresh_dedupe_db, monkeypatch):
    import poster

    dup = "Same old caption about a sparkling clean pool on a sunny day."
    fresh_dedupe_db.save_caption(dup)
    calls = []

    def fake_generate(category, weather):
        calls.append(1)
        return dup, True

    monkeypatch.setattr(poster, "_generate_caption", fake_generate)
    caption, _, duplicate_of = poster._generate_unique_caption("realistic", "")
    assert caption == dup
    assert duplicate_of == dup
    assert len(calls) == poster.CAPTION_DEDUPE_ATTEMPTS


@pytest.fixture(scope="module")
def client():
    import main

    return TestClient(main.app, base_url="https://testserver")


def test_translate_endpoint_returns_501(client):
    h = {"Authorization": f"Bearer {os.environ['VP_INTERNAL_API_TOKEN']}"}
    r = client.post("/admin/item/abc/translate", json={"target_lang": "es", "caption": "hi"}, headers=h)
    assert r.status_code == 501
    assert r.json()["ok"] is False


def test_scheduler_preview_stub_removed(client):
    h = {"Authorization": f"Bearer {os.environ['VP_INTERNAL_API_TOKEN']}"}
    assert client.get("/admin/scheduler-preview", headers=h).status_code == 404


def test_forwarded_for_ignored_unless_proxy_trusted(monkeypatch):
    from starlette.requests import Request

    import vp_security

    scope = {
        "type": "http",
        "headers": [(b"x-forwarded-for", b"203.0.113.9")],
        "client": ("10.0.0.5", 1234),
    }
    monkeypatch.delenv("TRUST_PROXY_HEADERS", raising=False)
    assert vp_security.client_ip(Request(scope)) == "10.0.0.5"
    monkeypatch.setenv("TRUST_PROXY_HEADERS", "true")
    assert vp_security.client_ip(Request(scope)) == "203.0.113.9"
