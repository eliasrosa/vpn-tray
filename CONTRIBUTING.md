# Contribuindo

Obrigado pelo interesse! Leia antes:
- [docs/architecture.md](docs/architecture.md): as camadas e onde cada coisa mora;
- [docs/development.md](docs/development.md): como rodar testes, lint e o demo.

## Fluxo

1. Abra uma issue para discutir mudanças grandes. Para bugs, use o modelo "Bug".
2. Crie uma branch a partir da `main` atualizada.
3. Faça a mudança **com testes** e rode:

   ```bash
   ruff check .
   ruff format --check .
   python3 -m pytest
   ```

4. Abra o PR. O **título** segue o Conventional Commits, porque vira o commit do squash e decide a versão.
5. Para entrar na `main` protegida, a CI precisa estar verde: lint, testes, título do PR, CodeQL e revisão de dependências.

## Título do PR: Conventional Commits

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
| `refactor`, `docs`, `test`, `ci`, `build`, `chore`, `style` | não | `test: cobre importação com porta no host` |

Para uma **quebra de compatibilidade** (major, **2**.0.0), use `feat!: …` ou ponha `BREAKING CHANGE: …` no corpo.

Não edite `CHANGELOG.md` nem `VERSION`: o semantic-release atualiza os dois no merge.

## Regras do código

- **Arquitetura hexagonal**: o domínio não faz I/O, a aplicação só conhece portas, e GTK só pode ser usado em `entrypoints/tray`. `tests/test_architecture.py` verifica isso.
- **Adaptador novo**: implemente também em `adapters/memory.py`.
- **Helper root** (`system/vpn-tray-helper`): é autocontido e precisa ser revisado com cuidado redobrado. Toda mudança de validação entra nos dois lados e ganha um caso em `tests/test_contract_helper.py`.
- **Sem dependências Python de terceiros** em runtime.

## Dados de exemplo (repositório público)

Em código, testes, docs e prints, use só valores fictícios:
- **Perfis:** `work`, `lab`, `quebrada`.
- **Hosts:** domínios reservados (`vpn.example.com`, `vpn.example.org`).
- **Usuários:** `alice`, `bob`.
- **Hashes:** `"ab" * 32`.

Nunca use nomes de empresa, hosts ou IPs internos, usuários ou certificados reais.

## Segurança

Vulnerabilidades **não** vão em issue pública. Veja [SECURITY.md](SECURITY.md).
