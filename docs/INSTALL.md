# Zoen

Um monstrinho. Seu agente pessoal no iMessage.
A little monster. Your personal agent over iMessage.

## Um clique / One click

1. Abra https://aiworthusing.com/agent-index/zoen
2. Aperte **Text this agent**
3. Abre um SMS para +1 628 246-3032:
   `Set this up for me: aiworthusing.com/agent-index/zoen`

[Text this agent](sms:+16282463032?&body=Set%20this%20up%20for%20me%3A%20aiworthusing.com%2Fagent-index%2Fzoen)

Open the page. Tap **Text this agent**. Send it.

O Plow sobe o Zoen. Depois é só texto.
Plow starts Zoen. Then text what you want.

**iPhone.** É o escritório. That's the office.

**Mac + Latch.** O único app: https://plow.co/latch
The only Mac app. Zoen asks. You tap yes. It drives the machine.

Compartilhar / Share: [SHARE.md](SHARE.md)
A página do Index é o link: https://aiworthusing.com/agent-index/zoen

## Power users

Já clonou? `./install.sh`

```sh
curl -fsSL https://raw.githubusercontent.com/EnzoTironi/Plow/main/install.sh | sh
```

Sobe o mesmo `:v1` do Text this agent. Same `:v1` 1-click deploys.

Sair: `./bin/plow-agents lines` e `./bin/plow-agents revoke ln_…`

Docker local, com Docker aberto: `./install.sh --local`.
Isso guarda memória, sessões e o WhatsApp. `./install.sh --local --fresh` apaga o home.

Para testar as mudanças deste checkout e preparar uma atualização, veja
[runtime e validação](RUNTIME.md). O instalador público usa a imagem publicada;
ele não atualiza automaticamente uma instância existente com o código deste checkout.
