# CLI: `vpnctl`

```text
vpnctl status [--json]
vpnctl connect [NOME] [--wait 120] [--no-browser]
vpnctl disconnect [NOME]
vpnctl logs [NOME] [-n 80] [-f]
vpnctl import ARQUIVO [--name N] [--default] [--dry-run]
vpnctl policy [show] | policy require-password on|off
vpnctl agents [show] | enabled|allow-connect|allow-disconnect on|off
vpnctl mcp
vpnctl setup-agents [--claude] [--kiro] [--dry-run] [--remove]
vpnctl --version
```

Quando o `NOME` é omitido:
- `connect` usa a VPN padrão;
- `disconnect` usa a VPN ativa;
- `logs` usa a VPN padrão.

## Comandos

| Comando | O que faz |
|---|---|
| `status` | Estado de cada VPN, VPN padrão, política e permissões dos agentes. |
| `connect` | Conecta (derrubando outra que esteja ativa) e espera até `--wait` segundos. Com SAML, abre o navegador se o ícone não estiver rodando. `--no-browser` só imprime a URL. `--wait 0` não espera. |
| `disconnect` | Desconecta. |
| `logs` | Últimas linhas do journal da VPN. `-f` segue ao vivo. |
| `import` | Converte um `.conf` do openfortivpn em perfil. Se o arquivo for do root, pede senha para ler. A senha nunca aparece na saída. `--dry-run` só mostra o que faria. |
| `policy require-password on\|off` | Liga ou desliga a senha a cada conexão. Pede senha de administrador. Veja [security.md](security.md). |
| `agents …` | O que agentes podem fazer pelo MCP. Veja [agents.md](agents.md). |
| `mcp` | Servidor MCP via stdio (para clientes MCP). |
| `setup-agents` | Registra o MCP e a skill no Claude Code e no Kiro. |

## Saída e códigos

Com `--json`, a saída é JSON (para scripts e agentes). Em caso de erro, sai `{"ok": false, "error": "..."}`.

| Código | Significado |
|---|---|
| 0 | ok |
| 1 | erro (VPN inexistente, senha recusada, helper falhou…) |
| 2 | uso inválido |
| 4 | a VPN não subiu (`connect` terminou em erro ou estourou o tempo) |

Exemplo de `vpnctl status --json`, resumido:

```json
{
  "overall": "on",
  "default": "work",
  "profiles": {
    "work": {"state": "on", "label": "conectada", "auth": "saml", "host": "vpn.example.com",
             "waiting_browser_login": false, "untrusted_cert": null, "last_error": null}
  },
  "policy": {"require_password_connect": false},
  "agents": {"enabled": true, "allow_connect": true, "allow_disconnect": true}
}
```

**Escopo: só VPN.** O `vpnctl` não testa banco, API nem outros serviços. Isso fica com a ferramenta de cada um.
