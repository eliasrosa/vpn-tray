"""Erros da aplicação (mensagens prontas para o usuário)."""


class VpnTrayError(Exception):
    """Base."""


class NotFound(VpnTrayError):
    pass


class AuthenticationDenied(VpnTrayError):
    def __init__(self, message: str = "Senha não confirmada (política “pedir senha ao conectar”)."):
        super().__init__(message)


class StartFailed(VpnTrayError):
    pass


class AdminError(VpnTrayError):
    """Falha no helper privilegiado."""


class AdminCancelled(AdminError):
    """Usuário cancelou a senha do pkexec."""


class InvalidProfile(VpnTrayError):
    pass


class PermissionDenied(VpnTrayError):
    """Preferência do usuário proíbe a ação (ex.: agentes não podem conectar)."""


class ConfirmationRequired(VpnTrayError):
    pass
