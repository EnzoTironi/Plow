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

Start with what you need. These are things to ask for, using the accounts you
connect and the tools available for the task:

- **"help me get this week under control."** Turn scattered notes into a plan,
  keep useful details, and set reminders.
- **"find a good spot for saturday."** Compare places and reviews. Bring back a
  shortlist with the details that matter to you.
- **"catch me up before this meeting."** Research the company, recent news,
  and the notes in your connected workspace.
- **"what should i make next?"** Explore search demand, social trends, and
  audience comments. Turn the findings into a content brief.
- **"find the right customers for this."** Research companies and business
  contacts. Prepare a lead list and outreach drafts for you to review.
- **"i have an idea for an app."** Build it, test it, and bring back a working
  result with pictures or video.

## your apps, connected.

Ask to connect a service in your private iMessage conversation. Open the sign-in
link, choose what Zoen can access, and come back to the same chat.

The native Hermes catalog includes services such as Notion, Todoist, Linear,
and Canva. [Treg](https://treg.to/use-cases) adds access to **thousands of API
tools** for research, search, social trends, business data, and creative work.
Zoen finds the tool for the job as you need it.

Connectors use your account and the permissions you grant. Treg's paid calls use
your Treg balance; Zoen asks for a budget before spending it. Thousands refers to
API tools in Treg's catalog, spread across dozens of providers. Availability and
account requirements vary by tool. See the [integration catalog](docs/INTEGRATIONS.md)
for supported services and what we have validated.

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
