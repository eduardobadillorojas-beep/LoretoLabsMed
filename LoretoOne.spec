# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_submodules, collect_data_files
from pathlib import Path


# ============================================================
# RUTAS DEL PROYECTO
# ============================================================

root = Path(SPECPATH)
project = root


# ============================================================
# ARCHIVOS DE DATOS
# ============================================================

datas = []

# Recursos de paquetes externos.
for pkg in [
    "django",
    "whitenoise",
]:
    try:
        datas += collect_data_files(pkg)
    except Exception:
        pass


# Recursos propios de Loreto One que Django carga por ruta.
for rel in [
    "core/templates",
    "core/static",
    "api/templates",
    "api/static",
    "pacientes/templates",
    "pacientes/static",
    "recepcion/templates",
    "recepcion/static",
    "cuenta_recepcion/templates",
    "cuenta_recepcion/static",
    "desktop/templates",
    "desktop/static",
    "frontend",
    "staticfiles",
]:
    p = project / rel

    if p.exists():
        datas.append(
            (
                str(p),
                rel,
            )
        )


# ============================================================
# IMPORTACIONES OCULTAS
# ============================================================

hiddenimports = []


# Aplicaciones y módulos completos de Loreto One.
for pkg in [
    "config",
    "core",
    "api",
    "pacientes",
    "recepcion",
    "cuenta_recepcion",
    "desktop",
]:
    try:
        hiddenimports += collect_submodules(pkg)
    except Exception:
        pass


# WhiteNoise usa módulos que Django puede importar dinámicamente.
try:
    hiddenimports += collect_submodules("whitenoise")
except Exception:
    pass


# Módulos que PyInstaller puede no detectar automáticamente.
hiddenimports += [

    # --------------------------------------------------------
    # CONFIGURACIÓN DJANGO DE LORETO ONE
    # --------------------------------------------------------

    "config",
    "config.settings",
    "config.settings_desktop",
    "config.urls",
    "config.wsgi",

    # --------------------------------------------------------
    # WAITRESS
    # --------------------------------------------------------

    "waitress",
    "waitress.server",
    "waitress.task",
    "waitress.channel",
    "waitress.runner",
    "waitress.wasyncore",

    # --------------------------------------------------------
    # DJANGO
    # --------------------------------------------------------

    "django",
    "django.conf",
    "django.apps",
    "django.urls",
    "django.core",
    "django.core.management",
    "django.core.management.commands",
    "django.core.management.commands.migrate",

    # --------------------------------------------------------
    # WHITENOISE
    # --------------------------------------------------------

    "whitenoise",
    "whitenoise.middleware",

    # --------------------------------------------------------
    # DEPENDENCIAS DE LORETO ONE
    # --------------------------------------------------------

    "dj_database_url",
    "storages",
    "pydicom",
    "PIL",
]


# Eliminar duplicados conservando el orden.
hiddenimports = list(dict.fromkeys(hiddenimports))


# ============================================================
# ANÁLISIS DE PYINSTALLER
# ============================================================

a = Analysis(

    # IMPORTANTE:
    # Este es el launcher NUEVO ubicado en la raíz del proyecto.
    # NO utilizar desktop/launcher.py.
    ["launcher.py"],

    pathex=[
        str(project),
    ],

    binaries=[],

    datas=datas,

    hiddenimports=hiddenimports,

    hookspath=[],

    hooksconfig={},

    runtime_hooks=[],

    excludes=[],

    noarchive=False,
)


# ============================================================
# ARCHIVO PYZ
# ============================================================

pyz = PYZ(
    a.pure
)


# ============================================================
# EJECUTABLE LORETO ONE
# ============================================================

exe = EXE(
    pyz,
    a.scripts,
    [],

    exclude_binaries=True,

    name="LoretoOne",
    icon=str(project / "assets" / "loretoone.ico"),

    debug=False,

    bootloader_ignore_signals=False,

    strip=False,

    upx=True,

    console=False,
)


# ============================================================
# DISTRIBUCIÓN FINAL
# ============================================================

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,

    strip=False,

    upx=True,

    name="LoretoOne",
)
