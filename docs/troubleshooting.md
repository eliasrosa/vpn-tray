# Problemas comuns

### O ícone não aparece

- **Não está rodando.** Teste com `pgrep -af vpn-tray` e abra com `~/.local/bin/vpn-tray &`.
- **Falta a biblioteca de bandeja.** Veja os requisitos em [installation.md](installation.md):
  - XApp, no Cinnamon/Mint;
  - AyatanaAppIndicator, no GNOME (que também precisa da extensão AppIndicator) e no KDE.
- **Ele não abre ao iniciar a sessão.** Confira se existe `~/.config/autostart/vpn-tray.desktop`.

### "VPN Tray não está instalado: rode o install.sh"

O helper root não foi instalado. Rode `./install.sh` na pasta do repositório.

### Pede senha toda vez que conecto

Isso é a política **pedir senha ao conectar**. Para desligar, use o menu **Segurança** ou `vpnctl policy require-password off` (pede senha de administrador).

### O navegador não abriu no login SAML

- Use o item **Abrir login no navegador** no menu, ou `vpnctl status --json`, que mostra o `login_url`.
- Pela CLI, `vpnctl connect --no-browser` imprime a URL.
- Confira se `xdg-open https://example.com` abre o seu navegador.

### "Gateway certificate validation failed"

O servidor apresentou um certificado fora da lista de confiança. Use **Confiar no certificado e reconectar…** no menu, mas só depois de conferir o SHA256 com quem administra a VPN.

### A VPN conecta mas não alcanço um serviço interno

O VPN Tray só garante o túnel. Com `vpnctl status` em `conectada`, o problema está em rota, DNS ou no próprio serviço. Para conferir a rota e o DNS que a VPN aplicou, veja `vpnctl logs -n 40`.

### O agente não vê as ferramentas `vpn_*`

1. Confira o registro: `claude mcp get vpn-tray` ou o arquivo `~/.kiro/settings/mcp.json`.
2. Abra uma **sessão nova** do agente, porque os MCPs são carregados ao iniciar.
3. Refaça o registro com `vpnctl setup-agents`.

### Usei um alias com `sudo openfortivpn` antes

O app mostra "openfortivpn rodando fora do app" e não consegue controlar essa conexão. Encerre o processo antigo e passe a usar o ícone ou o `vpnctl`. Coloque a config em `/etc/openfortivpn/<nome>.conf` e rode `./install.sh`, ou use `vpnctl import`.

### Ver o que está acontecendo

```bash
vpnctl status
vpnctl logs -f
journalctl -u 'vpn-tray@*' -n 100
```

- `vpnctl status`: estado de tudo.
- `vpnctl logs -f`: log ao vivo da VPN padrão.
- `journalctl -u 'vpn-tray@*' -n 100`: todas as VPNs.
