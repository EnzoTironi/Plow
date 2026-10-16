# Zoen: plow-pattern-upgrade

Branch `plow-pattern-upgrade`, from `main` at `d3742ad`. Measured against
`~/Downloads/enzo-agents/PLOW-PATTERN.md`. Nothing was pushed, published or
sent; images and Index entries are untouched.

## Summary

- **`main` was red; it's green now.** It had 5 failing tests out of 244: one real bug (the GLM Flash fallback for Luna was never written to a fresh config) and four tests left behind by intended changes. Now 284 tests pass, and none can reach the network.
- **Owner approvals are real again.** `HERMES_YOLO_MODE=1` approved every gate, including the Plow plugin's approval for email sent from the owner's Gmail. It was a workaround for Zoen's quiet layer dropping the `/approve` prompt. Now:
  - the prompt reaches iMessage and WhatsApp;
  - commands inside Zoen's own VM stay prompt-free via `approvals.mode: off`;
  - YOLO and the agent's passwordless sudo are gone.
- **New Plow base, base persona inherited.** The base moves to `c692e80` (2026-10-12), which brings an email security fix, a Latch link fix and home-chat fixes. The image now keeps the base `SOUL.md` with two tested overrides instead of replacing it. The composed identity is 15,982 characters, down from 19,916, against Hermes' 20k truncation.
- **Idle installs stop burning tokens.** The floor cron used to wake the model 12 times a day on every install, owner or no owner. It now wakes only while the owner has written in the last 72 hours.
- **Fixes:**
  - the `install.sh` cloud path was broken: `plow-agents` refuses a tag;
  - `plow-agents` was fetched from a moving branch;
  - a relay ping carried the real Plow bearer;
  - the root pairing step could chmod a symlink target to 0666.
- **Docs.**
  - New or rewritten: README in the Plow order, an English INSTALL, `REVIEW.md`, a real-line checklist, a `justfile`, pinned CI, a listing draft, and a persona migration map.

## Changes by area

| Area | Change | Test |
|---|---|---|
| Config | `enable-zoen-face.py` runs both edits: the Luna→GLM Flash pin was skipped whenever the plugin was just listed. | `test_luna_falls_through_to_glm_flash` |
| Tests | Stale tests updated to the behavior Enzo shipped (d3c8a85, f8bcde3, 1b96a66). `tests/conftest.py` fails any test that opens a non-loopback connection, even when the code swallows the error. | conftest; the old WhatsApp test called the live relay |
| Base | `FROM base-c692e80@sha256:e04a373e…`. Same Hermes runtime (dbd0272) and plow-init entry point; every plugin symbol `zoen-face` reads exists at the new plugin pin `7a5270e`. | `test_wiring`, `test_base_fixture_is_the_pinned_base` |
| Approvals | `quiet.py` and `whatsapp_line.py` pass messages marked `is_approval_prompt`. `approvals.mode: off` is written at boot. No YOLO. | `test_gateway_approval_prompt_*`, `test_shell_approvals_*`, `test_the_image_never_sets_yolo` |
| Root | The sudoers grant for `hermes` is removed. Nothing in the repo used it. | `test_the_agent_user_has_no_root` |
| Supply chain | `gh` is verified by sha256 before unpacking. `plow-agents` is fetched at commit `53dd922`. CI actions are pinned by commit. | `test_gh_is_checksummed_*`, `test_install_pins_*` |
| Identity | `image/zoen-soul.py` adapts the base `SOUL.md` at build time (identity header; "never speak first") and fails the build if the base rewords those passages. Zoen's rules move to `persona.md`, deduplicated. See [docs/persona-migration.md](docs/persona-migration.md). | `tests/test_persona.py`: size, Hermes' own injection scanner, base safety rules, overrides |
| Tools | Every `plow_*` and `zoen_*` name in a prompt or skill is a real tool, and every `SKILL.md` has routable frontmatter. | `tests/test_tool_names.py` |
| WhatsApp | The ping never carries a real bearer. State is handed to `hermes` as 0700/0600 instead of 0777/0666, and symlinks are never followed. Retries back off: 0.2s, then 2s, then 5s. | `test_relay_ping_*`, `test_shared_state_*`, `test_state_handoff_*`, `test_pairing_backs_off_*` |
| Floor cron | Hermes monitor mode with `floor_monitor.py`. `register_cron.py` installs the monitor and adds it to existing jobs in place. | `tests/test_floor_monitor.py`, `test_register_cron.py` |
| Install | `install.sh` deploys `exe:zoen` (the admitted 1-click image); its messages are in English. | `test_install_cloud_default_*`, `test_user_facing_scripts_speak_english` |
| Docs | README, INSTALL, REVIEW, `checks/manual-scenarios.md`, `justfile`, NOTICE, an ADR 0001 addendum, `docs/agent-index/listing.md`. | `test_stories_and_install_lead_with_one_click` |

