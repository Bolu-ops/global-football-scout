"""API integration tests against the live database (skipped when it is unreachable)."""

import pytest
from sqlalchemy import text

pytest.importorskip("fastapi")


@pytest.fixture(scope="module")
def client():
    from gfs_core.db import get_engine

    try:
        with get_engine().connect() as conn:
            conn.execute(text("select 1"))
    except Exception:  # noqa: BLE001
        pytest.skip("database not reachable")
    from fastapi.testclient import TestClient

    from backend.main import app

    return TestClient(app)


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_search_and_detail(client):
    r = client.get("/players", params={"q": "vinicius", "limit": 3})
    assert r.status_code == 200
    hits = r.json()
    if not hits:
        pytest.skip("no players loaded")
    pid = hits[0]["player_id"]
    detail = client.get(f"/players/{pid}").json()
    assert detail["player_id"] == pid and "data_quality" in detail
    assert detail["age"] is None and "Data unavailable" in (detail["age_note"] or "")


def test_stats_percentile_context(client):
    hits = client.get("/players", params={"q": "vinicius", "limit": 1}).json()
    if not hits:
        pytest.skip("no players loaded")
    stats = client.get(f"/players/{hits[0]['player_id']}/stats").json()
    assert stats["metrics"]
    for m in stats["metrics"]:
        if m["percentile"] is not None:
            assert m["percentile_pool"] and m["percentile_pool_n"] >= 30


def test_similarity_excludes_top_leagues_and_explains(client):
    hits = client.get("/players", params={"q": "vinicius", "limit": 1}).json()
    if not hits:
        pytest.skip("no players loaded")
    r = client.post(
        f"/players/{hits[0]['player_id']}/similarity", json={"min_minutes": 250, "limit": 5}
    )
    assert r.status_code == 200
    body = r.json()
    if body["target"] is None:
        pytest.skip(body["reason"])
    excluded = {e["competition_id"] for e in body["excluded_competitions"]}
    for h in body["results"]:
        assert h["competition_id"] not in excluded
        assert h["player_id"] != body["target"]["player_id"]
        assert 0 <= h["similarity"] <= 100 and 0 <= h["compatibility"] <= 1
        assert h["explanation"]["supporting"] is not None
        assert h["estimated_value_eur"] is None and "unavailable" in h["value_note"]
    ranks = [h["rank"] for h in body["results"]]
    assert ranks == sorted(ranks)


def test_transfer_value_is_honest_without_model(client):
    r = client.get("/players/1/transfer-value").json()
    assert r["estimated_value_eur"] is None and "Data unavailable" in r["status"]


def test_admin_and_model_info(client):
    stats = client.get("/admin/stats").json()
    assert stats["counts"]["metric_definitions"] == 79
    info = client.get("/model/info").json()
    assert info["transfer_value"]["status"].startswith(
        ("not trained", "active", "trained, not activated")
    )
    assert "exclusion_rule" in info and "limitations" in info


def test_natural_language_without_key(client, monkeypatch):
    from gfs_core.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    r = client.post("/scouting/natural-language", json={"query": "winger like Vinicius"})
    assert r.status_code in (503, 200)
    get_settings.cache_clear()


@pytest.fixture
def settings_env(monkeypatch):
    from gfs_core.config import get_settings

    def set_env(**values):
        for k, v in values.items():
            monkeypatch.setenv(k, v)
        get_settings.cache_clear()

    yield set_env
    get_settings.cache_clear()


def test_admin_routes_disabled_without_token(client, settings_env):
    settings_env(ADMIN_TOKEN="")
    assert client.get("/admin/identity-reviews").status_code == 503
    assert client.post("/admin/cache/clear").status_code == 503
    assert client.get("/admin/stats").status_code == 200  # read-only stats stay public


def test_admin_routes_require_matching_token(client, settings_env):
    settings_env(ADMIN_TOKEN="s3cret-test-token")
    assert client.get("/admin/identity-reviews").status_code == 401
    bad = {"X-Admin-Token": "wrong"}
    assert client.post("/admin/identity-reviews/1/approve", headers=bad).status_code == 401
    good = {"X-Admin-Token": "s3cret-test-token"}
    assert client.get("/admin/identity-reviews", headers=good).status_code == 200


def test_llm_budget_per_client_and_global(settings_env):
    import uuid

    from backend import cache
    from backend.security import llm_allowed

    if cache._client() is None:
        pytest.skip("redis not reachable")
    settings_env(LLM_HOURLY_LIMIT_PER_CLIENT="2", LLM_DAILY_LIMIT="1000000")
    ip = f"test-{uuid.uuid4()}"
    assert [llm_allowed(ip) for _ in range(3)] == [True, True, False]
    assert llm_allowed(f"test-{uuid.uuid4()}")  # another visitor has their own budget
    settings_env(LLM_HOURLY_LIMIT_PER_CLIENT="100", LLM_DAILY_LIMIT="0")
    assert not llm_allowed(f"test-{uuid.uuid4()}")  # global daily cap applies to everyone
