---
name: vpn-tray
description: Confere e controla a VPN corporativa (openfortivpn via VPN Tray) do usuário. Use antes de acessar recursos de rede interna (bancos hml/prd, APIs internas, hosts 10.x/172.x) para saber se a VPN está conectada; quando um acesso interno der timeout, "Connection closed" ou host não resolver; ou quando o usuário pedir para ver o status da VPN, conectar ou desconectar. Só cuida da VPN — o acesso ao banco/serviço é feito depois com as ferramentas próprias (MCP do banco etc.). Nunca conecta sem confirmação explícita do usuário.
inclusion: auto
---

# VPN Tray: status e conexão da VPN

O usuário tem VPNs (openfortivpn) gerenciadas pelo VPN Tray. Elas rodam como serviços
`vpn-tray@<nome>.service`, e há um ícone ao lado do relógio.

**Escopo: só VPN.** Esta skill diz se a VPN está no ar e conecta ou desconecta. Ela não
testa banco nem serviço. Isso continua com a ferramenta de cada um: o MCP do banco
(por exemplo `db-staging`, `db-prod`), `curl`, o cliente da API etc.

Você controla por:

- **MCP `vpn-tray`** (preferencial), com `vpn_status`, `vpn_connect`, `vpn_disconnect` e
  `vpn_logs`;
- **CLI `vpnctl`** (fallback). Use `vpnctl status|connect|disconnect|logs` e `--json` para
  ler a saída.

## Fluxo

1. **Ver o status.** Rode `vpn_status` (ou `vpnctl status --json`).
   - Se `overall` for `on`, a VPN está conectada. Siga direto para a tarefa, por exemplo a
     consulta pelo MCP do banco.
   - Se for `connecting` com `waiting_browser_login`, falta o usuário terminar o login no
     navegador. Avise e espere.
   - Se for `off` ou `error`, vá para o passo 2.
2. **Perguntar antes de conectar.** Por exemplo: "A VPN `work` está desligada. Quer que eu
   conecte?" Espere um sim explícito.
3. **Conectar** com `vpn_connect` (`user_confirmed: true`) ou `vpnctl connect --json`.
   - Com SAML, o login abre no navegador do usuário. Avise: "termine o login no navegador".
   - Se a política "pedir senha ao conectar" estiver ligada, aparece uma caixinha de senha
     na tela dele. Isso é esperado; **nunca** tente contornar.
   - Se voltar `connecting`, espere uns segundos e consulte `vpn_status`. Não chame
     `vpn_connect` de novo em loop.
   - Se voltar `error`, veja `vpn_logs` e explique ao usuário. Um `untrusted_cert`, por
     exemplo, ele resolve pelo menu do ícone.
4. **Seguir com a tarefa** usando a ferramenta própria (MCP do banco etc.).
   - Se o recurso falhar **com a VPN conectada**, o problema não é a VPN: pode ser
     credencial, o próprio serviço ou o MCP. Não reconecte a VPN por causa disso.
5. **Desconectar** só se o usuário pedir, com `vpn_disconnect` (`user_confirmed: true`).

## Regras

- Nunca use `user_confirmed: true` sem o usuário ter dito que pode **nesta conversa**.
  Uma permissão antiga não vale para uma conexão nova.
- Não edite `~/.config/vpn-tray/settings.json`, `/etc/openfortivpn/*`, nem a política
  (`vpnctl policy`, `vpnctl agents`) para ganhar permissão. Se uma ação for recusada por
  configuração, explique ao usuário como ele mesmo pode liberar.
- Não leia nem mostre os `.conf` (eles têm senhas). O `vpn_status` basta.
- Não use `sudo`, nem rode `openfortivpn` ou `systemctl start` à mão. Passe sempre pelo
  MCP ou pelo `vpnctl`: assim valem as travas do usuário.
- Cadastrar uma VPN nova é com o usuário, pelo ícone ("Adicionar VPN…") ou por
  `vpnctl import arquivo.conf`, porque pede a senha dele.

## Referência rápida

```bash
vpnctl status
vpnctl status --json
vpnctl connect work --json
vpnctl disconnect
vpnctl logs work -n 60
```

- `vpnctl status`: estado de cada VPN, VPN padrão, política e permissões.
- `vpnctl status --json`: o mesmo, para ler por script (`overall`: on/off/connecting/error).
- `vpnctl connect work --json`: espera até 120 s. Saída 0 = conectou, 4 = não subiu.
- `vpnctl disconnect`: desconecta a VPN ativa.
- `vpnctl logs work -n 60`: diagnóstico de falha na conexão.
