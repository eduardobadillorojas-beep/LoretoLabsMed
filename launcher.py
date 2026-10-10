"""Lanzador de Loreto One Desktop para Windows 10/11 de 64 bits."""

from __future__ import annotations

import http.client
import io
import json
import logging
import os
from pathlib import Path
import secrets
import sys
import threading
import time
import uuid
from urllib.error import HTTPError


APP_NAME = "Loreto One"
HOST = "127.0.0.1"
PORT = 8765
URL = f"http://{HOST}:{PORT}/"

# launcher.py está en la raíz del proyecto.
PROJECT_DIR = Path(__file__).resolve().parent

if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

DATA_DIR = (
    Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    / "LoretoOne"
)

LOG_DIR = DATA_DIR / "logs"


def configure_environment() -> None:
    """Prepara el entorno local de Loreto One Desktop."""

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    secret_file = DATA_DIR / "desktop-secret.key"

    if not secret_file.exists():
        secret_file.write_text(
            secrets.token_urlsafe(64),
            encoding="utf-8",
        )

    os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings_desktop"
    os.environ["LORETO_DESKTOP_DATA_DIR"] = str(DATA_DIR)
    os.environ["LORETO_DESKTOP_SECRET_KEY"] = (
        secret_file.read_text(encoding="utf-8").strip()
    )
    os.environ["LORETO_DESKTOP_MODE"] = "1"

    # Desktop nunca debe conectarse directamente a PostgreSQL/Render.
    os.environ.pop("RENDER", None)
    os.environ.pop("DATABASE_URL", None)


def configure_logging() -> None:
    """Configura el archivo de registro del programa."""

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        filename=LOG_DIR / "desktop.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        encoding="utf-8",
        force=True,
    )


def server_is_ready() -> bool:
    """Comprueba si el servidor local de Loreto One responde."""

    connection = None

    try:
        connection = http.client.HTTPConnection(
            HOST,
            PORT,
            timeout=1,
        )

        connection.request("GET", "/login/")
        response = connection.getresponse()
        response.read(32)

        return response.status < 500

    except OSError:
        return False

    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass


def find_edge() -> Path | None:
    """Localiza Microsoft Edge."""

    candidates = [
        Path(os.environ.get("PROGRAMFILES(X86)", ""))
        / "Microsoft/Edge/Application/msedge.exe",

        Path(os.environ.get("PROGRAMFILES", ""))
        / "Microsoft/Edge/Application/msedge.exe",

        Path(os.environ.get("LOCALAPPDATA", ""))
        / "Microsoft/Edge/Application/msedge.exe",
    ]

    return next(
        (path for path in candidates if path.is_file()),
        None,
    )


def run_manage(*arguments: str) -> None:
    """
    Ejecuta comandos de administración de Django dentro de LoretoOne.exe.

    No requiere python.exe externo.

    La salida estándar se captura en memoria porque los ejecutables
    compilados por PyInstaller con console=False pueden tener
    sys.stdout y sys.stderr establecidos como None.
    """

    from django.core.management import call_command

    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()

    try:
        logging.info(
            "Ejecutando comando Django: %s",
            " ".join(arguments),
        )

        call_command(
            *arguments,
            verbosity=1,
            interactive=False,
            stdout=stdout_buffer,
            stderr=stderr_buffer,
        )

        stdout_text = stdout_buffer.getvalue().strip()
        stderr_text = stderr_buffer.getvalue().strip()

        if stdout_text:
            logging.info(
                "Salida Django [%s]:\n%s",
                " ".join(arguments),
                stdout_text,
            )

        if stderr_text:
            logging.warning(
                "Salida STDERR Django [%s]:\n%s",
                " ".join(arguments),
                stderr_text,
            )

        logging.info(
            "Comando Django finalizado correctamente: %s",
            " ".join(arguments),
        )

    except Exception as exc:

        stdout_text = stdout_buffer.getvalue().strip()
        stderr_text = stderr_buffer.getvalue().strip()

        if stdout_text:
            logging.error(
                "Salida Django antes del error [%s]:\n%s",
                " ".join(arguments),
                stdout_text,
            )

        if stderr_text:
            logging.error(
                "STDERR Django antes del error [%s]:\n%s",
                " ".join(arguments),
                stderr_text,
            )

        logging.exception(
            "Error ejecutando comando Django: %s",
            " ".join(arguments),
        )

        raise RuntimeError(
            f"No se pudo preparar la base local: {' '.join(arguments)}"
        ) from exc

    finally:
        stdout_buffer.close()
        stderr_buffer.close()


