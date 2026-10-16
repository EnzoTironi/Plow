# Zoen usage gap since 2026-10-07

**What the data shows.**
- 44 users reported through 2026-10-06, about 56–72M tokens a day.
- 2026-10-07 has 15.9M (Luna 3.8M, GLM 12.1M). From then on, every day is zero.
- Founder Agent, Meetly, Rundown and Life Assistant all report through 2026-10-16, so the Index is receiving.
- Zoen's code didn't change between Sep 23 and Oct 7.
- All 44 installs stopped within the same day.

**What the image does.** A cloud 1-click install reports without a compose file:
- `ENV AGENT_ID=zoen` is in the image;
- the base `agent-index` service reads it from the container environment and fixes `HERMES_HOME=/var/lib/hermes`, which is where Hermes writes `state.db`;
- the base image also sets `HERMES_HOME` as ENV;
- Zoen doesn't override the service, and the base bump changes neither the service nor the client pin.

The compose comment ("agentsview reports 0 tokens for Hermes") is about local runs. It is redundant with the base now.

**Verdict.** I found no gap in the image, so I changed nothing for it beyond a regression test. A simultaneous stop across 44 installs points outside the repo:
- the agents were stopped or reprovisioned;
- or they stopped calling the model, for example out of credits or a routing change; Sonnet usage also disappeared on Oct 3.

Since most of the usage looked like the floor cron (above), "fewer installs running" and "no one using it" both fit. What to check:

1. `./bin/plow-agents agents`: are Zoen installs `running`?
2. On one running install:
   - `docker logs` or the VM log for `agent-index:` lines;
   - as `hermes`, `HERMES_HOME=/var/lib/hermes /opt/hermes/.venv/bin/python3 /opt/plow/agent-index-client.py status` should print exit 0;
   - `--dry-run` should show non-zero token counts.
3. Ask Plow whether Zoen agents were changed on 2026-10-07, the day the image was admitted for 1-click.
4. Once a fixed install reports, `/v1/usage?agent_id=zoen` should show the day again.