## First principles: what we kept, what we changed, why

**The job.** You text what you want; it gets done. That covers research with receipts, plans, comparisons, and things built and shown. It acts in your accounts only after a yes. iMessage is the whole interface, and the Mac is optional.

### Kept

| What | Why |
|---|---|
| The voice | It's the product. |
| Fast reception | 98% install success, the best of any agent with 40+ attempts. |
| The free thread with work handed to a child | Answers stay fast while long work runs. |
| The connector catalog | It already does the job. |
| Memory | It already does the job. |
| The first-run ritual | It already does the job. |
| The WhatsApp line | No usage data says it is unused, and its relay has 39 passing tests. Its client side was hardened instead. |

### Changed

| Decision | Evidence |
|---|---|
| **YOLO + sudo is never right** for an agent that reads a stranger's email and web pages. YOLO turned off the one gate on email sent in the owner's name. Sudo let any turn rewrite the persona and the gates. | Pinned Hermes `tools/approval.py` (`_run_approval_gate` returns approved when YOLO is on). Gateway `_approval_notify_sync` sends the ask with `adapter.send`, which `quiet.py` dropped. |
| **The proactive loop must not cost an absent owner anything.** | Index usage for Zoen was flat across weekends: Luna 47–56M/day from Sep 27 to Oct 6. A fleet of 2-hour timers looks like this; 44 people don't. `zoen-floor` was `0 */2 * * *` with no gate. It now runs every 2h while the owner is around, and never after 72 quiet hours. |
| **Inherit, don't fork, the base persona.** Base fixes now reach Zoen. | Enzo's own ADR 0001 says "The base persona stays". The old file also dropped four base safety rules (see the migration map). |
| **The scripted install must work.** | `plow-agents` at `53dd922` dies on a tag. Checked by running it. |

### Proposed, not shipped

I couldn't verify these here. Full arguments: [docs/proposals.md](docs/proposals.md).

1. An opt-in daily brief, offered once after the first real result. The recurring job is what gives Meetly, Founder and Prucê their depth.
2. Fold the 23 `principle-*` skills into `floor`. They are 6,656 characters in every prompt, but existing homes need a pruning migration first.
3. Pick the onboarding burst's language from the first text (it is Portuguese today).
4. Local installs use the relay's uid+secret path instead of sending the real Plow bearer.

## Validation

### a. Plow pattern scorecard (PLOW-PATTERN.md §8)

