import { LEGAL } from "./legal.js";

const COPY = {
  ...LEGAL,
  welcome: {
    label: "Your connections, with Zoen",
    title: "More of your life.",
    accent: "In the same conversation.",
    text: "Ask Zoen to connect your account. The authorization link arrives in iMessage, and you carry on there.",
  },
  received: {
    label: "Authorization received",
    title: "You can go back.",
    accent: "I'll take it from here.",
    text: "The response is in. Zoen will check the connection and let you know in the conversation.",
  },
  denied: {
    label: "Authorization not completed",
    title: "That's fine.",
    accent: "You choose the access.",
    text: "This return didn't connect the account yet. If you just created your account, tap the same link Zoen sent you again. The authorization is still open.",
  },
  expired: {
    label: "Link expired",
    title: "Shall we try again?",
    accent: "I'll be waiting there.",
    text: "This link has expired or is no longer available. Ask Zoen for a new one in iMessage to continue.",
  },
  used: {
    label: "Link already used",
    title: "We'll carry on",
    accent: "in the conversation.",
    text: "This link was already used or canceled. Check with Zoen whether the connection finished, or ask for a new attempt.",
  },
  invalid: {
    label: "Couldn't finish",
    title: "Let's try",
    accent: "one more time.",
    text: "We couldn't confirm this return. Go back to iMessage and ask Zoen for a new link.",
  },
  confirm: {
    label: "Two-factor confirmation",
    title: "So we can start",
    accent: "talking.",
    text: "I need a two-factor confirmation for your security. This button sends an SMS to confirm your phone and gives you a contact back. Send that contact a Hi. You can keep talking over iMessage/Google Messages, or send the code here and continue securely.",
    button: "Send the SMS",
    href: "sms:+16282463032?&body=Set%20this%20up%20for%20me%3A%20aiworthusing.com%2Fagent-index%2Fzoen",
    hint: "You can close this page after sending.",
  },
};

function attr(value) {
  return String(value).replaceAll("&", "&amp;").replaceAll('"', "&quot;");
}

// Only our static copy enters HTML. OAuth parameters never enter the page.
export function page(kind, headers, status = 200) {
  const copy = COPY[kind];
  return new Response(`<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="dark">
  <meta name="robots" content="noindex, nofollow">
  <title>${copy.label} · Zoen</title>
  <link rel="icon" type="image/webp" href="/zoen-avatar.webp">
  <link rel="stylesheet" href="/style.css">
</head>
<body class="${copy.article ? "legal-page" : "connection-page"}">
  <header class="brand" aria-label="Zoen">
    <img src="/zoen-avatar.webp" width="36" height="36" alt="">
    <span class="wordmark">Zoen</span>
    <span class="divider" aria-hidden="true"></span>
    <span class="brand-detail">your connections</span>
  </header>
  <main>
    <p class="eyebrow"><span class="status-dot" aria-hidden="true"></span>${copy.label}</p>
    <h1>${copy.title}<br><em>${copy.accent}</em></h1>
    <p class="description">${copy.text}</p>
    ${copy.article ? `<article aria-label="${copy.label}">${copy.article}</article>` : `<a class="button" href="${attr(copy.href || "sms:")}">${copy.button || "Back to iMessage"} <span aria-hidden="true">↗</span></a>
    <p class="hint">${copy.hint || "You can close this page and keep talking in the conversation."}</p>`}
  </main>
  <footer><p>A little less to figure out alone.</p>
    <nav aria-label="About Zoen">
      <a href="https://tryzoen.com">Zoen</a>
      <a href="/privacy">Privacy</a>
      <a href="/terms">Terms</a>
      <a href="mailto:enzo@zoen.space">Contact</a>
    </nav>
  </footer>
</body>
</html>`, { status, headers: {
    ...headers,
    "Content-Type": "text/html; charset=utf-8",
    "Content-Security-Policy": "default-src 'none'; style-src 'self'; img-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
  } });
}
