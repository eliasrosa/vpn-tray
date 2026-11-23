# Segurança

> Encontrou uma vulnerabilidade? Veja [SECURITY.md](../SECURITY.md) para reportar em privado.

## Camadas

### 1. Pedir senha ao conectar (polkit): a trava

Para ligar ou desligar:
- no menu do ícone: **Segurança → Pedir senha ao conectar**;
- no terminal: `vpnctl policy require-password on|off`.

Com ela ligada:
- **qualquer** conexão abre a caixinha de senha do sistema: ícone, CLI, agente ou até `systemctl start` direto;
- desconectar continua livre.

A política é imposta pelo polkit (`AUTH_SELF`), não pelo app, então não dá para contornar por fora. Mudá-la, nos dois sentidos, pede **senha de administrador** (`pkexec`): um agente não desliga a trava sozinho.

### 2. Regra do polkit restrita

Mesmo sem a senha ao conectar, a regra só libera:
- o **seu usuário**;
- numa sessão **local e ativa**;
- as units `vpn-tray@<nome>.service`, com um nome validado;
- os verbos `start`, `stop` e `restart`. Nada de `enable` nem de outras units.

### 3. Helper root mínimo

Tudo que escreve em `/etc` passa por `/usr/local/libexec/vpn-tray/vpn-tray-helper` via `pkexec`:
- aceita só campos conhecidos: host, porta, usuário/senha, realm e trusted-cert;
- valida nome, host, porta e hash, e recusa quebras de linha, o que impede injetar linhas como `pppd-plugin = …` no `.conf`;
- é **autocontido**: não importa código do repositório, porque roda como root e não pode carregar código de uma pasta que o usuário consegue editar. Um teste de contrato garante que ele e o domínio recusam as mesmas entradas.

### 4. Regras para agentes (preferência)

- O MCP exige `user_confirmed=true` para conectar ou desconectar.
- Ele respeita `agents.enabled`, `allow_connect` e `allow_disconnect`.
- Isso fica em `~/.config/vpn-tray/settings.json`: é **preferência**, não trava, porque quem acessa o seu `$HOME` pode editar. Para uma garantia de verdade, use a camada 1.

## Segredos

| Arquivo | Permissão | Conteúdo |
|---|---|---|
| `/etc/openfortivpn/<nome>.conf` | 0600 (root) | host, porta, usuário, **senha**, realm, trusted-cert |
| `/etc/openfortivpn/<nome>.args` | 0644 | só metadados: modo de login e host |
| `~/.config/vpn-tray/settings.json` | do usuário | VPN padrão, autoconnect, permissões dos agentes |
| `/etc/vpn-tray/policy.json` | 0644 | só se a senha ao conectar está ligada |

O app, a CLI e o MCP nunca leem o `.conf`. Status, logs e saídas `--json` não contêm senha.

## Fora do escopo

- **O próprio openfortivpn**: problemas nele vão para o [projeto oficial](https://github.com/adrienverge/openfortivpn/security).
- **Quem já tem root na máquina, ou escrita no seu `$HOME`.**
