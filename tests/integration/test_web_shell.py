from pathlib import Path

WEB_ROOT = Path(__file__).parents[2] / "apps" / "web"


def test_mobile_web_shell_contains_gateway_views_and_pwa_assets() -> None:
    index = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    app = (WEB_ROOT / "app.js").read_text(encoding="utf-8")

    assert '<link rel="manifest" href="manifest.webmanifest" />' in index
    for view in ("chat", "runs", "approvals", "artifacts", "system"):
        assert f"view-{view}" in index
    for route in (
        "/api/v1/chat",
        "/api/v1/runs",
        "/api/v1/approvals",
        "/api/v1/artifacts",
        '"pause"',
        '"steer"',
        '"cancel"',
    ):
        assert route in app
    assert (WEB_ROOT / "service-worker.js").exists()
    assert (WEB_ROOT / "icon.svg").exists()
