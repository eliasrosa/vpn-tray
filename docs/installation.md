# Instalação

## Requisitos

| O quê | Por quê | Pacote no Debian/Ubuntu/Mint |
|---|---|---|
| Linux com systemd e polkit | a conexão roda como serviço e o polkit controla quem liga | já vem no sistema |
| [openfortivpn](https://github.com/adrienverge/openfortivpn) 1.21 ou mais novo | o cliente da VPN; `--saml-login` exige 1.21+ | `openfortivpn` |
| Python 3.10 ou mais novo + PyGObject | o app e a CLI | `python3-gi` |
| GTK 3 e notificações | ícone, janelas e avisos | `gir1.2-gtk-3.0`, `gir1.2-notify-0.7` |
| Bandeja do sistema | onde o ícone aparece | `gir1.2-xapp-1.0` (Cinnamon/Mint) **ou** `gir1.2-ayatanaappindicator3-0.1` (GNOME/KDE com AppIndicator) |
| Leitor de SVG *(opcional)* | ícone na janela de log | `librsvg2-common` |

Em Debian, Ubuntu e Mint:

```bash
sudo apt install openfortivpn python3-gi gir1.2-gtk-3.0 gir1.2-notify-0.7 gir1.2-xapp-1.0 librsvg2-common
```

O projeto foi testado no Linux Mint 22 com Cinnamon. A CI roda no Ubuntu 24.04.

Para conferir se está tudo no lugar, sem instalar nada:

```bash
command -v openfortivpn && openfortivpn --version
python3 -c "import gi; gi.require_version('Gtk','3.0'); gi.require_version('Notify','0.7'); print('GTK ok')"
python3 -c "import gi; gi.require_version('XApp','1.0'); print('XApp ok')" \
  || python3 -c "import gi; gi.require_version('AyatanaAppIndicator3','0.1'); print('Ayatana ok')"
```

## Instalar

```bash
git clone https://github.com/eliasrosa/vpn-tray.git
cd vpn-tray
./install.sh
```

Parte de sistema, com `sudo` (uma vez):

| Item | Para onde vai |
|---|---|
| Helper root (validação e escrita de perfis) | `/usr/local/libexec/vpn-tray/vpn-tray-helper` |
| Modelo da regra do polkit | `/usr/local/libexec/vpn-tray/50-vpn-tray.rules.in` |
| Unit do systemd, apontando para o `openfortivpn` do `PATH` | `/etc/systemd/system/vpn-tray@.service` |
| Regra do polkit, gerada a partir da política (que é mantida se já existir) | `/etc/polkit-1/rules.d/50-vpn-tray.rules` |
| Política | `/etc/vpn-tray/policy.json` |
| Metadados sem segredo de cada `/etc/openfortivpn/<nome>.conf` (SAML se o arquivo não tiver `password`; o `config` padrão do pacote é ignorado) | `/etc/openfortivpn/<nome>.args` |

Parte do usuário, sem `sudo`:
- links `~/.local/bin/vpn-tray` e `~/.local/bin/vpnctl` para esta pasta;
- ícone no menu de aplicativos e no autostart;
- VPN padrão, quando houver só um perfil;
- MCP e skill nos agentes encontrados (Claude Code, Kiro). Para pular: `./install.sh --no-agents`.

Como os links apontam para o clone, **a pasta do repositório precisa continuar onde está**.

## Atualizar

```bash
cd vpn-tray
git pull
./install.sh
```

Rode o `./install.sh` sempre que atualizar: ele reaplica a unit, o helper e os links. Os perfis, a política e as suas configurações são mantidos.

## Desinstalar

```bash
./uninstall.sh
```

Remove a unit, a regra do polkit, o helper, a política, os links, o autostart e o registro nos agentes. **Os perfis em `/etc/openfortivpn` ficam**, porque contêm as suas configurações e senhas. Para apagá-los, use "Remover VPN" no menu do ícone antes de desinstalar, ou apague à mão.
