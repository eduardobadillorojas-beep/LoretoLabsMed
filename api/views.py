import json
import hashlib
import secrets
import uuid
from datetime import datetime

from django.db import transaction
import logging
from django.contrib.auth import authenticate, get_user_model
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.csrf import csrf_exempt

from core.models import Institucion, Estudio, Paciente, TipoEstudio, MembresiaInstitucion, AreaInstitucional, ModuloSistema, AccesoModuloMembresia

from .models import DispositivoSync, SyncOutbox
from .sync_context import importar_desde_servidor


LOG = logging.getLogger(__name__)
API_VERSION = '1.2'


def _token_hash(token):
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def _institucion_desde_token(request):
    token = request.headers.get('X-Loreto-Sync-Token', '').strip()
    if not token:
        return None

    dispositivo = (
        DispositivoSync.objects
        .select_related('institucion')
        .filter(
            token_hash=_token_hash(token),
            activo=True,
            institucion__activa=True,
        )
        .first()
    )
    if dispositivo is None:
        return None

    DispositivoSync.objects.filter(pk=dispositivo.pk).update(
        ultima_conexion=timezone.now(),
    )
    return dispositivo.institucion


def _requiere_institucion(request):
    institucion = _institucion_desde_token(request)
    if institucion is not None:
        return institucion, None
    return None, JsonResponse(
        {'ok': False, 'error': 'Dispositivo no autorizado para sincronizar.'},
        status=401,
    )


@csrf_exempt
@require_POST
def sync_activar_dispositivo(request):
    """Registra una computadora usando credenciales administrativas normales."""
    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse(
            {'ok': False, 'error': 'JSON inválido.'},
            status=400,
        )

    username = str(payload.get('username', '')).strip()
    password = str(payload.get('password', ''))
    nombre = str(payload.get('nombre_dispositivo', '')).strip()[:150]

    try:
        dispositivo_id = uuid.UUID(str(payload.get('dispositivo_id', '')))
    except (ValueError, TypeError, AttributeError):
        return JsonResponse(
            {'ok': False, 'error': 'Identificador de dispositivo inválido.'},
            status=400,
        )

    usuario = authenticate(
        request,
        username=username,
        password=password,
    )
    if usuario is None or not usuario.is_active:
        return JsonResponse(
            {'ok': False, 'error': 'Usuario o contraseña incorrectos.'},
            status=401,
        )

    institucion_id = payload.get('institucion_id')

    try:
        if isinstance(institucion_id, bool):
            raise ValueError('Boolean is not a valid institution ID')
        institucion_id = int(institucion_id)
        if institucion_id <= 0:
            raise ValueError('Institution ID must be positive')
    except (TypeError, ValueError):
        return JsonResponse(
            {'ok': False, 'error': 'Debe seleccionar una institucion valida.'},
            status=400,
        )

    institucion = Institucion.objects.filter(
        pk=institucion_id,
        activa=True,
    ).first()

    if institucion is not None and not usuario.is_superuser:
        autorizado = MembresiaInstitucion.objects.filter(
            usuario=usuario,
            institucion=institucion,
            activa=True,
            rol__in=['ADMIN', 'SISTEMAS'],
        ).exists()
        if not autorizado:
            institucion = None

    if institucion is None:
        return JsonResponse(
            {
                'ok': False,
                'error': 'Se requiere una cuenta administradora o de sistemas para activar este equipo.',
            },
            status=403,
        )

    token = secrets.token_urlsafe(48)
    dispositivo, _ = DispositivoSync.objects.update_or_create(
        institucion=institucion,
        dispositivo_id=dispositivo_id,
        defaults={
            'nombre': nombre or 'Equipo Loreto One',
            'token_hash': _token_hash(token),
            'autorizado_por': usuario,
            'activo': True,
            'ultima_conexion': timezone.now(),
        },
    )

    return JsonResponse({
        'ok': True,
        'token': token,
        'dispositivo': {
            'id': str(dispositivo.dispositivo_id),
            'nombre': dispositivo.nombre,
        },
        'institucion': {
            'id': institucion.id,
            'nombre': institucion.nombre,
        },
    })


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
    institucion, error = _requiere_institucion(request)
    if error:
        return error

    return JsonResponse({
        'ok': True,
        'api_version': API_VERSION,
        'server_time': timezone.now().isoformat(),
        'institucion': {
            'id': institucion.id,
            'nombre': institucion.nombre,
        },
    })


