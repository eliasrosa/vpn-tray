"""Núcleo do VPN Tray, sem GTK: usado pelo app, pela CLI (vpnctl) e pelo MCP.

Tudo aqui é ou função pura (testável sem sistema) ou uma chamada simples e
síncrona ao sistema (systemctl, journalctl, pkexec).

Escopo: só VPN. Testar banco/serviço é com o MCP/ferramenta de cada um.
"""
import json
import os
import re
import subprocess
import time

def _read_version():
    try:
        with open(os.path.join(os.path.dirname(os.path.realpath(__file__)), "VERSION")) as f:
            return f.read().strip()
    except OSError:
        return "0.0.0"


__version__ = _read_version()

CONF_DIR = os.environ.get("VPN_TRAY_CONF_DIR", "/etc/openfortivpn")
POLICY_FILE = os.environ.get("VPN_TRAY_POLICY", "/etc/vpn-tray/policy.json")
HELPER = "/usr/local/libexec/vpn-tray/vpn-tray-helper"
CFG_FILE = os.environ.get("VPN_TRAY_SETTINGS") or os.path.join(
    os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"),
    "vpn-tray", "settings.json")
APP_DBUS_NAME = "br.local.vpntray"

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
HOST_RE = re.compile(r"^[A-Za-z0-9.-]{1,253}$")
HASH_RE = re.compile(r"^[0-9a-f]{64}$")

OFF, CONNECTING, ON, ERROR = "off", "connecting", "on", "error"
LABEL = {OFF: "desconectada", CONNECTING: "conectando…", ON: "conectada", ERROR: "erro"}
DOT = {OFF: "○", CONNECTING: "◐", ON: "●", ERROR: "✕"}

RE_AUTH = re.compile(r"Authenticate at '([^']+)'")
RE_CERT = re.compile(r"trusted-cert\s*=\s*([0-9a-f]{64})")
RE_UP = re.compile(r"Tunnel is up and running")
RE_ERR = re.compile(r"ERROR:\s*(.+)")

DEFAULT_SETTINGS = {
    "default": None,
    "autoconnect": False,
    # O que agentes (MCP/CLI em nome de um agente) podem fazer. A trava de
    # verdade é a política do polkit (senha ao conectar); isto aqui é a
    # preferência — um agente com acesso ao seu $HOME consegue editar.
    "agents": {"enabled": True, "allow_connect": True, "allow_disconnect": True},
}


def unit_of(name):
    return f"vpn-tray@{name}.service"


# =========================================================== funções puras
def parse_args_file(text):
    """Conteúdo de /etc/openfortivpn/<nome>.args -> dict."""
    meta = {}
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            meta[k.strip()] = v.strip()
    return meta


def parse_unit_show(out):
    """Saída de `systemctl show -p Id,ActiveState,InvocationID u1 u2` -> {nome: props}."""
    result, cur = {}, {}
    for line in out.splitlines() + [""]:
        if not line.strip():
            uid = cur.get("Id", "")
            if uid.startswith("vpn-tray@") and uid.endswith(".service"):
                result[uid[len("vpn-tray@"):-len(".service")]] = cur
            cur = {}
            continue
        k, _, v = line.partition("=")
        cur[k] = v
    return result


def profile_state(active_state, tunnel_up):
    if active_state == "failed":
        return ERROR
    if active_state in ("active", "activating"):
        return ON if tunnel_up else CONNECTING
    if active_state == "deactivating":
        return CONNECTING
    return OFF


def overall_state(states, external=False):
    vals = set(states.values())
    for s in (ON, CONNECTING, ERROR):
        if s in vals:
            return s
    return ON if external else OFF


def first_with(states, wanted):
    return next((k for k, v in states.items() if v == wanted), None)


def tooltip_for(overall, states, default, waiting_login=False, external=False):
    if overall == ON:
        return f"VPN conectada ({first_with(states, ON) or 'fora do app'})"
    if overall == CONNECTING:
        n = first_with(states, CONNECTING)
        return f"VPN {n}: " + ("aguardando login no navegador" if waiting_login else "conectando…")
    if overall == ERROR:
        return "VPN: erro na última conexão — clique para ver"
    if default:
        return f"VPN desconectada — clique para conectar ({default})"
    return "VPN: nenhuma cadastrada — clique para adicionar"


