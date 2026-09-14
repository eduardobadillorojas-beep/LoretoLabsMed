from contextvars import ContextVar
from contextlib import contextmanager


_importando = ContextVar('loreto_sync_importando', default=False)


def esta_importando():
    return _importando.get()


@contextmanager
def importar_desde_servidor():
    token = _importando.set(True)
    try:
        yield
    finally:
        _importando.reset(token)