@csrf_exempt
@require_POST
def sync_push(request):
    institucion, error = _requiere_institucion(request)
    if error:
        return error

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
                with transaction.atomic():
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
                        if paciente.institucion_id != institucion.id:
                            raise ValueError(
                                'Acceso denegado: el paciente pertenece a otra institucion.'
                            )
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
            except Exception:
                LOG.exception('Error al sincronizar un registro; operación revertida')
                errores.append({
                    'entidad': 'PACIENTE',
                    'sync_id': str(item.get('sync_id', '')),
                    'error': 'Registro rechazado. Comprueba sus datos y permisos.',
                })

        for item in estudios:
            try:
                with transaction.atomic():
                    sync_id = uuid.UUID(str(item['sync_id']))
                    paciente_sync_id = uuid.UUID(str(item['paciente_sync_id']))
                    tipo_codigo = str(item['tipo_estudio_codigo']).strip()
                    formato_entrega = str(
                        item.get('formato_entrega') or 'DIGITAL'
                    ).strip().upper()
    
                    if formato_entrega not in {'DIGITAL', 'IMPRESO', 'AMBOS'}:
                        raise ValueError(
                            'El formato de entrega debe ser DIGITAL, IMPRESO o AMBOS.'
                        )
    
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
                            'formato_entrega': formato_entrega,
                        },
                    )
    
                    if not creado:
                        if estudio.paciente.institucion_id != institucion.id:
                            raise ValueError(
                                'Acceso denegado: el estudio pertenece a otra institucion.'
                            )
                        estudio.paciente = paciente
                        estudio.tipo_estudio = tipo_estudio
                        estudio.medico_solicitante = item.get('medico_solicitante') or ''
                        estudio.descripcion = item.get('descripcion') or ''
                        estudio.estado = item.get('estado') or estudio.estado
                        estudio.formato_entrega = formato_entrega
                        estudio.save()
    
                    respuesta_estudios.append({
                        'sync_id': str(estudio.sync_id),
                        'id': estudio.id,
                        'paciente_sync_id': str(paciente.sync_id),
                        'actualizado_el': estudio.actualizado_el.isoformat(),
                        'creado': creado,
                    })
            except Exception:
                LOG.exception('Error al sincronizar un registro; operación revertida')
                errores.append({
                    'entidad': 'ESTUDIO',
                    'sync_id': str(item.get('sync_id', '')),
                    'error': 'Registro rechazado. Comprueba sus datos y permisos.',
                })

    return JsonResponse({
        'ok': not errores,
        'pacientes': respuesta_pacientes,
        'estudios': respuesta_estudios,
        'errores': errores,
        'server_time': timezone.now().isoformat(),
    }, status=200 if not errores else 207)



@require_GET
def sync_usuarios(request):
    institucion, error = _requiere_institucion(request)
    if error:
        return error

    User = get_user_model()
    membresias = (
        MembresiaInstitucion.objects
        .filter(institucion=institucion, activa=True)
        .select_related('usuario', 'area')
        .prefetch_related('accesos_modulos__modulo')
        .order_by('usuario__username')
    )

    usuarios = []
    for membresia in membresias:
        usuario = membresia.usuario
        usuarios.append({
            'username': usuario.username,
            'password': usuario.password,
            'first_name': usuario.first_name,
            'last_name': usuario.last_name,
            'email': usuario.email,
            'is_active': usuario.is_active,
            'is_staff': usuario.is_staff,
            'is_superuser': usuario.is_superuser,
            'rol': membresia.rol,
            'puesto': membresia.puesto,
            'area_clave': membresia.area.clave if membresia.area else None,
            'accesos': [
                {
                    'codigo': acceso.modulo.codigo,
                    'puede_ver': acceso.puede_ver,
                    'puede_registrar': acceso.puede_registrar,
                    'puede_editar': acceso.puede_editar,
                    'puede_administrar': acceso.puede_administrar,
                }
                for acceso in membresia.accesos_modulos.all()
            ],
        })

    return JsonResponse({
        'ok': True,
        'total': len(usuarios),
        'usuarios': usuarios,
    })

@require_GET
def sync_pull(request):
    institucion, error = _requiere_institucion(request)
    if error:
        return error

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
            'formato_entrega': e.formato_entrega,
            'actualizado_el': e.actualizado_el.isoformat(),
        }
        for e in estudios
    ]

    timestamps = [
        *(p.actualizado_el for p in pacientes),
        *(e.actualizado_el for e in estudios),
    ]
    cursores_saturados = []
    if len(pacientes) >= limit:
        cursores_saturados.append(pacientes[-1].actualizado_el)
    if len(estudios) >= limit:
        cursores_saturados.append(estudios[-1].actualizado_el)

    # Si una colección llenó la página, no se debe adelantar el cursor por
    # encima de ella debido a registros más recientes de la otra colección.
    # Es preferible repetir un update_or_create que omitir datos.
    if cursores_saturados:
        siguiente_fecha = min(cursores_saturados)
    elif timestamps:
        siguiente_fecha = max(timestamps)
    else:
        siguiente_fecha = since or timezone.now()

    next_since = siguiente_fecha.isoformat()

    return JsonResponse({
        'ok': True,
        'pacientes': data_pacientes,
        'estudios': data_estudios,
        'next_since': next_since,
        'server_time': timezone.now().isoformat(),
        'hay_mas': len(pacientes) >= limit or len(estudios) >= limit,
    })


@require_GET
def catalogo_servicios(request):
    """Entrega los servicios de la instituci?n autorizada al Desktop."""
    from core.models import Servicio

    institucion, error = _requiere_institucion(request)
    if error:
        return error

    servicios = (
        Servicio.objects
        .filter(institucion=institucion)
        .select_related("tipo_estudio")
        .order_by("id")
    )

    datos = [
        {
            "id": servicio.id,
            "nombre": servicio.nombre,
            "tipo": servicio.tipo,
            "precio_base": str(servicio.precio_base),
            "precio_editable": servicio.precio_editable,
            "activo": servicio.activo,
            "tipo_estudio_codigo": (
                servicio.tipo_estudio.codigo
                if servicio.tipo_estudio_id else None
            ),
        }
        for servicio in servicios
    ]

    return JsonResponse({
        "ok": True,
        "institucion_id": institucion.id,
        "total": len(datos),
        "servicios": datos,
    })
