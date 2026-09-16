# Instalar o Zoen

Um comando. Docker aberto. Mande do celular a frase que aparecer.

```sh
curl -fsSL https://raw.githubusercontent.com/EnzoTironi/Plow/main/install.sh | sh
```

Já clonou? `./install.sh`

Quando terminar, mande um iMessage. É só isso.

No Mac, o único app que você instala é este:
https://plow.co/latch
O resto o Zoen pede um sim e faz.

Pausar: `docker compose stop`. Sair: `./bin/plow-agents revoke` e
`docker compose down`.

---

Se algo falhar: Docker ligado? `docker info`. Linha ocupada? o script
pega uma livre. `plow-credentials` virou pasta? `docker compose down`,
`rmdir plow-credentials`, `./install.sh` de novo.

Dona do repo, Index:

```sh
curl -O https://raw.githubusercontent.com/plow-pbc/agent-index-client/f900ff144076f0a766584b6ec4d0993600779b16/standalone/agent_index_client.py
set -a; . ./plow-credentials; set +a
python3 agent_index_client.py --register --agent zoen \
  --name "Zoen" \
  --blurb "Your Software Factory. Text what you want. It gets built. Pictures and video come back." \
  --runtime Hermes \
  --repo https://github.com/EnzoTironi/Plow \
  --install-url https://github.com/EnzoTironi/Plow/blob/main/docs/INSTALL.md
```