def show_error(message: str) -> None:
    """Muestra un error al usuario y lo registra."""

    logging.exception(message)

    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()

        messagebox.showerror(
            APP_NAME,
            message,
            parent=root,
        )

        root.destroy()

    except Exception:
        # En un ejecutable sin consola sys.stderr puede ser None.
        try:
            if sys.stderr is not None:
                print(message, file=sys.stderr)
        except Exception:
            pass


def ensure_sync_configuration() -> None:
    """
    Activa la computadora la primera vez con una cuenta administradora.

    El token técnico se genera en el servidor y nunca se muestra al usuario.
    """

    from desktop.sync import (
        cargar_configuracion,
        guardar_configuracion,
        _request,
    )

    if cargar_configuracion():
        logging.info(
            "La configuración de sincronización ya existe."
        )
        return

    import tkinter as tk
    from tkinter import simpledialog, messagebox

    root = tk.Tk()
    root.withdraw()

    try:
        messagebox.showinfo(
            APP_NAME,
            "Activación inicial\n\n"
            "Esta computadora se conectará con Loreto One Web.\n"
            "Necesitas Internet solamente para esta activación y una cuenta "
            "administradora o de sistemas.",
            parent=root,
        )

        username = simpledialog.askstring(
            APP_NAME,
            "Usuario administrador:",
            parent=root,
        )
        if not username:
            raise RuntimeError(
                "La configuración inicial fue cancelada. "
                "Puedes abrir Loreto One nuevamente para continuar."
            )

        password = simpledialog.askstring(
            APP_NAME,
            "Contraseña:",
            show="*",
            parent=root,
        )
        if not password:
            raise RuntimeError(
                "La configuración inicial fue cancelada. "
                "Puedes abrir Loreto One nuevamente para continuar."
            )

        url = "https://loreto-pacs.onrender.com"

        device_file = DATA_DIR / "device-id.txt"
        if device_file.exists():
            try:
                device_id = str(uuid.UUID(device_file.read_text(encoding="utf-8").strip()))
            except (ValueError, OSError):
                device_id = str(uuid.uuid4())
        else:
            device_id = str(uuid.uuid4())

        device_file.write_text(device_id, encoding="utf-8")

        config_temporal = {"url": url, "token": "activacion"}
        nombre_equipo = os.environ.get("COMPUTERNAME", "Equipo Loreto One").strip()

        try:
            activacion = _request(
                config_temporal,
                method="POST",
                path="/api/v1/sync/activar/",
                payload={
                    "username": username.strip(),
                    "password": password,
                    "dispositivo_id": device_id,
                    "nombre_dispositivo": nombre_equipo,
                },
            )
            if not activacion.get("ok") or not activacion.get("token"):
                raise RuntimeError(
                    activacion.get("error", "El servidor rechazó la activación.")
                )
        except HTTPError as exc:
            try:
                detalle = json.loads(exc.read().decode("utf-8")).get("error", "")
            except Exception:
                detalle = ""
            raise RuntimeError(
                detalle or "El servidor rechazó la activación de esta computadora."
            ) from exc
        except Exception as exc:
            if isinstance(exc, RuntimeError):
                raise
            raise RuntimeError(
                "No se pudo activar esta computadora. "
                "Comprueba la conexión a Internet e inténtalo nuevamente."
            ) from exc

        guardar_configuracion(
            url,
            activacion["token"],
        )

        messagebox.showinfo(
            APP_NAME,
            "Computadora activada correctamente para:\n\n"
            f"{activacion['institucion']['nombre']}\n\n"
            "A partir de ahora Loreto One podrá trabajar sin Internet y "
            "sincronizará los cambios automáticamente.",
            parent=root,
        )

        logging.info(
            "Configuración de sincronización guardada correctamente."
        )

    finally:
        try:
            root.destroy()
        except Exception:
            pass


