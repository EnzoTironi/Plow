# Index

Read this before choosing a workflow, someone else's app, or outside data.
Then open the named playbook. Connect only the catalog name the task needs.
Confirm the name with `zoen_connections` action `catalog` before `connect`.
A name here is a candidate. Saved credentials are not a verified account.

## Use cases

Their own app comes first: notes, tasks, mail, calendar, files, design, code,
money, or CRM. Use the connector below. Outside data they do not already have
an account for goes to `treg` or `monid`. Discover, inspect the live price, and
ask before a paid call. Buying, trading, sending, or deleting waits for a yes.
These are jobs people ask for. A page here is not a finished result.

Sources, checked 2026-09-22:

- Treg jobs: https://treg.to/use-cases
- Treg sequences: https://treg.to/workflows
- Monid jobs: https://monid.ai/ and https://docs.monid.ai/cli/examples.html
- Poke recipes: https://poke.com/recipes
- Assistant jobs: https://assistantbenchmark.com/use-cases

### Treg

Search `treg` with the words in quotes. One job is a use case. A sequence is a
workflow. Read https://treg.to/use-cases or https://treg.to/workflows when the
shape of the job matters. Do not invent an endpoint id.

People and companies: "work email" from a name, domain, or LinkedIn URL.
"email verification". "person enrichment" from an email or LinkedIn URL.
"people search" by title, seniority, company, or location. "company enrichment"
from a domain. "LinkedIn profile" by URL. "phone number" from a LinkedIn URL,
work email, or name plus company. "email format" for a domain. "companies by
industry", size, location, tech, or funding.

Search and the public web: "Google organic results" for a keyword. "keywords a
domain ranks for". "keyword research" volume, CPC, competition. "backlink
profile". "AI visibility" for how ChatGPT or Perplexity names a brand. Posts by
keyword on Reddit, X, LinkedIn, or TikTok. Comments on an Instagram, YouTube,
Reddit, or LinkedIn post. Creators by keyword on Instagram, TikTok, YouTube,
or X.

Video: "YouTube transcript". YouTube video stats, channel stats, search, and
comments. Spoken words from a Facebook or X video URL.

Commerce and places: "Amazon product" by ASIN. "TikTok Shop" products and
reviews. "app store" search. "local businesses" on Yelp or Tripadvisor.
Reviews from Tripadvisor, Trustpilot, or Yelp.

Markets: stock quote, stock news, crypto price, daily price history.

Competitors, public only: live ads from a Page or advertiser. PPC keywords a
domain bids on. Employee reviews. Job postings by title, company, or location.

Their own properties, only after that account is connected: Search Console
clicks and index status, GA4 reports, their Google Ads and Meta Ads numbers,
Google Business Profile reviews. Those are not public scrapes.

Sequences on https://treg.to/workflows: a verified lead list from one prompt.
Screen an Instagram creator list. Discover creators by niche, country, and
followers. Expand a keyword and read its seasonality. A competitor's live Meta
ads plus the Google keywords they bid on. What TikTok and Xiaohongshu say
about a category.

### Monid

`monid_discover` with the words in quotes, then `monid_inspect`, then
`monid_run` only with a budget. Discover and inspect do not spend.

Published jobs: "web search" that returns the page text with the results.
"twitter posts". "linkedin posts". "google maps reviews". Social posts and
profiles on X, Instagram, TikTok, YouTube, Reddit, Facebook, Telegram, WeChat,
and RedNote. Amazon pages. Google reviews. People search. A company dossier:
funding, headcount, news. A funding signal through to a verified work email.
Weather. Image, video, voice, and 3D generation. Browser automation.

Documented runs, as the shape of the job: an SDR lead, four social feeds in
one pass, a company dossier, a video pipeline. Prices on the site are old
receipts. The live price is `monid_inspect`.

### Poke recipes

https://poke.com/recipes is the list of life jobs. Match the ask, then use
their connected app, the browser, or a catalog search. A recipe name is not an
install.

Morning and inbox: morning briefing of calendar, mail, and priorities. Daily
weather and outfit. Follow-up reminders for mail they sent and never got back.
Birthday reminders and gift ideas from mail and calendar. Subscription
watchdog and a monthly subscription audit. Add flights, deadlines, and travel
confirmations onto the calendar. Route receipt mail into the expense tool they
already use.

Body and home: hydration reminders. Meal log with daily totals. Sleep and
readiness when they connect a ring or band. Period log. Cycle support notes.
Mood check-in. Journal prompt. Nightly gratitude. Stress tracker. Pollen alert.
Bad-weather alert. Rent reminder. Campus dining menu. Apartment listing watch.
Lights and speakers only through a connected home account.