def menu_spec(profiles, states, default, info, external=False, autoconnect=False,
              security=None):
    """Descreve o menu como dados (testável sem GTK).

    info: {nome: {"auth_url", "tunnel_up", "cert", "error"}}
    security: {"require_password": bool, "agents_connect": bool, "agents_disconnect": bool}
    Entradas:
      ("label", texto)                      — informativo, não clicável
      ("item", texto, (ação, *args))        — clicável
      ("sep",)
      ("check", texto, ativo, (ação,))
      ("radio", texto, [(nome, ativo, (ação, nome)), ...])  — submenu de rádio
      ("submenu", texto, [entradas...])
    """
    spec = []
    if not profiles:
        spec.append(("label", "Nenhuma VPN cadastrada"))
    for name in profiles:
        st = states.get(name, OFF)
        i = info.get(name, {})
        star = " ★" if name == default else ""
        spec.append(("label", f"{DOT[st]}  {name}{star} — {LABEL[st]}"))
        if st == ON:
            spec.append(("item", f"Desconectar {name}", ("disconnect", name)))
        elif st == CONNECTING:
            if i.get("auth_url") and not i.get("tunnel_up"):
                spec.append(("item", "Abrir login no navegador", ("open_url", i["auth_url"])))
            spec.append(("item", f"Cancelar conexão {name}", ("disconnect", name)))
        else:
            spec.append(("item", f"Conectar {name}", ("connect", name)))
        if i.get("cert"):
            spec.append(("item", "Confiar no certificado e reconectar…",
                         ("trust_cert", name, i["cert"])))
        if st == ERROR and i.get("error"):
            spec.append(("label", f"Erro: {i['error'][:70]}"))
        spec.append(("sep",))
    if external:
        spec.append(("label", "openfortivpn rodando fora do app (alias?)"))
        spec.append(("sep",))

    spec.append(("item", "Adicionar VPN…", ("add",)))
    if profiles:
        spec.append(("submenu", "Ver log",
                     [("item", n, ("log", n)) for n in profiles]))
    if len(profiles) > 1:
        spec.append(("radio", "VPN padrão",
                     [(n, n == default, ("set_default", n)) for n in profiles]))
    spec.append(("check", "Conectar a padrão ao iniciar a sessão",
                 bool(autoconnect), ("toggle_autoconnect",)))
    sec = security or {}
    spec.append(("submenu", "Segurança", [
        ("check", "Pedir senha ao conectar (vale para app, CLI e agentes)",
         bool(sec.get("require_password")), ("toggle_require_password",)),
        ("check", "Agentes (MCP) podem conectar",
         bool(sec.get("agents_connect")), ("toggle_agents", "allow_connect")),
        ("check", "Agentes (MCP) podem desconectar",
         bool(sec.get("agents_disconnect")), ("toggle_agents", "allow_disconnect")),
    ]))
    if profiles:
        spec.append(("submenu", "Remover VPN",
                     [("item", n, ("remove", n)) for n in profiles]))
    spec.append(("sep",))
    spec.append(("item", "Sair do app (a VPN continua como está)", ("quit",)))
    return spec


def validate_new_profile(data, existing):
    """Retorna mensagem de erro ou None. Mesmas regras do helper root."""
    name = data.get("name", "")
    if not name:
        return "Dê um nome para a VPN."
    if not NAME_RE.match(name):
        return "Nome: só letras minúsculas, números, - e _ (até 32)."
    if name in existing:
        return f"Já existe uma VPN chamada “{name}”."
    if not data.get("host"):
        return "Informe o servidor."
    if not HOST_RE.match(data.get("host", "")):
        return "Servidor inválido (ex.: vpn.example.com)."
    try:
        port = int(data.get("port") or 0)
    except (TypeError, ValueError):
        port = 0
    if not 0 < port < 65536:
        return "Porta inválida."
    if data.get("auth") == "password" and not (data.get("username") and data.get("password")):
        return "Informe usuário e senha."
    cert = (data.get("trusted_cert") or "").lower().replace(":", "")
    if cert and not HASH_RE.match(cert):
        return "Certificado: cole o SHA256 em hex (64 caracteres)."
    for k, v in data.items():
        if isinstance(v, str) and any(c in v for c in "\r\n\0"):
            return f"Campo inválido: {k}"
    return None


