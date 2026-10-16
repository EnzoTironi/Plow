<p align="center">
  <video src="docs/zoen-launch.mp4" width="900" autoplay muted loop playsinline controls>
    <a href="docs/zoen-launch.mp4">Zoen</a>
  </video>
</p>

<h1 align="center">Zoen</h1>

<p align="center"><strong>big dreams. everyday problems. one little monster.</strong></p>

<p align="center">life happens. text zoen.</p>

i'm zoen. your little monster in iMessage.

the week that needs a plan. the place you need to find.
the idea that won't leave you alone. the work that keeps following you home.

text me. let's get it done.

## your life. your work. your zoen.

the thing you keep putting off? start there.

- **"my week is a mess."** let's turn the pile into a plan. and keep the
  important things from slipping through.
- **"find us somewhere good for saturday."** the place, the reviews, the
  shortlist. you bring your people.
- **"which one should i buy?"** compare the details, the price, and what
  people actually say. fewer tabs. a clearer choice.
- **"i don't have an hour for this video."** send the link. let's get to
  the useful part.
- **"help me find my next job."** find the openings. get to know the
  companies. figure out where you'd like to be.
- **"i have a meeting in an hour."** who's coming. what they're working on.
  what you need to know. walk in ready.
- **"this needs to stop living in my head."** send the notes. let's turn
  them into next steps you can follow.
- **"what should i make next?"** find what people care about. turn it into
  something worth sharing.
- **"who needs what i'm building?"** find the right companies and people.
  bring you a list worth talking to.
- **"what are people really saying?"** the questions. the complaints.
  the things worth fixing. let's look closer.
- **"what are my competitors trying?"** look at the ads. spot the patterns.
  find your own angle.
- **"find creators who fit our brand."** a shortlist with a reason behind
  every name.
- **"this app should exist."** oh, we're doing this. from the first idea
  to something you can actually use.

## one conversation. a little less on your plate.

your email. your calendar. your notes. your tasks.
bring them into the conversation. tell me what you need.

you choose what to connect. if something costs money, we agree on it first.

you don't have to keep every detail in your head.
i'll take it from here.

less to juggle. more life.

## what it will and won't do

- it works on its own: research, plans, drafts, code, pull requests, pictures
  and video of the result. it does not wait for a yes to start.
- anything hard to undo waits for you: email sent from your gmail, money,
  production, deletes, installs or logins on your mac. the ask shows up in the
  chat. reply `/approve` or `/deny`.
- it never sends as you without that yes, and never signs your messages as a bot.
- your mac is optional. without it, zoen works from its own cloud machine.
- in a group it stays quiet until someone says its name.

## Start

One tap.