Money: daily portfolio summary on `robinhood` when they connect it. A trade
waits for a yes. Market close for tickers they name. Spending review on the
account they connect.

Work and study: Notion pages, a personal memory log, Todoist, Linear, Asana,
GitHub, Vercel, Netlify, Supabase, Sentry, PostHog, Canva, Webflow. Meeting
notes when a notes app is connected. Weekly reading suggestion. Friday
productivity check-in. A decision council that stress-tests a choice before
they commit. YouTube link to a short summary, via a transcript. Daily AI news.
QR code from a link or a Wi-Fi password. One styled image when they ask for
that effect.

Odds and ends they actually ask for: a daily fact, a horoscope, a scripture
passage, a meme that fits the chat, a weather comparison, a cat photo.

### Assistant benchmark

https://assistantbenchmark.com/use-cases is what people ask a text assistant
to do. Same rule: their app first, then the browser, then `treg` or `monid`.
Money, a send, a booking, and a delete wait for a yes.

Travel: check in and send the boarding pass. A flight on points. Family seats
together. A whole trip: train, hotel, dinners, tickets. Watch fares and say
when a better one appears. A hotel with free cancellation. A rental car.
`kiwi` for dates, `trivago` for stays.

Mail and calendar, skill `google-workspace` after `google`: morning briefing
with drafts. Inbox triage. Guardrails before a stranger's mail can give
orders. Events from a voice note. A meeting across several calendars, in the
group chat when they are already in it. School and activity logistics onto the
calendar. Catch a conflict before the day. Clear junk mail, and ask before
trash.

Errands: a doctor or dentist slot that fits the calendar. A week of errands.
A visa packet from documents already in their mail. A DMV slot and the form.
A missing delivery. An apartment search. A weekly nudge to a contractor.

Shopping, stop before pay: reorder a product to checkout and wait. Order
lunch. Furniture plus someone to assemble it. A clothing drop only when they
already said to buy it. Insurance quotes. Cut or switch a bill. List recurring
charges from mail. Log payments from mail into their sheet. A refund they
already asked you to chase.

Work: outreach queued, nothing sent until they approve. A site change through
the repo and the PR playbooks. Meeting transcripts into follow-ups. A study
plan and a quiz. A daily brief on a list of companies. A morning news brief.
Launch-day comments. A content desk: research, draft, picture, schedule.
Client intake through a booked time. Ads with a number they set, shown before
anything goes live.

In the chat: an image, a short edit, a trivia round, a page they can open.
Talk a draft through by voice. A PDF cleaned up and sent where they asked.

## Playbooks

- Life, research, travel, study, documents: `personal.md`
- Any account or extra API: `connections.md`
- New or changed behavior: `feature.md`
- Defect with a repro: `bug-fix.md`
- Read-only how/why: `investigation.md`
- Decision record: `spec.md`
- GitHub tickets under a spec: `cards.md`
- End of feature or bug fix: `opening-a-pr.md`
- Missing Mac app, CLI, or login: `kit.md`
- `delegate_task` slugs: `models.md`

## Connectors

Exact `zoen_connections` names. OAuth sends one iMessage link. Public names
need no account. `google` is Zoen's own OAuth, then skill `google-workspace`.
`slack` is the existing Plow connection.

Their work:

- Notes and tasks: `notion` `todoist` `craft` `airtable` `clickup` `monday` `asana` `linear`
- Files and design: `dropbox` `figma` `canva` `miro`
- Calendar: `calendly`
- Mail and chat: `google` `slack` `intercom`
- Code and deploys: `gitlab` `atlassian` `sentry` `vercel` `netlify` `cloudflare` `buildkite` `circleci` `semgrep` `postman`
- Data and apps: `supabase` `neon` `prisma-postgres` `motherduck` `railway` `algolia` `webflow` `wordpress-com`
- Customers: `attio` `close` `klaviyo` `fireflies`
- Money: `stripe` `square` `paypal` `plaid` `robinhood`
- Product stats: `amplitude` `mixpanel` `datadog` `grafana` `betterstack`
- Media: `cloudinary` `gamma` `comfy-cloud` `hugging_face` `strava`

No login:

- Places and travel: `kiwi` `trivago` `alltrails`
- Docs and answers: `context7` `deepwiki` `microsoft-learn` `aws-knowledge` `twilio-docs` `wolfram`

Outside catalogs, after their own account when they have one:

- `treg` — discover, inspect, then a paid call only with a budget
- `monid` — `monid_discover`, `monid_inspect`, then `monid_run` only with a budget

The phone flow does not activate `n8n` or `unreal-engine`.