| # | Item | Grade | Evidence |
|---|---|---|---|
| 1 | Base pinned by tag and digest, current; downloads pinned and checksummed | PASS | `Dockerfile` FROM, `GH_SHA256_*`, `install.sh` `RUNNER_REF`; `test_gh_is_checksummed_*` |
| 2 | Content-only variant; base inherited | PARTIAL | `SOUL.md` is inherited now (`test_persona.py`). Zoen still wraps plow-init (`plow-init-then-face.sh`) and patches the Plow adapter at runtime (`zoen-face`). That is its design, guarded by `catalog_image.py`. |
| 3 | `AGENT_ID`/`NAME`/`BLURB` (and trust) in the image | PASS | `ENV AGENT_ID=zoen`, `AGENT_NAME`, `AGENT_BLURB`; `test_usage_reporting_is_the_base_reporter`. Hermes has no `PLOW_THREAD_TRUST`; the plugin owns trust. |
| 4 | Identity first; base contract word for word, tested | PASS | `test_zoen_keeps_the_base_safety_rules`, `test_zoen_is_not_a_plow_assistant_and_never_speaks_first` |
| 5 | One skill per turn type; frontmatter tested | PARTIAL | Frontmatter: `test_every_skill_has_routable_frontmatter`. Turn types: owner/group/WhatsApp/cron are routed inside skill `zoen`, not split into separate skills. |
| 6 | Deterministic logic in scripts, atomic state, corrupt state throws | PARTIAL | `register_cron.py` raises on corrupt `jobs.json`; `memory.py`/`google_account.py` write atomically; `floor_monitor.py`. Scripts don't share one JSON/`error:` contract. |
| 7 | Untrusted text reaches scripts via files only | PARTIAL | `memory.py remember "<text>"` takes text on argv through the terminal tool. |
| 8 | Owner gates from runtime context; approvals bound to exact content | PASS | The plugin's Gmail gate keys `/approve` on sha256(argv) and now reaches the chat (`test_gateway_approval_prompt_*`). |
| 9 | Uncertain sends never resent; idempotency; bounded retries | PASS | `_Uncertain` is never retried; `idempotency_key` on chat open; `test_pairing_backs_off_*` |
| 10 | Latch: skills first, one install link, never pose as the Mac | PASS | `runtime/persona.md` `# Face`, `## Tools` |
| 11 | Offline hermetic tests and contract tests; CI runs them | PASS | `tests/conftest.py`, `test_persona.py`, `test_tool_names.py`; `.github/workflows/test.yml` |
| 12 | `checks/manual-scenarios.md` | PASS | [checks/manual-scenarios.md](checks/manual-scenarios.md) |
| 13 | README in order with known limitations; `REVIEW.md` | PASS | [README.md](README.md), [REVIEW.md](REVIEW.md) |
| 14 | No secrets or personal data; English; MIT | PARTIAL | MIT, English docs and scripts (`test_user_facing_scripts_speak_english`). Enzo's own WhatsApp number (`WHATSAPP_DOOR`) and contact card ship on purpose. `tests/test_zoen_face_quiet.py` `_home_chat` uses `+16503466610` and `+55 31 98888-7777`; confirm they are not real people. `docs/SHARE.md` keeps paired PT/EN pitches. |
| 15 | Listing complete and out of WIP | PASS | Live record: blessed and deployable 2026-10-07, 4 capabilities, 2 tools, `latch: optional`, video, 4 images, 9 stories. Story quality: see `docs/agent-index/listing.md`. |

**One line:** 1 PASS · 2 PARTIAL · 3 PASS · 4 PASS · 5 PARTIAL · 6 PARTIAL · 7 PARTIAL · 8 PASS · 9 PASS · 10 PASS · 11 PASS · 12 PASS · 13 PASS · 14 PARTIAL · 15 PASS (10 PASS, 5 PARTIAL, 0 FAIL).

### b. Agent Index publish requirements

Live record: `/v1/agent?agent_id=zoen&fresh=1`, read 2026-10-16.

| Requirement | Status | Enzo's action |
|---|---|---|
| MIT license | Met: `LICENSE` is MIT | None. |
| Working usage reporting | Wired in the image. `ENV AGENT_ID=zoen`; the base reporter fixes `HERMES_HOME=/var/lib/hermes`; Zoen ships no competing reporter (`test_usage_reporting_is_the_base_reporter`). **The Index has received nothing since 2026-10-07** (section e). | Run the checks in section e on a live install. |
| Blessed | Met: 2026-10-07T19:53:59Z | None. |
| Video | Met: YouTube `tRFsr7kEotI` | None. |
| At least one image | Met: 4 | None. |
| Deployable or `install_url` | Both: deployable 2026-10-07; `install_url` is `docs/INSTALL.md` on main | After merge, the URL serves the English guide. |
| Exactly 4 capabilities | Met | Optional wording edit in `docs/agent-index/listing.md`. |
| Tools | Met: Plow Chat, Plow Latch | Optional wording edit. |
| `latch` field | Met: `optional` | None. |
| Stories | 9 published, 7 of them second-person ad copy for the earlier software-factory pitch | Replace them with real first-person moments (drafts in `listing.md`, brackets to fill). |
| Promote the new image | Not done: running agents keep the old image | `plow-agents image push ghcr.io/enzotironi/zoen/all-in-one:vN --promote zoen` after the checks in section c. |

### c. Unverified, and how to verify