def start_waitress() -> None:
    """
    Ejecuta Waitress dentro del propio LoretoOne.exe.

    No crea otro proceso de Python.
    """

    try:
        from waitress import serve
        from config.wsgi import application

        logging.info(
            "Iniciando servidor local en %s:%s",
            HOST,
            PORT,
        )

        serve(
            application,
            host=HOST,
            port=PORT,
            threads=4,
        )

    except Exception:
        logging.exception(
            "El servidor local de Loreto One se cerró inesperadamente."
        )


def wait_for_server(timeout_seconds: float = 30.0) -> bool:
    """Espera hasta que el servidor local esté disponible."""

    deadline = time.time() + timeout_seconds

    while time.time() < deadline:

        if server_is_ready():
            return True

        time.sleep(0.5)

    return False


def main() -> int:
    try:
        configure_environment()
        configure_logging()

        logging.info(
            "=========================================="
        )
        logging.info(
            "Iniciando Loreto One Desktop"
        )
        logging.info(
            "PROJECT_DIR=%s",
            PROJECT_DIR,
        )
        logging.info(
            "DATA_DIR=%s",
            DATA_DIR,
        )

        # ----------------------------------------------------
        # INICIALIZAR DJANGO
        # ----------------------------------------------------

        import django

        django.setup()

        logging.info(
            "Django inicializado correctamente."
        )

        # ----------------------------------------------------
        # PREPARAR SQLITE LOCAL
        # ----------------------------------------------------

        run_manage(
            "migrate",
            "--noinput",
        )

        logging.info(
            "Base de datos local preparada correctamente."
        )

        # ----------------------------------------------------
        # CONFIGURAR SINCRONIZACIÓN
        # ----------------------------------------------------

        ensure_sync_configuration()

        # ----------------------------------------------------
        # INICIAR SERVIDOR LOCAL
        # ----------------------------------------------------

        if not server_is_ready():

            server_thread = threading.Thread(
                target=start_waitress,
                name="LoretoOneLocalServer",
                daemon=True,
            )

            server_thread.start()

            if not wait_for_server(30):

                raise RuntimeError(
                    "El servidor local de Loreto One "
                    "no respondió en 30 segundos. "
                    "Revisa desktop.log."
                )

        logging.info(
            "Servidor local disponible."
        )

        # ----------------------------------------------------
        # SINCRONIZACIÓN AUTOMÁTICA
        # ----------------------------------------------------

        from desktop.sync import iniciar_sincronizacion_automatica

        iniciar_sincronizacion_automatica(
            intervalo_segundos=30
        )

        logging.info(
            "Sincronización automática iniciada."
        )

        # ----------------------------------------------------
        # LOCALIZAR MICROSOFT EDGE
        # ----------------------------------------------------

        edge = find_edge()

        if not edge:
            raise RuntimeError(
                "No se encontró Microsoft Edge "
                "en esta computadora."
            )

        profile = DATA_DIR / "edge-profile"

        profile.mkdir(
            parents=True,
            exist_ok=True,
        )

        logging.info(
            "Abriendo interfaz de Loreto One."
        )

        # ----------------------------------------------------
        # ABRIR LORETO ONE COMO APLICACIÓN
        # ----------------------------------------------------

        import subprocess

        window = subprocess.Popen(
            [
                str(edge),
                f"--app={URL}",
                f"--user-data-dir={profile}",
                "--no-first-run",
                "--disable-sync",
            ]
        )

        # Mantener LoretoOne.exe vivo mientras la ventana esté abierta.
        window.wait()

        logging.info(
            "Ventana de Loreto One cerrada."
        )

        return 0

    except Exception as exc:

        logging.exception(
            "Error fatal iniciando Loreto One Desktop."
        )

        show_error(str(exc))

        return 1


if __name__ == "__main__":
    raise SystemExit(main())
