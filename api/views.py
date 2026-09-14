import json
import os
import uuid
from datetime import datetime

from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from core.models import Institucion, Estudio, Paciente, TipoEstudio

from .models import SyncOutbox
from .sync_context import importar_desde_servidor


API_VERSION = '1.0'


def _sync_token_valido(request):
    esperado = os.environ.get('LORETO_SYNC_TOKEN', '').strip()
    recibido = request.headers.get('X-Loreto-Sync-Token', '').strip()
    return bool(esperado) and recibido == esperado


def _requiere_token(request):
    if _sync_token_valido(request):
        return None
    return JsonResponse(
        {'ok': False, 'error': 'Token de sincronización inválido.'},
        status=401,
    )


def _institucion_sync():
    valor = os.environ.get('LORETO_SYNC_INSTITUCION_ID', '').strip()

    if valor:
        try:
            return Institucion.objects.get(pk=int(valor), activa=True)
        except (ValueError, Institucion.DoesNotExist):
            return None

    return (
        Institucion.objects
        .filter(activa=True)
        .order_by('id')
        .first()
    )


def _parse_datetime(valor):
    if not valor:
        return None

    try:
        fecha = datetime.fromisoformat(valor.replace('Z', '+00:00'))
    except ValueError:
        return None

    if timezone.is_naive(fecha):
        fecha = timezone.make_aware(fecha)

    return fecha


@require_GET
def catalogo_estudios(request):
    """Devuelve el catálogo maestro activo del servidor."""
    estudios = (
        TipoEstudio.objects
        .filter(activo=True)
        .order_by('modalidad', 'codigo')
    )

    data = [
        {
            'codigo': estudio.codigo,
            'nombre': estudio.nombre,
            'modalidad': estudio.modalidad,
            'activo': estudio.activo,
            'tiempo_estimado': estudio.tiempo_estimado,
        }
        for estudio in estudios
    ]

    return JsonResponse({
        'ok': True,
        'total': len(data),
        'estudios': data,
    })


@require_GET
def sync_estado(request):
    error = _requiere_token(request)
    if error:
        return error

    institucion = _institucion_sync()
    if institucion is None:
        return JsonResponse(
            {
                'ok': False,
                'error': 'No existe una institución activa configurada para sincronización.',
            },
            status=503,
        )

    return JsonResponse({
        'ok': True,
        'api_version': API_VERSION,
        'server_time': timezone.now().isoformat(),
        'institucion': {
            'id': institucion.id,
            'nombre': institucion.nombre,
        },
    })


@require_POST
def sync_push(request):
    error = _requiere_token(request)
    if error:
        return error

    institucion = _institucion_sync()
    if institucion is None:
        return JsonResponse(
            {'ok': False, 'error': 'No existe institución activa para sincronización.'},
            status=503,
        )

    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse(
            {'ok': False, 'error': 'JSON inválido.'},
            status=400,
        )

    pacientes = payload.get('pacientes') or []
    estudios = payload.get('estudios') or []

    if not isinstance(pacientes, list) or not isinstance(estudios, list):
        return JsonResponse(
            {'ok': False, 'error': 'pacientes y estudios deben ser listas.'},
            status=400,
        )

    if len(pacientes) + len(estudios) > 200:
        return JsonResponse(
            {'ok': False, 'error': 'Máximo 200 registros por sincronización.'},
            status=413,
        )

    respuesta_pacientes = []
    respuesta_estudios = []
    errores = []

    with transaction.atomic():
        for item in pacientes:
            try:
                sync_id = uuid.UUID(str(item['sync_id']))
                paciente, creado = Paciente.objects.get_or_create(
                    sync_id=sync_id,
                    defaults={
                        'institucion': institucion,
                        'nombre': str(item.get('nombre', '')).strip(),
                        'apellido': str(item.get('apellido', '')).strip(),
                        'fecha_nacimiento': item['fecha_nacimiento'],
                        'genero': item.get('genero', 'O'),
                        'telefono': item.get('telefono') or '',
                        'identificacion': '',
                        'origen_registro': item.get('origen_registro', 'RECEPCION'),
                    },
                )

                if not creado:
                    paciente.nombre = str(item.get('nombre', paciente.nombre)).strip()
                    paciente.apellido = str(item.get('apellido', paciente.apellido)).strip()
                    paciente.fecha_nacimiento = item.get('fecha_nacimiento', paciente.fecha_nacimiento)
                    paciente.genero = item.get('genero', paciente.genero)
                    paciente.telefono = item.get('telefono') or ''
                    paciente.save()

                respuesta_pacientes.append({
                    'sync_id': str(paciente.sync_id),
                    'id': paciente.id,
                    'identificacion': paciente.identificacion,
                    'creado': creado,
                    'actualizado_el': paciente.actualizado_el.isoformat(),
                })
            except Exception as exc:
                errores.append({
                    'entidad': 'PACIENTE',
                    'sync_id': str(item.get('sync_id', '')),
                    'error': str(exc),
                })

        for item in estudios:
            try:
                sync_id = uuid.UUID(str(item['sync_id']))
                paciente_sync_id = uuid.UUID(str(item['paciente_sync_id']))
                tipo_codigo = str(item['tipo_estudio_codigo']).strip()

                paciente = Paciente.objects.get(
                    sync_id=paciente_sync_id,
                    institucion=institucion,
                )
                tipo_estudio = TipoEstudio.objects.get(
                    codigo=tipo_codigo,
                    activo=True,
                )

                estudio, creado = Estudio.objects.get_or_create(
                    sync_id=sync_id,
                    defaults={
                        'paciente': paciente,
                        'tipo_estudio': tipo_estudio,
                        'medico_solicitante': item.get('medico_solicitante') or '',
                        'descripcion': item.get('descripcion') or '',
                        'estado': item.get('estado') or 'PENDIENTE',
                    },
                )

                if not creado:
                    estudio.paciente = paciente
                    estudio.tipo_estudio = tipo_estudio
                    estudio.medico_solicitante = item.get('medico_solicitante') or ''
                    estudio.descripcion = item.get('descripcion') or ''
                    estudio.estado = item.get('estado') or estudio.estado
                    estudio.save()

                respuesta_estudios.append({
                    'sync_id': str(estudio.sync_id),
                    'id': estudio.id,
                    'paciente_sync_id': str(paciente.sync_id),
                    'actualizado_el': estudio.actualizado_el.isoformat(),
                    'creado': creado,
                })
            except Exception as exc:
                errores.append({
                    'entidad': 'ESTUDIO',
                    'sync_id': str(item.get('sync_id', '')),
                    'error': str(exc),
                })

    return JsonResponse({
        'ok': not errores,
        'pacientes': respuesta_pacientes,
        'estudios': respuesta_estudios,
        'errores': errores,
        'server_time': timezone.now().isoformat(),
    }, status=200 if not errores else 207)


