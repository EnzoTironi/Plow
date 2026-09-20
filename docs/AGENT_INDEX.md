# Zoen on the Agent Index

Public page: https://aiworthusing.com/agent-index/zoen

## Blurb

life happens. text zoen. plan your week. find a great place. compare before you buy. walk into the meeting ready. find your next customer. turn an idea into something real. your apps and thousands of tools, in one conversation. big dreams. everyday problems. one little monster.

Keep this text aligned with `AGENT_BLURB` in `Dockerfile` and `compose.yml`.
Publish the blurb and gallery together; preserve verification, video, logo,
repository, installation link, and existing stories. The short description stays
under 300 characters. The gallery uses four illustrations from `docs/agent-index/`.
Keep the real iMessage screenshot in the existing `horses-in-sf` story.

## Real connection story

Story ID: `your-apps-in-the-conversation`

Title: you texted "connect it." your apps joined the conversation.

Tags: `Setup & first run`, `imessage`

Body:

you wanted your apps in the same conversation. you texted me, signed in, and
i checked that we were connected. later, we restarted my computer. your
connections were still there. you didn't have to start over. one less thing
to think about.

This is a completed local validation, recorded in `docs/CONNECTORS.md` and
`docs/INTEGRATIONS.md`. The publishable body in
`agent-index/connection-story.json` keeps this account of the validation and adds
explicitly prospective requests. Update its stable story ID; do not create a new
story for every example or imply those requests were completed for customers.

## Product examples

The README and connection-story examples cover planning, places, shopping
comparisons, video summaries, job research, meeting preparation, notes and tasks,
content research, business leads, customer feedback, competitor ads, creators,
and software. They are things to ask, not completed-task claims.

## Gallery

- `agent-index/zoen-thousands.png`: thousands of tools. one conversation.
- `agent-index/zoen-day.png`: your day. a little lighter.
- `agent-index/zoen-idea.png`: big idea? text me.
- `agent-index/zoen-apps.png`: your apps. in the conversation.

Use immutable GitHub raw URLs at the published commit. Image prompts and mascot
references are in `agent-index/PROMPTS.md`. The illustrated requests make no
claims about customer results, automatic account access, or free paid tools.

The Index currently derives its Use cases section from stories, not the public
record's `use_cases` array. The inherited reporter supports `blurb` and `images`
for page updates. Do not change the reporter just to add marketing fields.

Sources checked September 20, 2026:

- Brand voice: https://x.com/tryZoen
- Product direction: https://tryzoen.com
- Treg use cases: https://treg.to/use-cases
- Treg workflows: https://treg.to/workflows
- Treg architecture: https://github.com/superdesigndev/treg
- Local places: https://treg.to/use-cases/find-local-businesses-by-keyword-and-location
- Product comparisons: https://treg.to/use-cases/amazon-product-detail-by-asin
- Video captions: https://treg.to/use-cases/youtube-transcript-api
- Job research: https://treg.to/use-cases/job-postings-across-companies
- Meeting preparation: https://treg.to/use-cases/enrich-a-company
- Lead research: https://treg.to/workflows/find-and-verify-a-lead-list
- Customer feedback: https://treg.to/use-cases/mine-the-comments
- Competitor ads: https://treg.to/workflows/mine-competitor-meta-ads-as-creative-pack
- Content research: https://treg.to/workflows/keyword-demand-to-ad-budget
- Creator discovery: https://treg.to/workflows/discover-creators-in-a-niche

Treg's homepage and repository show different changing totals. Use "thousands
of API tools" instead of equating endpoints with distinct apps or claiming an
exact provider count. Personal account access still requires the relevant
connection; paid calls require a Treg balance and an approved budget.
OAuth, account identity, catalog lookup, and persistence were validated. Paid
provider calls were not exhaustively tested. Video summaries need accessible
captions; job listings and prices need freshness checks; public ad research does
not reveal private performance data. Do not advertise unimplemented account
connections such as Google Ads, Analytics, or Search Console.
