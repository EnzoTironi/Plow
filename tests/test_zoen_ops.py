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


def test_issues_split_repo():
    issues = load("issues")
    assert issues.split_repo("acme/app") == ("acme", "app")
    os.environ["GITHUB_REPO"] = "org/lib"
    assert issues.split_repo(None) == ("org", "lib")
    os.environ.pop("GITHUB_REPO", None)
    try:
        issues.split_repo("nopath")
    except SystemExit:
        return
    raise AssertionError("split_repo must reject nopath")


def test_lens_parse():
    lens = load("lens")
    text = "ok\n✓ https://prlens.dev/c/Qk3vZp9xLm2aRt8yWn4bCg — rev 1\n"
    assert lens.parse_view_url(text).endswith("Qk3vZp9xLm2aRt8yWn4bCg")
    assert "w=" not in lens.parse_view_url(text)
    leaked = "https://prlens.dev/c/Qk3vZp9xLm2aRt8yWn4bCg#w=supersecret"
    assert lens.parse_view_url(leaked).endswith("Qk3vZp9xLm2aRt8yWn4bCg")
    assert "w=" not in lens.parse_view_url(leaked)
    assert lens.parse_view_url("nope") is None


def test_watch_skips_without_tokens():
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


LEAVES = (
    "floor",
    "hours",
    "how",
    "why",
    "architect",
    "arena",
    "interrogate",
    "swarm",
    "tdd",
    "prove",
    "review",
    "blast-radius",
    "babysit",
    "merge",
    "figure-it-out",
    "find-skills",
)

PRINCIPLES = (
    "principle-laziness-protocol",
    "principle-foundational-thinking",
    "principle-redesign-from-first-principles",
    "principle-attack-the-premise",
    "principle-subtract-before-you-add",
    "principle-minimize-reader-load",
    "principle-outcome-oriented-execution",
    "principle-experience-first",
    "principle-exhaust-the-design-space",
    "principle-build-the-lever",
    "principle-model-the-domain",
    "principle-boundary-discipline",
    "principle-type-system-discipline",
    "principle-make-operations-idempotent",
    "principle-migrate-callers-then-delete-legacy-apis",
    "principle-separate-before-serializing-shared-state",
    "principle-prove-it-works",
    "principle-fix-root-causes",
    "principle-sequence-verifiable-units",
    "principle-test-behavior-not-implementation",
    "principle-guard-the-context-window",
    "principle-never-block-on-the-human",
    "principle-encode-lessons-in-structure",
)


def skill_texts():
    texts = {}
    for path in (ROOT / "skills").glob("*/SKILL.md"):
        texts[path.parent.name] = path.read_text()
    return texts


