"""Adaptador de configuração de agentes: registra o MCP `vpn-tray` e a skill
no Claude Code e no Kiro.

Chamado por `vpnctl setup-agents [--claude] [--kiro] [--dry-run] [--remove]`.
Sem flags, faz os dois. Sempre guarda backup antes de mexer em JSON.
"""

import glob
import json
import os
import shutil
import subprocess
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
VPNCTL = os.path.expanduser("~/.local/bin/vpnctl")
SKILL_SRC = os.path.join(ROOT, "agent", "SKILL.md")
SERVER = "vpn-tray"
READ_ONLY = ["vpn_status", "vpn_logs"]


def claude_bin():
    found = shutil.which("claude")
    if found:
        return found
    cands = glob.glob(os.path.expanduser("~/.config/Claude/claude-code/*/*/claude"))
    cands = [c for c in cands if os.access(c, os.X_OK)]
    return max(cands, key=os.path.getmtime) if cands else None


def backup(path):
    if os.path.exists(path):
        dst = f"{path}.bak-vpn-tray-{time.strftime('%Y%m%d-%H%M%S')}"
        shutil.copy2(path, dst)
        return dst
    return None


def link_skill(dest_dir, dry, remove, log):
    target = os.path.join(dest_dir, "SKILL.md")
    if remove:
        if os.path.islink(target) or os.path.exists(target):
            log(f"remover skill {dest_dir}")
            if not dry:
                shutil.rmtree(dest_dir, ignore_errors=True)
        return
    log(f"skill: {target} -> {SKILL_SRC}")
    if dry:
        return
    os.makedirs(dest_dir, exist_ok=True)
    if os.path.islink(target) or os.path.exists(target):
        os.remove(target)
    os.symlink(SKILL_SRC, target)  # link: atualizar o repo atualiza a skill


def setup_claude(dry, remove, log):
    exe = claude_bin()
    if not exe:
        log("Claude Code: CLI `claude` não encontrada — pulei.")
        return False
    run = (
        (lambda *a: log("$ " + " ".join(a)))
        if dry
        else (lambda *a: subprocess.run(a, capture_output=True, text=True))
    )
    run(exe, "mcp", "remove", "-s", "user", SERVER)
    if not remove:
        r = run(exe, "mcp", "add", "-s", "user", SERVER, "--", VPNCTL, "mcp")
        if r is not None and r.returncode != 0:
            log(f"Claude Code: falhou ao registrar: {r.stderr.strip()}")
            return False
        log(f"Claude Code: MCP '{SERVER}' registrado (escopo usuário).")

    # Ferramentas só-leitura liberadas sem prompt; conectar/desconectar seguem
    # pedindo aprovação no Claude (fora a confirmação que o próprio MCP exige).
    settings = os.path.expanduser("~/.claude/settings.json")
    try:
        with open(settings) as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    allow = data.setdefault("permissions", {}).setdefault("allow", [])
    wanted = [f"mcp__{SERVER}__{t}" for t in READ_ONLY]
    new = [w for w in allow if w not in wanted] if remove else allow + [w for w in wanted if w not in allow]
    if new != allow:
        log(("remover" if remove else "liberar sem prompt") + ": " + ", ".join(wanted) + f" em {settings}")
        if not dry:
            backup(settings)
            data["permissions"]["allow"] = new
            with open(settings, "w") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.write("\n")
    link_skill(os.path.expanduser("~/.claude/skills/vpn-tray"), dry, remove, log)
    return True


def setup_kiro(dry, remove, log):
    path = os.path.expanduser("~/.kiro/settings/mcp.json")
    if not os.path.isdir(os.path.dirname(path)):
        log("Kiro: ~/.kiro/settings não existe — pulei.")
        return False
    try:
        with open(path) as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    servers = data.setdefault("mcpServers", {})
    if remove:
        changed = servers.pop(SERVER, None) is not None
        log(f"Kiro: remover MCP '{SERVER}' de {path}" if changed else "Kiro: nada a remover")
    else:
        servers[SERVER] = {"command": VPNCTL, "args": ["mcp"], "disabled": False, "autoApprove": READ_ONLY}
        changed = True
        log(f"Kiro: MCP '{SERVER}' em {path} (autoApprove só leitura)")
    if changed and not dry:
        b = backup(path)
        b and log(f"  backup: {b}")
        with open(path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
    link_skill(os.path.expanduser("~/.kiro/skills/vpn-tray"), dry, remove, log)
    return True


def main(claude=False, kiro=False, dry_run=False, remove=False, log=print):
    if not (claude or kiro):
        claude = kiro = True
    ok = True
    if claude:
        ok &= setup_claude(dry_run, remove, log)
    if kiro:
        ok &= setup_kiro(dry_run, remove, log)
    if not dry_run and not remove:
        log("Reinicie a sessão do agente para ele enxergar o MCP novo.")
    return 0 if ok else 1
