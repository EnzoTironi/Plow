# Zoen listing: proposed edits (DRAFT for Enzo)

Live record read 2026-10-16 from
`https://agent-index-server.vercel.app/v1/agent?agent_id=zoen&fresh=1`.
Nothing here is published; Enzo edits and publishes it with the
agent-index client (`--does`, `--story`, `--tags`).

## What is already right

| Field | Live value | Status |
|---|---|---|
| `agent_id` / name | `zoen` / Zoen | Keep. |
| Blessed / deployable | 2026-10-07 / 2026-10-07 | Out of WIP. |
| `install_url` | `…/Plow/blob/main/docs/INSTALL.md` | Keep (the guide is now English-only). |
| `latch` | `optional` | Correct: Zoen works without a Mac. |
| Video | YouTube `tRFsr7kEotI` | Keep. |
| Images | 4 illustrations from `docs/agent-index/` | Keep. |
| Capabilities | exactly 4 | Keep the count; see the wording below. |
| Tools | Plow Chat, Plow Latch | Keep; see the wording below. |
| Install success | 44 of 45 (98%) | See the usage note in CHANGES.md before quoting it. |

## Blurb

Unchanged:

> life happens. text zoen. plan your week. find a great place. compare before
> you buy. walk into the meeting ready. find your next customer. turn an idea
> into something real. your apps and thousands of tools, in one conversation.
> big dreams. everyday problems. one little monster.

## Capabilities (exactly four)

The live four are good. One edit makes the safety behavior visible, since it
is now enforced:

1. Turn a messy week into a plan: keeps the important things from slipping
2. Find a good place to go: the place, the reviews, a shortlist
3. Compare before you buy: details, price and what people actually say
4. Act in your accounts after a yes: email from your gmail waits for /approve

`--does` takes `Title: detail`, so the fourth one is:
`--does 'Act in your accounts after a yes: email from your gmail waits for /approve'`.
Swap it back to "Walk into a meeting ready" if the safety line belongs in a
story instead.

## Tools

- **Plow Chat:** "Text it from iMessage, like a friend who gets things done.
  WhatsApp too, after one tap." (only if WhatsApp pairing is meant to be public)
- **Plow Latch:** "Optional: works on your Mac when a job needs it, after you
  tap yes." (unchanged)

## Stories

Keep `horses-in-sf` (it has real screenshots) and
`your-apps-in-the-conversation` (a recorded validation).

The other seven are second-person ad copy for the earlier software-factory
pitch ("You texted a dream", "Don't read the code. Watch the product."). The
Index rewards what Rundown's stories do: first person, one specific moment, a
number or a time, and what the agent did *not* do. Replace them with real
moments. The drafts below describe behavior the code on this branch supports.
Every `[bracket]` is something only Enzo can fill from a real conversation;
do not publish a draft with a bracket left in it.

### 1. It answered the whole burst, not the first line

Tags: `imessage`, `Setup & first run`

> I sent three texts in a row at [time]: [what they said]. It didn't answer
> the first one and then the second. One bubble came back [N] seconds later,
> about all three, and then it went quiet and did the work. The result landed
> [N] minutes later with [a link / a picture] I could open from the thread.

### 2. It asked before sending from my gmail

Tags: `approval`, `Founder operations`

> I asked it to email [who] about [what]. It wrote the email, and then the
> chat showed me exactly what would go out and to whom, and waited. I replied
> /approve and it sent. The time I said /deny, nothing went out, and it told me
> so instead of trying another way.

### 3. It brought the receipts

Tags: `research`, `Shopping`

> I asked which [product] to buy. Every claim came with the page it came from,
> a link or a screenshot in its own bubble. When it couldn't find [the thing],
> it said so instead of filling the gap.

### 4. It stayed quiet in the group until we said its name

Tags: `Team`, `imessage`

> [Who] and I planned [what] in a group with Zoen in it. It said nothing for
> [N] messages. When I wrote "zoen, [ask]", one answer came back for both of
> us. No intro, no progress chatter.

### 5. It went quiet when I did

Tags: `automation`

> I didn't text it for [N] days. It didn't text me either: no check-ins, no
> "just following up". When I came back with [ask], it picked up [the task]
> where we left it.

(This one describes the new floor gate: no background model turns after 72
quiet hours. Publish it only after scenario 6 in `checks/manual-scenarios.md`
passes on a real line.)

## Publish

From a running container, after the edits above are final:

```sh
scripts/publish-stories.sh   # reads docs/stories.json; add the new stories there first
```