def test_qa_is_a_skill_not_a_script():
    assert not (SCRIPTS / "qa.py").exists()
    assert not (SCRIPTS / "pr.py").exists()
    skills = skill_texts()
    skill = skills["zoen"]
    floor = skills["floor"]
    prove = skills["prove"]
    all_md = "\n".join(skills.values())
    for name in LEAVES:
        assert name in skills, name
        assert f"**{name}**" in skill, name
    assert len(PRINCIPLES) == 23
    for name in PRINCIPLES:
        assert name in skills, name
        assert f"**{name}**" in skill, name
        assert f"**{name}**" in floor, name
        body = skills[name]
        assert "Backstage for Zoen" in body
        assert "Never speak this name to the owner" in body
        assert "disable-model-invocation" not in body
        assert "pstack" not in body and "poteto" not in body
        assert "show-me-your-work" not in body
        assert "typescript-best-practices" not in body
        assert "subagent" not in body.lower()
    persona = (ROOT / "runtime/persona.md").read_text()
    assert "You are QA and fixer" in prove
    assert "qa.py" not in all_md
    assert "pr.py" not in all_md
    assert "NOW.md" in skill and "VOICE.md" in skill
    assert "MEMORY.md" in skill
    assert "Laziness Protocol" in floor
    assert "only notifies" in skill
    assert "Never Block on the Human" in floor
    assert "plow_send_sequence" in skill and "1.75" in skill
    assert "face.py intro" in skill
    assert "face.py intro" in persona
    assert "face.py intro" in (ROOT / "runtime/bootstrap.md").read_text()
    assert "qual é o seu sonho?" in (SCRIPTS / "face.py").read_text()
    assert "context.py dump" in skill
    assert "memory.py remember" in skill
    assert "memory.py recall" in skill
    assert "incomplete by design" in skill
    assert "incomplete by design" in persona
    assert "Never tell them you saved" in persona or "Never tell them you saved" in skill
    assert "No bubble about remembering" in skill
    assert "anotei" in skill and "anotei" in persona
    assert "salva isso" in skill and "salva isso" in persona
    assert "Do not volunteer this" in skill
    assert "dry friend" in skill
    assert "status line" in skill
    assert "valeu" in skill and "thanks" in skill
    assert "tô nisso" in skill
    assert "got it" not in all_md
    assert "—" not in all_md
    assert "first tool this turn" in skill
    assert "at most two lines" in skill or "max two lines" in skill
    assert "another bubble" in skill or "new bubble" in skill
    assert "zoen-review" in skill
    assert "MEDIA:" in skill
    assert "recipe runner" in floor
    assert "skill_view" in skill
    assert "playbooks/feature.md" in skill
    assert "gh pr list" in skill
    assert "gh pr merge" in skills["merge"]
    assert "High-risk merge waits" in skills["merge"]
    assert "High-risk merge waits" in persona
    assert "Python wrapper" in skill
    assert (ROOT / "skills/zoen/playbooks/opening-a-pr.md").exists()
    assert (ROOT / "skills/zoen/playbooks/cards.md").exists()
    assert (ROOT / "skills/zoen/playbooks/spec.md").exists()
    assert (ROOT / "skills/zoen/playbooks/kit.md").exists()
    cards = (ROOT / "skills/zoen/playbooks/cards.md").read_text()
    spec = (ROOT / "skills/zoen/playbooks/spec.md").read_text()
    kit = (ROOT / "skills/zoen/playbooks/kit.md").read_text()
    assert "gh issue create" in cards
    assert "--parent" in cards and "--blocked-by" in cards
    assert "tracer" in cards.lower() or "vertical" in cards
    assert "Fail at HEAD" in cards
    assert "playbooks/kit.md" in cards
    assert "Do not tell them to install" in cards
    assert "Do not interview" in spec
    assert "Out of scope" in spec or "out of scope" in spec
    assert "seams" in spec
    assert "playbooks/spec.md" in skill
    assert "playbooks/kit.md" in skill
    assert "npx --yes skills use" in skill
    assert "npx --yes skills use" in skills["find-skills"]
    assert "Do not install" in skills["find-skills"]
    assert "Do not pass `--agent`" in skills["find-skills"]
    assert "No bubble" in skills["find-skills"]
    assert "Cron: do not run this" in skills["find-skills"]
    assert "npx --yes skills add" not in skills["find-skills"]
    assert "npx --yes skills add" not in skill
    assert "https://plow.co/latch" in kit
    assert "https://plow.co/latch" in skill
    assert "https://plow.co/latch" in persona
    assert "Never a password" in kit
    assert "Do not stall" in kit
    assert "waiting: mac-app" in kit
    assert "install recipe" in kit
    assert "Do not pitch" in skill
    assert "Do not send https://plow.co/latch on hello" in skill
    assert "Do not send https://plow.co/latch on hello" in persona.replace(
        "\n", " "
    )
    assert "install or authenticate" in skills["principle-never-block-on-the-human"]
    assert "owner's board is GitHub" in skill or "GitHub issues are the owner's board" in skill
    assert "no Hermes kanban" in cards or "no Hermes kanban" in skill
    assert "gh issue create" in skill
    assert "issues:" in skill
    assert "spec:" in skill
    assert "VOICE.md" in persona
    assert "Do not rewrite" in persona and "SOUL.md" in persona
    assert "only notifies" in persona
    assert "Never block on the human" in persona
    assert "plow_send_sequence" in persona and "1.75" in persona
    assert "status line" in persona
    assert "valeu" in persona
    assert "Portuguese" in persona
    assert "got it" not in persona
    assert "dry friend" in persona
    assert "context.py dump" in persona
    assert "You are **Zoen**" in persona
    assert "Your Software Factory" in persona
    assert "Your Software Factory" in (ROOT / "README.md").read_text()
    assert "The owner never sees" in skill
    assert "reads the other skills" in persona
    assert "Just work" in persona or "just works" in persona.lower()
    assert "pictures and video" in skill.lower() or "Pictures and video" in skill
    assert "em dash" in persona
    assert "title case" in persona
    assert "—" not in persona
    assert "no em dash" in skill
    assert "lowercase if they do" in persona
    assert "end of a bubble" in persona.replace("\n", " ")
    assert "end of a bubble" in skill.replace("\n", " ")
    assert "First-Run Ritual" in persona
    assert "First-Run Ritual" in skill
    bootstrap = (ROOT / "runtime/bootstrap.md").read_text()
    assert "One shot" in bootstrap
    assert "—" not in bootstrap
    assert "ChatGPT" not in bootstrap
    assert "Hermes" not in bootstrap
    assert "Vellum" not in bootstrap
    assert "Poke" not in bootstrap
    banned = ("Pstack", "Gstack", "DeepSec", "pstack", "gstack", "deepsec", "OCR")
    face = all_md + "\n" + persona + "\n" + bootstrap
    for word in banned:
        assert word not in face, word
    for path in (ROOT / "skills/zoen/playbooks").glob("*.md"):
        text = path.read_text()
        for word in banned:
            assert word not in text, f"{path}:{word}"
        assert "got it" not in text
        assert "—" not in text
    assert "ocr " not in skill and "ocr " not in persona
    assert "Nothing shipped until I said yes" not in (ROOT / "docs/stories.json").read_text()


