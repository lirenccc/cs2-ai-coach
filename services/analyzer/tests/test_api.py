from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


TOKEN = "0123456789abcdef"


def client_for(tmp_path: Path) -> TestClient:
    settings = Settings(
        analyzer_host="127.0.0.1",
        analyzer_port=8765,
        session_token=TOKEN,
        db_path=tmp_path / "api.db",
        extract_root=tmp_path / "extracted",
    )
    return TestClient(create_app(settings))


def auth():
    return {"x-cs2-coach-token": TOKEN}


def test_health_requires_token(tmp_path: Path):
    with client_for(tmp_path) as client:
        assert client.get("/v1/health").status_code == 401
        assert client.get(
            "/v1/health",
            headers={"x-cs2-coach-token": "wrong-token"},
        ).status_code == 401

        response = client.get("/v1/health", headers=auth())
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["version"] == "0.1.0"
        assert body["parser"]["name"] == "composite"
        assert "available" in body["parser"]
        assert "version" in body["parser"]


def test_shutdown_requires_token_and_invokes_callback(tmp_path: Path):
    called: list[bool] = []

    settings = Settings(
        analyzer_host="127.0.0.1",
        analyzer_port=8765,
        session_token=TOKEN,
        db_path=tmp_path / "api.db",
        extract_root=tmp_path / "extracted",
    )
    app = create_app(settings, on_shutdown_request=lambda: called.append(True))
    with TestClient(app) as client:
        assert client.post("/v1/shutdown").status_code == 401
        response = client.post("/v1/shutdown", headers=auth())
        assert response.status_code == 200
        assert response.json()["status"] == "shutting_down"

    assert called == [True]


def test_import_demo_and_dedupe(tmp_path: Path):
    demo = tmp_path / "比赛.dem"
    demo.write_bytes(b"fixture")

    with client_for(tmp_path) as client:
        first = client.post(
            "/v1/demos/import",
            headers=auth(),
            json={"path": str(demo)},
        )
        second = client.post(
            "/v1/demos/import",
            headers=auth(),
            json={"path": str(demo)},
        )

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    body = first.json()
    assert body["deduplicated"] is False
    assert second.json()["deduplicated"] is True
    assert body["demo_id"] == second.json()["demo_id"]
    assert "match_id" in body
    assert body["parse_status"] in {"completed", "failed"}


def test_import_rejects_non_demo(tmp_path: Path):
    path = tmp_path / "not-demo.txt"
    path.write_bytes(b"x")

    with client_for(tmp_path) as client:
        response = client.post(
            "/v1/demos/import",
            headers=auth(),
            json={"path": str(path)},
        )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "DEMO_INVALID"


def test_import_accepts_zip_with_dem(tmp_path: Path):
    import zipfile

    payload = b"zip-import-fixture"
    zip_path = tmp_path / "9208210907649202700_0.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("9208210907649202700_0.dem", payload)

    with client_for(tmp_path) as client:
        response = client.post(
            "/v1/demos/import",
            headers=auth(),
            json={"path": str(zip_path)},
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["deduplicated"] is False
    assert body["original_path"].endswith(".zip")
    assert len(body["sha256"]) == 64
    assert body["match_id"]
    assert body["parse_status"] in {"completed", "failed"}
