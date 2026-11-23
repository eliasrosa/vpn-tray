#!/usr/bin/env bash
# Remove o VPN Tray (mantém seus .conf em /etc/openfortivpn).
set -euo pipefail
pkill -f "\.local/bin/vpn-tray$|bin/vpn-tray$" 2>/dev/null || true
~/.local/bin/vpnctl setup-agents --remove 2>/dev/null || true
while IFS= read -r unit; do
  if [ -n "$unit" ]; then sudo systemctl stop "$unit"; fi
done < <(systemctl list-units 'vpn-tray@*' --plain --no-legend | awk '{print $1}')
sudo rm -f /etc/systemd/system/vpn-tray@.service /etc/polkit-1/rules.d/50-vpn-tray.rules
sudo rm -rf /usr/local/libexec/vpn-tray /etc/vpn-tray
sudo systemctl daemon-reload
rm -f ~/.local/bin/vpn-tray ~/.local/bin/vpnctl ~/.local/share/applications/vpn-tray.desktop ~/.config/autostart/vpn-tray.desktop
echo "Removido. Os perfis em /etc/openfortivpn/*.conf foram mantidos (.args também)."
