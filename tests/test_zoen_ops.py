#!/usr/bin/env python3
"""Run: python3 tests/test_zoen_ops.py"""
import importlib.util
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills/zoen/scripts"


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_issues_splits_owner_and_repo():
    issues = load("issues")
    assert issues.split_repo("acme/app") == ("acme", "app")
    os.environ["GITHUB_REPO"] = "org/lib"
    try:
        assert issues.split_repo(None) == ("org", "lib")
    finally:
        os.environ.pop("GITHUB_REPO", None)
    try:
        issues.split_repo("nopath")
    except SystemExit:
        return
    raise AssertionError("split_repo must reject nopath")


def test_lens_strips_the_secret_fragment_from_a_view_url():
    lens = load("lens")
    text = "ok\n✓ https://prlens.dev/c/Qk3vZp9xLm2aRt8yWn4bCg — rev 1\n"
    assert lens.parse_view_url(text).endswith("Qk3vZp9xLm2aRt8yWn4bCg")
    assert "w=" not in lens.parse_view_url(text)
    leaked = "https://prlens.dev/c/Qk3vZp9xLm2aRt8yWn4bCg#w=supersecret"
    assert lens.parse_view_url(leaked).endswith("Qk3vZp9xLm2aRt8yWn4bCg")
    assert "w=" not in lens.parse_view_url(leaked)
    assert lens.parse_view_url("nope") is None


def test_watch_skips_unconfigured_sources():
    watch = load("watch")
    saved = {
        key: os.environ.pop(key)
        for key in list(os.environ)
        if key.startswith(("SENTRY", "POSTHOG", "CLOUDFLARE", "VERCEL"))
    }
    try:
        snap = watch.snapshot()
        assert snap["configured"] == []
        assert set(snap["skipped"]) == {"sentry", "posthog", "cloudflare", "vercel"}
        assert snap["alerts"] == []
    finally:
        os.environ.update(saved)


def test_install_cloud_default_deploys_the_public_digest():
    text = (ROOT / "install.sh").read_text()
    toml = (ROOT / "plow-agents.toml").read_text()
    assert 'image = "ghcr.io/enzotironi/zoen/all-in-one:v1"' in toml
    assert (
        "ghcr.io/enzotironi/zoen/all-in-one@sha256:"
        "78c01798f5f43d40a69f8dd06c84448e78ba861e6764f8d7e2999ef8f7bb1cca"
    ) in text
    _, _, after = text.partition('[ "$LOCAL" = 1 ]')
    then_part, _, else_part = after.partition("else")
    assert 'face.py" rename' in then_part
    assert "docker compose up" in then_part
    assert "plow mint" in then_part
    assert then_part.find('face.py" rename') < then_part.find("docker compose up")
    assert 'deploy "$IMAGE"' in else_part
    assert "plow mint" not in else_part
    assert "docker compose up" not in else_part


if __name__ == "__main__":
    test_issues_splits_owner_and_repo()
    test_lens_strips_the_secret_fragment_from_a_view_url()
    test_watch_skips_unconfigured_sources()
    test_install_cloud_default_deploys_the_public_digest()
    print("ok")
