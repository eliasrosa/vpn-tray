#!/usr/bin/env bash
# Instala o VPN Tray. Pede sudo para a parte de sistema (unit, polkit, helper).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"

OFV="$(command -v openfortivpn || true)"
if [ -z "$OFV" ]; then
  echo "openfortivpn não encontrado. Instale antes (ex.: sudo apt install openfortivpn)." >&2
  exit 1
fi
for cmd in pkexec systemctl journalctl python3; do
  command -v "$cmd" >/dev/null || { echo "Falta o comando: $cmd" >&2; exit 1; }
done

echo "==> Parte de sistema (sudo)"
sudo install -Dm755 -o root -g root "$HERE/system/vpn-tray-helper" /usr/local/libexec/vpn-tray/vpn-tray-helper
sed "s#@OPENFORTIVPN@#$OFV#" "$HERE/system/vpn-tray@.service" \
  | sudo install -Dm644 -o root -g root /dev/stdin /etc/systemd/system/vpn-tray@.service
sudo install -Dm644 -o root -g root "$HERE/system/50-vpn-tray.rules.in" /usr/local/libexec/vpn-tray/50-vpn-tray.rules.in
# regra do polkit gerada a partir da política (mantém "pedir senha" se já estava ligada)
sudo /usr/local/libexec/vpn-tray/vpn-tray-helper policy apply
sudo systemctl daemon-reload

# Configs que já existem em /etc/openfortivpn/<nome>.conf: cria o <nome>.args
# (sem segredo) para o app enxergar. Com "password" no arquivo = usuário/senha;
# sem = SAML. O "config" padrão do pacote é ignorado.
for conf in $(sudo find /etc/openfortivpn -maxdepth 1 -name '*.conf' -printf '%f\n' 2>/dev/null); do
  name="${conf%.conf}"
  [[ "$name" =~ ^[a-z0-9][a-z0-9_-]{0,31}$ ]] || continue
  [ "$name" = "config" ] && continue
  if ! sudo test -e "/etc/openfortivpn/$name.args"; then
    host=$(sudo awk -F= '/^[[:space:]]*host[[:space:]]*=/{gsub(/[[:space:]]/,"",$2);print $2;exit}' "/etc/openfortivpn/$conf")
    if sudo grep -qE '^[[:space:]]*password[[:space:]]*=' "/etc/openfortivpn/$conf"; then
      auth=password; extra=""
    else
      auth=saml; extra="--saml-login"
    fi
    printf '# lido pelo vpn-tray@.service e pelo app (sem segredos aqui)\nEXTRA_ARGS=%s\nVPN_HOST=%s\nVPN_AUTH=%s\n' "$extra" "$host" "$auth" \
      | sudo install -m644 -o root -g root /dev/stdin "/etc/openfortivpn/$name.args"
    echo "    perfil importado: $name ($auth)"
  fi
done

echo "==> Parte do usuário"
chmod +x "$HERE/vpn_tray.py"
mkdir -p ~/.local/bin ~/.local/share/applications ~/.config/autostart
ln -sf "$HERE/vpn_tray.py" ~/.local/bin/vpn-tray
chmod +x "$HERE/vpnctl"
ln -sf "$HERE/vpnctl" ~/.local/bin/vpnctl
DESKTOP="[Desktop Entry]
Type=Application
Name=VPN Tray
Comment=Liga/desliga VPN (openfortivpn) pelo ícone ao lado do relógio
Exec=$HOME/.local/bin/vpn-tray
Icon=$HERE/icons/vpn-on.svg
Terminal=false
Categories=Network;
X-GNOME-Autostart-enabled=true"
echo "$DESKTOP" > ~/.local/share/applications/vpn-tray.desktop
echo "$DESKTOP" > ~/.config/autostart/vpn-tray.desktop

# padrão inicial: se houver exatamente um perfil e ainda não houver padrão
CFG=~/.config/vpn-tray/settings.json
mapfile -t ARGS_FILES < <(ls /etc/openfortivpn/*.args 2>/dev/null)
if [ ! -f "$CFG" ] && [ "${#ARGS_FILES[@]}" -eq 1 ]; then
  only="$(basename "${ARGS_FILES[0]}" .args)"
  mkdir -p ~/.config/vpn-tray && printf '{"default": "%s"}\n' "$only" > "$CFG"
fi

pkill -f "\.local/bin/vpn-tray$|vpn_tray.py$" 2>/dev/null || true
nohup "$HOME/.local/bin/vpn-tray" >/dev/null 2>&1 &

if [ "${1:-}" != "--no-agents" ]; then
  echo "==> Agentes (MCP + skill)"
  "$HOME/.local/bin/vpnctl" setup-agents || true
fi

echo "Pronto: ícone ao lado do relógio (abre a cada login) e \`vpnctl\` no terminal."
