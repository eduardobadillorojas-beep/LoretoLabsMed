"""Sincronización offline-first de Loreto One Desktop con el servidor."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone as dt_timezone
import threading
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.db import transaction
from django.utils import timezone

from api.models import SyncCursor, SyncOutbox
from api.sync_context import importar_desde_servidor
from core.models import Estudio, Institucion, Paciente, TipoEstudio


DATA_DIR = Path(
    os.environ.get(
        "LORETO_DESKTOP_DATA_DIR",
        Path.home() / "AppData" / "Local" / "LoretoOne",
    )
)
CONFIG_FILE = DATA_DIR / "sync.json"
LOG = logging.getLogger(__name__)


def cargar_configuracion():
    if not CONFIG_FILE.exists():
        return None

    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        LOG.exception("No se pudo leer %s", CONFIG_FILE)
        return None

    url = str(data.get("url", "")).strip().rstrip("/")
    token = str(data.get("token", "")).strip()
    if not url or not token:
        return None

    return {"url": url, "token": token}


def guardar_configuracion(url: str, token: str):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(
        json.dumps(
            {"url": url.rstrip("/"), "token": token},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _request(config, method="GET", path="", payload=None):
    body = None
    headers = {
        "Accept": "application/json",
        "X-Loreto-Sync-Token": config["token"],
    }

    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = Request(
        config["url"] + path,
        data=body,
        headers=headers,
        method=method,
    )

    with urlopen(request, timeout=15) as response:
        raw = response.read()

    return json.loads(raw.decode("utf-8"))


def _iso(fecha):
    if not fecha:
        return None
    return fecha.astimezone(dt_timezone.utc).isoformat()


def sincronizar_catalogo(config):
    data = _request(config, path="/api/v1/catalogo/estudios/")
    if not data.get("ok"):
        raise RuntimeError(data.get("error", "No se pudo obtener el catálogo."))

    actualizados = 0
    for item in data.get("estudios", []):
        TipoEstudio.objects.update_or_create(
            codigo=item["codigo"],
            defaults={
                "nombre": item["nombre"],
                "modalidad": item["modalidad"],
                "activo": bool(item.get("activo", True)),
                "tiempo_estimado": int(item.get("tiempo_estimado", 10)),
            },
        )
        actualizados += 1

    return actualizados


def _payload_paciente(paciente):
    return {
        "sync_id": str(paciente.sync_id),
        "nombre": paciente.nombre,
        "apellido": paciente.apellido,
        "fecha_nacimiento": paciente.fecha_nacimiento.isoformat(),
        "genero": paciente.genero,
        "telefono": paciente.telefono or "",
        "origen_registro": paciente.origen_registro,
    }


def _payload_estudio(estudio):
    return {
        "sync_id": str(estudio.sync_id),
        "paciente_sync_id": str(estudio.paciente.sync_id),
        "tipo_estudio_codigo": estudio.tipo_estudio.codigo,
        "medico_solicitante": estudio.medico_solicitante or "",
        "descripcion": estudio.descripcion or "",
        "estado": estudio.estado,
    }


def enviar_pendientes(config):
    enviados = 0
    errores = 0

    pendientes = list(
        SyncOutbox.objects
        .filter(enviado_el__isnull=True)
        .order_by("creado_el", "id")[:100]
    )

    while pendientes:
        pacientes = []
        estudios = []
        filas = []

        for fila in pendientes:
            try:
                if fila.entidad == "PACIENTE":
                    pacientes.append(_payload_paciente(Paciente.objects.get(pk=fila.objeto_id)))
                elif fila.entidad == "ESTUDIO":
                    estudios.append(_payload_estudio(Estudio.objects.select_related("paciente", "tipo_estudio").get(pk=fila.objeto_id)))
                filas.append(fila)
            except (Paciente.DoesNotExist, Estudio.DoesNotExist):
                fila.enviado_el = timezone.now()
                fila.ultimo_error = "El registro local ya no existe."
                fila.save(update_fields=["enviado_el", "ultimo_error", "actualizado_el"])

        if not filas:
            break

        try:
            respuesta = _request(
                config,
                method="POST",
                path="/api/v1/sync/push/",
                payload={"pacientes": pacientes, "estudios": estudios},
            )
        except (HTTPError, URLError, TimeoutError, OSError):
            LOG.exception("No se pudo enviar la cola de sincronización")
            errores += len(filas)
            break

        ahora = timezone.now()
        if respuesta.get("pacientes"):
            with importar_desde_servidor():
                for item in respuesta["pacientes"]:
                    try:
                        paciente = Paciente.objects.get(sync_id=item["sync_id"])
                        if item.get("identificacion"):
                            paciente.identificacion = item["identificacion"]
                            paciente.save(update_fields=["identificacion", "actualizado_el"])
                    except Paciente.DoesNotExist:
                        LOG.warning("Paciente sincronizado no encontrado: %s", item.get("sync_id"))

        errores_api = respuesta.get("errores") or []
        ids_error = {str(item.get("sync_id")) for item in errores_api}

        for fila in filas:
            fila.intentos += 1
            if str(fila.sync_id) in ids_error:
                fila.ultimo_error = next(
                    (item.get("error", "Error de API") for item in errores_api if str(item.get("sync_id")) == str(fila.sync_id)),
                    "Error de API",
                )
                errores += 1
            else:
                fila.enviado_el = ahora
                fila.ultimo_error = ""
                enviados += 1
            fila.save(update_fields=["intentos", "enviado_el", "ultimo_error", "actualizado_el"])

        if errores_api:
            break

        pendientes = list(
            SyncOutbox.objects
            .filter(enviado_el__isnull=True)
            .order_by("creado_el", "id")[:100]
        )

    return enviados, errores


def _cursor_actual():
    return SyncCursor.objects.filter(clave="principal").first()


def descargar_cambios(config):
    cursor = _cursor_actual()

    if cursor is None:
        estado = _request(config, path="/api/v1/sync/estado/")
        servidor = estado.get("server_time")
        if not servidor:
            return 0
        fecha = datetime.fromisoformat(servidor.replace("Z", "+00:00"))
        SyncCursor.objects.create(clave="principal", valor=fecha)
        return 0

    total = 0
    since = cursor.valor
    institucion_local = (
        Institucion.objects
        .filter(activa=True)
        .order_by("id")
        .first()
    )
    if institucion_local is None:
        raise RuntimeError("No existe una institución activa en la base local.")

    while True:
        data = _request(
            config,
            path="/api/v1/sync/pull/"
            + "?since="
            + since.astimezone(dt_timezone.utc).isoformat()
            + "&limit=100",
        )

        pacientes = data.get("pacientes", [])
        estudios = data.get("estudios", [])

        with transaction.atomic(), importar_desde_servidor():
            for item in pacientes:
                pendiente = SyncOutbox.objects.filter(
                    entidad="PACIENTE",
                    sync_id=item["sync_id"],
                    enviado_el__isnull=True,
                ).exists()
                if pendiente:
                    continue

                try:
                    paciente = Paciente.objects.get(sync_id=item["sync_id"])
                except Paciente.DoesNotExist:
                    identificacion = item.get("identificacion", "")
                    paciente = (
                        Paciente.objects.filter(identificacion=identificacion).first()
                        if identificacion
                        else None
                    )
                    if paciente is None:
                        paciente = Paciente(
                            institucion=institucion_local,
                            sync_id=item["sync_id"],
                            identificacion=identificacion,
                            nombre=item["nombre"],
                            apellido=item["apellido"],
                            fecha_nacimiento=item["fecha_nacimiento"],
                            genero=item["genero"],
                            telefono=item.get("telefono", ""),
                            origen_registro=item.get("origen_registro", "RECEPCION"),
                        )
                    else:
                        paciente.sync_id = item["sync_id"]
                paciente.identificacion = item.get("identificacion", paciente.identificacion)
                paciente.nombre = item["nombre"]
                paciente.apellido = item["apellido"]
                paciente.fecha_nacimiento = item["fecha_nacimiento"]
                paciente.genero = item["genero"]
                paciente.telefono = item.get("telefono", "")
                paciente.origen_registro = item.get("origen_registro", paciente.origen_registro)
                paciente.save()
                total += 1

            for item in estudios:
                pendiente = SyncOutbox.objects.filter(
                    entidad="ESTUDIO",
                    sync_id=item["sync_id"],
                    enviado_el__isnull=True,
                ).exists()
                if pendiente:
                    continue

                try:
                    paciente = Paciente.objects.get(sync_id=item["paciente_sync_id"])
                    tipo = TipoEstudio.objects.get(codigo=item["tipo_estudio_codigo"])
                except (Paciente.DoesNotExist, TipoEstudio.DoesNotExist):
                    LOG.warning("No se pudo importar estudio %s: faltan relaciones.", item.get("sync_id"))
                    continue

                estudio, _ = Estudio.objects.get_or_create(
                    sync_id=item["sync_id"],
                    defaults={
                        "paciente": paciente,
                        "tipo_estudio": tipo,
                        "medico_solicitante": item.get("medico_solicitante", ""),
                        "descripcion": item.get("descripcion", ""),
                        "estado": item.get("estado", "PENDIENTE"),
                    },
                )
                estudio.paciente = paciente
                estudio.tipo_estudio = tipo
                estudio.medico_solicitante = item.get("medico_solicitante", "")
                estudio.descripcion = item.get("descripcion", "")
                estudio.estado = item.get("estado", estudio.estado)
                estudio.save()
                total += 1

        siguiente = data.get("next_since")
        if siguiente:
            since = datetime.fromisoformat(siguiente.replace("Z", "+00:00"))
            cursor.valor = since
            cursor.save(update_fields=["valor", "actualizado_el"])

        if not data.get("hay_mas"):
            break

    return total


def ejecutar_sincronizacion():
    config = cargar_configuracion()
    if not config:
        LOG.info("Sincronización desactivada: no existe sync.json configurado.")
        return {"estado": "desactivada"}

    try:
        catalogo = sincronizar_catalogo(config)
        enviados, errores = enviar_pendientes(config)
        descargados = descargar_cambios(config)
        LOG.info(
            "Sincronización completada: catálogo=%s, enviados=%s, errores=%s, descargados=%s",
            catalogo,
            enviados,
            errores,
            descargados,
        )
        return {
            "estado": "ok",
            "catalogo": catalogo,
            "enviados": enviados,
            "errores": errores,
            "descargados": descargados,
        }
    except Exception:
        LOG.exception("Error general durante la sincronización")
        return {"estado": "error"}


_SYNC_THREAD = None
_SYNC_STOP = threading.Event()
_SYNC_LOCK = threading.Lock()


def ejecutar_sincronizacion_segura():
    """Ejecuta una sincronización sin permitir ejecuciones simultáneas."""
    if not _SYNC_LOCK.acquire(blocking=False):
        return {"estado": "ocupada"}
    try:
        return ejecutar_sincronizacion()
    finally:
        _SYNC_LOCK.release()


def iniciar_sincronizacion_automatica(intervalo_segundos=30):
    """Mantiene la sincronización activa mientras Loreto One Desktop está abierto."""
    global _SYNC_THREAD
    if _SYNC_THREAD is not None and _SYNC_THREAD.is_alive():
        return

    _SYNC_STOP.clear()

    def worker():
        LOG.info("Sincronización automática iniciada; intervalo=%ss", intervalo_segundos)
        while not _SYNC_STOP.is_set():
            try:
                ejecutar_sincronizacion_segura()
            except Exception:
                LOG.exception("Error inesperado en la sincronización automática")
            _SYNC_STOP.wait(intervalo_segundos)
        LOG.info("Sincronización automática detenida")

    _SYNC_THREAD = threading.Thread(
        target=worker,
        name="LoretoOneSync",
        daemon=True,
    )
    _SYNC_THREAD.start()


def detener_sincronizacion_automatica():
    _SYNC_STOP.set()