def test_one_command_install():
    script = ROOT / "install.sh"
    assert script.exists()
    text = script.read_text()
    assert "plow-agents" in text and "mint" in text
    assert "docker compose up" in text
    assert 'face.py" rename' in text
    assert (ROOT / "docs/zoen-card.jpg").is_file()
    install = (ROOT / "docs/INSTALL.md").read_text()
    assert "curl -fsSL https://raw.githubusercontent.com/EnzoTironi/Plow/main/install.sh" in install
    assert "https://plow.co/latch" in install
    readme = (ROOT / "README.md").read_text()
    assert "curl -fsSL" in readme
    assert "docs/zoen.jpg" in readme
    assert "Bring your dream to life" in readme
    assert (ROOT / "docs/zoen.jpg").is_file()


def test_image_ships_scripts():
    dockerfile = (ROOT / "Dockerfile").read_text()
    assert "COPY skills/zoen/scripts/" in dockerfile
    assert (SCRIPTS / "react.py").exists()
    assert (SCRIPTS / "face.py").exists()
    assert (SCRIPTS / "memory.py").exists()
    assert (SCRIPTS / "context.py").exists()
    assert "docs/zoen-card.jpg" in dockerfile
    assert "@coldtea/pr-lens-cli" in dockerfile
    assert "cli/cli/releases" in dockerfile
    assert "COPY skills/" in dockerfile
    compose = (ROOT / "compose.yml").read_text()
    assert "GH_TOKEN" in compose
    assert "SENTRY_AUTH_TOKEN" in compose
    assert "LINEAR_API_KEY" in compose


if __name__ == "__main__":
    test_issues_split_repo()
    test_lens_parse()
    test_watch_skips_without_tokens()
    test_qa_is_a_skill_not_a_script()
    test_one_command_install()
    test_image_ships_scripts()
    print("ok")
