# Show a page

A picture or a video still goes in the thread. This playbook is for a page
they need to open: a preview, a draft site, a report, a folder of files.

`cloudflared` is already on this machine. Do not ask them to install it.
Do not name the tunnel, the binary, or the machine.

1. Serve only the artifact, on `127.0.0.1`, not `0.0.0.0`. A static
   directory is `python3 -m http.server PORT --bind 127.0.0.1 --directory DIR`.
2. Start `cloudflared tunnel --url http://127.0.0.1:PORT`. No account and
   no token. Read the https URL it prints. It looks like
   `https://<name>.trycloudflare.com`.
3. Open that URL and check the page is the artifact. No secret, token,
   mailbox, or other file beside it.
4. Send the link in its own bubble with `zoen_imessage`. Say what it is
   in their words. Do not say how the link was made.
5. Leave it up while they might still be looking. Stop it when the task
   is done or they are finished with the page. Do not tunnel the agent
   API, a shell, or the whole disk. Do not start a second tunnel for the
   same page.

A quick tunnel is public to anyone who has the link. If the page must
stay private, send the file in the thread instead.
