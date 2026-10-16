# Zoen end-to-end checklist

Run on a real Plow line before promoting an image, with a second phone for the
group scenarios and a Mac with Latch for scenario 7. Every box must pass.
Record failures next to the item, with the time and what the phone showed.

Setup:

```sh
just image image-test        # or the docker commands in the justfile
./bin/plow-agents mint ln_xxx
docker compose up --build -d && docker compose logs -f agent
```

## 0. Image

- [ ] `just image-test` ends with `image-identity-ok`.
- [ ] `docker compose exec agent head -1 /var/lib/hermes/SOUL.md` prints `# Zoen on Plow`.
- [ ] `docker compose exec agent ls /etc/sudoers.d` shows no `zoen`.

## Scenarios

1. [ ] **First contact.** Text "oi" as the owner from a fresh volume.
   - Expect: one onboarding burst within about 10s (bubbles, link, two contact
     cards), then one answer in Portuguese. No second burst.
   - Check: `docker compose logs agent | grep -c "onboarding"` does not grow on a
     second message.
2. [ ] **English owner.** From a fresh volume, text "hey, plan my saturday".
   - Expect: the onboarding burst (Portuguese, a known limitation), then every
     reply in English, starting on the request.
3. [ ] **Free thread.** Ask for research ("compare the 3 best e-bikes under $2k").
   - Expect: one short progress bubble, then the turn ends. While it works, ask
     "status?" and get one short bubble. The result arrives with a source link
     or a picture.
4. [ ] **Approval ask.** Connect Google, then ask Zoen to email someone a short
   note from your Gmail.
   - Expect: the chat shows the approval ask with the recipient and subject.
     Nothing is sent before `/approve`. `/deny` sends nothing and Zoen says so.
   - Fails if: the email goes out without an ask (an image with `HERMES_YOLO_MODE`).
5. [ ] **Shell work stays quiet.** Ask for something that makes Zoen run commands
   in its VM ("make me a tiny landing page and show me").
   - Expect: no `/approve` prompt for commands; pictures or a link come back.
6. [ ] **Floor while active and while away.** After scenario 3:
   - `docker compose exec --user hermes agent /opt/hermes/bin/hermes cron list`
     shows `zoen-floor` with `Monitor: zoen-floor-monitor.py`.
   - Expect: with the owner active, a floor run at most every two hours.
   - Set the clock check aside for a quiet install: on a volume where the owner
     last wrote more than 72h ago, `hermes cron list` shows runs as `no_change`
     and the model is not called (no new tokens in the Index usage for that day).
7. [ ] **Mac via Latch.** With Latch open, ask "what's on my desktop?".
   - Expect: Zoen lists the Mac's skills, asks Latch, and answers. With Latch
     closed, it says once that the Mac is asleep and keeps working.
8. [ ] **Group.** Add Zoen and a second phone to a group. Talk without its name.
   - Expect: silence. Say "zoen, find a place for dinner": one answer, no
     progress chatter, no intro.
9. [ ] **WhatsApp pairing.** Tap the pairing link from the onboarding burst and
   send the code.
   - Expect: Zoen introduces itself on WhatsApp without repeating the code;
     later WhatsApp messages are answered on WhatsApp.
10. [ ] **Restart.** `docker compose restart agent`.
    - Expect: no message to the owner, memory intact, the next text answered.