1. Open [https://aiworthusing.com/agent-index/zoen](https://aiworthusing.com/agent-index/zoen)
2. Tap **[Text this agent](sms:+16282463032?&body=Set%20this%20up%20for%20me%3A%20aiworthusing.com%2Fagent-index%2Fzoen)**
3. Send the SMS to +1 628 246-3032:
   `Set this up for me: aiworthusing.com/agent-index/zoen`

Then text Zoen. Plow starts your own copy on its own line.

Need the Mac later? The only app is [Latch](https://plow.co/latch).
Zoen asks. You tap yes.

[Full install guide](docs/INSTALL.md) · [Share it](docs/SHARE.md)

## Run it yourself

With Docker running and [plow-agents](https://github.com/plow-pbc/plow-agents):

```sh
plow-agents login           # once per Plow account
plow-agents lines           # pick a line marked free
plow-agents mint ln_xxx     # writes ./plow-credentials (never commit it)
docker compose up --build -d
docker compose logs -f agent   # wait for "plow-init: configured from … as cht_…"
```

Then text the line's number. `./install.sh --local` does the same steps for you
(login, a free line, mint, build). `docker compose down` keeps memory, sessions and
WhatsApp; `down -v` erases them.

## Deploy

The 1-click path runs the public image named in `plow-agents.toml`
(`ghcr.io/enzotironi/zoen/all-in-one:v1`). To ship a change:

```sh
plow-agents image build ghcr.io/enzotironi/zoen/all-in-one:vN
plow-agents image push ghcr.io/enzotironi/zoen/all-in-one:vN --promote zoen
```

Keep the package public; Plow checks the manifest before it pins the digest.
Promoting changes what new installs boot. Running agents keep their image until
they are updated through Plow. See [Rollout](docs/RUNTIME.md#rollout).

## Your Mac

Optional. With [Latch](https://plow.co/latch) open on your Mac, Zoen lists the
Mac's own skills and drives its browser, files and apps after you tap yes in
Latch. Asleep or missing, Zoen says so once and keeps working from its cloud
machine.

## How it works

- **Base.** Zoen is a variant of Plow's official Hermes image
  (`plow-pbc/plow-hermes-agent`), pinned by tag and digest. Boot, identity,
  the Plow Chat plugin and the Agent Index usage reporter are inherited.
- **Identity.** Hermes reads one file: the base `SOUL.md` followed by
  [`runtime/persona.md`](runtime/persona.md). The image keeps the base file and
  adapts two passages ([`image/zoen-soul.py`](image/zoen-soul.py)): the name, and
  "never speak first". The build fails if the base rewords them.
- **Face.** The `zoen-face` plugin ([`image/plugins/zoen-face`](image/plugins/zoen-face))
  answers bursts fast (reception), keeps leftover model prose out of iMessage,
  renames the send tool to `zoen_imessage`, and adds `zoen_connections` (the
  connector catalog and OAuth) and a WhatsApp line.
- **Approvals.** Commands inside Zoen's own VM run without a prompt
  (`approvals.mode: off`). Plugin gates still ask in the chat, such as an email
  sent from your Gmail. Zoen never runs with `HERMES_YOLO_MODE`, and the agent
  user has no sudo.
- **Relay.** OAuth callbacks and WhatsApp go through a Cloudflare Worker
  ([`services/oauth-relay`](services/oauth-relay)), so no port opens on the agent.
- **Skills.** [`skills/zoen`](skills/zoen) is the talker; the other skills
  are leaves it reads. The engineering principle skills come from pstack (see NOTICE).

Details: [runtime and validation](docs/RUNTIME.md), [connectors](docs/CONNECTORS.md),
[Google auth](docs/GOOGLE_AUTH.md), [ADR 0001](docs/adr/0001-zoen-links-kapso-beside-plow-chat.md).

## Known limitations

- The prebuilt onboarding burst and the WhatsApp pairing bubbles are in
  Portuguese. Replies after that follow the owner's language.
- The five-second first-reply target is not consistently met: a cold boot waits
  for Plow's home-chat startup, and live tests saw provider delays (see
  [Validation](docs/RUNTIME.md#validation)).
- A local install (not the cloud one) authenticates to the WhatsApp relay with
  its own Plow bearer, so the relay can verify the agent. Cloud installs send a
  placeholder and prove continuity with a per-install secret instead.
- The image tests need Docker. CI runs them; the unit suite does not.
- Google sign-in is a beta app with an unverified-app warning
  ([status](docs/GOOGLE_AUTH.md)).

## Development

```sh
just test          # unit suite: offline, hermetic, ~7s
just relay-test    # the Cloudflare relay (Node 24)
just image         # build the image (Docker)
just image-test    # in-image checks against the built image (Docker)
```

Without `just`, the commands are in the [justfile](justfile). Tests never reach the
network (`tests/conftest.py` fails a test that tries) and compose the real
identity from the pinned base (`tests/test_persona.py`).

**Bump the Plow base.**

1. Pick the newest `base-<sha>` on the
   [registry](https://gallery.ecr.aws/e1h7x4a2/plow-cloud-agents) and read the
   base's commits since the current pin.
2. Update `FROM` with the tag and the multi-arch index digest.
3. Copy the base's `image/seed/SOUL.md` at that sha to `tests/fixtures/base-SOUL.md`
   and update `BASE_SHA` and `BASE_SOUL_SHA256` in `tests/test_persona.py`.
4. `just test`. If `zoen-soul.py` refuses the new base, read the base's new
   wording and update `OVERRIDES`.
5. If the plugin pin moved, check every adapter attribute `zoen-face` reads
   still exists, then `just image image-test`.

Reviewers: [REVIEW.md](REVIEW.md). Release checks on a real line:
[checks/manual-scenarios.md](checks/manual-scenarios.md). Agent Index copy:
[docs/agent-index/listing.md](docs/agent-index/listing.md).

## License

MIT. Built on [Plow](https://plow.co). Third-party notices: [NOTICE](NOTICE).
Want to help? Open a pull request. `main` stays protected.
