# AGENTS.md: instruções para agentes de IA

Você recebeu este repositório. Identifique o que o usuário quer e siga a seção certa:

| O usuário quer… | Vá para |
|---|---|
| **instalar** o VPN Tray na máquina dele | [1. Instalar](#1-instalar) |
| **usar** a VPN numa tarefa (conectar, ver status) | [2. Usar](#2-usar) |
| **mudar o código** (bug, feature, docs) | [3. Contribuir](#3-contribuir) |

Regras que valem sempre:
- **Nunca** use `sudo` sozinho, nem digite a senha do usuário.
- **Nunca** leia, mostre ou copie `/etc/openfortivpn/*.conf`, porque eles têm senhas.
- **Nunca** conecte a VPN sem um "sim" explícito do usuário **nesta conversa**.
- **Nunca** desligue travas de segurança (`vpnctl policy`, `vpnctl agents`) para conseguir fazer algo. Explique ao usuário como ele mesmo libera.

---

## 1. Instalar

### 1.1 Conferir os requisitos (sem sudo)

```bash
uname -s
command -v systemctl pkexec journalctl
command -v openfortivpn && openfortivpn --version
python3 -c "import gi; gi.require_version('Gtk','3.0'); gi.require_version('Notify','0.7'); print('gtk ok')"
python3 -c "import gi; gi.require_version('XApp','1.0'); print('xapp ok')" \
  || python3 -c "import gi; gi.require_version('AyatanaAppIndicator3','0.1'); print('ayatana ok')"
```

- `uname -s` precisa dar `Linux`.
- `command -v systemctl pkexec journalctl` precisa achar os três.
- O `openfortivpn` precisa ser 1.21 ou mais novo.
- Pelo menos uma biblioteca de bandeja precisa dar "ok".

Se algo faltar, **mostre ao usuário** o comando de instalação de [docs/installation.md](docs/installation.md#requisitos) e peça para ele rodar. No Debian, Ubuntu e Mint é `sudo apt install …`.

### 1.2 Rodar o instalador (o usuário roda, por causa do sudo)

O `./install.sh` pede `sudo`. **Peça ao usuário para rodar no terminal dele**, a partir da pasta do clone:

```bash
./install.sh
```

Explique o que vai acontecer: ele instala a unit do systemd, a regra do polkit, o helper root, os links em `~/.local/bin` e o autostart, e registra o MCP e a skill nos agentes. Se o usuário não quiser o registro nos agentes, use `./install.sh --no-agents`.

A pasta do clone **precisa continuar onde está**, porque os links apontam para ela.

### 1.3 Cadastrar a VPN

Tem três caminhos. Escolha com o usuário:
- **Ícone → Adicionar VPN…**: formulário. O usuário digita servidor e senha; você não toca neles.
- **`vpnctl import arquivo.conf`**: se ele já tiver um `.conf` do openfortivpn. Pede senha.
- Config que já está em `/etc/openfortivpn/<nome>.conf`: o `install.sh` importa sozinho.

### 1.4 Verificar

```bash
vpnctl --version
vpnctl status
pgrep -af vpn-tray
```

- `vpnctl status` deve listar as VPNs.
- `pgrep -af vpn-tray` mostra o ícone rodando. Se ele não estiver, abra com `~/.local/bin/vpn-tray &`.

Para conferir o registro nos agentes, use `claude mcp get vpn-tray` (Claude Code) ou olhe o `~/.kiro/settings/mcp.json` (Kiro). Avise o usuário para **abrir uma sessão nova** do agente, para as ferramentas `vpn_*` aparecerem.

Se der problema, veja [docs/troubleshooting.md](docs/troubleshooting.md).

---

## 2. Usar

Siga a skill [`agent/SKILL.md`](agent/SKILL.md). Resumo:

1. `vpn_status` (MCP) ou `vpnctl status --json`.
2. Se estiver desligada, **pergunte** ao usuário se pode conectar.
3. Com o sim: `vpn_connect` com `user_confirmed: true`. Com SAML, avise que o login abre no navegador. Se a política exigir, avise também da caixinha de senha.
4. `vpn_status` de novo e siga a tarefa com a ferramenta própria (o MCP do banco etc.).

**Escopo: só VPN.** Não use o VPN Tray para testar banco ou serviço.

---

## 3. Contribuir

Antes de mexer, leia [docs/architecture.md](docs/architecture.md) e [docs/development.md](docs/development.md).

### Arquitetura (hexagonal), em uma tela

| Camada | Pasta | Pode importar |
|---|---|---|
| Domínio | `vpntray/domain/` | só stdlib, **sem I/O** |
| Portas | `vpntray/ports.py` | domínio |
| Aplicação | `vpntray/application/` | domínio, portas |
| Adaptadores | `vpntray/adapters/` | domínio, portas, `application.errors` |
| Entrada | `vpntray/entrypoints/` (CLI, MCP, `tray/` GTK) | tudo, via `composition.py` |

- GTK (`gi`) só pode aparecer em `vpntray/entrypoints/tray/`.
- Um adaptador novo também precisa da versão em `adapters/memory.py`, para os testes e o demo.
- O helper root (`system/vpn-tray-helper`) é **autocontido**: não importe o pacote nele. Ao mudar a validação, mude nos dois lugares e acrescente um caso em `tests/test_contract_helper.py`.

O arquivo `tests/test_architecture.py` reprova violações dessas fronteiras.

### Antes de abrir o PR

```bash
ruff check .
ruff format --check .
python3 -m pytest
```

Os três precisam passar. Se mexeu na interface, rode também `python3 tests/visual_snapshots.py` e confira os PNGs.

- **Testes**: todo comportamento novo precisa de teste. Nenhum teste pode tocar na VPN real, em `/etc` ou nas configurações do usuário. Use o sistema em memória (`MemorySystem` e `build_memory()`).
- **Dados fictícios** em código, testes, docs e prints:
  - perfis `work`, `lab`, `quebrada`;
  - hosts `vpn.example.com` e `vpn.example.org`;
  - usuários `alice` e `bob`.

  Este repositório é **público**: nunca use nome de empresa, hosts ou IPs internos, usuários ou certificados reais.

### Commits e PR

- **Nunca** faça push direto na `main`, que é protegida. Crie uma branch e abra um PR.
- O título do PR segue o [Conventional Commits](https://www.conventionalcommits.org/) (`feat: …`, `fix: …`, `refactor: …`, `docs: …`), porque vira o commit do squash e decide a versão:
  - `feat` sobe minor;
  - `fix` sobe patch;
  - `refactor`, `docs`, `test`, `ci` e `chore` não geram versão.
- Antes do push, sincronize com a `origin/main` (`git rebase origin/main`).
- Não edite `CHANGELOG.md` nem `VERSION` à mão: o semantic-release cuida deles.
