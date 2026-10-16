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
    # plow-agents deploy takes image@sha256:<digest>, exe:<slug> or --local; a tag dies
    # with "deploy needs image@sha256:<64 hex>, exe:<slug>, or --local". exe:zoen is the
    # admitted 1-click image.
    assert 'IMAGE="${ZOEN_IMAGE:-exe:zoen}"' in text
    assert "all-in-one:v1" not in text.split("IMAGE=", 1)[1].split("\n", 1)[0]
    _, _, after = text.partition('[ "$LOCAL" = 1 ]')
    # The top-level else sits at column 0; nested ones (--fresh) are indented.
    then_part, _, else_part = after.partition("\nelse\n")
    else_part = else_part.partition("\nfi\n")[0]
    assert 'face.py" rename' in then_part
    assert "docker compose up" in then_part
    assert "plow mint" in then_part
    assert then_part.find('face.py" rename') < then_part.find("docker compose up")
    assert 'deploy "$IMAGE"' in else_part
    assert "plow mint" not in else_part
    assert "docker compose up" not in else_part


def test_install_pins_the_plow_agents_cli_by_commit():
    text = (ROOT / "install.sh").read_text()
    import re
    ref = re.search(r'RUNNER_REF="\$\{ZOEN_RUNNER_REF:-([0-9a-f]+)\}"', text)
    assert ref and len(ref.group(1)) == 40
    assert 'fetch -q --depth 1 "$RUNNER" "$RUNNER_REF"' in text
    assert "git clone --depth 1 \"$RUNNER\"" not in text


def test_user_facing_scripts_speak_english():
    for name in ("install.sh", "bin/plow-agents", ".env.example", "scripts/publish-stories.sh"):
        text = (ROOT / name).read_text()
        for word in ("baixando", "ligando", "não", "Pronto", "Opcionais", "ausente"):
            assert word not in text, (name, word)


if __name__ == "__main__":
    test_issues_splits_owner_and_repo()
    test_lens_strips_the_secret_fragment_from_a_view_url()
    test_watch_skips_unconfigured_sources()
    test_install_cloud_default_deploys_the_public_digest()
    print("ok")