def parse_openfortivpn_conf(text, name=None):
    """Arquivo de config do openfortivpn (ex.: /etc/openfortivpn/config) ->
    dados do formulário. Só pega as chaves que o VPN Tray sabe gravar."""
    kv = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip()
        if k == "trusted-cert":
            kv.setdefault("trusted-cert", []).append(v)
        else:
            kv[k] = v
    host = kv.get("host", "")
    port = kv.get("port", "443")
    if ":" in host and not host.startswith("["):  # host = vpn.example.net:10443
        host, _, port = host.partition(":")
    data = {
        "name": name or "",
        "host": host,
        "port": int(port) if str(port).isdigit() else 443,
        "auth": "password" if kv.get("password") else "saml",
        "username": kv.get("username", ""),
        "password": kv.get("password", ""),
        "realm": kv.get("realm", ""),
        "trusted_cert": (kv.get("trusted-cert") or [""])[0],
    }
    ignored = sorted(k for k in kv if k not in (
        "host", "port", "username", "password", "realm", "trusted-cert"))
    return data, ignored


# ============================================================ configuração
def load_settings(path=None):
    path = path or CFG_FILE
    data = json.loads(json.dumps(DEFAULT_SETTINGS))
    try:
        with open(path) as f:
            saved = json.load(f)
    except (OSError, ValueError):
        saved = {}
    for k, v in saved.items():
        if isinstance(v, dict) and isinstance(data.get(k), dict):
            data[k].update(v)
        else:
            data[k] = v
    return data


def save_settings(data, path=None):
    path = path or CFG_FILE
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def load_policy(path=None):
    try:
        with open(path or POLICY_FILE) as f:
            p = json.load(f)
    except (OSError, ValueError):
        p = {}
    return {"require_password_connect": bool(p.get("require_password_connect"))}


# ================================================================ sistema
def run(argv, timeout=15, input_text=None):
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                           input=input_text)
        return r.returncode, r.stdout, r.stderr.strip()
    except FileNotFoundError as e:
        return 127, "", str(e)
    except subprocess.TimeoutExpired:
        return 124, "", "tempo esgotado"


def list_profiles(conf_dir=None):
    conf_dir = conf_dir or CONF_DIR
    out = {}
    try:
        entries = sorted(os.listdir(conf_dir))
    except OSError:
        return out
    for fn in entries:
        name = fn[:-5]
        if fn.endswith(".args") and NAME_RE.match(name):
            try:
                with open(os.path.join(conf_dir, fn)) as f:
                    out[name] = parse_args_file(f.read())
            except OSError:
                pass
    return out


def unit_props(names):
    if not names:
        return {}
    code, out, _ = run(["systemctl", "show", "-p", "Id,ActiveState,InvocationID"]
                       + [unit_of(n) for n in names])
    return parse_unit_show(out) if code == 0 else {}


def invocation_lines(invocation):
    if not invocation:
        return []
    _c, out, _e = run(["journalctl", f"_SYSTEMD_INVOCATION_ID={invocation}",
                       "-o", "cat", "--no-pager"])
    return out.splitlines()


def summarize_lines(lines):
    info = {"auth_url": None, "tunnel_up": False, "cert": None, "error": None}
    for line in lines:
        m = RE_AUTH.search(line)
        if m and not info["auth_url"]:
            info["auth_url"] = m.group(1)
        m = RE_CERT.search(line)
        if m and not info["cert"]:
            info["cert"] = m.group(1)
        if RE_UP.search(line):
            info["tunnel_up"] = True
        m = RE_ERR.search(line)
        if m:
            info["error"] = m.group(1).strip()
    return info


