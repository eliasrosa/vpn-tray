## O que muda

<!-- Uma ou duas frases. O título do PR segue Conventional Commits (ex.: "fix(cli): …"). -->

## Por quê

<!-- Issue relacionada ou motivo. -->

## Como testei

- [ ] `ruff check .` e `ruff format --check .`
- [ ] `python3 -m pytest`
- [ ] Mudança de interface? Rodei `python3 tests/visual_snapshots.py` e conferi os PNGs
- [ ] Testei na máquina real (descreva abaixo, se aplicável)

## Checklist

- [ ] Respeita as camadas (`tests/test_architecture.py` passa) e tem testes para o comportamento novo
- [ ] Mexi em validação? Atualizei domínio **e** `system/vpn-tray-helper` + `tests/test_contract_helper.py`
- [ ] Só dados fictícios (perfis `work`/`lab`, hosts `*.example.com`, usuários `alice`/`bob`) — nada de empresa, IP interno, usuário ou certificado real
- [ ] Não editei `CHANGELOG.md` nem `VERSION` (o semantic-release cuida)
