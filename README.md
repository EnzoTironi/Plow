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
- **"i have a meeting in an hour."** who's coming. what they're working on.
  what you need to know. walk in ready.
- **"what should i make next?"** find what people care about. turn it into
  something worth sharing.
- **"who needs what i'm building?"** find the right companies and people.
  bring you a list worth talking to.
- **"this app should exist."** oh, we're doing this. from the first idea
  to something you can actually use.

## one conversation. a little less on your plate.

your notes. your work. the things you already use.
bring them along. tell me what you need.

you don't have to keep every detail in your head.
i'll take it from here.

less to juggle. more life.

## Start

One tap.

1. Open [https://aiworthusing.com/agent-index/zoen](https://aiworthusing.com/agent-index/zoen)
2. Tap **[Text this agent](sms:+16282463032?&body=Set%20this%20up%20for%20me%3A%20aiworthusing.com%2Fagent-index%2Fzoen)**
3. Send the SMS to +1 628 246-3032:
   `Set this up for me: aiworthusing.com/agent-index/zoen`

Then text Zoen.

Need the Mac later? The only app is [Latch](https://plow.co/latch).
Zoen asks. You tap yes.

[That's it.](docs/INSTALL.md) · [Share it.](docs/SHARE.md)

### Power users

```sh
curl -fsSL https://raw.githubusercontent.com/EnzoTironi/Plow/main/install.sh | sh
```

MIT. Built on [Plow](https://plow.co). Want to help? Open a pull request. `main` stays protected.

## Working on Zoen

The voice stays the same. Reception acknowledges an owner's message burst
independently of the main agent's response. `zoen_connections` manages native
Hermes OAuth and public MCP connections in the owner's iMessage DM. The callback
relay supports cloud sign-in without opening ports or changing Plow infrastructure.

See [implementation and validation](docs/RUNTIME.md) for the five-second target,
current connector limits, checks and rollout procedure. These changes need a new
image on an existing installation; changing this checkout does not update live agents.
