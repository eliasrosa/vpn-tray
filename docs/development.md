# Desenvolvimento

## Ambiente

Basta clonar; não há dependências Python de terceiros para rodar. Para desenvolver:

```bash
sudo apt install python3-pytest node
pipx install ruff
```

- `python3-pytest`: os testes.
- `node`: só para testar a regra do polkit.
- `ruff`: lint e formatação.

## Rodar

```bash
python3 -m pytest
ruff check .
ruff format --check .
python3 tests/visual_snapshots.py
./bin/vpn-tray --demo
./bin/vpnctl status
```

- `python3 -m pytest`: todos os testes.
- `ruff check .`: lint.
- `ruff format --check .`: formatação. Sem `--check`, formata.
- `python3 tests/visual_snapshots.py`: o teste visual. Gera os PNGs e um `index.html` em `tests/snapshots/`, que fica fora do git.
- `./bin/vpn-tray --demo`: ícone com VPNs de mentira. A "quebrada" simula o erro de certificado.
- `./bin/vpnctl status`: a CLI direto do clone.

## Testes

| Pasta | O que cobre | Precisa de tela |
|---|---|---|
| `tests/unit/` | domínio, casos de uso (com o sistema em memória) e apresentação do menu | não |
| `tests/adapters/` | cada adaptador (executor de processos falso, pastas temporárias), helper root, unit do systemd, regra do polkit e scripts | não |
| `tests/entrypoints/` | CLI (processo de verdade e em memória), MCP (protocolo e processo), `setup-agents` num `$HOME` falso e ícone GTK | só `test_tray.py` |
| `tests/test_architecture.py` | fronteiras entre camadas, GTK só no ícone e domínio sem I/O | não |
| `tests/test_contract_helper.py` | helper root e domínio recusam as mesmas entradas | não |

Regras:
- nenhum teste toca na VPN real, em `/etc` ou nas suas configurações;
- dados de exemplo são sempre fictícios: perfis `work`/`lab`/`quebrada`, hosts `vpn.example.com`, usuários `alice`/`bob`.

## Onde mexer

| Quero… | Mexa em |
|---|---|
| mudar uma regra (validação, estado) | `vpntray/domain/`, com teste em `tests/unit/test_domain.py` |
| um caso de uso novo | `vpntray/application/`, com uma porta nova em `ports.py` se precisar falar com o mundo |
| integrar com algo do sistema | um adaptador em `vpntray/adapters/` que implemente a porta, mais a versão em `adapters/memory.py` |
| um comando novo na CLI | `vpntray/entrypoints/cli.py`, que só chama casos de uso |
| mexer no menu | `entrypoints/tray/presenter.py` (dados, testável) e depois `app.py` |
| algo que escreve em `/etc` | `system/vpn-tray-helper`, mais um caso em `tests/test_contract_helper.py` |

Veja [architecture.md](architecture.md) para as camadas.

## Commits e versões

Os commits seguem [Conventional Commits](https://www.conventionalcommits.org/), e o [semantic-release](https://github.com/semantic-release/semantic-release) gera a versão, o `CHANGELOG.md` e a release a cada merge na `main`.

| Tipo | Versão |
|---|---|
| `feat` | minor |
| `fix`, `security`, `perf`, `docs(skill)` | patch |
| `feat!` ou `BREAKING CHANGE:` | major |
| `refactor`, `docs`, `test`, `ci`, `build`, `chore`, `style` | nenhuma |

## Fluxo no GitHub

- A `main` é protegida: mudanças entram **só por PR**, com CI verde e histórico linear.
- O merge é **squash**, e o **título do PR vira o commit**, então ele precisa seguir o Conventional Commits (há uma verificação para isso).
- A CI roda:
  - **lint** (ruff e shellcheck);
  - **testes** com tela virtual;
  - **CodeQL**;
  - **revisão de dependências** nos PRs.
- O **Dependabot** atualiza as GitHub Actions (fixadas por SHA) e as ferramentas de release (`package.json`) toda semana.
- O **release** roda depois do merge e só publica versão quando há commits que a justificam. Ele grava o `CHANGELOG.md` e o `VERSION` na `main` usando uma **deploy key** deste repositório (secret `RELEASE_DEPLOY_KEY`), que é a única exceção à regra da branch.
  - **Trocar a chave:** gere outra (`ssh-keygen -t ed25519`), cadastre a pública em *Settings → Deploy keys* com escrita, atualize o secret e apague a antiga.
