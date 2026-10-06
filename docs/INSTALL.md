# Zoen

A little monster. Your personal agent over iMessage.

## One click

1. Open https://aiworthusing.com/agent-index/zoen
2. Tap **Text this agent**
3. It opens an SMS to +1 628 246-3032:
   `Set this up for me: aiworthusing.com/agent-index/zoen`

[Text this agent](sms:+16282463032?&body=Set%20this%20up%20for%20me%3A%20aiworthusing.com%2Fagent-index%2Fzoen)

Open the page. Tap **Text this agent**. Send it.

Plow starts Zoen. Then text what you want.

**iPhone.** That's the office.

**Mac + Latch.** The only Mac app: https://plow.co/latch
Zoen asks. You tap yes. It drives the machine.

Share: [SHARE.md](SHARE.md)
The Index page is the link: https://aiworthusing.com/agent-index/zoen

## Power users

Already cloned? `./install.sh`

```sh
curl -fsSL https://raw.githubusercontent.com/EnzoTironi/Plow/main/install.sh | sh
```

Starts the same `:v1` that Text this agent deploys.

Leave: `./bin/plow-agents lines` and `./bin/plow-agents revoke ln_…`

Local Docker, with Docker open: `./install.sh --local`.
That keeps memory, sessions and WhatsApp. `./install.sh --local --fresh` erases the home.

To test this checkout's changes and prepare an update, see
[runtime and validation](RUNTIME.md). The public installer uses the published image;
it does not automatically update an existing instance with this checkout's code.
