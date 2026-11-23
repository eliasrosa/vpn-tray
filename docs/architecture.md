# Arquitetura

O VPN Tray segue a **arquitetura hexagonal** (portas e adaptadores):
- as regras de negócio não sabem que existem GTK, systemd ou terminal;
- quem fala com o mundo são os adaptadores, plugados por contratos (portas).

```mermaid
flowchart LR
    subgraph entrada["entrypoints (adaptadores de entrada)"]
        cli["CLI<br/>vpnctl"]
        mcp["MCP<br/>vpnctl mcp"]
        tray["Ícone GTK<br/>vpn-tray"]
    end
    subgraph app["application (casos de uso)"]
        status[StatusService]
        conn[ConnectionService]
        prof[ProfileService]
        prefs[PreferencesService]
        guard[AgentGuard]
        mon[ConnectionMonitor]
    end
    subgraph dom["domain"]
        rules["regras · modelos · openfortivpn"]
    end
    ports{{"ports<br/>(Protocols)"}}
    subgraph saida["adapters (adaptadores de saída)"]
        sd[systemd / journald]
        fs[arquivos]
        pk[pkexec → helper root]
        dt[xdg-open · /proc · D-Bus]
        mem[memória<br/>testes e demo]
    end
    cli & mcp & tray --> app
    app --> dom
    app --> ports
    saida -. implementam .-> ports
    comp[composition.py] --> saida
    comp --> app
```

## Camadas

| Camada | Pasta | Pode depender de | Contém |
|---|---|---|---|
| Domínio | `vpntray/domain/` | só stdlib (sem I/O) | estados, validação de perfil, leitura do log e do `.conf` do openfortivpn |
| Portas | `vpntray/ports.py` | domínio | contratos (`Protocol`): `ServiceManager`, `Journal`, `JournalFollower`, `ProfileRepository`, `ProfileAdmin`, `SettingsRepository`, `PolicyReader`, `Browser`, `NetworkProbe`, `Clock` |
| Aplicação | `vpntray/application/` | domínio, portas | casos de uso e erros |
| Adaptadores | `vpntray/adapters/` | domínio, portas, `application.errors` | systemd, arquivos, pkexec, área de trabalho, configuração dos agentes e o **sistema em memória** |
| Entrada | `vpntray/entrypoints/` | tudo, via `composition` | `cli.py`, `mcp.py`, `tray/` (GTK) |
| Composição | `vpntray/composition.py` | tudo | `build()` monta o sistema real; `build_memory()` monta o de memória |

O arquivo `tests/test_architecture.py` **reprova o build** se:
- uma camada importar o que não deve;
- algo fora de `entrypoints/tray` importar GTK;
- o domínio fizer I/O.

## Casos de uso

| Caso de uso | Quem usa | O que faz |
|---|---|---|
| `StatusService` | CLI, MCP | retrato das VPNs a partir do systemd e do log de cada execução |
| `ConnectionService` | CLI, MCP | conectar (derrubando outra), esperar subir, avisar o login SAML; desconectar |
| `ConnectionMonitor` | ícone | acompanhar ao vivo e emitir eventos (`auth`, `cert`, `up`, `failed`, `down`), sem GTK |
| `ProfileService` | ícone, CLI | validar, cadastrar, importar, remover e confiar em certificado |
| `PreferencesService` | ícone, CLI | VPN padrão, autoconnect, permissões dos agentes e política |
| `AgentGuard` | MCP | regras para agentes (habilitado, permissões, confirmação) |

## Fluxo: conectar uma VPN SAML pelo ícone

```mermaid
sequenceDiagram
    actor U as Usuário
    participant T as Ícone (GTK)
    participant M as ConnectionMonitor
    participant S as systemd (adapter)
    participant J as journal (follower)
    participant B as Navegador
    U->>T: menu → Conectar work
    T->>M: connect("work") (em thread)
    M->>S: start vpn-tray@work
    Note over S: polkit pode pedir senha
    T->>M: poll() a cada 2 s
    M->>J: seguir a execução (InvocationID)
    J-->>M: "Authenticate at 'https://…'"
    M-->>T: evento auth(url)
    T->>B: abre o login
    J-->>M: "Tunnel is up and running."
    M-->>T: evento up → ícone verde
```

## Decisões

- **O helper root fica fora do pacote.** Ele roda como root via `pkexec` e não pode importar código de uma pasta que o usuário edita. A validação existe nele e no domínio; `tests/test_contract_helper.py` garante que os dois concordam.
- **Sem dependências Python de terceiros.** Só stdlib e PyGObject, que vem do sistema. O MCP implementa o JSON-RPC na mão (são poucas mensagens).
- **O monitor é síncrono e sem GTK.** Quem chama `poll()` é o laço do GTK; nos testes é o próprio teste. Ações que podem bloquear (a senha do polkit) rodam por um *runner* injetável: thread no app real, síncrono nos testes e no demo.
- **O sistema em memória implementa todas as portas.** Testes rápidos (quase 200, em cerca de 1,5 s) e o modo `--demo` usam a mesma simulação.
