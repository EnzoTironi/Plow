# Zoen: proposals not shipped on plow-pattern-upgrade

I couldn't verify these here, and each touches the live path.

1. **An opt-in daily loop.** Meetly, Founder Agent and Prucê all earn depth from one recurring job the owner chose: a poll, a pipeline monitor, a daily menu. Zoen's only loop was a silent maintenance pass. Proposal: after the first real result, Zoen offers one daily brief at a time the owner picks, as a normal Hermes cron in their chat, and never asks again. It needs about 300 persona characters and a real-line check of how it lands.
2. **Fold the 23 `principle-*` skills into `floor`.**
   - **Cost:** they put 6,656 characters of name and description into every system prompt (19 other skills: 3,399). Those characters ride every iMessage turn, though only a coding child reads them.
   - **Blocker:** Hermes leaves a removed bundled skill in existing homes and only drops it from its manifest (`tools/skills_sync.py`). The 44 current owners would see no savings without a pruning migration, and I can't run that here.
   - **Proposal:** move them to `skills/floor/principles/`. Add a boot step that deletes a home copy only when it is byte-identical to the shipped one.
3. **Onboarding in the owner's language.** The prebuilt burst is Portuguese, while the Index audience reads English. The first text already arrives before the burst, so the language could be chosen from it. That path is the most latency-sensitive one Zoen has, so it needs a real line.
4. **The relay with a local install.** A local, non-cloud install still authenticates to Enzo's relay with its real Plow bearer, so the relay can verify the agent. The relay already accepts the `agent_uid` + secret path the cloud uses. Switching local installs to that path stops the bearer from leaving, at the cost of trust-on-first-use. That's a security trade-off for Enzo to make.
