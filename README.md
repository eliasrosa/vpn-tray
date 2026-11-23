# VPN Tray

Ícone na bandeja, CLI e servidor MCP para usar o [openfortivpn](https://github.com/adrienverge/openfortivpn) no Linux, com login SAML/SSO pelo navegador, conexão como serviço do systemd e senha opcional a cada conexão.

[![CI](https://github.com/eliasrosa/vpn-tray/actions/workflows/ci.yml/badge.svg)](https://github.com/eliasrosa/vpn-tray/actions/workflows/ci.yml)
[![CodeQL](https://github.com/eliasrosa/vpn-tray/actions/workflows/codeql.yml/badge.svg)](https://github.com/eliasrosa/vpn-tray/actions/workflows/codeql.yml)
[![semantic-release](https://img.shields.io/badge/semantic--release-conventionalcommits-e10079)](https://github.com/semantic-release/semantic-release)
[![Licença: MIT](https://img.shields.io/badge/licen%C3%A7a-MIT-blue)](LICENSE)

![Menu aguardando o login SAML](docs/screenshots/menu-2-aguardando-login.png)

> Projeto independente. Não tem relação com a Fortinet. FortiGate e FortiClient são marcas da Fortinet, Inc.

## O que ele faz

- **Ícone ao lado do relógio**, que mostra se a VPN está desconectada, conectando, conectada ou com erro. Qualquer clique só abre o menu, então um clique sem querer não derruba a conexão.
- **Login SAML/SSO**: o navegador abre sozinho na página de login da empresa.
- **Conexão como serviço do systemd** (`vpn-tray@<perfil>`): fechar o app não derruba a VPN.
- **Várias VPNs**, com formulário de cadastro, importação de `.conf`, log ao vivo e confiança de certificado com um clique.
- **`vpnctl`**: CLI com saída `--json`.
- **Servidor MCP e skill** para agentes como Claude Code e Kiro. O agente consulta o status e só conecta com a sua confirmação.
- **Segurança em camadas**: regra do polkit restrita ao seu usuário, opção de pedir senha a cada conexão e helper root que só grava campos conhecidos.

## Instalação rápida

```bash
git clone https://github.com/eliasrosa/vpn-tray.git
cd vpn-tray
./install.sh
```

O instalador pede `sudo` uma vez. Antes, veja os requisitos em [docs/installation.md](docs/installation.md).

> **Vai pedir para um agente instalar?** Passe o repositório para ele: as instruções estão em [AGENTS.md](AGENTS.md).

## Documentação

| | |
|---|---|
| [Instalação](docs/installation.md) | requisitos, instalar, atualizar e desinstalar |
| [Uso do ícone](docs/usage.md) | menu, nova VPN, SAML, certificados e log |
| [CLI `vpnctl`](docs/cli.md) | comandos, `--json` e códigos de saída |
| [Agentes (MCP + skill)](docs/agents.md) | Claude Code, Kiro e outros clientes MCP |
| [Segurança](docs/security.md) | camadas de proteção e modelo de ameaças ([reportar falha](SECURITY.md)) |
| [Arquitetura](docs/architecture.md) | hexagonal: domínio, portas, adaptadores |
| [Desenvolvimento](docs/development.md) | testes, lint, teste visual, modo demo e releases |
| [Problemas comuns](docs/troubleshooting.md) | o que fazer quando algo não funciona |
| [Contribuindo](CONTRIBUTING.md) · [Changelog](CHANGELOG.md) | |

## Créditos

- **[openfortivpn](https://github.com/adrienverge/openfortivpn)** (GPL-3.0): o cliente que faz a VPN de verdade. O VPN Tray chama o binário instalado no sistema, sem incluir código dele.
- **[openfortigui](https://github.com/theinvisible/openfortigui)** (GPL-3.0): GUI para o openfortivpn que serviu de inspiração.

## Licença

[MIT](LICENSE).
