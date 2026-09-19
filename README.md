<p align="center">
  <video src="docs/zoen-launch.mp4" width="900" autoplay muted loop playsinline controls>
    <a href="docs/zoen-launch.mp4">Zoen</a>
  </video>
</p>

<h1 align="center">Zoen</h1>

<p align="center"><strong>Bring your dreams to life.</strong></p>

<p align="center">Your personal agent, over iMessage.</p>

You already know what you want.
You text it.

Research, documents, plans, reminders, connected accounts, or software.
Zoen follows through and brings the result back to your phone.
For software, the review still comes with pictures and video.

No dashboard. No ticket. No waiting room.
A little monster who makes the thing.

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

The voice stays the same. Reception now acknowledges an owner's message burst
independently of model and attachment latency. Google/Slack connection lifecycle
is available through `zoen_connections` in the owner's iMessage DM; consent stays
with Plow and the provider. No separate Zoen website is required.

See [implementation and validation](docs/RUNTIME.md) for the five-second target,
current connector limits, checks and rollout procedure. These changes need a new
image on an existing installation; changing this checkout does not update live agents.
