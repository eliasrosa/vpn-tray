# Changelog

Todas as mudanças relevantes deste projeto. Seguimos o [Versionamento Semântico](https://semver.org/lang/pt-BR/).
A partir da 1.0.0, este arquivo é atualizado automaticamente pelo semantic-release a partir dos commits.

## 1.0.0 (2026-11-23)

### Novidades

* **bandeja:** ícone ao lado do relógio (XApp/Cinnamon, com AyatanaAppIndicator como alternativa) com quatro estados: desconectada, conectando/aguardando login, conectada e erro.
* **bandeja:** qualquer clique só abre o menu; conectar, desconectar e cancelar são sempre itens do menu.
* **bandeja:** várias VPNs, VPN padrão (★), conectar ao iniciar a sessão e log ao vivo numa janela do próprio app.
* **bandeja:** formulário "Nova VPN" com seções, login SAML ou usuário/senha, avançado recolhido, validação ao vivo, importação de `.conf` e "conectar depois de salvar".
* **saml:** o navegador abre sozinho no login, também quando a conexão é iniciada pela CLI ou por um agente.
* **certificado:** detecta certificado não confiável e oferece "confiar e reconectar", mostrando o SHA256.
* **serviço:** conexão como unit do systemd (`vpn-tray@<perfil>.service`); sair do app não derruba a VPN.
* **cli:** `vpnctl` com `status`, `connect`, `disconnect`, `logs`, `import`, `policy` e `agents`, saída `--json` e códigos de saída previsíveis.
* **mcp:** servidor MCP via stdio, sem dependências (`vpn_status`, `vpn_connect`, `vpn_disconnect`, `vpn_logs`); conectar e desconectar exigem `user_confirmed=true`.
* **agentes:** skill e `vpnctl setup-agents` para registrar no Claude Code e no Kiro (`--dry-run` e `--remove`).
* **instalação:** `install.sh` detecta o `openfortivpn` no `PATH` e importa as configs que já existem em `/etc/openfortivpn`.

### Segurança

* Regra do polkit restrita ao usuário que instalou, numa sessão local e ativa, e só para start, stop e restart de `vpn-tray@*`.
* Política opcional "pedir senha ao conectar" (`AUTH_SELF`), imposta pelo polkit para app, CLI e agentes; mudar a política exige senha de administrador.
* Helper root (via `pkexec`) que só grava campos conhecidos, valida nome, host, porta e hash, e recusa quebras de linha e opções como `pppd-plugin`.
* Senhas só em `/etc/openfortivpn/<nome>.conf` (0600); metadados sem segredo em `<nome>.args` (0644).
