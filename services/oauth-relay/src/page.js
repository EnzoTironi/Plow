import { LEGAL } from "./legal.js";

const COPY = {
  ...LEGAL,
  welcome: {
    label: "Suas conexões, com o Zoen",
    title: "Mais da sua vida.",
    accent: "Na mesma conversa.",
    text: "Peça ao Zoen para conectar sua conta. O link de autorização chega pelo iMessage, e vocês continuam por lá.",
  },
  received: {
    label: "Autorização recebida",
    title: "Pode voltar.",
    accent: "Eu sigo com você.",
    text: "O retorno já chegou. O Zoen vai conferir a conexão e te avisar na conversa.",
  },
  denied: {
    label: "Autorização não concluída",
    title: "Tudo bem.",
    accent: "Você escolhe o acesso.",
    text: "Esta volta ainda não conectou a conta. Se você acabou de criar o cadastro, toque de novo no mesmo link que o Zoen mandou. A autorização continua aberta.",
  },
  expired: {
    label: "Link expirado",
    title: "Vamos de novo?",
    accent: "Eu te espero por lá.",
    text: "Este link já expirou ou não está mais disponível. Peça um novo ao Zoen no iMessage para continuar.",
  },
  used: {
    label: "Link já utilizado",
    title: "A gente continua",
    accent: "na conversa.",
    text: "Este link já foi usado ou cancelado. Confira com o Zoen se a conexão terminou ou peça uma nova tentativa.",
  },
  invalid: {
    label: "Não deu para concluir",
    title: "Vamos tentar",
    accent: "mais uma vez.",
    text: "Não conseguimos confirmar este retorno. Volte ao iMessage e peça um novo link ao Zoen.",
  },
  confirm: {
    label: "Confirmação de dois fatores",
    title: "Falta um passo.",
    accent: "Pra gente começar.",
    text: "Esse botão manda um SMS pra confirmar o seu telefone. Quando a linha existir, eu te mando um código no iMessage. Você envia esse código aqui no WhatsApp. Pode levar alguns minutinhos.",
    button: "Enviar o SMS",
    href: "sms:+16282463032?&body=Set%20this%20up%20for%20me%3A%20aiworthusing.com%2Fagent-index%2Fzoen",
    hint: "Pode fechar esta página depois de enviar.",
  },
};

function attr(value) {
  return String(value).replaceAll("&", "&amp;").replaceAll('"', "&quot;");
}

// Only our static copy enters HTML. OAuth parameters never enter the page.
export function page(kind, headers, status = 200) {
  const copy = COPY[kind];
  return new Response(`<!doctype html>
<html lang="${copy.article ? "en" : "pt-BR"}">
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
    <span class="brand-detail">${copy.article ? "your connections" : "conexões"}</span>
  </header>
  <main>
    <p class="eyebrow"><span class="status-dot" aria-hidden="true"></span>${copy.label}</p>
    <h1>${copy.title}<br><em>${copy.accent}</em></h1>
    <p class="description">${copy.text}</p>
    ${copy.article ? `<article aria-label="${copy.label}">${copy.article}</article>` : `<a class="button" href="${attr(copy.href || "sms:")}">${copy.button || "Voltar ao iMessage"} <span aria-hidden="true">↗</span></a>
    <p class="hint">${copy.hint || "Pode fechar esta página e continuar na conversa."}</p>`}
  </main>
  <footer><p>${copy.article ? "A little less to figure out alone." : "Um pouco menos para resolver sozinho."}</p>
    <nav aria-label="${copy.article ? "About Zoen" : "Sobre o Zoen"}">
      <a href="https://tryzoen.com">Zoen</a>
      <a href="/privacy">${copy.article ? "Privacy" : "Privacidade"}</a>
      <a href="/terms">${copy.article ? "Terms" : "Termos"}</a>
      <a href="mailto:enzo@zoen.space">${copy.article ? "Contact" : "Contato"}</a>
    </nav>
  </footer>
</body>
</html>`, { status, headers: {
    ...headers,
    "Content-Type": "text/html; charset=utf-8",
    "Content-Security-Policy": "default-src 'none'; style-src 'self'; img-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
  } });
}
