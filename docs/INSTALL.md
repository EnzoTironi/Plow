# Install Zoen

A little monster. Your personal agent over iMessage.

## One tap (recommended)

1. Open https://aiworthusing.com/agent-index/zoen
2. Tap **Text this agent**
3. Your phone opens an SMS to +1 628 246-3032:
   `Set this up for me: aiworthusing.com/agent-index/zoen`

[Text this agent](sms:+16282463032?&body=Set%20this%20up%20for%20me%3A%20aiworthusing.com%2Fagent-index%2Fzoen)

Plow starts your own Zoen on its own line. Text it what you want.

- **iPhone.** That's the office.
- **Mac + Latch (optional).** The only Mac app is https://plow.co/latch. Zoen
  asks, you tap yes in Latch, and it drives the machine.

Share: [SHARE.md](SHARE.md). The Index page is the link:
https://aiworthusing.com/agent-index/zoen

## Scripted

The same install, from a terminal. With no flag it asks Plow for the cloud
image that "Text this agent" boots (`exe:zoen`); `--local` builds this checkout
in Docker instead.

```sh
curl -fsSL https://raw.githubusercontent.com/EnzoTironi/Plow/main/install.sh | sh
./install.sh --local          # memory, sessions and WhatsApp stay in a Docker volume
./install.sh --local --fresh  # same, but erases that volume first
```

The script fetches the official `plow-agents` CLI at a pinned commit
(`ZOEN_RUNNER_REF`), signs you in by text, picks a free line, then deploys.

## Run it yourself

### Prerequisites

| Need | Check |
|---|---|
| Docker Desktop or Engine, running, Compose ≥ 2.24 | `docker info` and `docker compose version` |
| Python 3.11+ (for `plow-agents`) | `python3 --version` |
| `plow-agents`, at the commit `install.sh` pins | `./bin/plow-agents --help` |
| A Plow account with a free line | `./bin/plow-agents lines` shows `free` |

### Steps

```sh
git clone https://github.com/EnzoTironi/Plow.git && cd Plow
./bin/plow-agents login            # text the code it prints, once per account
./bin/plow-agents lines            # pick a line marked free
./bin/plow-agents mint ln_xxx      # writes ./plow-credentials (0600, git-ignored)
docker compose up --build -d
docker compose logs -f agent
```

Wait for `plow-init: configured from … as cht_…`. Until the owner texts, the log
says `plow-init: waiting for a home chat on ln_…`, which is normal.

Then text the line's number from the phone you signed in with. Within about ten
seconds you get the onboarding bubbles and both contact cards, then Zoen
answers your message.

### Acceptance

- [ ] One onboarding burst, not two.
- [ ] Zoen answers in the language you wrote in.
- [ ] Ask for something that needs the web ("find somewhere good for saturday"):
      one short progress bubble, then a result with a link or picture.
- [ ] Ask it to send an email from your Gmail: the chat shows an approval ask,
      and nothing is sent until you reply `/approve`.

## Verify

```sh
docker compose exec agent head -3 /var/lib/hermes/SOUL.md       # "# Zoen on Plow"
docker compose exec agent grep -c "You are \*\*Zoen\*\*" /var/lib/hermes/SOUL.md   # 1
docker compose exec agent /opt/hermes/.venv/bin/python -c "import yaml; print(yaml.safe_load(open('/var/lib/hermes/config.yaml'))['approvals'])"  # {'mode': 'off'}
docker compose exec agent sh -c 'test -z "$HERMES_YOLO_MODE" && echo no-yolo'
docker compose exec --user hermes agent /opt/hermes/bin/hermes cron list   # zoen-floor, "Monitor: zoen-floor-monitor.py"
```

Usage reporting is the base image's `agent-index` service; it registers once and
reports every five minutes. Its log lines start with `agent-index:`.

## Update

- **Cloud.** A new image reaches new installs once it is promoted
  (`plow-agents image push … --promote zoen`). Running agents keep their image
  until they are updated through Plow.
- **Local.** `git pull && docker compose up --build -d`. Memory, sessions and
  WhatsApp stay in the volume. Never `down -v` to upgrade.
- An open conversation keeps the prompt it started with until it resets; a new
  conversation picks up a new persona.

## Uninstall

```sh
docker compose down                 # stop; keep the volume
docker compose down -v              # stop and erase memory, sessions, WhatsApp
./bin/plow-agents lines
./bin/plow-agents revoke ln_xxx     # retire this agent's credential and free the line
```

## Troubleshooting

| You see | Do |
|---|---|
| `plow-init: waiting for a home chat on ln_…` | Text the line from the owner's phone. |
| `… -- parking; no gateway will start` | The reason is on the same line. A 401/403 right after a rotation clears within two minutes; a 404 means the agent was revoked. |
| `deploy needs image@sha256:<64 hex>, exe:<slug>, or --local` | `ZOEN_IMAGE` must be a digest (`plow-agents image push` prints it), or leave it unset for `exe:zoen`. |
| `add plow-credentials to .dockerignore before building` | Keep the repo's `.dockerignore`; the credential never enters the image. |
| No reply, and Docker shows the container running | `docker compose logs agent | tail -50`; look for `plow-init` and `zoen-face` lines. |
| Zoen says your Mac is asleep | Open Latch on the Mac. Zoen retries next turn. |
| An approval ask never appeared | Check the image is from this branch or later (older images ran with `HERMES_YOLO_MODE`). |

## For developers

Tests, image checks and the base-bump steps are in the
[README](../README.md#development) and [runtime notes](RUNTIME.md).
