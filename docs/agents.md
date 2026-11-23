# Agentes (MCP + skill)

O VPN Tray expõe a VPN para agentes de IA de dois jeitos:

- **Servidor MCP** (`vpnctl mcp`): ferramentas com regras de segurança embutidas.
- **Skill** ([`agent/SKILL.md`](../agent/SKILL.md)): ensina o agente *quando* e *como* usar essas ferramentas.

> Para um agente que vai **instalar ou modificar** este repositório, as instruções ficam em [AGENTS.md](../AGENTS.md).

## Registrar

```bash
vpnctl setup-agents
```

O `install.sh` já roda esse comando. Por agente:

| Agente | MCP | Skill |
|---|---|---|
| Claude Code | `claude mcp add -s user vpn-tray -- ~/.local/bin/vpnctl mcp` | `~/.claude/skills/vpn-tray` (link) |
| Kiro | entrada `vpn-tray` em `~/.kiro/settings/mcp.json` (com backup) | `~/.kiro/skills/vpn-tray` (link) |

- `--claude` / `--kiro`: registra só em um deles.
- `--dry-run`: mostra o que mudaria, sem mexer em nada.
- `--remove`: desfaz o registro.

Abra uma **sessão nova** do agente depois de registrar, porque os MCPs são carregados quando a sessão começa.

Em outro cliente MCP, configure assim:

```json
{ "command": "/home/<você>/.local/bin/vpnctl", "args": ["mcp"] }
```

## Ferramentas

| Ferramenta | O que faz | Exige |
|---|---|---|
| `vpn_status` | estado de cada VPN, padrão, política e permissões | nada (liberada sem prompt) |
| `vpn_logs` | últimas linhas do log | `agents.enabled` |
| `vpn_connect` | conecta e espera subir; com SAML, o login abre no navegador | `allow_connect` + `user_confirmed=true` |
| `vpn_disconnect` | desconecta | `allow_disconnect` + `user_confirmed=true` |

Se a política "pedir senha ao conectar" estiver ligada, o `vpn_connect` ainda abre a caixinha de senha do sistema na tela do usuário. Nenhum agente consegue pular essa etapa.

## Fluxo que a skill ensina

1. `vpn_status`.
2. Se estiver conectada, segue a tarefa com a ferramenta própria (por exemplo, o MCP do banco).
3. Se estiver desligada, **pergunta ao usuário** se pode conectar.
4. Com o sim, roda `vpn_connect` (`user_confirmed: true`), avisa sobre o login no navegador e roda `vpn_status` de novo.
5. Se o recurso falhar com a VPN conectada, o problema não é a VPN: o agente não fica reconectando.

## Permissões

```bash
vpnctl agents
vpnctl agents allow-connect off
vpnctl agents enabled off
```

- `vpnctl agents`: mostra as permissões.
- `vpnctl agents allow-connect off`: agentes não conectam.
- `vpnctl agents enabled off`: agentes só conseguem ver o status.

Também dá para mudar pelo menu do ícone, em **Segurança**. Essas permissões são preferência do usuário, não trava. A trava de verdade é a política do polkit; veja [security.md](security.md).

**Escopo: só VPN.** O MCP não testa banco nem serviço. O agente faz isso com as próprias ferramentas, depois de ver que a VPN está no ar.