@require_GET
def sync_pull(request):
    error = _requiere_token(request)
    if error:
        return error

    institucion = _institucion_sync()
    if institucion is None:
        return JsonResponse(
            {'ok': False, 'error': 'No existe institución activa para sincronización.'},
            status=503,
        )

    since = _parse_datetime(request.GET.get('since'))
    limit_raw = request.GET.get('limit', '100')
    try:
        limit = max(1, min(int(limit_raw), 100))
    except ValueError:
        limit = 100

    pacientes_qs = Paciente.objects.filter(institucion=institucion)
    estudios_qs = Estudio.objects.filter(paciente__institucion=institucion)

    if since:
        pacientes_qs = pacientes_qs.filter(actualizado_el__gt=since)
        estudios_qs = estudios_qs.filter(actualizado_el__gt=since)

    pacientes = list(
        pacientes_qs
        .order_by('actualizado_el', 'id')[:limit]
    )
    estudios = list(
        estudios_qs
        .select_related('paciente', 'tipo_estudio')
        .order_by('actualizado_el', 'id')[:limit]
    )

    data_pacientes = [
        {
            'sync_id': str(p.sync_id),
            'id': p.id,
            'identificacion': p.identificacion,
            'nombre': p.nombre,
            'apellido': p.apellido,
            'fecha_nacimiento': p.fecha_nacimiento.isoformat(),
            'genero': p.genero,
            'telefono': p.telefono or '',
            'origen_registro': p.origen_registro,
            'actualizado_el': p.actualizado_el.isoformat(),
        }
        for p in pacientes
    ]

    data_estudios = [
        {
            'sync_id': str(e.sync_id),
            'id': e.id,
            'paciente_sync_id': str(e.paciente.sync_id),
            'tipo_estudio_codigo': e.tipo_estudio.codigo,
            'medico_solicitante': e.medico_solicitante or '',
            'descripcion': e.descripcion or '',
            'estado': e.estado,
            'actualizado_el': e.actualizado_el.isoformat(),
        }
        for e in estudios
    ]

    timestamps = [
        *(p.actualizado_el for p in pacientes),
        *(e.actualizado_el for e in estudios),
    ]
    next_since = max(timestamps).isoformat() if timestamps else (
        since.isoformat() if since else timezone.now().isoformat()
    )

    return JsonResponse({
        'ok': True,
        'pacientes': data_pacientes,
        'estudios': data_estudios,
        'next_since': next_since,
        'server_time': timezone.now().isoformat(),
        'hay_mas': len(pacientes) >= limit or len(estudios) >= limit,
    })