def ppp_interfaces():
    try:
        return sorted(n for n in os.listdir("/sys/class/net") if n.startswith("ppp"))
    except OSError:
        return []


def external_running():
    """openfortivpn rodando fora das units do app (ex.: um alias/script próprio)."""
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            with open(f"/proc/{pid}/comm") as f:
                if f.read().strip() != "openfortivpn":
                    continue
            with open(f"/proc/{pid}/cgroup") as g:
                if "vpn-tray@" not in g.read():
                    return True
        except OSError:
            continue
    return False


def status(conf_dir=None, settings=None):
    """Retrato completo, para CLI/MCP."""
    settings = settings or load_settings()
    profiles = list_profiles(conf_dir)
    props = unit_props(list(profiles))
    result = {"profiles": {}, "default": None, "overall": OFF,
              "ppp": ppp_interfaces(), "external_openfortivpn": False,
              "policy": load_policy(), "agents": settings.get("agents", {})}
    states = {}
    for name, meta in profiles.items():
        p = props.get(name, {})
        active = p.get("ActiveState", "inactive")
        info = summarize_lines(invocation_lines(p.get("InvocationID"))) \
            if active in ("active", "activating", "failed") else \
            {"auth_url": None, "tunnel_up": False, "cert": None, "error": None}
        st = profile_state(active, info["tunnel_up"])
        states[name] = st
        result["profiles"][name] = {
            "state": st, "label": LABEL[st], "unit": unit_of(name),
            "systemd": active, "auth": meta.get("VPN_AUTH", "?"),
            "host": meta.get("VPN_HOST", ""),
            "waiting_browser_login": bool(info["auth_url"] and not info["tunnel_up"]
                                          and st == CONNECTING),
            "login_url": info["auth_url"] if st == CONNECTING else None,
            "untrusted_cert": info["cert"], "last_error": info["error"] if st == ERROR else None,
        }
    d = settings.get("default")
    result["default"] = d if d in profiles else next(iter(profiles), None)
    ext = not any(s in (ON, CONNECTING) for s in states.values()) and external_running()
    result["external_openfortivpn"] = ext
    result["overall"] = overall_state(states, ext)
    return result


def systemctl(verb, name, timeout=120):
    """start/stop. Com a política 'pedir senha', o polkit abre a caixinha
    de senha na sessão gráfica — por isso o timeout é longo."""
    return run(["systemctl", verb, unit_of(name)], timeout=timeout)


def tray_running():
    code, out, _ = run(["gdbus", "call", "--session", "--dest", "org.freedesktop.DBus",
                        "--object-path", "/org/freedesktop/DBus", "--method",
                        "org.freedesktop.DBus.NameHasOwner", APP_DBUS_NAME], timeout=5)
    return code == 0 and "true" in out


def open_browser(url):
    run(["xdg-open", url], timeout=10)


def wait_for(name, timeout=120, on_login_url=None, poll=1.0, clock=time.monotonic,
             sleep=time.sleep):
    """Espera a unit ficar ON (ou falhar). Devolve o status do perfil."""
    start = clock()
    deadline = start + timeout
    announced = False
    while True:
        st = status()["profiles"].get(name, {})
        state = st.get("state")
        if state in (ON, ERROR):
            return st
        if state == OFF and clock() - start > 3:  # parou/nem subiu
            return st
        if st.get("login_url") and not announced:
            announced = True
            on_login_url and on_login_url(st["login_url"])
        if clock() >= deadline:
            return st
        sleep(poll)


def logs(name, lines=80):
    _c, out, err = run(["journalctl", "-u", unit_of(name), "-n", str(lines),
                        "-o", "short-iso", "--no-pager"])
    return out or err


def helper(args, stdin_text=None, timeout=300):
    """Ações privilegiadas (pkexec pede a senha numa caixinha gráfica)."""
    if not os.path.exists(HELPER):
        return 1, "", "VPN Tray não está instalado: rode o install.sh."
    return run(["pkexec", HELPER] + list(args), timeout=timeout, input_text=stdin_text)