| Check | Why it did not run here | How | Expected |
|---|---|---|---|
| Docker build | No Docker on this Mac | `just image` | Build succeeds. The `zoen-soul.py` step passes. `sha256sum -c` passes for `gh` on amd64 and arm64. |
| Identity in the image | Needs the image | `just image-test` (last step) | `image-identity-ok` |
| `tests/integration_image.py` | Needs the image | `just image-test` | Exits 0. Reception, recipient guard, handoff. |
| `tests/tasks_image.py` | Needs the image | `just image-test` | Exits 0. Kanban recovery and cron migration. |
| `tests/catalog_image.py` | Needs the image | `just image-test` | Exits 0; seed `SOUL.md` starts `# Zoen`; `zoen_imessage` is visible; `plow_send_sequence` is not. |
| `tests/browser_image.py` | Needs the image | `just image-test` | Exits 0. |
| `tests/integration_google.py`, `integration_oauth.py` | Need the image and a local relay | The CI job `hermes-integration` (`wrangler dev` on 8791) | Exits 0. |
| `tests/integration_owner_profile.py` | Needs the image and a Plow fixture | `docker run … /workspace/tests/integration_owner_profile.py` | Exits 0. |
| `approvals.mode: off` on the pinned Hermes | Needs the gateway | On a live install, ask for `rm -rf /tmp/x`: no prompt. Ask for a Gmail send: a prompt. | Scenario 4 and 5 in `checks/manual-scenarios.md` |
| Floor monitor in the scheduler | Needs Hermes cron | `docker compose exec --user hermes agent /opt/hermes/bin/hermes cron list` | `Monitor: zoen-floor-monitor.py`; runs are `no_change` after 72 quiet hours. |
| Live line | No Plow line used here | `checks/manual-scenarios.md` 1–10 | Every box passes. |
| Latch on a real Mac | Rule: no Latch | Scenario 7 | Mac skills are listed; asleep is said once. |
| CI on GitHub | Not pushed | Open the PR | `unit`, `oauth-relay`, `hermes-integration` are all green. |

### d. Test inventory

| Suite | Command | main → branch |
|---|---|---|
| Python unit | `just test` | 244 collected, 239 pass, 5 fail → 284 collected, 284 pass |
| oauth-relay (Node 24) | `just relay-test` | 39 pass → 39 pass (the relay is unchanged) |
| Branch tests against `main`'s code | Copy `tests/` into a `main` worktree and run pytest | 30 fail and 2 modules don't import (their code isn't on `main`). Every behavior change is caught. |
| Network guard | Run the old WhatsApp test under `tests/conftest.py` | It fails, naming `zoen-oauth-relay.agenttironi.workers.dev`. |
| Static | `compile()` on every `.py`; `sh -n`; YAML/JSON/TOML parse | 63 Python files, 6 shell scripts, 5 YAML, 2 JSON, 1 TOML: all clean. |
| `plow-agents` CLI | Run `deploy` at `53dd922` with an empty home | A tag is refused; `exe:zoen` passes validation. |
| In-image and integration | `just image-test`, CI | Not run here (section c). |

### e. Usage gap since 2026-10-07 ([details](docs/usage-gap.md))

**Not a gap in the image.** A cloud 1-click install reports without compose: `ENV AGENT_ID=zoen`; the base reporter fixes
`HERMES_HOME=/var/lib/hermes`; there's no Zoen override; the bump changes neither (`test_usage_reporting_is_the_base_reporter`).
All 44 installs went silent the same day while other Hermes agents kept reporting, which points outside the repo:
installs stopped or reprovisioned, or no model calls at all. Check `plow-agents agents`, `agent-index:` log lines,
and `agent-index-client.py status`/`--dry-run` on one install, and ask Plow about 2026-10-07.

## Needs Enzo's decision

1. **Approvals.** Shell commands in Zoen's VM run without a prompt (`approvals.mode: off`), the same as before; email from the owner's Gmail now asks. The one-line revert would bring back YOLO, which I don't recommend.
2. **No sudo.** If a flow needs system packages, bake them into the image rather than restoring root.
3. **The floor gate's 72-hour window** (`ACTIVE_SECONDS` in `floor_monitor.py`).
4. **The four proposals above** (daily loop, principle-skill fold, onboarding language, relay auth).
5. **Stories and capability wording** in `docs/agent-index/listing.md`.
6. **Phone numbers in test fixtures** (scorecard item 14).
