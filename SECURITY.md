# Segurança

## Como reportar

Encontrou uma vulnerabilidade? **Não abra uma issue pública.** Use o
[reporte privado de vulnerabilidades do GitHub](https://github.com/eliasrosa/vpn-tray/security/advisories/new).
Descreva o impacto e como reproduzir. Não inclua credenciais, hosts nem certificados reais.

## O que o VPN Tray protege

| Superfície | Proteção |
|---|---|
| Ligar e desligar a VPN | Regra do polkit restrita ao seu usuário, numa sessão local e ativa, só para `vpn-tray@*` e só para start, stop e restart. |
| Conectar sem você ver | Política opcional "pedir senha ao conectar" (`AUTH_SELF`), que vale para app, CLI, agentes e `systemctl` direto. |
| Desligar essa trava | Mudar a política, nos dois sentidos, exige senha de administrador (`pkexec`). |
| Agentes (MCP) | `user_confirmed=true` obrigatório para conectar ou desconectar, mais as permissões `agents.*`. Essas permissões são preferência do usuário, não trava. |
| Escrita como root | O helper aceita só campos conhecidos, valida tudo e recusa quebras de linha e opções como `pppd-plugin`. |
| Segredos | Senhas só em `/etc/openfortivpn/<nome>.conf` (0600). O `.args`, o status e os logs do app não contêm senha. |

## Fora do escopo

- **O próprio openfortivpn.** Problemas nele devem ser reportados ao [projeto oficial](https://github.com/adrienverge/openfortivpn/security).
- **Quem já tem root na máquina, ou acesso de escrita ao seu `$HOME`.** Essa pessoa já consegue mudar `settings.json` e o autostart.
