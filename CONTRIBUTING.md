# Contribuindo

## Commits: Conventional Commits

As versões e o `CHANGELOG.md` são gerados pelo [semantic-release](https://github.com/semantic-release/semantic-release) a partir das mensagens de commit. O formato é:

```text
<tipo>(<escopo opcional>): <descrição no imperativo>
```

| Tipo | Gera versão | Exemplo |
|---|---|---|
| `feat` | minor (1.**1**.0) | `feat(cli): adiciona vpnctl restart` |
| `fix` | patch (1.0.**1**) | `fix(saml): não reabre o navegador ao reiniciar o app` |
| `security` | patch | `security(helper): recusa host com espaço` |
| `perf` | patch | `perf: lê o journal uma vez só` |
| `docs(skill)` | patch | `docs(skill): explica a política de senha` |
| `docs`, `test`, `refactor`, `ci`, `chore` | não | `test: cobre importação com porta no host` |

Para uma **quebra de compatibilidade** (major, **2**.0.0), coloque `!` depois do tipo (`feat!: …`) ou uma linha `BREAKING CHANGE: …` no corpo do commit.

## Antes de abrir o PR

```bash
python3 -m pytest -q tests
python3 tests/visual_snapshots.py
```

- Os testes têm que passar. Nenhum deles pode depender de VPN real, de root ou da sua configuração.
- O teste visual vale quando você mexe na interface: confira os PNGs em `tests/snapshots/`.

## Dados de exemplo

Em código, testes, docs e prints, use só valores fictícios:
- **Perfis:** `work`, `lab`, `quebrada`.
- **Hosts:** domínios reservados (`vpn.example.com`, `vpn.example.org`).
- **Usuários:** `alice`, `bob`.
- **Hashes:** `"ab" * 32`.

Nunca use nomes de empresa, hosts ou IPs internos, usuários ou certificados reais.
