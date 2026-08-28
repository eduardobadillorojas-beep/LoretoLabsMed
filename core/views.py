from datetime import date
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path
import hashlib
import json
import logging
import textwrap
from html.parser import HTMLParser
from urllib.parse import quote
from xml.sax.saxutils import escape

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Prefetch, Q
from django.core.paginator import Paginator
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.html import strip_tags
from django.views.decorators.http import require_POST

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.pdfgen import canvas as pdf_canvas

import pydicom
import numpy as np
from PIL import Image as PILImage
from pydicom.errors import InvalidDicomError
from pydicom.pixels import apply_modality_lut

from .forms import (
    CitaForm,
    ConsultaForm,
    DestinoAtencionForm,
    EstudioForm,
    PacienteForm,
)

from .models import (
    ArchivoEstudio,
    BitacoraRadiologica,
    CargoPaciente,
    CorteCaja,
    CreditoPaciente,
    AbonoCredito,
    PagoAbonoCredito,
    Cita,
    Cobro,
    Consulta,
    Estudio,
    EstudioDicom,
    EliminacionSerieDicom,
    EstudioSolicitado,
    IndicacionMedica,
    InstanciaDicom,
    MedicamentoReceta,
    MembresiaInstitucion,
    MovimientoCaja,
    Paciente,
    PagoCobro,
    PerfilMedico,
    PlantillaReporteRadiologico,
    RecetaMedica,
    ReporteRadiologico,
    RevisionReporteRadiologico,
    SesionTrabajo,
    SolicitudEstudio,
    Servicio,
    SerieDicom,
    TipoEstudio,
)


logger = logging.getLogger(__name__)


class _LimpiadorReporteHTML(HTMLParser):
    etiquetas_permitidas = {
        'b', 'strong', 'i', 'em', 'u', 'br', 'p', 'ul', 'ol', 'li',
    }

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.partes = []

    def handle_starttag(self, tag, attrs):
        if tag in self.etiquetas_permitidas:
            self.partes.append(f'<{tag}>')

    def handle_startendtag(self, tag, attrs):
        if tag in self.etiquetas_permitidas:
            self.partes.append(f'<{tag}/>')

    def handle_endtag(self, tag):
        if tag in self.etiquetas_permitidas and tag != 'br':
            self.partes.append(f'</{tag}>')

    def handle_data(self, data):
        self.partes.append(escape(data))


def limpiar_html_reporte(valor):
    limpiador = _LimpiadorReporteHTML()
    limpiador.feed(valor or '')
    limpiador.close()
    return ''.join(limpiador.partes).strip()


def texto_plano_reporte(valor):
    texto = (valor or '').replace('<br>', '\n').replace('<br/>', '\n')
    texto = texto.replace('</p>', '\n').replace('</li>', '\n')
    return strip_tags(texto).strip()


# =========================================================
# UTILIDADES
# =========================================================

def obtener_membresia_usuario(request):
    return (
        MembresiaInstitucion.objects
        .select_related('institucion')
        .filter(
            usuario=request.user,
            activa=True,
            institucion__activa=True,
        )
        .first()
    )


def obtener_institucion_usuario(request):
    membresia = obtener_membresia_usuario(request)

    if not membresia:
        return None

    return membresia.institucion


def puede_administrar_configuracion(request, membresia=None):
    if request.user.is_superuser:
        return True

    if membresia is None:
        membresia = obtener_membresia_usuario(request)

    return bool(
        membresia
        and membresia.rol == 'ADMIN'
    )


def obtener_ip(request):
    forwarded_for = request.META.get(
        'HTTP_X_FORWARDED_FOR'
    )

    if forwarded_for:
        ip = forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')

    return ip


def calcular_edad(
    fecha_nacimiento,
    fecha_referencia=None
):
    if not fecha_nacimiento:
        return None

    if fecha_referencia is None:
        fecha_referencia = timezone.localdate()

    return (
        fecha_referencia.year
        - fecha_nacimiento.year
        - (
            (
                fecha_referencia.month,
                fecha_referencia.day,
            )
            <
            (
                fecha_nacimiento.month,
                fecha_nacimiento.day,
            )
        )
    )


def obtener_nombre_usuario(usuario):
    if not usuario:
        return ''

    nombre_completo = (
        usuario.get_full_name().strip()
    )

    if nombre_completo:
        return nombre_completo

    return usuario.username


def calcular_movimientos_corte(corte, hasta=None):
    hasta = hasta or timezone.now()
    desde = corte.abierto_el
    cero = Decimal('0.00')
    formas = {'EFECTIVO': cero, 'TARJETA': cero, 'TRANSFERENCIA': cero, 'OTRO': cero}

    cobros = list(
        Cobro.objects.filter(
            institucion=corte.institucion,
            creado_por=corte.responsable,
            creado_el__gte=desde,
            creado_el__lte=hasta,
        ).prefetch_related('pagos')
    )
    abonos = list(
        AbonoCredito.objects.filter(
            credito__institucion=corte.institucion,
            registrado_por=corte.responsable,
            creado_el__gte=desde,
            creado_el__lte=hasta,
        ).prefetch_related('pagos')
    )
    reembolsos = list(
        Cobro.objects.filter(
            institucion=corte.institucion,
            cancelado_por=corte.responsable,
            cancelado_el__gte=desde,
            cancelado_el__lte=hasta,
            estado='CANCELADO',
        ).prefetch_related('pagos')
    )
    movimientos = list(
        MovimientoCaja.objects.filter(
            corte=corte,
            creado_el__lte=hasta,
        ).select_related('registrado_por')
    )

    for cobro in cobros:
        pagos = list(cobro.pagos.all())
        if pagos:
            for pago in pagos:
                if pago.forma_pago in formas:
                    formas[pago.forma_pago] += pago.monto
        elif cobro.forma_pago in formas:
            formas[cobro.forma_pago] += cobro.total

    for abono in abonos:
        for pago in abono.pagos.all():
            if pago.forma_pago in formas:
                formas[pago.forma_pago] += pago.monto

    total_cobros = sum((c.total for c in cobros), cero)
    total_abonos = sum((a.monto for a in abonos), cero)
    total_reembolsos = sum((c.monto_reembolsado for c in reembolsos), cero)
    reembolso_efectivo = cero
    for cobro in reembolsos:
        if cobro.forma_reembolso == 'EFECTIVO':
            reembolso_efectivo += cobro.monto_reembolsado
        elif cobro.forma_reembolso == 'MIXTO':
            reembolso_efectivo += sum(
                (p.monto for p in cobro.pagos.all() if p.forma_pago == 'EFECTIVO'),
                cero,
            )
    total_entradas_efectivo = sum((m.monto for m in movimientos if m.tipo == 'ENTRADA'), cero)
    total_retiros_efectivo = sum((m.monto for m in movimientos if m.tipo == 'RETIRO'), cero)
    efectivo_esperado = corte.fondo_inicial + formas['EFECTIVO'] - reembolso_efectivo + total_entradas_efectivo - total_retiros_efectivo

    return {
        'total_cobros': total_cobros,
        'total_abonos': total_abonos,
        'total_reembolsos': total_reembolsos,
        'total_neto': total_cobros + total_abonos - total_reembolsos,
        'total_efectivo': formas['EFECTIVO'],
        'total_tarjeta': formas['TARJETA'],
        'total_transferencia': formas['TRANSFERENCIA'],
        'total_otro': formas['OTRO'],
        'total_entradas_efectivo': total_entradas_efectivo,
        'total_retiros_efectivo': total_retiros_efectivo,
        'reembolso_efectivo': reembolso_efectivo,
        'efectivo_esperado': efectivo_esperado,
        'numero_cobros': len(cobros),
        'numero_abonos': len(abonos),
        'numero_reembolsos': len(reembolsos),
        'numero_movimientos': len(movimientos),
        'movimientos': movimientos,
    }


def detectar_tipo_archivo(nombre):
    extension = Path(
        nombre
    ).suffix.lower()

    if extension in [
        '.dcm',
        '.dicom',
    ]:
        return 'DICOM'

    if extension in [
        '.jpg',
        '.jpeg',
        '.png',
        '.webp',
        '.bmp',
    ]:
        return 'IMAGEN'

    if extension in [
        '.pdf',
        '.doc',
        '.docx',
        '.txt',
    ]:
        return 'DOCUMENTO'

    return 'OTRO'


def valor_dicom(dataset, nombre, default=''):
    valor = getattr(dataset, nombre, default)
    return default if valor is None else str(valor).strip()


def entero_dicom(dataset, nombre):
    try:
        return int(getattr(dataset, nombre, None))
    except (TypeError, ValueError):
        return None


def fecha_dicom(valor):
    try:
        return date.fromisoformat(f'{valor[0:4]}-{valor[4:6]}-{valor[6:8]}')
    except (TypeError, ValueError):
        return None


def hora_dicom(valor):
    try:
        limpio = str(valor).split('.')[0].ljust(6, '0')
        return timezone.datetime.strptime(limpio[:6], '%H%M%S').time()
    except (TypeError, ValueError):
        return None


def analizar_archivo_dicom(archivo):
    archivo.seek(0)
    digest = hashlib.sha256()
    tamano = 0
    for bloque in archivo.chunks():
        digest.update(bloque)
        tamano += len(bloque)
    archivo.seek(0)
    try:
        dataset = pydicom.dcmread(archivo, stop_before_pixels=True, force=False)
    except (InvalidDicomError, EOFError, OSError, ValueError) as exc:
        archivo.seek(0)
        raise ValueError('El archivo no contiene un encabezado DICOM válido.') from exc

    requeridos = {
        'StudyInstanceUID': valor_dicom(dataset, 'StudyInstanceUID'),
        'SeriesInstanceUID': valor_dicom(dataset, 'SeriesInstanceUID'),
        'SOPInstanceUID': valor_dicom(dataset, 'SOPInstanceUID'),
    }
    faltantes = [nombre for nombre, valor in requeridos.items() if not valor]
    if faltantes:
        archivo.seek(0)
        raise ValueError('Faltan identificadores DICOM obligatorios: ' + ', '.join(faltantes) + '.')

    transfer_syntax = ''
    if getattr(dataset, 'file_meta', None):
        transfer_syntax = valor_dicom(dataset.file_meta, 'TransferSyntaxUID')

    metadatos = {
        'patient_id': valor_dicom(dataset, 'PatientID'),
        'patient_name': valor_dicom(dataset, 'PatientName'),
        'patient_birth_date': valor_dicom(dataset, 'PatientBirthDate'),
        'patient_sex': valor_dicom(dataset, 'PatientSex'),
        'study_date': valor_dicom(dataset, 'StudyDate'),
        'study_time': valor_dicom(dataset, 'StudyTime'),
        'study_description': valor_dicom(dataset, 'StudyDescription'),
        'series_description': valor_dicom(dataset, 'SeriesDescription'),
        'modality': valor_dicom(dataset, 'Modality'),
        'manufacturer': valor_dicom(dataset, 'Manufacturer'),
        'manufacturer_model': valor_dicom(dataset, 'ManufacturerModelName'),
        'station_name': valor_dicom(dataset, 'StationName'),
        'body_part_examined': valor_dicom(dataset, 'BodyPartExamined'),
        'protocol_name': valor_dicom(dataset, 'ProtocolName'),
        'accession_number': valor_dicom(dataset, 'AccessionNumber'),
        'referring_physician': valor_dicom(dataset, 'ReferringPhysicianName'),
        'sop_class_uid': valor_dicom(dataset, 'SOPClassUID'),
        'transfer_syntax_uid': transfer_syntax,
    }
    archivo.seek(0)
    return {'dataset': dataset, 'hash_sha256': digest.hexdigest(), 'tamano_bytes': tamano, 'metadatos': metadatos, **requeridos}


def crear_bitacora_radiologica(estudio):
    modalidad_original = (
        estudio.tipo_estudio.modalidad
    )

    modalidades_bitacora = {
        'RX': 'RX',
        'TAC': 'TAC',
        'FLUORO': 'FLUORO',
        'MASTO': 'MASTO',
    }

    if (
        modalidad_original
        not in modalidades_bitacora
    ):
        return None

    paciente = estudio.paciente

    fecha_realizacion = (
        estudio.fecha_finalizacion
        or timezone.now()
    )

    fecha_local = timezone.localtime(
        fecha_realizacion
    ).date()

    edad = calcular_edad(
        paciente.fecha_nacimiento,
        fecha_local
    )

    genero = (
        paciente.get_genero_display()
    )

    tecnico_nombre = (
        obtener_nombre_usuario(
            estudio.tecnico
        )
    )

    equipo_nombre = ''

    if estudio.equipo:
        equipo_nombre = (
            estudio.equipo.nombre
        )

    bitacora, creada = (
        BitacoraRadiologica.objects.get_or_create(
            estudio=estudio,
            defaults={
                'fecha_realizacion':
                    fecha_realizacion,

                'paciente_nombre':
                    (
                        f'{paciente.nombre} '
                        f'{paciente.apellido}'
                    ),

                'paciente_registro':
                    paciente.identificacion,

                'fecha_nacimiento':
                    paciente.fecha_nacimiento,

                'edad':
                    edad,

                'genero':
                    genero,

                'modalidad':
                    modalidades_bitacora[
                        modalidad_original
                    ],

                'estudio_nombre':
                    estudio.tipo_estudio.nombre,

                'medico_solicitante':
                    estudio.medico_solicitante,

                'tecnico':
                    estudio.tecnico,

                'tecnico_nombre':
                    tecnico_nombre,

                'equipo':
                    estudio.equipo,

                'equipo_nombre':
                    equipo_nombre,

                'observaciones':
                    estudio.descripcion,
            }
        )
    )

    return bitacora


# =========================================================
# INICIO
# =========================================================

def inicio(request):
    return render(
        request,
        'core/inicio.html'
    )


# =========================================================
# LOGIN
# =========================================================

def login_view(request):
    error_message = None

    if request.method == 'POST':
        usuario = request.POST.get(
            'username'
        )

        clave = request.POST.get(
            'password'
        )

        user = authenticate(
            request,
            username=usuario,
            password=clave
        )

        if user is not None:

            sesiones_anteriores = (
                SesionTrabajo.objects.filter(
                    usuario=user,
                    activa=True
                )
            )

            momento_actual = timezone.now()

            sesiones_anteriores.update(
                activa=False,
                fin=momento_actual
            )

            login(
                request,
                user
            )

            sesion_trabajo = (
                SesionTrabajo.objects.create(
                    usuario=user,
                    ip_inicio=obtener_ip(
                        request
                    ),
                    user_agent=(
                        request.META.get(
                            'HTTP_USER_AGENT',
                            ''
                        )
                    ),
                    activa=True
                )
            )

            request.session[
                'sesion_trabajo_id'
            ] = sesion_trabajo.id

            membresia = (
                MembresiaInstitucion.objects
                .select_related('institucion')
                .filter(
                    usuario=user,
                    activa=True,
                    institucion__activa=True,
                )
                .first()
            )

            if user.is_superuser:
                return redirect(
                    'panel_config'
                )

            if membresia is None:
                return redirect(
                    'panel_config'
                )

            if membresia.rol == 'RECEPCION':
                return redirect(
                    'panel_recepcion'
                )

            if membresia.rol == 'MEDICO':
                return redirect(
                    'panel_medico'
                )

            if membresia.rol in [
                'RADIOLOGIA',
                'TECNICO',
            ]:
                return redirect(
                    'panel_radiologo'
                )

            if membresia.rol == 'ADMIN':
                return redirect(
                    'panel_config'
                )

            return redirect(
                'panel_config'
            )

        error_message = (
            'Usuario o contraseña incorrectos'
        )

    return render(
        request,
        'core/login.html',
        {
            'error': error_message,
        }
    )


# =========================================================
# LOGOUT
# =========================================================

@login_required
def logout_view(request):
    momento_actual = timezone.now()

    sesion_trabajo_id = (
        request.session.get(
            'sesion_trabajo_id'
        )
    )

    if sesion_trabajo_id:

        sesion_trabajo = (
            SesionTrabajo.objects
            .filter(
                id=sesion_trabajo_id,
                usuario=request.user,
                activa=True
            )
            .first()
        )

    else:

        sesion_trabajo = (
            SesionTrabajo.objects
            .filter(
                usuario=request.user,
                activa=True
            )
            .order_by(
                '-inicio'
            )
            .first()
        )

    if sesion_trabajo:
        sesion_trabajo.fin = (
            momento_actual
        )

        sesion_trabajo.ultima_actividad = (
            momento_actual
        )

        sesion_trabajo.activa = False

        sesion_trabajo.ip_fin = (
            obtener_ip(request)
        )

        sesion_trabajo.save(
            update_fields=[
                'fin',
                'ultima_actividad',
                'activa',
                'ip_fin',
            ]
        )

    logout(request)

    return redirect(
        'inicio'
    )


# =========================================================
# MÉDICOS
# =========================================================

@login_required
def perfil_medico(request):
    membresia = obtener_membresia_usuario(request)

    if membresia is None:
        return redirect('panel_config')

    if membresia.rol not in [
        'MEDICO',
        'ADMIN',
    ]:
        return redirect('panel_config')

    perfil, _ = PerfilMedico.objects.get_or_create(
        institucion=membresia.institucion,
        usuario=request.user,
        defaults={
            'activo': True,
        }
    )

    guardado = False

    if request.method == 'POST':
        perfil.especialidad = (
            request.POST.get(
                'especialidad',
                ''
            )
            .strip()
            or None
        )

        perfil.cedula_profesional = (
            request.POST.get(
                'cedula_profesional',
                ''
            )
            .strip()
            or None
        )

        perfil.telefono_profesional = (
            request.POST.get(
                'telefono_profesional',
                ''
            )
            .strip()
            or None
        )

        firma = request.FILES.get(
            'firma'
        )

        if firma:
            perfil.firma = firma

        if request.POST.get(
            'eliminar_firma'
        ) == '1':
            if perfil.firma:
                perfil.firma.delete(
                    save=False
                )

            perfil.firma = None

        perfil.activo = True
        perfil.save()

        guardado = True

    context = {
        'membresia': membresia,
        'institucion': membresia.institucion,
        'perfil': perfil,
        'guardado': guardado,
    }

    return render(
        request,
        'core/perfil_medico.html',
        context
    )


@login_required
def panel_medico(request):
    membresia = obtener_membresia_usuario(request)

    if membresia is None:
        return redirect('panel_config')

    if membresia.rol not in [
        'MEDICO',
        'ADMIN',
    ]:
        return redirect('panel_config')

    institucion = membresia.institucion
    hoy = timezone.localdate()

    areas_medicas = [
        'CONSULTA',
        'TRAUMATOLOGIA',
        'DERMATOLOGIA',
        'ENDOCRINOLOGIA',
    ]

    consultas_en_espera = (
        Consulta.objects
        .select_related(
            'paciente',
            'medico',
        )
        .filter(
            paciente__institucion=institucion,
            estado='EN_ESPERA',
        )
        .order_by(
            'fecha_llegada'
        )
    )

    consultas_en_curso = (
        Consulta.objects
        .select_related(
            'paciente',
            'medico',
        )
        .filter(
            paciente__institucion=institucion,
            estado='EN_CONSULTA',
        )
        .order_by(
            'fecha_inicio',
            'fecha_llegada',
        )
    )

    citas_medicas_hoy = (
        Cita.objects
        .select_related(
            'paciente',
            'tipo_estudio',
        )
        .filter(
            institucion=institucion,
            area__in=areas_medicas,
            fecha_hora__date=hoy,
        )
        .exclude(
            estado__in=[
                'CANCELADA',
                'NO_ASISTIO',
                'FINALIZADA',
            ]
        )
        .order_by(
            'fecha_hora'
        )
    )

    proximas_citas_medicas = (
        Cita.objects
        .select_related(
            'paciente',
            'tipo_estudio',
        )
        .filter(
            institucion=institucion,
            area__in=areas_medicas,
            fecha_hora__date__gt=hoy,
        )
        .exclude(
            estado__in=[
                'CANCELADA',
                'NO_ASISTIO',
                'FINALIZADA',
            ]
        )
        .order_by(
            'fecha_hora'
        )[:20]
    )

    pacientes_atendidos = (
        Consulta.objects
        .select_related(
            'paciente',
            'medico',
        )
        .filter(
            paciente__institucion=institucion,
            estado='FINALIZADA',
        )
        .order_by(
            '-fecha_finalizacion',
            '-fecha_llegada',
        )[:10]
    )

    estudios_recientes = (
        Estudio.objects
        .select_related(
            'paciente',
            'tipo_estudio',
            'reporte_final_por',
        )
        .filter(
            paciente__institucion=institucion,
        )
        .order_by(
            '-fecha_creacion'
        )[:15]
    )

    context = {
        'membresia': membresia,
        'institucion': institucion,
        'consultas_en_espera':
            consultas_en_espera,
        'consultas_en_curso':
            consultas_en_curso,
        'citas_medicas_hoy':
            citas_medicas_hoy,
        'proximas_citas_medicas':
            proximas_citas_medicas,
        'pacientes_atendidos':
            pacientes_atendidos,
        'estudios_recientes':
            estudios_recientes,
    }

    return render(
        request,
        'core/panel_medico.html',
        context
    )


@login_required
def atender_consulta_medica(
    request,
    consulta_id
):
    membresia = obtener_membresia_usuario(request)

    if membresia is None:
        return redirect('panel_config')

    if membresia.rol not in [
        'MEDICO',
        'ADMIN',
    ]:
        return redirect('panel_config')

    consulta = get_object_or_404(
        Consulta.objects.select_related(
            'paciente',
            'medico',
        ),
        pk=consulta_id,
        paciente__institucion=membresia.institucion,
    )

    if request.method == 'POST':
        if consulta.estado == 'EN_ESPERA':
            consulta.estado = 'EN_CONSULTA'
            consulta.medico = request.user
            consulta.fecha_inicio = timezone.now()

            consulta.save(
                update_fields=[
                    'estado',
                    'medico',
                    'fecha_inicio',
                ]
            )

    return redirect(
        'detalle_paciente',
        paciente_id=consulta.paciente_id
    )


@login_required
def finalizar_consulta_medica(
    request,
    consulta_id
):
    membresia = obtener_membresia_usuario(request)

    if membresia is None:
        return redirect('panel_config')

    if membresia.rol not in [
        'MEDICO',
        'ADMIN',
    ]:
        return redirect('panel_config')

    consulta = get_object_or_404(
        Consulta.objects.select_related(
            'paciente',
            'medico',
        ),
        pk=consulta_id,
        paciente__institucion=membresia.institucion,
    )

    if request.method == 'POST':
        if consulta.estado == 'EN_CONSULTA':
            if (
                membresia.rol == 'ADMIN'
                or consulta.medico_id == request.user.id
                or consulta.medico_id is None
            ):
                if consulta.medico_id is None:
                    consulta.medico = request.user

                consulta.estado = 'FINALIZADA'
                consulta.fecha_finalizacion = timezone.now()

                consulta.save(
                    update_fields=[
                        'estado',
                        'medico',
                        'fecha_finalizacion',
                    ]
                )

    return redirect(
        'panel_medico'
    )


# =========================================================
# PANEL RADIOLOGÍA
# =========================================================

@login_required
def panel_radiologo(request):
    membresia = obtener_membresia_usuario(request)

    if membresia is None:
        return redirect('panel_config')

    if membresia.rol not in [
        'TECNICO',
        'RADIOLOGIA',
        'ADMIN',
    ]:
        return redirect('panel_config')

    institucion = membresia.institucion
    hoy = timezone.localdate()

    estudios_pendientes = (
        Estudio.objects
        .select_related(
            'paciente',
            'consulta',
            'tipo_estudio',
            'tecnico',
            'equipo',
        )
        .filter(
            paciente__institucion=institucion,
            estado='PENDIENTE',
        )
        .order_by(
            'fecha_creacion'
        )
    )

    estudios_en_proceso = (
        Estudio.objects
        .select_related(
            'paciente',
            'consulta',
            'tipo_estudio',
            'tecnico',
            'equipo',
        )
        .filter(
            paciente__institucion=institucion,
            estado='EN_PROCESO',
        )
        .order_by(
            'fecha_inicio',
            'fecha_creacion'
        )
    )

    estudios_realizados_hoy = (
        Estudio.objects
        .select_related(
            'paciente',
            'consulta',
            'tipo_estudio',
            'tecnico',
            'equipo',
        )
        .filter(
            paciente__institucion=institucion,
            estado='COMPLETADO',
            fecha_finalizacion__date=hoy,
        )
        .order_by(
            '-fecha_finalizacion'
        )
    )

    citas_radiologia_hoy = (
        Cita.objects
        .select_related(
            'tipo_estudio'
        )
        .filter(
            institucion=institucion,
            area='RADIOLOGIA',
            fecha_hora__date=hoy,
        )
        .exclude(
            estado__in=[
                'CANCELADA',
                'NO_ASISTIO',
                'FINALIZADA',
            ]
        )
        .order_by(
            'fecha_hora'
        )
    )

    # -----------------------------------------------------
    # BUSCADOR / HISTORIAL DE PACIENTES
    # -----------------------------------------------------

    busqueda_paciente = (
        request.GET.get('q', '').strip()
    )

    estudios_historial = (
        Estudio.objects
        .select_related(
            'tipo_estudio'
        )
        .order_by(
            '-fecha_creacion'
        )
    )

    pacientes_historial = (
        Paciente.objects
        .filter(
            institucion=institucion
        )
        .prefetch_related(
            Prefetch(
                'estudios',
                queryset=estudios_historial,
                to_attr='estudios_radiologia_historial',
            )
        )
        .order_by(
            '-creado_el'
        )
    )

    if busqueda_paciente:
        pacientes_historial = (
            pacientes_historial.filter(
                Q(
                    identificacion__icontains=
                    busqueda_paciente
                )
                |
                Q(
                    nombre__icontains=
                    busqueda_paciente
                )
                |
                Q(
                    apellido__icontains=
                    busqueda_paciente
                )
                |
                Q(
                    telefono__icontains=
                    busqueda_paciente
                )
            )
        )

    # Evita cargar una tabla enorme de una sola vez.
    # La búsqueda sigue funcionando sobre todos los pacientes
    # de la institución antes de aplicar este límite.
    pacientes_historial = (
        pacientes_historial[:50]
    )

    context = {
        'membresia': membresia,
        'institucion': institucion,
        'estudios_pendientes':
            estudios_pendientes,
        'estudios_en_proceso':
            estudios_en_proceso,
        'estudios_realizados_hoy':
            estudios_realizados_hoy,
        'citas_radiologia_hoy':
            citas_radiologia_hoy,
        'busqueda_paciente':
            busqueda_paciente,
        'pacientes_historial':
            pacientes_historial,
    }

    return render(
        request,
        'core/panel_radiologo.html',
        context
    )

# =========================================================
# ESTACIÓN DE TRABAJO RADIOLOGÍA
# =========================================================

@login_required
def estudio_radiologia(
    request,
    estudio_id
):
    membresia = obtener_membresia_usuario(request)

    if membresia is None:
        return redirect('panel_config')

    if membresia.rol not in [
        'TECNICO',
        'RADIOLOGIA',
        'ADMIN',
    ]:
        return redirect('panel_config')

    estudio = get_object_or_404(
        Estudio.objects.select_related(
            'paciente',
            'tipo_estudio',
            'tecnico',
            'equipo',
            'pre_reporte_por',
            'reporte_final_por',
        ),
        pk=estudio_id,
        paciente__institucion=membresia.institucion,
    )

    archivos = (
        estudio.archivos
        .select_related(
            'subido_por',
            'instancia_dicom__serie',
        )
        .all()
    )
    archivos_generales = [
        archivo for archivo in archivos
        if archivo.tipo_archivo != 'DICOM'
    ]

    registro_dicom = (
        EstudioDicom.objects
        .filter(estudio=estudio)
        .prefetch_related('series__instancias')
        .first()
    )

    antecedentes = (
        estudio.paciente.estudios
        .select_related(
            'tipo_estudio'
        )
        .exclude(
            pk=estudio.pk
        )
        .order_by(
            '-fecha_creacion'
        )
    )

    edad = calcular_edad(
        estudio.paciente.fecha_nacimiento
    )

    puede_pre_reportar = (
        membresia.rol
        in [
            'TECNICO',
            'RADIOLOGIA',
        ]
    )

    puede_emitir_reporte_final = (
        membresia.rol
        == 'RADIOLOGIA'
    )

    estudio_adicional_form = EstudioForm(
        initial={
            'estado': 'PENDIENTE',
            'medico_solicitante':
                estudio.medico_solicitante,
        }
    )

    context = {
        'estudio': estudio,
        'paciente': estudio.paciente,
        'archivos': archivos,
        'archivos_generales': archivos_generales,
        'registro_dicom': registro_dicom,
        'antecedentes': antecedentes,
        'edad': edad,
        'membresia': membresia,
        'puede_pre_reportar':
            puede_pre_reportar,
        'puede_emitir_reporte_final':
            puede_emitir_reporte_final,
        'estudio_adicional_form':
            estudio_adicional_form,
    }

    return render(
        request,
        'core/estudio_radiologia.html',
        context
    )

@login_required
def nuevo_estudio_desde_radiologia(
    request,
    estudio_id
):
    membresia = obtener_membresia_usuario(request)

    if membresia is None:
        return redirect('panel_config')

    if membresia.rol not in [
        'TECNICO',
        'RADIOLOGIA',
        'ADMIN',
    ]:
        return redirect('panel_config')

    estudio_origen = get_object_or_404(
        Estudio.objects.select_related(
            'paciente',
            'tipo_estudio',
        ),
        pk=estudio_id,
        paciente__institucion=membresia.institucion,
    )

    if request.method != 'POST':
        return redirect(
            'estudio_radiologia',
            estudio_id=estudio_origen.id
        )

    estudio_form = EstudioForm(
        request.POST
    )

    if estudio_form.is_valid():
        estudio_nuevo = estudio_form.save(
            commit=False
        )

        estudio_nuevo.paciente = (
            estudio_origen.paciente
        )

        estudio_nuevo.estado = 'PENDIENTE'

        if not estudio_nuevo.descripcion:
            estudio_nuevo.descripcion = (
                'Estudio adicional generado desde Radiología.'
            )

        estudio_nuevo.save()

        return redirect(
            'estudio_radiologia',
            estudio_id=estudio_nuevo.id
        )

    return redirect(
        'estudio_radiologia',
        estudio_id=estudio_origen.id
    )


# =========================================================
# INICIAR ESTUDIO
# =========================================================

@login_required
def iniciar_estudio_radiologia(
    request,
    estudio_id
):
    membresia = obtener_membresia_usuario(request)

    if membresia is None:
        return redirect('panel_config')

    if membresia.rol not in [
        'TECNICO',
        'RADIOLOGIA',
    ]:
        return redirect('panel_radiologo')

    estudio = get_object_or_404(
        Estudio,
        pk=estudio_id,
        paciente__institucion=membresia.institucion,
    )

    if request.method == 'POST':
        if estudio.estado == 'PENDIENTE':
            estudio.estado = 'EN_PROCESO'
            estudio.fecha_inicio = timezone.now()
            estudio.tecnico = request.user

            estudio.save(
                update_fields=[
                    'estado',
                    'fecha_inicio',
                    'tecnico',
                ]
            )

    return redirect(
        'estudio_radiologia',
        estudio_id=estudio.id
    )

# =========================================================
# CARGAR ARCHIVOS
# =========================================================

@login_required
def cargar_archivos_estudio(
    request,
    estudio_id
):
    membresia = obtener_membresia_usuario(request)

    if membresia is None:
        return redirect('panel_config')

    if membresia.rol not in [
        'TECNICO',
        'RADIOLOGIA',
    ]:
        return redirect('panel_radiologo')

    estudio = get_object_or_404(
        Estudio,
        pk=estudio_id,
        paciente__institucion=membresia.institucion,
    )

    if request.method == 'POST':
        archivos_manuales = request.FILES.getlist('archivos')
        archivos_carpeta = request.FILES.getlist('carpeta_dicom')
        dicom_carpeta = [
            archivo for archivo in archivos_carpeta
            if detectar_tipo_archivo(archivo.name) == 'DICOM'
        ]
        ignorados_carpeta = len(archivos_carpeta) - len(dicom_carpeta)
        archivos = archivos_manuales + dicom_carpeta

        if ignorados_carpeta:
            messages.info(
                request,
                f'Se ignoraron {ignorados_carpeta} archivo(s) no DICOM de la carpeta.'
            )

        if not archivos:
            messages.warning(request, 'No se encontraron archivos DICOM para cargar.')
            return redirect('estudio_radiologia', estudio_id=estudio.id)

        if estudio.estado == 'PENDIENTE':
            estudio.estado = 'EN_PROCESO'
            estudio.fecha_inicio = timezone.now()
            estudio.tecnico = request.user

            estudio.save(
                update_fields=[
                    'estado',
                    'fecha_inicio',
                    'tecnico',
                ]
            )

        archivos_cargados = 0
        for archivo in archivos:
            try:
                tipo_archivo = detectar_tipo_archivo(archivo.name)

                if tipo_archivo != 'DICOM':
                    ArchivoEstudio.objects.create(
                        estudio=estudio,
                        archivo=archivo,
                        tipo_archivo=tipo_archivo,
                        nombre_original=archivo.name,
                        subido_por=request.user
                    )
                    archivos_cargados += 1
                    continue

                datos = analizar_archivo_dicom(archivo)
                dataset = datos['dataset']
                institucion = estudio.paciente.institucion

                if InstanciaDicom.objects.filter(institucion=institucion, sop_instance_uid=datos['SOPInstanceUID']).exists():
                    messages.warning(request, f'{archivo.name}: la instancia DICOM ya existe.')
                    continue
                if InstanciaDicom.objects.filter(institucion=institucion, hash_sha256=datos['hash_sha256']).exists():
                    messages.warning(request, f'{archivo.name}: el archivo DICOM ya fue almacenado.')
                    continue

                with transaction.atomic():
                    registro, creado = EstudioDicom.objects.get_or_create(
                        estudio=estudio,
                        defaults={
                            'institucion': institucion,
                            'study_instance_uid': datos['StudyInstanceUID'],
                            'accession_number': datos['metadatos']['accession_number'],
                            'patient_id_dicom': datos['metadatos']['patient_id'],
                            'patient_name_dicom': datos['metadatos']['patient_name'],
                            'descripcion': datos['metadatos']['study_description'],
                            'fecha_estudio': fecha_dicom(datos['metadatos']['study_date']),
                            'hora_estudio': hora_dicom(datos['metadatos']['study_time']),
                            'medico_referente': datos['metadatos']['referring_physician'],
                        },
                    )
                    if not creado and registro.study_instance_uid != datos['StudyInstanceUID']:
                        raise ValueError('El archivo pertenece a otro Study Instance UID.')

                    serie, _ = SerieDicom.objects.get_or_create(
                        institucion=institucion,
                        series_instance_uid=datos['SeriesInstanceUID'],
                        defaults={
                            'estudio_dicom': registro,
                            'modalidad': datos['metadatos']['modality'],
                            'numero_serie': entero_dicom(dataset, 'SeriesNumber'),
                            'descripcion': datos['metadatos']['series_description'],
                            'protocolo': datos['metadatos']['protocol_name'],
                            'region_anatomica': datos['metadatos']['body_part_examined'],
                            'fabricante': datos['metadatos']['manufacturer'],
                            'estacion': datos['metadatos']['station_name'],
                        },
                    )
                    if serie.estudio_dicom_id != registro.id:
                        raise ValueError('La serie DICOM ya pertenece a otro estudio.')

                    archivo_guardado = ArchivoEstudio.objects.create(
                        estudio=estudio,
                        archivo=archivo,
                        tipo_archivo='DICOM',
                        nombre_original=archivo.name,
                        subido_por=request.user,
                    )
                    InstanciaDicom.objects.create(
                        institucion=institucion,
                        serie=serie,
                        archivo_estudio=archivo_guardado,
                        sop_instance_uid=datos['SOPInstanceUID'],
                        sop_class_uid=datos['metadatos']['sop_class_uid'],
                        transfer_syntax_uid=datos['metadatos']['transfer_syntax_uid'],
                        numero_instancia=entero_dicom(dataset, 'InstanceNumber'),
                        filas=entero_dicom(dataset, 'Rows'),
                        columnas=entero_dicom(dataset, 'Columns'),
                        numero_frames=entero_dicom(dataset, 'NumberOfFrames') or 1,
                        bits_asignados=entero_dicom(dataset, 'BitsAllocated'),
                        interpretacion_fotometrica=valor_dicom(dataset, 'PhotometricInterpretation'),
                        hash_sha256=datos['hash_sha256'],
                        tamano_bytes=datos['tamano_bytes'],
                        metadatos=datos['metadatos'],
                    )
                    archivos_cargados += 1

            except ValueError as exc:
                messages.error(request, f'{archivo.name}: {exc}')

            except Exception as exc:
                logger.exception(
                    (
                        'Error al subir archivo de estudio '
                        'al almacenamiento. estudio_id=%s '
                        'archivo=%s tipo_error=%s mensaje=%s'
                    ),
                    estudio.id,
                    archivo.name,
                    type(exc).__name__,
                    str(exc),
                )

                messages.error(request, f'No se pudo cargar {archivo.name}. Revisa el archivo.')

        if archivos_cargados:
            messages.success(request, f'Se cargaron {archivos_cargados} archivo(s) correctamente.')

    return redirect(
        'estudio_radiologia',
        estudio_id=estudio.id
    )

# =========================================================
# ELIMINAR ARCHIVO
# =========================================================

@login_required
def eliminar_archivo_estudio(
    request,
    estudio_id,
    archivo_id
):
    membresia = obtener_membresia_usuario(request)

    if membresia is None:
        return redirect('panel_config')

    if membresia.rol not in [
        'TECNICO',
        'RADIOLOGIA',
    ]:
        return redirect('panel_radiologo')

    estudio = get_object_or_404(
        Estudio,
        pk=estudio_id,
        paciente__institucion=membresia.institucion,
    )

    archivo = get_object_or_404(
        ArchivoEstudio,
        pk=archivo_id,
        estudio=estudio
    )

    if request.method == 'POST':
        if hasattr(archivo, 'instancia_dicom'):
            messages.error(request, 'El original DICOM es inmutable y no puede eliminarse.')
            return redirect('estudio_radiologia', estudio_id=estudio.id)
        archivo.archivo.delete(
            save=False
        )
        archivo.delete()

    return redirect(
        'estudio_radiologia',
        estudio_id=estudio.id
    )


@login_required
@require_POST
def eliminar_serie_dicom(request, estudio_id, serie_id):
    membresia = obtener_membresia_usuario(request)
    if membresia is None:
        return redirect('panel_config')
    if membresia.rol not in ['TECNICO', 'RADIOLOGIA', 'ADMIN']:
        return redirect('panel_config')

    estudio = get_object_or_404(
        Estudio,
        pk=estudio_id,
        paciente__institucion=membresia.institucion,
    )
    if estudio.estado == 'COMPLETADO':
        messages.error(
            request,
            'No se puede eliminar una serie de un estudio finalizado.',
        )
        return redirect('estudio_radiologia', estudio_id=estudio.id)

    serie = get_object_or_404(
        SerieDicom.objects.select_related('estudio_dicom'),
        pk=serie_id,
        estudio_dicom__estudio=estudio,
        institucion=membresia.institucion,
    )
    motivo = request.POST.get('motivo_eliminacion', '').strip()
    confirmacion = request.POST.get('confirmar_eliminacion') == 'SI'
    if not confirmacion or len(motivo) < 5:
        messages.error(
            request,
            'Confirma la eliminación e indica un motivo de al menos 5 caracteres.',
        )
        return redirect('estudio_radiologia', estudio_id=estudio.id)

    instancias = list(
        serie.instancias.select_related('archivo_estudio').all()
    )
    if not instancias:
        messages.error(
            request,
            'La serie no contiene instancias DICOM para eliminar.',
        )
        return redirect('estudio_radiologia', estudio_id=estudio.id)

    archivos_almacenados = [
        (
            instancia.archivo_estudio.archivo.storage,
            instancia.archivo_estudio.archivo.name,
        )
        for instancia in instancias
        if instancia.archivo_estudio.archivo.name
    ]
    archivo_ids = [
        instancia.archivo_estudio_id
        for instancia in instancias
    ]
    estudio_dicom = serie.estudio_dicom

    with transaction.atomic():
        EliminacionSerieDicom.objects.create(
            institucion=membresia.institucion,
            estudio=estudio,
            usuario=request.user,
            series_instance_uid=serie.series_instance_uid,
            numero_serie=serie.numero_serie,
            descripcion=serie.descripcion or '',
            modalidad=serie.modalidad or '',
            cantidad_instancias=len(instancias),
            motivo=motivo,
            metadatos={
                'sop_instance_uids': [
                    instancia.sop_instance_uid
                    for instancia in instancias
                ],
            },
        )
        InstanciaDicom.objects.filter(serie=serie).delete()
        ArchivoEstudio.objects.filter(pk__in=archivo_ids).delete()
        serie.delete()
        if not estudio_dicom.series.exists():
            estudio_dicom.delete()

    for storage, nombre in archivos_almacenados:
        try:
            storage.delete(nombre)
        except Exception as exc:
            logger.exception(
                'No fue posible eliminar archivo DICOM del almacenamiento. nombre=%s error=%s',
                nombre,
                str(exc),
            )

    messages.success(
        request,
        f'Serie DICOM eliminada correctamente ({len(instancias)} imagen(es)).',
    )
    return redirect('estudio_radiologia', estudio_id=estudio.id)


@login_required
def visor_instancia_dicom(request, estudio_id, instancia_id):
    membresia = obtener_membresia_usuario(request)
    if membresia is None:
        return redirect('panel_config')
    if membresia.rol not in ['TECNICO', 'RADIOLOGIA', 'MEDICO', 'ADMIN']:
        return redirect('panel_config')

    instancia = get_object_or_404(
        InstanciaDicom.objects.select_related(
            'archivo_estudio__estudio__paciente',
            'archivo_estudio__estudio__tipo_estudio',
            'serie__estudio_dicom',
        ),
        pk=instancia_id,
        archivo_estudio__estudio_id=estudio_id,
        institucion=membresia.institucion,
    )
    instancias_serie = list(
        instancia.serie.instancias
        .select_related('archivo_estudio')
        .order_by('numero_instancia', 'id')
    )
    posicion = next(
        indice for indice, item in enumerate(instancias_serie)
        if item.id == instancia.id
    )
    anterior = instancias_serie[posicion - 1] if posicion > 0 else None
    siguiente = instancias_serie[posicion + 1] if posicion + 1 < len(instancias_serie) else None
    try:
        frame_actual = max(0, int(request.GET.get('frame', 0) or 0))
    except (TypeError, ValueError):
        frame_actual = 0
    navegacion_instancias = []
    for indice, item in enumerate(instancias_serie):
        total_frames = max(1, item.numero_frames or 1)
        for frame in range(total_frames):
            imagen_url = reverse(
                'imagen_instancia_dicom',
                args=[estudio_id, item.id],
            )
            visor_url = reverse(
                'visor_instancia_dicom',
                args=[estudio_id, item.id],
            )
            if total_frames > 1:
                imagen_url = f'{imagen_url}?frame={frame}'
                visor_url = f'{visor_url}?frame={frame}'
            navegacion_instancias.append(
                {
                    'id': item.id,
                    'frame': frame,
                    'numero': item.numero_instancia or indice + 1,
                    'imagen_url': imagen_url,
                    'medir_url': reverse(
                        'medir_instancia_dicom',
                        args=[estudio_id, item.id],
                    ),
                    'visor_url': visor_url,
                    'original_url': item.archivo_estudio.archivo.url,
                    'fotometria': item.interpretacion_fotometrica or '',
                }
            )
    posicion_navegacion = next(
        (
            indice for indice, item in enumerate(navegacion_instancias)
            if item['id'] == instancia.id and item['frame'] == frame_actual
        ),
        0,
    )
    series_navegacion = []
    for serie in (
        instancia.serie.estudio_dicom.series
        .prefetch_related('instancias')
        .order_by('numero_serie', 'id')
    ):
        primera = serie.instancias.order_by('numero_instancia', 'id').first()
        if primera is None:
            continue
        series_navegacion.append(
            {
                'id': serie.id,
                'numero': serie.numero_serie,
                'descripcion': serie.descripcion or 'Serie sin descripción',
                'modalidad': serie.modalidad or 'DICOM',
                'cantidad': sum(
                    max(1, item.numero_frames or 1)
                    for item in serie.instancias.all()
                ),
                'visor_url': reverse(
                    'visor_instancia_dicom',
                    args=[estudio_id, primera.id],
                ),
                'miniatura_url': reverse(
                    'imagen_instancia_dicom',
                    args=[estudio_id, primera.id],
                ),
                'activa': serie.id == instancia.serie_id,
            }
        )

    estudio = instancia.archivo_estudio.estudio
    reporte, _ = ReporteRadiologico.objects.get_or_create(
        institucion=membresia.institucion,
        estudio=estudio,
        defaults={'elaborado_por': request.user},
    )
    plantillas = (
        PlantillaReporteRadiologico.objects
        .filter(institucion=membresia.institucion, activa=True)
        .filter(
            Q(tipo_estudio=estudio.tipo_estudio)
            | Q(tipo_estudio__isnull=True, modalidad=estudio.tipo_estudio.modalidad)
            | Q(tipo_estudio__isnull=True, modalidad='')
        )
        .select_related('tipo_estudio')
        .order_by('nombre')
    )
    plantillas_datos = [
        {
            'id': plantilla.id,
            'nombre': plantilla.nombre,
            'contenido_html': ''.join(filter(None, [
                plantilla.hallazgos_html,
                (
                    '<p><b>Impresión diagnóstica:</b></p>'
                    + plantilla.impresion_html
                    if plantilla.impresion_html else ''
                ),
            ])),
        }
        for plantilla in plantillas
    ]
    perfil_reporte = None
    usuario_reporte = reporte.finalizado_por or reporte.elaborado_por
    if usuario_reporte:
        perfil_reporte = PerfilMedico.objects.filter(
            institucion=membresia.institucion,
            usuario=usuario_reporte,
            activo=True,
        ).first()

    return render(
        request,
        'core/visor_instancia_dicom.html',
        {
            'instancia': instancia,
            'estudio': estudio,
            'paciente': estudio.paciente,
            'anterior': anterior,
            'siguiente': siguiente,
            'posicion': posicion_navegacion + 1,
            'total_instancias': len(navegacion_instancias),
            'frame_actual': frame_actual,
            'navegacion_instancias': navegacion_instancias,
            'series_navegacion': series_navegacion,
            'reporte_radiologico': reporte,
            'plantillas_reporte': plantillas,
            'plantillas_reporte_datos': plantillas_datos,
            'edad_paciente': calcular_edad(estudio.paciente.fecha_nacimiento),
            'puede_finalizar_reporte': (
                membresia.rol == 'RADIOLOGIA' or request.user.is_superuser
            ),
            'puede_editar_reporte': reporte.estado != 'FINAL',
            'perfil_reporte': perfil_reporte,
            'contenido_reporte_html': ''.join(filter(None, [
                reporte.hallazgos_html,
                (
                    '<p><b>Impresión diagnóstica:</b></p>'
                    + reporte.impresion_html
                    if reporte.impresion_html else ''
                ),
            ])),
        },
    )


def _snapshot_reporte(estudio, usuario=None):
    paciente = estudio.paciente
    return {
        'paciente': f'{paciente.nombre} {paciente.apellido}'.strip(),
        'registro': paciente.identificacion,
        'fecha_nacimiento': paciente.fecha_nacimiento.isoformat(),
        'edad': calcular_edad(paciente.fecha_nacimiento),
        'estudio': estudio.tipo_estudio.nombre,
        'modalidad': estudio.tipo_estudio.modalidad,
        'medico_solicitante': estudio.medico_solicitante or 'No especificado',
        'fecha_reporte': timezone.localtime().isoformat(),
        'radiologo': obtener_nombre_usuario(usuario) if usuario else '',
    }


@login_required
@require_POST
def guardar_reporte_radiologico(request, estudio_id):
    membresia = obtener_membresia_usuario(request)
    if membresia is None or membresia.rol not in [
        'TECNICO', 'RADIOLOGIA', 'MEDICO', 'ADMIN',
    ]:
        return redirect('panel_config')

    estudio = get_object_or_404(
        Estudio.objects.select_related('paciente', 'tipo_estudio'),
        pk=estudio_id,
        paciente__institucion=membresia.institucion,
    )
    instancia_id = request.POST.get('instancia_id')
    destino = reverse(
        'visor_instancia_dicom',
        args=[estudio.id, instancia_id],
    ) if instancia_id else reverse('estudio_radiologia', args=[estudio.id])

    accion = request.POST.get('accion', 'borrador')
    finalizar = accion == 'finalizar'
    if finalizar and not (
        membresia.rol == 'RADIOLOGIA' or request.user.is_superuser
    ):
        messages.error(request, 'Solo el médico radiólogo puede firmar el reporte final.')
        return redirect(destino)

    contenido = request.POST.get('contenido_html')
    if contenido is None:
        contenido = request.POST.get('hallazgos_html', '')
    hallazgos = limpiar_html_reporte(contenido)
    impresion = ''
    if finalizar and not texto_plano_reporte(hallazgos):
        messages.error(request, 'El reporte final no puede estar vacío.')
        return redirect(destino)

    with transaction.atomic():
        reporte, _ = ReporteRadiologico.objects.select_for_update().get_or_create(
            institucion=membresia.institucion,
            estudio=estudio,
            defaults={'elaborado_por': request.user},
        )
        if reporte.estado == 'FINAL':
            messages.error(
                request,
                'El reporte ya está finalizado. No puede modificarse silenciosamente.',
            )
            return redirect(destino)

        cambio_previo = bool(reporte.hallazgos_html or reporte.impresion_html)
        if cambio_previo:
            RevisionReporteRadiologico.objects.create(
                reporte=reporte,
                version=reporte.version,
                estado=reporte.estado,
                hallazgos_html=reporte.hallazgos_html,
                impresion_html=reporte.impresion_html,
                modificado_por=request.user,
                datos_snapshot=reporte.datos_snapshot,
            )
            reporte.version += 1

        reporte.hallazgos_html = hallazgos
        reporte.impresion_html = impresion
        reporte.elaborado_por = request.user
        reporte.datos_snapshot = _snapshot_reporte(estudio, request.user)

        if finalizar:
            reporte.estado = 'FINAL'
            reporte.finalizado_por = request.user
            reporte.finalizado_el = timezone.now()
            estudio.reporte_final = '\n\n'.join(filter(None, [
                texto_plano_reporte(hallazgos),
                texto_plano_reporte(impresion),
            ]))
            estudio.reporte_final_por = request.user
            estudio.fecha_reporte_final = reporte.finalizado_el
            estudio.estado_reporte = 'FINAL'
            estudio.save(update_fields=[
                'reporte_final', 'reporte_final_por',
                'fecha_reporte_final', 'estado_reporte',
            ])
        else:
            reporte.estado = 'BORRADOR'
            estudio.pre_reporte = '\n\n'.join(filter(None, [
                texto_plano_reporte(hallazgos),
                texto_plano_reporte(impresion),
            ]))
            estudio.pre_reporte_por = request.user
            estudio.fecha_pre_reporte = timezone.now()
            estudio.estado_reporte = 'PRE_REPORTE'
            estudio.save(update_fields=[
                'pre_reporte', 'pre_reporte_por',
                'fecha_pre_reporte', 'estado_reporte',
            ])
        reporte.save()

    messages.success(
        request,
        'Reporte final firmado correctamente.' if finalizar
        else 'Borrador radiológico guardado correctamente.',
    )
    return redirect(destino)


@login_required
@require_POST
def guardar_plantilla_reporte_radiologico(request, estudio_id):
    membresia = obtener_membresia_usuario(request)
    if membresia is None or membresia.rol not in ['RADIOLOGIA', 'ADMIN']:
        return redirect('panel_config')
    estudio = get_object_or_404(
        Estudio.objects.select_related('paciente', 'tipo_estudio'),
        pk=estudio_id,
        paciente__institucion=membresia.institucion,
    )
    instancia_id = request.POST.get('instancia_id')
    nombre = request.POST.get('nombre_plantilla', '').strip()
    if len(nombre) < 3:
        messages.error(request, 'La plantilla necesita un nombre de al menos 3 caracteres.')
    else:
        PlantillaReporteRadiologico.objects.update_or_create(
            institucion=membresia.institucion,
            nombre=nombre,
            defaults={
                'creada_por': request.user,
                'tipo_estudio': estudio.tipo_estudio,
                'modalidad': estudio.tipo_estudio.modalidad,
                'hallazgos_html': limpiar_html_reporte(
                    request.POST.get(
                        'contenido_html',
                        request.POST.get('hallazgos_html', ''),
                    )
                ),
                'impresion_html': '',
                'activa': True,
            },
        )
        messages.success(request, f'Plantilla “{nombre}” guardada correctamente.')
    if instancia_id:
        return redirect('visor_instancia_dicom', estudio.id, instancia_id)
    return redirect('estudio_radiologia', estudio.id)


def _html_para_reportlab(valor):
    valor = limpiar_html_reporte(valor)
    reemplazos = {
        '<p>': '', '</p>': '<br/><br/>',
        '<ul>': '', '</ul>': '', '<ol>': '', '</ol>': '',
        '<li>': '• ', '</li>': '<br/>',
        '<strong>': '<b>', '</strong>': '</b>',
        '<em>': '<i>', '</em>': '</i>',
        '<u>': '', '</u>': '',
    }
    for origen, destino in reemplazos.items():
        valor = valor.replace(origen, destino)
    return valor or '—'


@login_required
def _reporte_radiologico_pdf_enriquecido(request, estudio_id):
    membresia = obtener_membresia_usuario(request)
    if membresia is None or membresia.rol not in [
        'TECNICO', 'RADIOLOGIA', 'MEDICO', 'ADMIN',
    ]:
        return redirect('panel_config')
    reporte = get_object_or_404(
        ReporteRadiologico.objects.select_related(
            'estudio__paciente', 'estudio__tipo_estudio',
            'institucion', 'finalizado_por', 'elaborado_por',
        ),
        estudio_id=estudio_id,
        institucion=membresia.institucion,
    )
    estudio = reporte.estudio
    paciente = estudio.paciente
    institucion = reporte.institucion
    firmante = reporte.finalizado_por or reporte.elaborado_por
    perfil = PerfilMedico.objects.filter(
        institucion=institucion, usuario=firmante, activo=True,
    ).first() if firmante else None

    buffer = BytesIO()
    documento = SimpleDocTemplate(
        buffer, pagesize=letter, rightMargin=1.4 * cm, leftMargin=1.4 * cm,
        topMargin=1.0 * cm, bottomMargin=1.0 * cm,
        title='Reporte radiológico',
        author=obtener_nombre_usuario(firmante) if firmante else 'Loreto One',
    )
    estilos = getSampleStyleSheet()
    titulo = ParagraphStyle(
        'ReporteTitulo', parent=estilos['Heading1'], fontName='Helvetica-Bold',
        fontSize=13, leading=15, textColor=colors.HexColor('#0f2747'),
    )
    subtitulo = ParagraphStyle(
        'ReporteSubtitulo', parent=estilos['Heading2'], fontName='Helvetica-Bold',
        fontSize=9.5, leading=12, textColor=colors.HexColor('#17365d'),
        spaceBefore=9, spaceAfter=5,
    )
    normal = ParagraphStyle(
        'ReporteNormal', parent=estilos['Normal'], fontName='Helvetica',
        fontSize=8.5, leading=11, textColor=colors.HexColor('#111827'),
    )
    pequeno = ParagraphStyle(
        'ReportePequeno', parent=normal, fontSize=7, leading=8.5,
        textColor=colors.HexColor('#475569'),
    )
    centrado = ParagraphStyle('ReporteCentrado', parent=pequeno, alignment=TA_CENTER)

    def imagen_campo(campo, ancho, alto):
        if not campo:
            return None
        try:
            campo.open('rb')
            datos = campo.read()
            campo.close()
            return Image(BytesIO(datos), width=ancho, height=alto, kind='proportional')
        except Exception:
            return None

    nombre_institucion = institucion.nombre_comercial or institucion.nombre
    datos_institucion = [Paragraph(escape(nombre_institucion), titulo)]
    for dato in [institucion.direccion, institucion.telefono, institucion.email]:
        if dato:
            datos_institucion.append(Paragraph(escape(str(dato)), pequeno))
    horarios = []
    if institucion.horarios_servicio:
        horarios = [
            Paragraph('<b>HORARIO DE ATENCIÓN</b>', pequeno),
            Paragraph(escape(institucion.horarios_servicio), pequeno),
        ]
    encabezado = Table([[
        imagen_campo(institucion.logo, 2.1 * cm, 1.55 * cm) or '',
        datos_institucion,
        horarios,
    ]], colWidths=[2.5 * cm, 10.2 * cm, 6.1 * cm])
    encabezado.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LINEBELOW', (0, 0), (-1, -1), 1.1, colors.HexColor('#17365d')),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))

    edad = calcular_edad(paciente.fecha_nacimiento)
    fecha_documento = reporte.finalizado_el or reporte.actualizado_el
    datos = [
        [f'<b>PACIENTE:</b> {escape(paciente.nombre)} {escape(paciente.apellido)}',
         f'<b>REGISTRO:</b> {escape(paciente.identificacion)}'],
        [f'<b>EDAD:</b> {edad if edad is not None else "—"} años',
         f'<b>FECHA:</b> {timezone.localtime(fecha_documento):%d/%m/%Y %H:%M}'],
        [f'<b>ESTUDIO:</b> {escape(estudio.tipo_estudio.nombre)}',
         f'<b>MÉDICO SOLICITANTE:</b> {escape(estudio.medico_solicitante or "No especificado")}'],
    ]
    tabla_datos = Table(
        [[Paragraph(a, pequeno), Paragraph(b, pequeno)] for a, b in datos],
        colWidths=[9.4 * cm, 9.4 * cm],
    )
    tabla_datos.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), .45, colors.HexColor('#94a3b8')),
        ('INNERGRID', (0, 0), (-1, -1), .25, colors.HexColor('#cbd5e1')),
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#fbfdff')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('PADDING', (0, 0), (-1, -1), 5),
    ]))
    historia = [
        encabezado, Spacer(1, .18 * cm),
        Paragraph('REPORTE RADIOLÓGICO', titulo), Spacer(1, .12 * cm),
        tabla_datos,
        Paragraph('DESCRIPCIÓN E IMPRESIÓN RADIOLÓGICA', subtitulo),
        Paragraph(_html_para_reportlab(reporte.hallazgos_html), normal),
        Spacer(1, .65 * cm),
    ]
    if reporte.impresion_html:
        historia.extend([
            Paragraph('IMPRESIÓN DIAGNÓSTICA', subtitulo),
            Paragraph(_html_para_reportlab(reporte.impresion_html), normal),
            Spacer(1, .25 * cm),
        ])
    firma = imagen_campo(perfil.firma, 3.4 * cm, 1.05 * cm) if perfil else None
    firma_bloque = [firma or Spacer(1, .75 * cm)]
    firma_bloque.extend([
        Paragraph('_______________________________', centrado),
        Paragraph(f'<b>{escape(obtener_nombre_usuario(firmante) if firmante else "No especificado")}</b>', centrado),
    ])
    datos_firma = []
    if perfil and perfil.especialidad:
        datos_firma.append(escape(perfil.especialidad))
    if perfil and perfil.cedula_profesional:
        datos_firma.append('Céd. Prof. ' + escape(perfil.cedula_profesional))
    if datos_firma:
        firma_bloque.append(Paragraph(' | '.join(datos_firma), centrado))
    tabla_firma = Table([['', firma_bloque, '']], colWidths=[5.3 * cm, 8.2 * cm, 5.3 * cm])
    tabla_firma.setStyle(TableStyle([('ALIGN', (1, 0), (1, 0), 'CENTER')]))
    historia.append(KeepTogether([tabla_firma]))
    if reporte.estado != 'FINAL':
        historia.append(Paragraph('BORRADOR · Documento no firmado', centrado))
    try:
        documento.build(historia)
    except Exception as exc:
        logger.exception(
            'Falló el diseño enriquecido del reporte radiológico. estudio_id=%s error=%s',
            estudio.id,
            str(exc),
        )
        buffer = BytesIO()
        documento = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=1.6 * cm,
            leftMargin=1.6 * cm,
            topMargin=1.2 * cm,
            bottomMargin=1.2 * cm,
            title='Reporte radiológico',
        )
        contenido_plano = '\n\n'.join(filter(None, [
            texto_plano_reporte(reporte.hallazgos_html),
            texto_plano_reporte(reporte.impresion_html),
        ])) or 'Sin contenido.'
        historia_respaldo = [
            Paragraph(escape(nombre_institucion), titulo),
            Paragraph('REPORTE RADIOLÓGICO', subtitulo),
            Paragraph(
                '<b>Paciente:</b> '
                + escape(f'{paciente.nombre} {paciente.apellido}')
                + '<br/><b>Registro:</b> '
                + escape(paciente.identificacion)
                + '<br/><b>Estudio:</b> '
                + escape(estudio.tipo_estudio.nombre),
                normal,
            ),
            Spacer(1, .3 * cm),
            Paragraph(
                escape(contenido_plano).replace('\n', '<br/>'),
                normal,
            ),
        ]
        documento.build(historia_respaldo)

    respuesta = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    disposicion = 'attachment' if request.GET.get('descargar') == '1' else 'inline'
    respuesta['Content-Disposition'] = (
        f'{disposicion}; filename="reporte_{paciente.identificacion}_{estudio.id}.pdf"'
    )
    return respuesta


@login_required
def reporte_radiologico_pdf(request, estudio_id):
    """Genera el PDF y nunca deja al usuario frente a un error 500.

    El diseño institucional enriquecido es la primera opción. Si ReportLab
    encuentra un archivo, una fuente o un contenido inesperado, se entrega
    automáticamente un PDF clínico simplificado con la misma información.
    """
    try:
        return _reporte_radiologico_pdf_enriquecido(request, estudio_id)
    except Exception as exc:
        logger.exception(
            'Se activó el PDF de respaldo del reporte. estudio_id=%s error=%s',
            estudio_id,
            str(exc),
        )

    membresia = obtener_membresia_usuario(request)
    if membresia is None or membresia.rol not in [
        'TECNICO', 'RADIOLOGIA', 'MEDICO', 'ADMIN',
    ]:
        return redirect('panel_config')
    reporte = get_object_or_404(
        ReporteRadiologico.objects.select_related(
            'estudio__paciente', 'estudio__tipo_estudio',
            'institucion', 'finalizado_por', 'elaborado_por',
        ),
        estudio_id=estudio_id,
        institucion=membresia.institucion,
    )
    estudio = reporte.estudio
    paciente = estudio.paciente
    institucion = reporte.institucion
    firmante = reporte.finalizado_por or reporte.elaborado_por
    buffer = BytesIO()
    lienzo = pdf_canvas.Canvas(buffer, pagesize=letter)
    ancho_pagina, alto_pagina = letter
    margen = 1.6 * cm
    y = alto_pagina - margen

    def nueva_pagina():
        nonlocal y
        lienzo.showPage()
        y = alto_pagina - margen

    def escribir(texto, tamano=9, negrita=False, espacio=4):
        nonlocal y
        fuente = 'Helvetica-Bold' if negrita else 'Helvetica'
        lienzo.setFont(fuente, tamano)
        caracteres = max(38, int((ancho_pagina - 2 * margen) / (tamano * .52)))
        lineas = []
        for parrafo in str(texto or '—').splitlines() or ['—']:
            lineas.extend(textwrap.wrap(parrafo, width=caracteres) or [''])
        for linea in lineas:
            if y < margen + 1.2 * cm:
                nueva_pagina()
                lienzo.setFont(fuente, tamano)
            lienzo.drawString(margen, y, linea)
            y -= tamano + 3
        y -= espacio

    nombre_institucion = institucion.nombre_comercial or institucion.nombre
    escribir(nombre_institucion, 14, True, 2)
    escribir('REPORTE RADIOLÓGICO', 12, True, 10)
    escribir(f'Paciente: {paciente.nombre} {paciente.apellido}', 9, True)
    escribir(f'Registro: {paciente.identificacion}')
    escribir(f'Estudio: {estudio.tipo_estudio.nombre}')
    escribir(f'Médico solicitante: {estudio.medico_solicitante or "No especificado"}')
    escribir('DESCRIPCIÓN E IMPRESIÓN RADIOLÓGICA', 10, True, 7)
    contenido = '\n\n'.join(filter(None, [
        texto_plano_reporte(reporte.hallazgos_html),
        texto_plano_reporte(reporte.impresion_html),
    ])) or 'Sin contenido.'
    escribir(contenido, 9, False, 16)
    escribir('________________________________________', 9, False, 2)
    escribir(
        obtener_nombre_usuario(firmante) if firmante else 'No especificado',
        9,
        True,
    )
    if reporte.estado != 'FINAL':
        escribir('BORRADOR · Documento no firmado', 8, True)
    lienzo.save()
    respuesta = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    disposicion = 'attachment' if request.GET.get('descargar') == '1' else 'inline'
    respuesta['Content-Disposition'] = (
        f'{disposicion}; filename="reporte_{paciente.identificacion}_{estudio.id}.pdf"'
    )
    return respuesta


@login_required
def imagen_instancia_dicom(request, estudio_id, instancia_id):
    membresia = obtener_membresia_usuario(request)
    if membresia is None or membresia.rol not in ['TECNICO', 'RADIOLOGIA', 'MEDICO', 'ADMIN']:
        return HttpResponse(status=403)

    instancia = get_object_or_404(
        InstanciaDicom.objects.select_related('archivo_estudio'),
        pk=instancia_id,
        archivo_estudio__estudio_id=estudio_id,
        institucion=membresia.institucion,
    )

    try:
        with instancia.archivo_estudio.archivo.open('rb') as archivo:
            dataset = pydicom.dcmread(archivo)
            pixeles = dataset.pixel_array

        numero_frames = int(getattr(dataset, 'NumberOfFrames', 1) or 1)
        frame = int(request.GET.get('frame', 0))
        frame = max(0, min(frame, numero_frames - 1))
        if numero_frames > 1:
            pixeles = pixeles[frame]

        muestras = int(getattr(dataset, 'SamplesPerPixel', 1) or 1)
        if muestras == 1:
            pixeles = apply_modality_lut(pixeles, dataset).astype(np.float64)

        minimo = float(np.nanmin(pixeles))
        maximo = float(np.nanmax(pixeles))
        centro_predeterminado = (minimo + maximo) / 2
        ancho_predeterminado = max(maximo - minimo, 1.0)

        centro_dicom = getattr(dataset, 'WindowCenter', centro_predeterminado)
        ancho_dicom = getattr(dataset, 'WindowWidth', ancho_predeterminado)
        if hasattr(centro_dicom, '__iter__') and not isinstance(centro_dicom, str):
            centro_dicom = centro_dicom[0]
        if hasattr(ancho_dicom, '__iter__') and not isinstance(ancho_dicom, str):
            ancho_dicom = ancho_dicom[0]

        centro = float(request.GET.get('wc', centro_dicom))
        ancho = max(float(request.GET.get('ww', ancho_dicom)), 1.0)
        inferior = centro - ancho / 2
        imagen_8bits = np.clip((pixeles.astype(np.float64) - inferior) / ancho, 0, 1)
        imagen_8bits = (imagen_8bits * 255).astype(np.uint8)

        if muestras == 1:
            if valor_dicom(dataset, 'PhotometricInterpretation') == 'MONOCHROME1':
                imagen_8bits = 255 - imagen_8bits
            imagen = PILImage.fromarray(imagen_8bits, mode='L')
        else:
            imagen = PILImage.fromarray(imagen_8bits)

        salida = BytesIO()
        imagen.save(salida, format='PNG', optimize=True)
        respuesta = HttpResponse(salida.getvalue(), content_type='image/png')
        respuesta['Cache-Control'] = 'private, max-age=300'
        respuesta['X-DICOM-Window-Center'] = f'{centro:g}'
        respuesta['X-DICOM-Window-Width'] = f'{ancho:g}'
        return respuesta

    except Exception as exc:
        logger.exception(
            'No fue posible renderizar DICOM. instancia_id=%s error=%s',
            instancia.id,
            str(exc),
        )
        return HttpResponse(
            'No fue posible decodificar los píxeles de esta instancia DICOM.',
            status=422,
            content_type='text/plain; charset=utf-8',
        )


@login_required
@require_POST
def medir_instancia_dicom(request, estudio_id, instancia_id):
    membresia = obtener_membresia_usuario(request)
    if membresia is None or membresia.rol not in ['TECNICO', 'RADIOLOGIA', 'MEDICO', 'ADMIN']:
        return JsonResponse({'error': 'Acceso no autorizado.'}, status=403)

    instancia = get_object_or_404(
        InstanciaDicom.objects.select_related('archivo_estudio'),
        pk=instancia_id,
        archivo_estudio__estudio_id=estudio_id,
        institucion=membresia.institucion,
    )

    try:
        datos = json.loads(request.body.decode('utf-8'))
        herramienta = datos.get('herramienta')
        puntos = datos.get('puntos') or []
        frame = max(0, int(datos.get('frame', 0)))

        with instancia.archivo_estudio.archivo.open('rb') as archivo:
            dataset = pydicom.dcmread(archivo)

        filas = int(getattr(dataset, 'Rows', 0) or 0)
        columnas = int(getattr(dataset, 'Columns', 0) or 0)
        if not filas or not columnas:
            return JsonResponse({'error': 'El DICOM no contiene dimensiones válidas.'}, status=422)
        espaciado = getattr(dataset, 'PixelSpacing', None)
        if not espaciado:
            espaciado = getattr(dataset, 'ImagerPixelSpacing', None)
        fila_mm = float(espaciado[0]) if espaciado else None
        columna_mm = float(espaciado[1]) if espaciado else None

        def punto(indice):
            x = max(0.0, min(float(puntos[indice]['x']), columnas - 1))
            y = max(0.0, min(float(puntos[indice]['y']), filas - 1))
            return x, y

        if herramienta == 'distancia' and len(puntos) == 2:
            x1, y1 = punto(0)
            x2, y2 = punto(1)
            if fila_mm is not None and columna_mm is not None:
                distancia = ((x2 - x1) * columna_mm) ** 2 + ((y2 - y1) * fila_mm) ** 2
                return JsonResponse({'valor': distancia ** 0.5, 'unidad': 'mm', 'calibrada': True})
            distancia = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
            return JsonResponse({'valor': distancia, 'unidad': 'px', 'calibrada': False})

        if herramienta == 'roi' and len(puntos) == 2:
            if int(getattr(dataset, 'SamplesPerPixel', 1) or 1) != 1:
                return JsonResponse(
                    {'error': 'La ROI cuantitativa HU requiere una imagen monocromática.'},
                    status=422,
                )

            pixeles = dataset.pixel_array
            numero_frames = int(getattr(dataset, 'NumberOfFrames', 1) or 1)
            frame = min(frame, numero_frames - 1)
            if numero_frames > 1:
                pixeles = pixeles[frame]
            x1, y1 = punto(0)
            x2, y2 = punto(1)
            izquierda, derecha = sorted((int(round(x1)), int(round(x2))))
            arriba, abajo = sorted((int(round(y1)), int(round(y2))))
            derecha = min(columnas, max(derecha + 1, izquierda + 1))
            abajo = min(filas, max(abajo + 1, arriba + 1))

            valores = apply_modality_lut(pixeles, dataset).astype(np.float64)[arriba:abajo, izquierda:derecha]
            if valores.size == 0:
                return JsonResponse({'error': 'La ROI no contiene píxeles.'}, status=422)

            modalidad = valor_dicom(dataset, 'Modality').upper()
            tiene_escala = hasattr(dataset, 'RescaleSlope') and hasattr(dataset, 'RescaleIntercept')
            unidad = 'HU' if modalidad == 'CT' and tiene_escala else 'valor de píxel'
            area = None
            if fila_mm is not None and columna_mm is not None:
                area = valores.size * fila_mm * columna_mm

            return JsonResponse({
                'promedio': float(np.mean(valores)),
                'minimo': float(np.min(valores)),
                'maximo': float(np.max(valores)),
                'desviacion': float(np.std(valores)),
                'area_mm2': area,
                'pixeles': int(valores.size),
                'unidad': unidad,
                'es_hu': unidad == 'HU',
            })

        return JsonResponse({'error': 'Medición no válida.'}, status=400)

    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        return JsonResponse({'error': f'Datos de medición inválidos: {exc}'}, status=400)
    except Exception as exc:
        logger.exception('Error al medir DICOM. instancia_id=%s error=%s', instancia.id, str(exc))
        return JsonResponse({'error': 'No fue posible calcular la medición.'}, status=422)

# =========================================================
# PRE-REPORTE TÉCNICO
# =========================================================

@login_required
def guardar_pre_reporte_estudio(
    request,
    estudio_id
):
    membresia = obtener_membresia_usuario(request)

    if membresia is None:
        return redirect('panel_config')

    estudio = get_object_or_404(
        Estudio,
        pk=estudio_id,
        paciente__institucion=membresia.institucion,
    )

    if membresia.rol not in [
        'TECNICO',
        'RADIOLOGIA',
    ]:
        return redirect(
            'estudio_radiologia',
            estudio_id=estudio.id
        )

    if request.method == 'POST':
        pre_reporte = (
            request.POST.get(
                'pre_reporte',
                ''
            )
            .strip()
        )

        estudio.pre_reporte = (
            pre_reporte
            or None
        )

        if pre_reporte:
            estudio.pre_reporte_por = (
                request.user
            )

            estudio.fecha_pre_reporte = (
                timezone.now()
            )

            estudio.estado_reporte = (
                'POR_VALIDAR'
            )
        else:
            estudio.pre_reporte_por = None
            estudio.fecha_pre_reporte = None

            if estudio.reporte_final:
                estudio.estado_reporte = (
                    'FINAL'
                )
            else:
                estudio.estado_reporte = (
                    'SIN_REPORTE'
                )

        estudio.save(
            update_fields=[
                'pre_reporte',
                'pre_reporte_por',
                'fecha_pre_reporte',
                'estado_reporte',
            ]
        )

    return redirect(
        'estudio_radiologia',
        estudio_id=estudio.id
    )


# =========================================================
# REPORTE RADIOLÓGICO FINAL
# =========================================================

@login_required
def guardar_reporte_final_estudio(
    request,
    estudio_id
):
    membresia = obtener_membresia_usuario(request)

    if membresia is None:
        return redirect('panel_config')

    estudio = get_object_or_404(
        Estudio,
        pk=estudio_id,
        paciente__institucion=membresia.institucion,
    )

    # RADIOLOGIA representa al médico radiólogo
    # dentro del flujo actual de membresías.
    if membresia.rol != 'RADIOLOGIA':
        return redirect(
            'estudio_radiologia',
            estudio_id=estudio.id
        )

    if request.method == 'POST':
        reporte_final = (
            request.POST.get(
                'reporte_final',
                ''
            )
            .strip()
        )

        if reporte_final:
            estudio.reporte_final = (
                reporte_final
            )

            estudio.reporte_final_por = (
                request.user
            )

            estudio.fecha_reporte_final = (
                timezone.now()
            )

            estudio.estado_reporte = (
                'FINAL'
            )

            estudio.save(
                update_fields=[
                    'reporte_final',
                    'reporte_final_por',
                    'fecha_reporte_final',
                    'estado_reporte',
                ]
            )

    return redirect(
        'estudio_radiologia',
        estudio_id=estudio.id
    )


# =========================================================
# FINALIZAR ESTUDIO
# =========================================================

@login_required
def finalizar_estudio_radiologia(
    request,
    estudio_id
):
    membresia = obtener_membresia_usuario(request)

    if membresia is None:
        return redirect('panel_config')

    if membresia.rol not in [
        'TECNICO',
        'RADIOLOGIA',
    ]:
        return redirect('panel_radiologo')

    estudio = get_object_or_404(
        Estudio.objects.select_related(
            'paciente',
            'tipo_estudio',
            'tecnico',
            'equipo',
        ),
        pk=estudio_id,
        paciente__institucion=membresia.institucion,
    )

    if request.method == 'POST':
        momento_actual = timezone.now()

        if not estudio.fecha_inicio:
            estudio.fecha_inicio = momento_actual

        if not estudio.tecnico:
            estudio.tecnico = request.user

        estudio.estado = 'COMPLETADO'
        estudio.fecha_finalizacion = momento_actual

        estudio.save(
            update_fields=[
                'estado',
                'fecha_inicio',
                'fecha_finalizacion',
                'tecnico',
            ]
        )

        crear_bitacora_radiologica(
            estudio
        )

        return redirect(
            'panel_radiologo'
        )

    return redirect(
        'estudio_radiologia',
        estudio_id=estudio.id
    )

# =========================================================
# RECEPCIÓN
# =========================================================

@login_required
def panel_recepcion(request):
    membresia = obtener_membresia_usuario(request)

    if membresia is None:
        return redirect('panel_config')

    if membresia.rol not in [
        'RECEPCION',
        'ADMIN',
    ]:
        return redirect('panel_config')

    busqueda = request.GET.get(
        'buscar',
        ''
    ).strip()

    hoy = timezone.localdate()

    institucion = obtener_institucion_usuario(request)

    if institucion is None:
        return redirect('panel_config')

    consultas_estado = (
        Consulta.objects
        .select_related(
            'medico'
        )
        .order_by(
            '-fecha_llegada'
        )
    )

    estudios_estado = (
        Estudio.objects
        .select_related(
            'tipo_estudio'
        )
        .order_by(
            '-fecha_creacion'
        )
    )

    def preparar_estado_recepcion(
        lista_pacientes
    ):
        pacientes_preparados = list(
            lista_pacientes
        )

        for paciente in pacientes_preparados:
            consulta = None
            estudio = None

            if paciente.consultas_estado_recepcion:
                consulta = (
                    paciente
                    .consultas_estado_recepcion[0]
                )

            if paciente.estudios_estado_recepcion:
                estudio = (
                    paciente
                    .estudios_estado_recepcion[0]
                )

            actividad = None
            tipo_actividad = None

            if consulta and estudio:
                if (
                    consulta.fecha_llegada
                    >= estudio.fecha_creacion
                ):
                    actividad = consulta
                    tipo_actividad = 'CONSULTA'
                else:
                    actividad = estudio
                    tipo_actividad = 'ESTUDIO'

            elif consulta:
                actividad = consulta
                tipo_actividad = 'CONSULTA'

            elif estudio:
                actividad = estudio
                tipo_actividad = 'ESTUDIO'

            paciente.estado_atencion = 'Registrado'
            paciente.estado_atencion_clase = 'secondary'
            paciente.estado_atencion_area = ''

            if tipo_actividad == 'CONSULTA':
                paciente.estado_atencion_area = (
                    'Consulta médica'
                )

                if actividad.estado == 'EN_ESPERA':
                    paciente.estado_atencion = (
                        'En espera'
                    )
                    paciente.estado_atencion_clase = (
                        'warning'
                    )

                elif actividad.estado == 'EN_CONSULTA':
                    paciente.estado_atencion = (
                        'Siendo atendido'
                    )
                    paciente.estado_atencion_clase = (
                        'info'
                    )

                elif actividad.estado == 'FINALIZADA':
                    paciente.estado_atencion = (
                        'Atendido'
                    )
                    paciente.estado_atencion_clase = (
                        'success'
                    )

            elif tipo_actividad == 'ESTUDIO':
                paciente.estado_atencion_area = (
                    'Radiología'
                )

                if actividad.estado == 'PENDIENTE':
                    paciente.estado_atencion = (
                        'En espera'
                    )
                    paciente.estado_atencion_clase = (
                        'warning'
                    )

                elif actividad.estado == 'EN_PROCESO':
                    paciente.estado_atencion = (
                        'Siendo atendido'
                    )
                    paciente.estado_atencion_clase = (
                        'info'
                    )

                elif actividad.estado == 'COMPLETADO':
                    paciente.estado_atencion = (
                        'Atendido'
                    )
                    paciente.estado_atencion_clase = (
                        'success'
                    )

        return pacientes_preparados

    pacientes_queryset = (
        Paciente.objects
        .filter(
            institucion=institucion
        )
        .prefetch_related(
            Prefetch(
                'consultas',
                queryset=consultas_estado,
                to_attr='consultas_estado_recepcion',
            ),
            Prefetch(
                'estudios',
                queryset=estudios_estado,
                to_attr='estudios_estado_recepcion',
            ),
        )
        .order_by(
            '-creado_el'
        )
    )

    if busqueda:
        pacientes_queryset = (
            pacientes_queryset.filter(
                Q(
                    identificacion__icontains=
                    busqueda
                )
                |
                Q(
                    nombre__icontains=
                    busqueda
                )
                |
                Q(
                    apellido__icontains=
                    busqueda
                )
                |
                Q(
                    telefono__icontains=
                    busqueda
                )
            )
        )

    pacientes = preparar_estado_recepcion(
        pacientes_queryset
    )

    pacientes_de_hoy_queryset = (
        Paciente.objects
        .filter(
            institucion=institucion,
            creado_el__date=hoy
        )
        .prefetch_related(
            Prefetch(
                'consultas',
                queryset=consultas_estado,
                to_attr='consultas_estado_recepcion',
            ),
            Prefetch(
                'estudios',
                queryset=estudios_estado,
                to_attr='estudios_estado_recepcion',
            ),
        )
        .order_by(
            '-creado_el'
        )
    )

    pacientes_de_hoy = preparar_estado_recepcion(
        pacientes_de_hoy_queryset
    )

    pacientes_hoy = len(
        pacientes_de_hoy
    )

    citas_de_hoy = (
        Cita.objects
        .select_related(
            'tipo_estudio'
        )
        .filter(
            institucion=institucion,
            fecha_hora__date=hoy
        )
        .exclude(
            estado__in=[
                'CANCELADA',
                'NO_ASISTIO',
            ]
        )
        .order_by(
            'fecha_hora'
        )
    )

    citas_hoy = (
        citas_de_hoy.count()
    )

    context = {
        'pacientes':
            pacientes,

        'pacientes_de_hoy':
            pacientes_de_hoy,

        'busqueda':
            busqueda,

        'pacientes_hoy':
            pacientes_hoy,

        'total_citas_hoy':
            citas_hoy,

        'citas_de_hoy':
            citas_de_hoy,
    }

    return render(
        request,
        'core/panel_recepcion.html',
        context
    )


# =========================================================
# CITAS
# =========================================================

@login_required
def abrir_caja_recepcion(request):
    membresia = obtener_membresia_usuario(request)
    if membresia is None or membresia.rol not in ['RECEPCION', 'ADMIN']:
        return redirect('inicio')
    if request.method != 'POST':
        return redirect('caja_recepcion')
    if CorteCaja.objects.filter(institucion=membresia.institucion, responsable=request.user, estado='ABIERTA').exists():
        messages.warning(request, 'Ya tienes una caja abierta.')
        return redirect('caja_recepcion')
    try:
        fondo = Decimal(request.POST.get('fondo_inicial', '0')).quantize(Decimal('0.01'))
        if fondo < 0 or fondo > Decimal('9999999999.99'):
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        messages.error(request, 'Escribe un fondo inicial válido.')
        return redirect('caja_recepcion')
    corte = CorteCaja.objects.create(
        institucion=membresia.institucion,
        responsable=request.user,
        fondo_inicial=fondo,
        observaciones_apertura=request.POST.get('observaciones_apertura', '').strip() or None,
    )
    messages.success(request, f'Caja {corte.folio} abierta con ${fondo:.2f}.')
    return redirect('caja_recepcion')


@login_required
def registrar_movimiento_caja(request, corte_id):
    membresia = obtener_membresia_usuario(request)
    if membresia is None or membresia.rol not in ['RECEPCION', 'ADMIN']:
        return redirect('inicio')
    if request.method != 'POST':
        return redirect('caja_recepcion')
    with transaction.atomic():
        corte = get_object_or_404(
            CorteCaja.objects.select_for_update(),
            pk=corte_id,
            institucion=membresia.institucion,
            responsable=request.user,
            estado='ABIERTA',
        )
        tipo = request.POST.get('tipo', '').strip().upper()
        motivo = request.POST.get('motivo', '').strip()
        try:
            monto = Decimal(request.POST.get('monto', '')).quantize(Decimal('0.01'))
            if monto <= 0 or monto > Decimal('9999999999.99'):
                raise InvalidOperation
        except (InvalidOperation, ValueError):
            messages.error(request, 'Escribe un importe mayor a cero.')
            return redirect('caja_recepcion')
        if tipo not in ['ENTRADA', 'RETIRO']:
            messages.error(request, 'Selecciona un tipo de movimiento válido.')
            return redirect('caja_recepcion')
        if not motivo:
            messages.error(request, 'El motivo del movimiento es obligatorio.')
            return redirect('caja_recepcion')
        if tipo == 'RETIRO':
            resumen = calcular_movimientos_corte(corte)
            if monto > resumen['efectivo_esperado']:
                messages.error(request, 'El retiro no puede superar el efectivo esperado en caja.')
                return redirect('caja_recepcion')
        movimiento = MovimientoCaja.objects.create(
            corte=corte,
            tipo=tipo,
            monto=monto,
            motivo=motivo,
            registrado_por=request.user,
        )
    messages.success(request, f'{movimiento.get_tipo_display()} registrada por ${monto:.2f}.')
    return redirect('caja_recepcion')


@login_required
def cerrar_caja_recepcion(request, corte_id):
    membresia = obtener_membresia_usuario(request)
    if membresia is None or membresia.rol not in ['RECEPCION', 'ADMIN']:
        return redirect('inicio')
    if request.method != 'POST':
        return redirect('caja_recepcion')
    with transaction.atomic():
        corte = get_object_or_404(
            CorteCaja.objects.select_for_update(),
            pk=corte_id,
            institucion=membresia.institucion,
        )
        if corte.responsable_id != request.user.id:
            messages.error(request, 'Solo la persona responsable puede cerrar esta caja.')
            return redirect('caja_recepcion')
        if corte.estado == 'CERRADA':
            return redirect('ticket_corte_caja', corte_id=corte.id)
        try:
            contado = Decimal(request.POST.get('efectivo_contado', '')).quantize(Decimal('0.01'))
            entregado = Decimal(request.POST.get('efectivo_entregado', '')).quantize(Decimal('0.01'))
            dejado = Decimal(request.POST.get('efectivo_dejado', '')).quantize(Decimal('0.01'))
            if min(contado, entregado, dejado) < 0 or entregado + dejado != contado:
                raise InvalidOperation
        except (InvalidOperation, ValueError):
            messages.error(request, 'El efectivo contado debe ser igual al dinero entregado más el dinero dejado en caja.')
            return redirect('caja_recepcion')
        primera = request.POST.get('confirmacion_primera') == 'SI'
        segunda = request.POST.get('confirmacion_segunda') == 'SI'
        if not primera or not segunda:
            messages.error(request, 'Debes realizar las dos confirmaciones antes de cerrar la caja.')
            return redirect('caja_recepcion')
        ahora = timezone.now()
        resumen = calcular_movimientos_corte(corte, ahora)
        diferencia = (contado - resumen['efectivo_esperado']).quantize(Decimal('0.01'))
        observaciones = request.POST.get('observaciones_cierre', '').strip()
        if diferencia != 0 and not observaciones:
            messages.error(request, 'Explica el faltante o sobrante antes de cerrar la caja.')
            return redirect('caja_recepcion')
        for campo, valor in resumen.items():
            if campo == 'movimientos':
                continue
            setattr(corte, campo, valor)
        corte.efectivo_contado = contado
        corte.efectivo_entregado = entregado
        corte.efectivo_dejado = dejado
        corte.diferencia = diferencia
        corte.observaciones_cierre = observaciones or None
        corte.confirmacion_primera = primera
        corte.confirmacion_segunda = segunda
        corte.cerrado_el = ahora
        corte.estado = 'CERRADA'
        corte.save()
    messages.success(request, f'Corte {corte.folio} cerrado. Diferencia: ${corte.diferencia:.2f}.')
    return redirect('ticket_corte_caja', corte_id=corte.id)


@login_required
def ticket_corte_caja(request, corte_id):
    membresia = obtener_membresia_usuario(request)
    if membresia is None or membresia.rol not in ['RECEPCION', 'ADMIN']:
        return redirect('inicio')
    corte = get_object_or_404(CorteCaja.objects.select_related('institucion', 'responsable').prefetch_related('movimientos__registrado_por'), pk=corte_id, institucion=membresia.institucion, estado='CERRADA')
    if membresia.rol != 'ADMIN' and corte.responsable_id != request.user.id:
        return redirect('caja_recepcion')
    return render(request, 'core/ticket_corte_caja.html', {'corte': corte})


@login_required
def auditoria_cajas(request):
    membresia = obtener_membresia_usuario(request)
    if membresia is None or membresia.rol != 'ADMIN':
        return redirect('inicio')
    hoy = timezone.localdate()
    try:
        desde = date.fromisoformat(request.GET.get('desde', ''))
    except ValueError:
        desde = hoy.replace(day=1)
    try:
        hasta = date.fromisoformat(request.GET.get('hasta', ''))
    except ValueError:
        hasta = hoy
    if desde > hasta:
        desde, hasta = hasta, desde
    cortes = list(
        CorteCaja.objects.filter(
            institucion=membresia.institucion,
            estado='CERRADA',
            cerrado_el__date__range=(desde, hasta),
        ).select_related('responsable').order_by('-cerrado_el')
    )
    cajas_abiertas = list(
        CorteCaja.objects.filter(
            institucion=membresia.institucion,
            estado='ABIERTA',
        ).select_related('responsable').prefetch_related('movimientos__registrado_por').order_by('abierto_el')
    )
    for caja in cajas_abiertas:
        caja.resumen_actual = calcular_movimientos_corte(caja)
    servicios_frecuentes = list(
        CargoPaciente.objects.filter(
            institucion=membresia.institucion,
            estado='PAGADO',
            cobro__estado='PAGADO',
            cobro__creado_el__date__range=(desde, hasta),
        ).values('descripcion').annotate(total=Count('id')).order_by('-total', 'descripcion')[:10]
    )
    cero = Decimal('0.00')
    context = {
        'membresia': membresia, 'cortes': cortes, 'cajas_abiertas': cajas_abiertas, 'desde': desde, 'hasta': hasta,
        'total_neto': sum((c.total_neto for c in cortes), cero),
        'total_efectivo': sum((c.total_efectivo for c in cortes), cero),
        'total_tarjeta': sum((c.total_tarjeta for c in cortes), cero),
        'total_transferencia': sum((c.total_transferencia for c in cortes), cero),
        'total_reembolsos': sum((c.total_reembolsos for c in cortes), cero),
        'total_diferencias': sum((c.diferencia for c in cortes), cero),
        'servicios_frecuentes': servicios_frecuentes,
    }
    return render(request, 'core/auditoria_cajas.html', context)


@login_required
def caja_recepcion(request):
    membresia = obtener_membresia_usuario(request)

    if membresia is None:
        return redirect('panel_config')

    if membresia.rol not in [
        'RECEPCION',
        'ADMIN',
    ]:
        if membresia.rol == 'MEDICO':
            return redirect('panel_medico')

        if membresia.rol in [
            'RADIOLOGIA',
            'TECNICO',
        ]:
            return redirect('panel_radiologo')

        return redirect('inicio')

    fecha_texto = request.GET.get(
        'fecha',
        ''
    ).strip()

    try:
        fecha_consulta = date.fromisoformat(
            fecha_texto
        )
    except ValueError:
        fecha_consulta = timezone.localdate()

    busqueda = request.GET.get(
        'buscar',
        ''
    ).strip()

    cobros_queryset = (
        Cobro.objects
        .filter(
            institucion=membresia.institucion,
        )
        .filter(
            Q(creado_el__date=fecha_consulta)
            | Q(cancelado_el__date=fecha_consulta)
        )
        .select_related(
            'paciente',
            'creado_por',
            'cancelado_por',
        )
        .prefetch_related(
            'cargos',
            'pagos',
        )
        .distinct()
        .order_by('-creado_el')
    )

    if busqueda:
        cobros_queryset = cobros_queryset.filter(
            Q(folio__icontains=busqueda)
            | Q(paciente__nombre__icontains=busqueda)
            | Q(paciente__apellido__icontains=busqueda)
            | Q(paciente__identificacion__icontains=busqueda)
        )

    cobros = list(cobros_queryset)
    abonos_credito = list(
        AbonoCredito.objects.filter(
            credito__institucion=membresia.institucion,
            creado_el__date=fecha_consulta,
        ).select_related('credito__paciente', 'registrado_por').prefetch_related('pagos').order_by('-creado_el')
    )
    if busqueda:
        texto = busqueda.lower()
        abonos_credito = [a for a in abonos_credito if texto in a.folio.lower() or texto in a.credito.folio.lower() or texto in a.credito.paciente.identificacion.lower() or texto in f'{a.credito.paciente.nombre} {a.credito.paciente.apellido}'.lower()]
    cobros_creados_dia = [
        cobro
        for cobro in cobros
        if timezone.localtime(cobro.creado_el).date() == fecha_consulta
    ]

    total_abonos = sum((abono.monto for abono in abonos_credito), Decimal('0.00'))
    total_bruto = sum(
        (cobro.total for cobro in cobros_creados_dia),
        Decimal('0.00')
    ) + total_abonos

    cobros_cancelados_dia = [
        cobro
        for cobro in cobros
        if (
            cobro.estado == 'CANCELADO'
            and cobro.cancelado_el
            and timezone.localtime(cobro.cancelado_el).date() == fecha_consulta
        )
    ]

    total_reembolsado = sum(
        (
            cobro.monto_reembolsado
            for cobro in cobros_cancelados_dia
        ),
        Decimal('0.00')
    )

    total_general = total_bruto - total_reembolsado

    totales_forma = {
        'EFECTIVO': Decimal('0.00'),
        'TARJETA': Decimal('0.00'),
        'TRANSFERENCIA': Decimal('0.00'),
        'OTRO': Decimal('0.00'),
    }

    for cobro in cobros:
        pagos_cobro = list(cobro.pagos.all())
        cobro.pagos_mostrables = pagos_cobro

        if cobro not in cobros_creados_dia:
            continue

        if pagos_cobro:
            for pago in pagos_cobro:
                if pago.forma_pago in totales_forma:
                    totales_forma[pago.forma_pago] += pago.monto
        elif cobro.forma_pago in totales_forma:
            totales_forma[cobro.forma_pago] += cobro.total

    for abono in abonos_credito:
        abono.pagos_mostrables = list(abono.pagos.all())
        for pago in abono.pagos_mostrables:
            if pago.forma_pago in totales_forma:
                totales_forma[pago.forma_pago] += pago.monto

    caja_abierta = (
        CorteCaja.objects.filter(
            institucion=membresia.institucion,
            responsable=request.user,
            estado='ABIERTA',
        ).first()
    )
    resumen_turno = calcular_movimientos_corte(caja_abierta) if caja_abierta else None
    cortes_propios = CorteCaja.objects.filter(
        institucion=membresia.institucion,
        responsable=request.user,
        estado='CERRADA',
    ).order_by('-cerrado_el')[:10]

    context = {
        'membresia': membresia,
        'fecha_consulta': fecha_consulta,
        'fecha_texto': fecha_consulta.isoformat(),
        'busqueda': busqueda,
        'cobros': cobros,
        'abonos_credito': abonos_credito,
        'total_abonos': total_abonos,
        'total_general': total_general,
        'total_bruto': total_bruto,
        'total_reembolsado': total_reembolsado,
        'total_efectivo': totales_forma['EFECTIVO'],
        'total_tarjeta': totales_forma['TARJETA'],
        'total_transferencia': totales_forma['TRANSFERENCIA'],
        'total_otro': totales_forma['OTRO'],
        'numero_cobros': len(cobros_creados_dia) + len(abonos_credito),
        'numero_reembolsos': len(cobros_cancelados_dia),
        'caja_abierta': caja_abierta,
        'resumen_turno': resumen_turno,
        'cortes_propios': cortes_propios,
    }

    return render(
        request,
        'core/caja_recepcion.html',
        context
    )

@login_required
def nueva_cita(request):
    institucion = obtener_institucion_usuario(request)

    if institucion is None:
        return redirect('panel_config')

    if request.method == 'POST':

        cita_form = CitaForm(
            request.POST
        )

        if cita_form.is_valid():

            cita = cita_form.save(
                commit=False
            )

            cita.creada_por = (
                request.user
            )

            cita.institucion = (
                institucion
            )

            cita.save()

            return redirect(
                'panel_recepcion'
            )

    else:

        cita_form = CitaForm(
            initial={
                'estado':
                    'PROGRAMADA',

                'duracion_minutos':
                    30,
            }
        )

    context = {
        'cita_form':
            cita_form,
    }

    return render(
        request,
        'core/nueva_cita.html',
        context
    )


# =========================================================
# EXPEDIENTE
# =========================================================

@login_required
def servicios_paciente_recepcion(
    request,
    paciente_id
):
    membresia = obtener_membresia_usuario(request)

    if membresia is None:
        return redirect('panel_config')

    if membresia.rol not in [
        'RECEPCION',
        'ADMIN',
    ]:
        if membresia.rol == 'MEDICO':
            return redirect('panel_medico')

        if membresia.rol in [
            'RADIOLOGIA',
            'TECNICO',
        ]:
            return redirect('panel_radiologo')

        return redirect('inicio')

    paciente = get_object_or_404(
        Paciente,
        pk=paciente_id,
        institucion=membresia.institucion,
    )

    if request.method == 'POST':
        accion = request.POST.get(
            'accion',
            ''
        ).strip()

        if accion == 'AGREGAR':
            servicio = get_object_or_404(
                Servicio,
                pk=request.POST.get('servicio_id'),
                institucion=membresia.institucion,
                activo=True,
            )

            try:
                cantidad = Decimal(
                    request.POST.get(
                        'cantidad',
                        '1'
                    )
                )

                if cantidad <= 0:
                    raise InvalidOperation

                if cantidad > Decimal('99999999.99'):
                    raise InvalidOperation

                cantidad = cantidad.quantize(
                    Decimal('0.01')
                )
            except (InvalidOperation, ValueError):
                messages.error(
                    request,
                    'Escribe una cantidad válida mayor que cero.'
                )
                return redirect(
                    'servicios_paciente_recepcion',
                    paciente_id=paciente.id,
                )

            try:
                precio_unitario = Decimal(
                    request.POST.get(
                        'precio_unitario',
                        str(servicio.precio_base)
                    )
                )

                if precio_unitario < 0:
                    raise InvalidOperation

                if precio_unitario > Decimal(
                    '9999999999.99'
                ):
                    raise InvalidOperation

                precio_unitario = precio_unitario.quantize(
                    Decimal('0.01')
                )
            except (InvalidOperation, ValueError):
                messages.error(
                    request,
                    'Escribe un precio válido mayor o igual a cero.'
                )
                return redirect(
                    'servicios_paciente_recepcion',
                    paciente_id=paciente.id,
                )

            CargoPaciente.objects.create(
                institucion=membresia.institucion,
                paciente=paciente,
                servicio=servicio,
                descripcion=servicio.nombre,
                cantidad=cantidad,
                precio_unitario=precio_unitario,
                estado='PENDIENTE',
                origen='RECEPCION',
                agregado_por=request.user,
                notas=(
                    request.POST.get(
                        'notas',
                        ''
                    ).strip()
                    or None
                ),
            )

            messages.success(
                request,
                'Servicio agregado a la cuenta del paciente.'
            )

        elif accion == 'CREAR_CREDITO':
            cargos_ids = request.POST.getlist('cargos_ids')
            modo_cobro = request.POST.get('modo_cobro', 'TOTAL').strip()

            try:
                numero_cuotas = int(request.POST.get('numero_cuotas', '1'))
                fecha_vencimiento = date.fromisoformat(request.POST.get('fecha_vencimiento', ''))
                if numero_cuotas < 1 or numero_cuotas > 120 or fecha_vencimiento < timezone.localdate():
                    raise ValueError
            except (TypeError, ValueError):
                messages.error(request, 'Indica cuotas y una fecha de vencimiento válidas.')
                return redirect('servicios_paciente_recepcion', paciente_id=paciente.id)

            with transaction.atomic():
                seleccion = CargoPaciente.objects.select_for_update().filter(
                    institucion=membresia.institucion, paciente=paciente,
                    estado='PENDIENTE', cobro__isnull=True, credito__isnull=True,
                ).order_by('creado_el', 'pk')
                if modo_cobro != 'TOTAL':
                    seleccion = seleccion.filter(pk__in=cargos_ids)
                cargos_credito = list(seleccion)
                if not cargos_credito:
                    messages.error(request, 'Selecciona al menos un cargo pendiente para el crédito.')
                    return redirect('servicios_paciente_recepcion', paciente_id=paciente.id)
                total_credito = sum((c.subtotal for c in cargos_credito), Decimal('0.00')).quantize(Decimal('0.01'))
                credito = CreditoPaciente.objects.create(
                    institucion=membresia.institucion, paciente=paciente,
                    total=total_credito, saldo=total_credito,
                    numero_cuotas=numero_cuotas, fecha_vencimiento=fecha_vencimiento,
                    notas=request.POST.get('notas_credito', '').strip() or None,
                    autorizado_por=request.user, creado_por=request.user,
                )
                CargoPaciente.objects.filter(pk__in=[c.pk for c in cargos_credito]).update(
                    estado='CREDITO', credito=credito, actualizado_el=timezone.now()
                )
            messages.success(request, f'Crédito {credito.folio} creado por ${credito.total:.2f}.')

        elif accion == 'COBRAR':
            if not CorteCaja.objects.filter(
                institucion=membresia.institucion,
                responsable=request.user,
                estado='ABIERTA',
            ).exists():
                messages.error(request, 'Debes abrir tu caja antes de registrar un cobro.')
                return redirect('caja_recepcion')

            modo_cobro = request.POST.get(
                'modo_cobro',
                'TOTAL'
            ).strip()

            cargos_ids = request.POST.getlist(
                'cargos_ids'
            )

            tipo_pago = request.POST.get(
                'tipo_pago',
                'UNICO'
            ).strip()

            forma_pago_solicitada = request.POST.get(
                'forma_pago',
                'EFECTIVO'
            ).strip()

            formas_validas = {
                valor
                for valor, etiqueta
                in PagoCobro.FORMA_PAGO_CHOICES
            }

            if forma_pago_solicitada not in formas_validas:
                forma_pago_solicitada = 'OTRO'

            forma_pago = (
                'MIXTO'
                if tipo_pago == 'MIXTO'
                else forma_pago_solicitada
            )

            telefono_envio = (
                request.POST.get(
                    'telefono_envio',
                    ''
                ).strip()
                or paciente.telefono
                or None
            )

            with transaction.atomic():
                cargos_queryset = (
                    CargoPaciente.objects
                    .select_for_update()
                    .filter(
                        institucion=membresia.institucion,
                        paciente=paciente,
                        estado='PENDIENTE',
                        cobro__isnull=True,
                    )
                    .order_by('creado_el', 'pk')
                )

                if modo_cobro != 'TOTAL':
                    cargos_queryset = cargos_queryset.filter(
                        pk__in=cargos_ids
                    )

                cargos_seleccionados = list(
                    cargos_queryset
                )

                if not cargos_seleccionados:
                    messages.error(
                        request,
                        (
                            'La cuenta no tiene cargos pendientes.'
                            if modo_cobro == 'TOTAL'
                            else 'Selecciona al menos un cargo pendiente.'
                        )
                    )
                    return redirect(
                        'servicios_paciente_recepcion',
                        paciente_id=paciente.id,
                    )

                total_cobro = sum(
                    (
                        cargo.subtotal
                        for cargo in cargos_seleccionados
                    ),
                    Decimal('0.00')
                ).quantize(Decimal('0.01'))

                monto_recibido = None
                cambio = Decimal('0.00')
                pagos_a_registrar = []

                if forma_pago == 'MIXTO':
                    nombres_formas = {
                        'EFECTIVO': 'monto_efectivo',
                        'TARJETA': 'monto_tarjeta',
                        'TRANSFERENCIA': 'monto_transferencia',
                        'OTRO': 'monto_otro',
                    }

                    try:
                        for forma, campo in nombres_formas.items():
                            texto_monto = request.POST.get(
                                campo,
                                '0'
                            ).strip() or '0'

                            monto = Decimal(texto_monto).quantize(
                                Decimal('0.01')
                            )

                            if monto < 0 or monto > Decimal('9999999999.99'):
                                raise InvalidOperation

                            if monto > 0:
                                pagos_a_registrar.append({
                                    'forma_pago': forma,
                                    'monto': monto,
                                    'referencia': (
                                        request.POST.get(
                                            f'referencia_{forma.lower()}',
                                            ''
                                        ).strip()
                                        or None
                                    ),
                                })

                        total_distribuido = sum(
                            (
                                pago['monto']
                                for pago in pagos_a_registrar
                            ),
                            Decimal('0.00')
                        ).quantize(Decimal('0.01'))

                        if (
                            len(pagos_a_registrar) < 2
                            or total_distribuido != total_cobro
                        ):
                            raise InvalidOperation
                    except (InvalidOperation, ValueError):
                        messages.error(
                            request,
                            (
                                'En un pago mixto utiliza al menos dos formas '
                                'y asegúrate de que los importes sumen exactamente '
                                f'${total_cobro:.2f}.'
                            )
                        )
                        return redirect(
                            'servicios_paciente_recepcion',
                            paciente_id=paciente.id,
                        )

                    efectivo_aplicado = next(
                        (
                            pago['monto']
                            for pago in pagos_a_registrar
                            if pago['forma_pago'] == 'EFECTIVO'
                        ),
                        Decimal('0.00')
                    )

                    if efectivo_aplicado > 0:
                        try:
                            monto_recibido = Decimal(
                                request.POST.get(
                                    'monto_recibido',
                                    str(efectivo_aplicado)
                                )
                            ).quantize(Decimal('0.01'))

                            if monto_recibido < efectivo_aplicado:
                                raise InvalidOperation

                            cambio = (
                                monto_recibido
                                - efectivo_aplicado
                            ).quantize(Decimal('0.01'))
                        except (InvalidOperation, ValueError):
                            messages.error(
                                request,
                                'El efectivo recibido debe cubrir la parte pagada en efectivo.'
                            )
                            return redirect(
                                'servicios_paciente_recepcion',
                                paciente_id=paciente.id,
                            )

                elif forma_pago == 'EFECTIVO':
                    try:
                        monto_recibido = Decimal(
                            request.POST.get(
                                'monto_recibido',
                                str(total_cobro)
                            )
                        ).quantize(
                            Decimal('0.01')
                        )

                        if monto_recibido < total_cobro:
                            raise InvalidOperation

                        if monto_recibido > Decimal('9999999999.99'):
                            raise InvalidOperation

                        cambio = (
                            monto_recibido
                            - total_cobro
                        ).quantize(
                            Decimal('0.01')
                        )
                    except (InvalidOperation, ValueError):
                        messages.error(
                            request,
                            'El efectivo recibido debe cubrir el total de la cuenta.'
                        )
                        return redirect(
                            'servicios_paciente_recepcion',
                            paciente_id=paciente.id,
                        )

                    pagos_a_registrar.append({
                        'forma_pago': forma_pago,
                        'monto': total_cobro,
                        'referencia': None,
                    })
                else:
                    pagos_a_registrar.append({
                        'forma_pago': forma_pago,
                        'monto': total_cobro,
                        'referencia': (
                            request.POST.get(
                                f'referencia_{forma_pago.lower()}',
                                ''
                            ).strip()
                            or None
                        ),
                    })

                cobro = Cobro.objects.create(
                    institucion=membresia.institucion,
                    paciente=paciente,
                    forma_pago=forma_pago,
                    total=total_cobro,
                    monto_recibido=monto_recibido,
                    cambio=cambio,
                    telefono_envio=telefono_envio,
                    creado_por=request.user,
                )

                PagoCobro.objects.bulk_create([
                    PagoCobro(
                        cobro=cobro,
                        forma_pago=pago['forma_pago'],
                        monto=pago['monto'],
                        referencia=pago['referencia'],
                    )
                    for pago in pagos_a_registrar
                ])

                CargoPaciente.objects.filter(
                    pk__in=[
                        cargo.pk
                        for cargo in cargos_seleccionados
                    ]
                ).update(
                    estado='PAGADO',
                    cobro=cobro,
                    actualizado_el=timezone.now(),
                )

            messages.success(
                request,
                (
                    f'Cuenta cobrada en un solo comprobante con '
                    f'{len(cargos_seleccionados)} concepto(s).'
                )
            )

            salida = request.POST.get(
                'salida',
                'DIGITAL'
            ).strip()

            destino = reverse(
                'cobro_exitoso',
                kwargs={
                    'cobro_id': cobro.id,
                }
            )

            return redirect(
                f'{destino}?salida={salida}'
            )

        elif accion in [
            'PAGAR',
            'CANCELAR',
        ]:
            cargo = get_object_or_404(
                CargoPaciente,
                pk=request.POST.get('cargo_id'),
                institucion=membresia.institucion,
                paciente=paciente,
            )

            if cargo.estado != 'PENDIENTE':
                messages.warning(
                    request,
                    'Ese cargo ya no está pendiente.'
                )
            else:
                cargo.estado = (
                    'PAGADO'
                    if accion == 'PAGAR'
                    else 'CANCELADO'
                )
                cargo.save(
                    update_fields=[
                        'estado',
                        'actualizado_el',
                    ]
                )

                messages.success(
                    request,
                    (
                        'Cargo marcado como pagado.'
                        if accion == 'PAGAR'
                        else 'Cargo cancelado correctamente.'
                    )
                )

        return redirect(
            'servicios_paciente_recepcion',
            paciente_id=paciente.id,
        )

    cargos = list(
        CargoPaciente.objects
        .filter(
            institucion=membresia.institucion,
            paciente=paciente,
        )
        .select_related(
            'servicio',
            'agregado_por',
            'cobro',
        )
        .order_by('-creado_el')
    )

    cargos_pendientes = [
        cargo
        for cargo in cargos
        if cargo.estado == 'PENDIENTE'
    ]

    cargos_pagados = [
        cargo
        for cargo in cargos
        if cargo.estado == 'PAGADO'
    ]

    cargos_pagados_con_cobro = [
        cargo
        for cargo in cargos_pagados
        if cargo.cobro_id
    ]

    creditos = list(
        CreditoPaciente.objects.filter(
            institucion=membresia.institucion,
            paciente=paciente,
        ).prefetch_related('abonos', 'cargos').order_by('-creado_el')
    )
    for credito in creditos:
        if credito.estado == 'VIGENTE' and credito.saldo > 0 and credito.fecha_vencimiento < timezone.localdate():
            credito.estado = 'VENCIDO'
            credito.save(update_fields=['estado', 'actualizado_el'])

    total_pendiente = sum(
        (
            cargo.subtotal
            for cargo in cargos_pendientes
        ),
        Decimal('0.00')
    )

    total_pagado = sum(
        (
            cargo.subtotal
            for cargo in cargos_pagados
        ),
        Decimal('0.00')
    )

    servicios_catalogo = (
        Servicio.objects
        .filter(
            institucion=membresia.institucion,
            activo=True,
        )
        .select_related('tipo_estudio')
        .order_by(
            'tipo',
            'nombre',
        )
    )

    estudios = list(
        Estudio.objects
        .select_related(
            'tipo_estudio'
        )
        .filter(
            paciente=paciente
        )
        .order_by(
            '-fecha_creacion'
        )
    )

    total_servicios = len(
        estudios
    )

    total_realizados = sum(
        1
        for estudio in estudios
        if estudio.estado == 'COMPLETADO'
    )

    total_en_proceso = sum(
        1
        for estudio in estudios
        if estudio.estado == 'EN_PROCESO'
    )

    total_pendientes = sum(
        1
        for estudio in estudios
        if estudio.estado == 'PENDIENTE'
    )

    resumen_por_tipo = {}

    for estudio in estudios:
        nombre = (
            estudio.tipo_estudio.nombre
            if estudio.tipo_estudio
            else 'Servicio sin especificar'
        )

        if nombre not in resumen_por_tipo:
            resumen_por_tipo[nombre] = {
                'nombre': nombre,
                'cantidad': 0,
                'realizados': 0,
            }

        resumen_por_tipo[nombre]['cantidad'] += 1

        if estudio.estado == 'COMPLETADO':
            resumen_por_tipo[nombre]['realizados'] += 1

    resumen_servicios = sorted(
        resumen_por_tipo.values(),
        key=lambda item: (
            -item['cantidad'],
            item['nombre'].lower(),
        )
    )

    context = {
        'paciente': paciente,
        'cargos': cargos,
        'cargos_pendientes': cargos_pendientes,
        'cargos_pagados': cargos_pagados,
        'cargos_pagados_con_cobro': cargos_pagados_con_cobro,
        'total_pendiente': total_pendiente,
        'total_pagado': total_pagado,
        'servicios_catalogo': servicios_catalogo,
        'estudios': estudios,
        'total_servicios': total_servicios,
        'total_realizados': total_realizados,
        'total_en_proceso': total_en_proceso,
        'total_pendientes': total_pendientes,
        'resumen_servicios': resumen_servicios,
        'membresia': membresia,
        'creditos': creditos,
        'hoy': timezone.localdate(),
    }

    return render(
        request,
        'core/servicios_paciente_recepcion.html',
        context
    )


@login_required
def registrar_abono_credito(request, credito_id):
    membresia = obtener_membresia_usuario(request)
    if membresia is None or membresia.rol not in ['RECEPCION', 'ADMIN']:
        return redirect('inicio')
    credito = get_object_or_404(
        CreditoPaciente.objects.select_related('paciente', 'institucion'),
        pk=credito_id, institucion=membresia.institucion,
    )
    if request.method != 'POST' or credito.estado not in ['VIGENTE', 'VENCIDO']:
        messages.error(request, 'El crédito no admite abonos.')
        return redirect('servicios_paciente_recepcion', paciente_id=credito.paciente_id)
    if not CorteCaja.objects.filter(institucion=membresia.institucion, responsable=request.user, estado='ABIERTA').exists():
        messages.error(request, 'Debes abrir tu caja antes de registrar un abono.')
        return redirect('caja_recepcion')

    pagos = []
    try:
        for forma, campo in [('EFECTIVO', 'abono_efectivo'), ('TARJETA', 'abono_tarjeta'), ('TRANSFERENCIA', 'abono_transferencia'), ('OTRO', 'abono_otro')]:
            monto = Decimal(request.POST.get(campo, '0').strip() or '0').quantize(Decimal('0.01'))
            if monto < 0:
                raise InvalidOperation
            if monto > 0:
                pagos.append((forma, monto, request.POST.get(f'abono_referencia_{forma.lower()}', '').strip() or None))
        total_abono = sum((p[1] for p in pagos), Decimal('0.00')).quantize(Decimal('0.01'))
        if total_abono <= 0 or total_abono > credito.saldo:
            raise InvalidOperation
        efectivo = next((p[1] for p in pagos if p[0] == 'EFECTIVO'), Decimal('0.00'))
        recibido = None
        cambio = Decimal('0.00')
        if efectivo:
            recibido = Decimal(request.POST.get('abono_recibido', str(efectivo))).quantize(Decimal('0.01'))
            if recibido < efectivo:
                raise InvalidOperation
            cambio = recibido - efectivo
    except (InvalidOperation, ValueError):
        messages.error(request, 'Revisa los importes: el abono debe ser mayor a cero, no superar el saldo y el efectivo recibido debe cubrir el efectivo aplicado.')
        return redirect('servicios_paciente_recepcion', paciente_id=credito.paciente_id)

    with transaction.atomic():
        credito = CreditoPaciente.objects.select_for_update().get(pk=credito.pk)
        if total_abono > credito.saldo:
            messages.error(request, 'El saldo cambió; vuelve a intentar.')
            return redirect('servicios_paciente_recepcion', paciente_id=credito.paciente_id)
        forma_resumen = pagos[0][0] if len(pagos) == 1 else 'OTRO'
        abono = AbonoCredito.objects.create(
            credito=credito, monto=total_abono, forma_pago=forma_resumen,
            referencia=pagos[0][2] if len(pagos) == 1 else 'Pago mixto',
            monto_recibido=recibido, cambio=cambio, registrado_por=request.user,
        )
        PagoAbonoCredito.objects.bulk_create([
            PagoAbonoCredito(abono=abono, forma_pago=f, monto=m, referencia=r)
            for f, m, r in pagos
        ])
        credito.saldo = (credito.saldo - total_abono).quantize(Decimal('0.01'))
        credito.estado = 'LIQUIDADO' if credito.saldo == 0 else ('VENCIDO' if credito.fecha_vencimiento < timezone.localdate() else 'VIGENTE')
        credito.save(update_fields=['saldo', 'estado', 'actualizado_el'])
        if credito.estado == 'LIQUIDADO':
            credito.cargos.update(estado='PAGADO', actualizado_el=timezone.now())

    messages.success(request, f'Abono {abono.folio} registrado por ${abono.monto:.2f}.')
    return redirect('ticket_abono_credito', abono_id=abono.id)


@login_required
def ticket_abono_credito(request, abono_id):
    membresia = obtener_membresia_usuario(request)
    if membresia is None or membresia.rol not in ['RECEPCION', 'ADMIN']:
        return redirect('inicio')
    abono = get_object_or_404(
        AbonoCredito.objects.select_related('credito__paciente', 'credito__institucion', 'registrado_por').prefetch_related('pagos'),
        pk=abono_id, credito__institucion=membresia.institucion,
    )
    return render(request, 'core/ticket_abono_credito.html', {'abono': abono})


def construir_pdf_cobro(cobro):
    buffer = BytesIO()

    documento = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        topMargin=1.4 * cm,
        bottomMargin=1.4 * cm,
        title=f'Comprobante {cobro.folio}',
    )

    estilos = getSampleStyleSheet()

    titulo = ParagraphStyle(
        'TituloCobro',
        parent=estilos['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=15,
        leading=18,
        textColor=colors.HexColor('#17365d'),
    )

    normal = ParagraphStyle(
        'NormalCobro',
        parent=estilos['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=10,
    )

    pequeno = ParagraphStyle(
        'PequenoCobro',
        parent=normal,
        fontSize=7,
        leading=8.5,
        textColor=colors.HexColor('#475569'),
    )

    institucion = cobro.institucion
    paciente = cobro.paciente
    historia = []

    logo = None

    if institucion.logo:
        try:
            institucion.logo.open('rb')
            datos_logo = institucion.logo.read()
            institucion.logo.close()

            if datos_logo:
                logo = Image(
                    BytesIO(datos_logo),
                    width=2.2 * cm,
                    height=1.5 * cm,
                    kind='proportional',
                )
        except Exception:
            logo = None

    nombre_institucion = (
        institucion.nombre_comercial
        or institucion.nombre
    )

    datos_institucion = [
        Paragraph(
            escape(nombre_institucion),
            titulo
        )
    ]

    if institucion.rfc:
        datos_institucion.append(
            Paragraph(
                f'RFC: {escape(institucion.rfc)}',
                pequeno
            )
        )

    if institucion.direccion:
        datos_institucion.append(
            Paragraph(
                escape(institucion.direccion),
                pequeno
            )
        )

    if institucion.telefono:
        datos_institucion.append(
            Paragraph(
                f'Tel. {escape(institucion.telefono)}',
                pequeno
            )
        )

    encabezado = Table(
        [[logo or '', datos_institucion]],
        colWidths=[2.6 * cm, 15.4 * cm],
    )

    encabezado.setStyle(
        TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LINEBELOW', (0, 0), (-1, -1), 1, colors.HexColor('#17365d')),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ])
    )

    historia.append(encabezado)
    historia.append(Spacer(1, 10))
    historia.append(
        Paragraph(
            'COMPROBANTE DE CUENTA',
            titulo
        )
    )
    historia.append(Spacer(1, 6))

    fecha_local = timezone.localtime(
        cobro.creado_el
    )

    datos_cobro = [
        ['Folio', cobro.folio],
        ['Fecha', fecha_local.strftime('%d/%m/%Y %H:%M')],
        [
            'Paciente',
            f'{paciente.nombre} {paciente.apellido}'
        ],
        ['Registro', paciente.identificacion],
        ['Conceptos incluidos', str(cobro.cargos.count())],
        ['Forma de pago', cobro.get_forma_pago_display()],
    ]

    tabla_datos = Table(
        datos_cobro,
        colWidths=[3.2 * cm, 14.8 * cm],
    )

    tabla_datos.setStyle(
        TableStyle([
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ])
    )

    historia.append(tabla_datos)
    historia.append(Spacer(1, 10))

    filas = [[
        'Concepto',
        'Cantidad',
        'Precio',
        'Subtotal',
    ]]

    for cargo in cobro.cargos.all():
        filas.append([
            Paragraph(
                escape(cargo.descripcion),
                normal
            ),
            f'{cargo.cantidad:.2f}',
            f'${cargo.precio_unitario:.2f}',
            f'${cargo.subtotal:.2f}',
        ])

    tabla_cargos = Table(
        filas,
        colWidths=[10.2 * cm, 2.2 * cm, 2.8 * cm, 2.8 * cm],
        repeatRows=1,
    )

    tabla_cargos.setStyle(
        TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#17365d')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 7.5),
            ('ALIGN', (1, 1), (-1, -1), 'RIGHT'),
            ('GRID', (0, 0), (-1, -1), .35, colors.HexColor('#cbd5e1')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ])
    )

    historia.append(tabla_cargos)
    historia.append(Spacer(1, 10))

    totales = [
        ['TOTAL PAGADO', f'${cobro.total:.2f}'],
    ]

    pagos_cobro = list(cobro.pagos.all())

    for pago in pagos_cobro:
        totales.append([
            pago.get_forma_pago_display().upper(),
            f'${pago.monto:.2f}',
        ])

    if cobro.monto_recibido is not None:
        totales.extend([
            [
                'EFECTIVO RECIBIDO',
                f'${cobro.monto_recibido:.2f}'
            ],
            ['CAMBIO', f'${cobro.cambio:.2f}'],
        ])

    tabla_totales = Table(
        totales,
        colWidths=[14.5 * cm, 3.5 * cm],
    )

    tabla_totales.setStyle(
        TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
            ('LINEABOVE', (0, 0), (-1, 0), 1, colors.HexColor('#17365d')),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
        ])
    )

    historia.append(tabla_totales)
    historia.append(Spacer(1, 18))
    historia.append(
        Paragraph(
            'Este documento es un comprobante interno de pago y no sustituye un CFDI.',
            pequeno
        )
    )

    if institucion.pie_documentos:
        historia.append(Spacer(1, 6))
        historia.append(
            Paragraph(
                escape(institucion.pie_documentos),
                pequeno
            )
        )

    documento.build(historia)
    contenido = buffer.getvalue()
    buffer.close()
    return contenido


@login_required
def cobro_exitoso(
    request,
    cobro_id
):
    membresia = obtener_membresia_usuario(request)

    if membresia is None or membresia.rol not in [
        'RECEPCION',
        'ADMIN',
    ]:
        return redirect('inicio')

    cobro = get_object_or_404(
        Cobro.objects.select_related(
            'institucion',
            'paciente',
            'creado_por',
            'cancelado_por',
        ).prefetch_related(
            'cargos',
            'pagos',
        ),
        pk=cobro_id,
        institucion=membresia.institucion,
    )

    enlace_pdf = request.build_absolute_uri(
        reverse(
            'comprobante_cobro_pdf',
            kwargs={
                'token': cobro.token_publico,
            }
        )
    )

    telefono = ''.join(
        caracter
        for caracter in (cobro.telefono_envio or '')
        if caracter.isdigit()
    )

    if len(telefono) == 10:
        telefono = f'52{telefono}'

    mensaje = (
        f'Hola. Compartimos su comprobante de pago '
        f'{cobro.folio} de '
        f'{cobro.institucion.nombre_comercial or cobro.institucion.nombre}: '
        f'{enlace_pdf}'
    )

    enlace_whatsapp = ''

    if telefono:
        enlace_whatsapp = (
            f'https://wa.me/{telefono}?text={quote(mensaje)}'
        )

    context = {
        'cobro': cobro,
        'enlace_pdf': enlace_pdf,
        'enlace_whatsapp': enlace_whatsapp,
        'salida': request.GET.get('salida', 'DIGITAL'),
    }

    return render(
        request,
        'core/cobro_exitoso.html',
        context
    )


@login_required
def cancelar_cobro_recepcion(
    request,
    cobro_id
):
    membresia = obtener_membresia_usuario(request)

    if membresia is None or membresia.rol not in [
        'RECEPCION',
        'ADMIN',
    ]:
        return redirect('inicio')

    if request.method != 'POST':
        return redirect(
            'cobro_exitoso',
            cobro_id=cobro_id,
        )

    if not CorteCaja.objects.filter(
        institucion=membresia.institucion,
        responsable=request.user,
        estado='ABIERTA',
    ).exists():
        messages.error(request, 'Debes abrir tu caja antes de registrar un reembolso.')
        return redirect('caja_recepcion')

    motivo = request.POST.get(
        'motivo_cancelacion',
        ''
    ).strip()

    destino_cargos = request.POST.get(
        'destino_cargos',
        'CANCELAR'
    ).strip()

    forma_reembolso = request.POST.get(
        'forma_reembolso',
        'EFECTIVO'
    ).strip()

    confirmacion = request.POST.get(
        'confirmar_cancelacion',
        ''
    ).strip()

    destinos_validos = {
        valor
        for valor, etiqueta
        in Cobro.DESTINO_CARGOS_CHOICES
    }

    formas_validas = {
        valor
        for valor, etiqueta
        in Cobro.FORMA_PAGO_CHOICES
    }

    if len(motivo) < 5:
        messages.error(
            request,
            'Escribe un motivo de cancelación de al menos cinco caracteres.'
        )
        return redirect(
            'cobro_exitoso',
            cobro_id=cobro_id,
        )

    if destino_cargos not in destinos_validos:
        destino_cargos = 'CANCELAR'

    if forma_reembolso not in formas_validas:
        forma_reembolso = 'OTRO'

    if confirmacion != 'SI':
        messages.error(
            request,
            'Debes confirmar que el dinero fue devuelto al paciente.'
        )
        return redirect(
            'cobro_exitoso',
            cobro_id=cobro_id,
        )

    with transaction.atomic():
        cobro = get_object_or_404(
            Cobro.objects.select_for_update(),
            pk=cobro_id,
            institucion=membresia.institucion,
        )

        if cobro.estado != 'PAGADO':
            messages.warning(
                request,
                'Este pago ya estaba cancelado.'
            )
            return redirect(
                'cobro_exitoso',
                cobro_id=cobro.id,
            )

        cargos_originales = list(
            CargoPaciente.objects
            .select_for_update()
            .filter(cobro=cobro)
            .order_by('creado_el', 'pk')
        )

        if destino_cargos == 'REABRIR':
            cargos_reabiertos = []

            for cargo in cargos_originales:
                nota_reapertura = (
                    f'Reabierto por cancelación del cobro {cobro.folio}.'
                )

                if cargo.notas:
                    nota_reapertura = (
                        f'{cargo.notas}\n{nota_reapertura}'
                    )

                cargos_reabiertos.append(
                    CargoPaciente(
                        institucion=cargo.institucion,
                        paciente=cargo.paciente,
                        servicio=cargo.servicio,
                        consulta=cargo.consulta,
                        estudio=cargo.estudio,
                        descripcion=cargo.descripcion,
                        cantidad=cargo.cantidad,
                        precio_unitario=cargo.precio_unitario,
                        estado='PENDIENTE',
                        origen='RECEPCION',
                        agregado_por=request.user,
                        notas=nota_reapertura,
                    )
                )

            CargoPaciente.objects.bulk_create(
                cargos_reabiertos
            )

        CargoPaciente.objects.filter(
            pk__in=[cargo.pk for cargo in cargos_originales]
        ).update(
            estado='CANCELADO',
            actualizado_el=timezone.now(),
        )

        cobro.estado = 'CANCELADO'
        cobro.cancelado_por = request.user
        cobro.cancelado_el = timezone.now()
        cobro.motivo_cancelacion = motivo[:300]
        cobro.forma_reembolso = forma_reembolso
        cobro.monto_reembolsado = cobro.total
        cobro.destino_cargos_cancelacion = destino_cargos
        cobro.save(
            update_fields=[
                'estado',
                'cancelado_por',
                'cancelado_el',
                'motivo_cancelacion',
                'forma_reembolso',
                'monto_reembolsado',
                'destino_cargos_cancelacion',
            ]
        )

    messages.success(
        request,
        (
            f'Pago {cobro.folio} cancelado. '
            f'Reembolso registrado por ${cobro.total:.2f}.'
        )
    )

    return redirect(
        'cobro_exitoso',
        cobro_id=cobro.id,
    )


@login_required
def ticket_cobro(
    request,
    cobro_id
):
    membresia = obtener_membresia_usuario(request)

    if membresia is None or membresia.rol not in [
        'RECEPCION',
        'ADMIN',
    ]:
        return redirect('inicio')

    cobro = get_object_or_404(
        Cobro.objects.select_related(
            'institucion',
            'paciente',
            'creado_por',
            'cancelado_por',
        ).prefetch_related(
            'cargos',
            'pagos',
        ),
        pk=cobro_id,
        institucion=membresia.institucion,
    )

    return render(
        request,
        'core/ticket_cobro.html',
        {
            'cobro': cobro,
        }
    )


@login_required
def ticket_cargos_agrupados(
    request,
    paciente_id
):
    membresia = obtener_membresia_usuario(request)

    if membresia is None or membresia.rol not in [
        'RECEPCION',
        'ADMIN',
    ]:
        return redirect('inicio')

    paciente = get_object_or_404(
        Paciente,
        pk=paciente_id,
        institucion=membresia.institucion,
    )

    if request.method != 'POST':
        return redirect(
            'servicios_paciente_recepcion',
            paciente_id=paciente.id,
        )

    accion_agrupado = request.POST.get(
        'accion_agrupado',
        'SELECCIONADOS'
    ).strip()

    cargos_queryset = (
        CargoPaciente.objects
        .filter(
            institucion=membresia.institucion,
            paciente=paciente,
            estado='PAGADO',
            cobro__isnull=False,
            cobro__estado='PAGADO',
        )
        .select_related(
            'cobro',
            'cobro__creado_por',
        )
        .order_by(
            'cobro__creado_el',
            'creado_el',
            'pk',
        )
    )

    if accion_agrupado != 'TODOS':
        cargos_ids = request.POST.getlist(
            'cargos_pagados_ids'
        )
        cargos_queryset = cargos_queryset.filter(
            pk__in=cargos_ids
        )

    cargos = list(cargos_queryset)

    if not cargos:
        messages.error(
            request,
            'Selecciona al menos un servicio pagado para imprimirlo.'
        )
        return redirect(
            'servicios_paciente_recepcion',
            paciente_id=paciente.id,
        )

    total = sum(
        (cargo.subtotal for cargo in cargos),
        Decimal('0.00')
    ).quantize(Decimal('0.01'))

    folios = []

    for cargo in cargos:
        if cargo.cobro.folio not in folios:
            folios.append(cargo.cobro.folio)

    return render(
        request,
        'core/ticket_cargos_agrupados.html',
        {
            'institucion': membresia.institucion,
            'paciente': paciente,
            'cargos': cargos,
            'folios': folios,
            'total': total,
            'fecha_emision': timezone.now(),
            'emitido_por': request.user,
        }
    )


def comprobante_cobro_pdf(
    request,
    token
):
    cobro = get_object_or_404(
        Cobro.objects.select_related(
            'institucion',
            'paciente',
            'creado_por',
        ).prefetch_related(
            'cargos',
            'pagos',
        ),
        token_publico=token,
        estado='PAGADO',
    )

    contenido = construir_pdf_cobro(cobro)

    response = HttpResponse(
        contenido,
        content_type='application/pdf'
    )

    response['Content-Disposition'] = (
        f'inline; filename="comprobante-{cobro.folio}.pdf"'
    )

    response['X-Content-Type-Options'] = 'nosniff'
    response['Cache-Control'] = 'private, no-store'
    return response


@login_required
def detalle_paciente(
    request,
    paciente_id
):
    membresia = obtener_membresia_usuario(request)

    if membresia is None:
        return redirect('panel_config')

    if membresia.rol not in [
        'MEDICO',
        'RADIOLOGIA',
        'TECNICO',
        'ADMIN',
    ]:
        return redirect('panel_recepcion')

    paciente = get_object_or_404(
        Paciente,
        pk=paciente_id,
        institucion=membresia.institucion
    )

    estudios = list(
        paciente.estudios
        .select_related(
            'tipo_estudio',
            'reporte_final_por',
            'pre_reporte_por',
        )
        .prefetch_related(
            'archivos'
        )
        .all()
        .order_by(
            '-fecha_creacion'
        )
    )
    primera_instancia_por_estudio = {}
    for instancia_dicom in (
        InstanciaDicom.objects
        .filter(archivo_estudio__estudio__in=estudios)
        .select_related('archivo_estudio')
        .order_by('archivo_estudio__estudio_id', 'serie__numero_serie', 'numero_instancia', 'id')
    ):
        primera_instancia_por_estudio.setdefault(
            instancia_dicom.archivo_estudio.estudio_id,
            instancia_dicom,
        )
    for estudio_item in estudios:
        primera = primera_instancia_por_estudio.get(estudio_item.id)
        estudio_item.visor_dicom_url = (
            reverse('visor_instancia_dicom', args=[estudio_item.id, primera.id])
            if primera else None
        )

    consultas = list(
        paciente.consultas
        .select_related(
            'medico'
        )
        .all()
        .order_by(
            '-fecha_llegada'
        )
    )

    citas = list(
        paciente.citas
        .select_related(
            'tipo_estudio'
        )
        .all()
        .order_by(
            '-fecha_hora'
        )
    )

    historial_eventos = []
    if paciente.creado_el:
        historial_eventos.append({
            'fecha': paciente.creado_el,
            'tipo': 'REGISTRO',
            'etiqueta': 'Registro inicial',
            'titulo': 'Paciente registrado en Recepción',
            'estado': 'Expediente creado',
            'objeto': paciente,
        })
    for consulta_item in consultas:
        historial_eventos.append({
            'fecha': consulta_item.fecha_llegada,
            'tipo': 'CONSULTA',
            'etiqueta': 'Consulta',
            'titulo': consulta_item.motivo_consulta or 'Consulta médica',
            'estado': consulta_item.get_estado_display(),
            'objeto': consulta_item,
        })
    for estudio_item in estudios:
        estudio_item.reporte_pdf_url = None
        try:
            reporte_item = estudio_item.reporte_radiologico
        except ReporteRadiologico.DoesNotExist:
            reporte_item = None
        if reporte_item:
            estudio_item.reporte_pdf_url = reverse(
                'reporte_radiologico_pdf', args=[estudio_item.id],
            )
        historial_eventos.append({
            'fecha': estudio_item.fecha_creacion,
            'tipo': 'IMAGEN',
            'etiqueta': estudio_item.tipo_estudio.get_modalidad_display(),
            'titulo': estudio_item.tipo_estudio.nombre,
            'estado': estudio_item.get_estado_display(),
            'objeto': estudio_item,
        })
    historial_eventos.sort(
        key=lambda evento: evento['fecha'] or timezone.now(),
        reverse=True,
    )

    consulta_activa = None

    if membresia.rol in [
        'MEDICO',
        'ADMIN',
    ]:
        consulta_activa = (
            paciente.consultas
            .select_related(
                'medico'
            )
            .filter(
                estado='EN_CONSULTA'
            )
            .filter(
                Q(
                    medico=request.user
                )
                |
                Q(
                    medico__isnull=True
                )
            )
            .order_by(
                '-fecha_inicio',
                '-fecha_llegada',
            )
            .first()
        )

    edad = calcular_edad(
        paciente.fecha_nacimiento
    )

    puede_editar_clinica = (
        membresia.rol
        in [
            'MEDICO',
            'ADMIN',
        ]
    )

    receta_activa = None
    indicacion_activa = None
    solicitudes_activas = []

    if consulta_activa and puede_editar_clinica:
        receta_activa = (
            RecetaMedica.objects
            .filter(
                consulta=consulta_activa
            )
            .prefetch_related(
                'medicamentos'
            )
            .first()
        )

        indicacion_activa = (
            IndicacionMedica.objects
            .filter(
                consulta=consulta_activa
            )
            .first()
        )

        solicitudes_activas = (
            SolicitudEstudio.objects
            .filter(
                consulta=consulta_activa
            )
            .prefetch_related(
                'estudios_solicitados'
            )
            .order_by(
                '-creada_el'
            )
        )

    context = {
        'paciente': paciente,
        'estudios': estudios,
        'consultas': consultas,
        'citas': citas,
        'edad': edad,
        'membresia': membresia,
        'consulta_activa': consulta_activa,
        'puede_editar_clinica':
            puede_editar_clinica,
        'receta_activa': receta_activa,
        'indicacion_activa': indicacion_activa,
        'solicitudes_activas': solicitudes_activas,
        'historial_eventos': historial_eventos,
    }

    return render(
        request,
        'core/detalle_paciente.html',
        context
    )



@login_required
def generar_documentos_clinicos_pdf(
    request,
    consulta_id
):
    membresia = obtener_membresia_usuario(request)

    if membresia is None:
        return redirect('panel_config')

    if membresia.rol not in [
        'MEDICO',
        'ADMIN',
    ]:
        return redirect('panel_config')

    consulta = get_object_or_404(
        Consulta.objects.select_related(
            'paciente',
            'medico',
            'paciente__institucion',
        ),
        pk=consulta_id,
        paciente__institucion=membresia.institucion,
    )

    if (
        membresia.rol != 'ADMIN'
        and consulta.medico_id
        and consulta.medico_id != request.user.id
    ):
        return redirect(
            'detalle_paciente',
            paciente_id=consulta.paciente_id
        )

    incluir_receta = (
        request.GET.get('receta') == '1'
    )

    incluir_solicitudes = (
        request.GET.get('solicitudes') == '1'
    )

    incluir_indicaciones = (
        request.GET.get('indicaciones') == '1'
    )

    incluir_resumen = (
        request.GET.get('resumen') == '1'
    )

    if not any([
        incluir_receta,
        incluir_solicitudes,
        incluir_indicaciones,
        incluir_resumen,
    ]):
        incluir_receta = True

    institucion = consulta.paciente.institucion

    medico_documento = (
        consulta.medico
        or request.user
    )

    perfil_medico = (
        PerfilMedico.objects
        .filter(
            institucion=institucion,
            usuario=medico_documento,
            activo=True,
        )
        .first()
    )

    receta = (
        RecetaMedica.objects
        .filter(
            consulta=consulta
        )
        .prefetch_related(
            'medicamentos'
        )
        .first()
    )

    indicacion = (
        IndicacionMedica.objects
        .filter(
            consulta=consulta
        )
        .first()
    )

    solicitudes = list(
        SolicitudEstudio.objects
        .filter(
            consulta=consulta
        )
        .prefetch_related(
            'estudios_solicitados'
        )
        .order_by(
            'creada_el'
        )
    )

    buffer = BytesIO()

    response_disposition = (
        'attachment'
        if request.GET.get('descargar') == '1'
        else 'inline'
    )

    nombre_archivo = (
        'documentos_'
        f'{consulta.paciente.identificacion}_'
        f'{timezone.localdate():%Y%m%d}.pdf'
    )

    documento = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=1.05 * cm,
        leftMargin=1.05 * cm,
        topMargin=0.8 * cm,
        bottomMargin=0.85 * cm,
        title='Documentos clínicos',
        author=obtener_nombre_usuario(
            medico_documento
        ),
    )

    estilos_base = getSampleStyleSheet()

    estilo_institucion = ParagraphStyle(
        'InstitucionCompacta',
        parent=estilos_base['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=11.5,
        leading=13,
        alignment=TA_LEFT,
        textColor=colors.HexColor('#0f2747'),
        spaceAfter=1,
    )

    estilo_institucion_sub = ParagraphStyle(
        'InstitucionSub',
        parent=estilos_base['Normal'],
        fontName='Helvetica',
        fontSize=6.7,
        leading=8.2,
        textColor=colors.HexColor('#334155'),
    )

    estilo_titulo = ParagraphStyle(
        'TituloCompacto',
        parent=estilos_base['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=9.2,
        leading=10.5,
        textColor=colors.HexColor('#0f2747'),
        spaceBefore=2,
        spaceAfter=3,
    )

    estilo_texto = ParagraphStyle(
        'TextoCompacto',
        parent=estilos_base['Normal'],
        fontName='Helvetica',
        fontSize=7.0,
        leading=8.5,
        textColor=colors.HexColor('#111827'),
    )

    estilo_texto_65 = ParagraphStyle(
        'Texto65',
        parent=estilo_texto,
        fontSize=6.5,
        leading=7.7,
    )

    estilo_pequeno = ParagraphStyle(
        'PequenoCompacto',
        parent=estilos_base['Normal'],
        fontName='Helvetica',
        fontSize=5.8,
        leading=6.8,
        textColor=colors.HexColor('#475569'),
    )

    estilo_tabla = ParagraphStyle(
        'TablaCompacta',
        parent=estilos_base['Normal'],
        fontName='Helvetica',
        fontSize=5.8,
        leading=6.7,
        textColor=colors.HexColor('#111827'),
    )

    estilo_tabla_negrita = ParagraphStyle(
        'TablaCompactaNegrita',
        parent=estilo_tabla,
        fontName='Helvetica-Bold',
    )

    estilo_centrado = ParagraphStyle(
        'CentradoCompacto',
        parent=estilo_pequeno,
        alignment=TA_CENTER,
    )

    historia = []

    def limpio(valor):
        if valor is None:
            return ''
        return escape(str(valor))

    def parrafo(valor, estilo=estilo_texto):
        return Paragraph(
            limpio(valor).replace('\n', '<br/>'),
            estilo
        )

    def imagen_desde_campo(campo, ancho, alto):
        if not campo:
            return None

        try:
            campo.open('rb')
            datos = campo.read()
            campo.close()

            if not datos:
                return None

            return Image(
                BytesIO(datos),
                width=ancho,
                height=alto,
                kind='proportional',
            )
        except Exception:
            return None

    def nombre_institucion():
        return (
            institucion.nombre_comercial
            or institucion.nombre
        )

    telefonos = [
        valor
        for valor in [
            institucion.telefono,
            institucion.telefono_secundario,
        ]
        if valor
    ]

    logo = imagen_desde_campo(
        institucion.logo,
        2.15 * cm,
        1.65 * cm,
    )

    bloque_institucion = [
        Paragraph(
            limpio(nombre_institucion()),
            estilo_institucion
        )
    ]

    if institucion.direccion:
        bloque_institucion.append(
            parrafo(
                institucion.direccion,
                estilo_institucion_sub
            )
        )

    if telefonos:
        bloque_institucion.append(
            parrafo(
                'Tel. ' + ' / '.join(telefonos),
                estilo_institucion_sub
            )
        )

    if institucion.email:
        bloque_institucion.append(
            parrafo(
                institucion.email,
                estilo_institucion_sub
            )
        )

    bloque_horarios = []

    if institucion.horarios_servicio:
        bloque_horarios.extend([
            Paragraph(
                '<b>HORARIO DE ATENCIÓN</b>',
                estilo_institucion_sub
            ),
            parrafo(
                institucion.horarios_servicio,
                estilo_institucion_sub
            ),
        ])

    encabezado = Table(
        [[
            logo or '',
            bloque_institucion,
            bloque_horarios,
        ]],
        colWidths=[
            2.5 * cm,
            10.4 * cm,
            6.25 * cm,
        ],
    )

    encabezado.setStyle(
        TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 2),
            ('RIGHTPADDING', (0, 0), (-1, -1), 2),
            ('TOPPADDING', (0, 0), (-1, -1), 1),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            (
                'LINEBELOW',
                (0, 0),
                (-1, -1),
                1.1,
                colors.HexColor('#17365d')
            ),
        ])
    )

    historia.append(encabezado)
    historia.append(Spacer(1, 0.12 * cm))

    edad = calcular_edad(
        consulta.paciente.fecha_nacimiento
    )

    paciente_info = [
        [
            Paragraph(
                '<b>PACIENTE:</b> '
                + limpio(
                    f'{consulta.paciente.nombre} '
                    f'{consulta.paciente.apellido}'
                ),
                estilo_texto_65
            ),
            Paragraph(
                '<b>REGISTRO:</b> '
                + limpio(
                    consulta.paciente.identificacion
                ),
                estilo_texto_65
            ),
        ],
        [
            Paragraph(
                '<b>FECHA DE NACIMIENTO:</b> '
                + limpio(
                    f'{consulta.paciente.fecha_nacimiento:%d/%m/%Y}'
                )
                + (
                    ' &nbsp;|&nbsp; '
                    + limpio(f'{edad} años')
                    if edad is not None
                    else ''
                ),
                estilo_texto_65
            ),
            Paragraph(
                '<b>FECHA:</b> '
                + limpio(
                    f'{timezone.localdate():%d/%m/%Y}'
                ),
                estilo_texto_65
            ),
        ],
    ]

    tabla_paciente = Table(
        paciente_info,
        colWidths=[
            12.7 * cm,
            6.45 * cm,
        ],
    )

    tabla_paciente.setStyle(
        TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            (
                'BACKGROUND',
                (0, 0),
                (-1, -1),
                colors.HexColor('#fbfdff')
            ),
            (
                'BOX',
                (0, 0),
                (-1, -1),
                0.45,
                colors.HexColor('#94a3b8')
            ),
            (
                'INNERGRID',
                (0, 0),
                (-1, -1),
                0.25,
                colors.HexColor('#cbd5e1')
            ),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ])
    )

    historia.append(tabla_paciente)
    historia.append(Spacer(1, 0.16 * cm))

    secciones_agregadas = 0

    if incluir_resumen:
        historia.append(
            Paragraph(
                'RESUMEN CLÍNICO / REFERENCIA',
                estilo_titulo
            )
        )

        datos_resumen = []

        fecha_atencion = (
            consulta.fecha_inicio
            or consulta.fecha_llegada
        )

        if fecha_atencion:
            try:
                fecha_atencion = timezone.localtime(
                    fecha_atencion
                )
            except Exception:
                pass

            datos_resumen.append(
                '<b>Fecha y hora de atención:</b> '
                + limpio(
                    fecha_atencion.strftime(
                        '%d/%m/%Y %H:%M'
                    )
                )
            )

        if consulta.motivo_consulta:
            datos_resumen.append(
                '<b>Motivo de consulta:</b> '
                + limpio(
                    consulta.motivo_consulta
                )
            )

        for dato in datos_resumen:
            historia.append(
                Paragraph(
                    dato,
                    estilo_texto_65
                )
            )
            historia.append(
                Spacer(1, 0.05 * cm)
            )

        signos = []

        if (
            consulta.presion_sistolica is not None
            or consulta.presion_diastolica is not None
        ):
            sistolica = (
                str(consulta.presion_sistolica)
                if consulta.presion_sistolica is not None
                else '—'
            )
            diastolica = (
                str(consulta.presion_diastolica)
                if consulta.presion_diastolica is not None
                else '—'
            )
            signos.append(
                ('TA', f'{sistolica}/{diastolica} mmHg')
            )

        if consulta.frecuencia_cardiaca is not None:
            signos.append(
                ('FC', f'{consulta.frecuencia_cardiaca} lpm')
            )

        if consulta.frecuencia_respiratoria is not None:
            signos.append(
                ('FR', f'{consulta.frecuencia_respiratoria} rpm')
            )

        if consulta.temperatura is not None:
            signos.append(
                ('Temp.', f'{consulta.temperatura} °C')
            )

        if consulta.saturacion_oxigeno is not None:
            signos.append(
                ('SpO₂', f'{consulta.saturacion_oxigeno}%')
            )

        if consulta.peso_kg is not None:
            signos.append(
                ('Peso', f'{consulta.peso_kg} kg')
            )

        if consulta.talla_cm is not None:
            signos.append(
                ('Talla', f'{consulta.talla_cm} cm')
            )

        if signos:
            celdas = []

            for etiqueta, valor in signos:
                celdas.append(
                    Paragraph(
                        '<b>'
                        + limpio(etiqueta)
                        + '</b><br/>'
                        + limpio(valor),
                        estilo_centrado
                    )
                )

            ancho_total = 19.15 * cm
            ancho_columna = ancho_total / len(celdas)

            tabla_signos = Table(
                [celdas],
                colWidths=[
                    ancho_columna
                    for _ in celdas
                ],
            )

            tabla_signos.setStyle(
                TableStyle([
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    (
                        'BACKGROUND',
                        (0, 0),
                        (-1, -1),
                        colors.HexColor('#f4f7fb')
                    ),
                    (
                        'BOX',
                        (0, 0),
                        (-1, -1),
                        0.5,
                        colors.HexColor('#7b95b7')
                    ),
                    (
                        'INNERGRID',
                        (0, 0),
                        (-1, -1),
                        0.3,
                        colors.HexColor('#aebdd0')
                    ),
                    ('TOPPADDING', (0, 0), (-1, -1), 3),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                    ('LEFTPADDING', (0, 0), (-1, -1), 2),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 2),
                ])
            )

            historia.append(
                Spacer(1, 0.05 * cm)
            )
            historia.append(tabla_signos)

        secciones_agregadas += 1

    if incluir_receta:
        if secciones_agregadas:
            historia.append(
                Spacer(1, 0.12 * cm)
            )

        historia.append(
            Paragraph(
                'RECETA MÉDICA',
                estilo_titulo
            )
        )

        if receta and receta.medicamentos.exists():
            encabezados = [
                'Medicamento',
                'Presentación',
                'Dosis',
                'Vía',
                'Frecuencia',
                'Cantidad',
                'Duración',
                'Indicaciones',
            ]

            filas = [[
                Paragraph(
                    '<b>' + titulo + '</b>',
                    estilo_tabla_negrita
                )
                for titulo in encabezados
            ]]

            for medicamento in receta.medicamentos.all():
                via = (
                    medicamento.get_via_display()
                    if medicamento.via
                    else ''
                )

                filas.append([
                    parrafo(
                        medicamento.medicamento,
                        estilo_tabla_negrita
                    ),
                    parrafo(
                        medicamento.presentacion,
                        estilo_tabla
                    ),
                    parrafo(
                        medicamento.dosis,
                        estilo_tabla
                    ),
                    parrafo(
                        via,
                        estilo_tabla
                    ),
                    parrafo(
                        medicamento.frecuencia,
                        estilo_tabla
                    ),
                    parrafo(
                        medicamento.cantidad,
                        estilo_tabla
                    ),
                    parrafo(
                        medicamento.duracion,
                        estilo_tabla
                    ),
                    parrafo(
                        medicamento.indicaciones,
                        estilo_tabla
                    ),
                ])

            tabla_receta = Table(
                filas,
                colWidths=[
                    3.2 * cm,
                    2.45 * cm,
                    2.05 * cm,
                    1.55 * cm,
                    2.2 * cm,
                    1.85 * cm,
                    1.65 * cm,
                    4.2 * cm,
                ],
                repeatRows=1,
            )

            tabla_receta.setStyle(
                TableStyle([
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    (
                        'BACKGROUND',
                        (0, 0),
                        (-1, 0),
                        colors.HexColor('#e9eff6')
                    ),
                    (
                        'BOX',
                        (0, 0),
                        (-1, -1),
                        0.45,
                        colors.HexColor('#7b95b7')
                    ),
                    (
                        'INNERGRID',
                        (0, 0),
                        (-1, -1),
                        0.22,
                        colors.HexColor('#c7d2e0')
                    ),
                    ('LEFTPADDING', (0, 0), (-1, -1), 2.6),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 2.6),
                    ('TOPPADDING', (0, 0), (-1, -1), 2.5),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
                ])
            )

            historia.append(tabla_receta)

            if receta.observaciones:
                historia.append(
                    Spacer(1, 0.06 * cm)
                )
                historia.append(
                    Paragraph(
                        '<b>Observaciones:</b> '
                        + limpio(
                            receta.observaciones
                        ),
                        estilo_pequeno
                    )
                )
        else:
            historia.append(
                Paragraph(
                    'No hay medicamentos guardados en esta consulta.',
                    estilo_texto_65
                )
            )

        secciones_agregadas += 1

    if incluir_solicitudes:
        if secciones_agregadas:
            historia.append(
                Spacer(1, 0.12 * cm)
            )

        historia.append(
            Paragraph(
                'SOLICITUD DE ESTUDIOS',
                estilo_titulo
            )
        )

        if solicitudes:
            for numero, solicitud in enumerate(
                solicitudes,
                start=1
            ):
                linea_solicitud = (
                    '<b>Solicitud '
                    + limpio(numero)
                    + ':</b> '
                    + limpio(
                        solicitud.get_tipo_display()
                    )
                    + ' · '
                    + limpio(
                        solicitud.get_prioridad_display()
                    )
                )

                historia.append(
                    Paragraph(
                        linea_solicitud,
                        estilo_texto_65
                    )
                )

                if solicitud.motivo_clinico:
                    historia.append(
                        Paragraph(
                            '<b>Motivo clínico:</b> '
                            + limpio(
                                solicitud.motivo_clinico
                            ),
                            estilo_pequeno
                        )
                    )

                estudios_texto = []

                for estudio_solicitado in (
                    solicitud.estudios_solicitados.all()
                ):
                    item = (
                        '• '
                        + limpio(
                            estudio_solicitado.nombre
                        )
                    )

                    if estudio_solicitado.region_o_detalle:
                        item += (
                            ' — '
                            + limpio(
                                estudio_solicitado.region_o_detalle
                            )
                        )

                    if estudio_solicitado.indicaciones:
                        item += (
                            ' | '
                            + limpio(
                                estudio_solicitado.indicaciones
                            )
                        )

                    estudios_texto.append(item)

                if estudios_texto:
                    historia.append(
                        Paragraph(
                            '<br/>'.join(
                                estudios_texto
                            ),
                            estilo_pequeno
                        )
                    )

                if solicitud.observaciones:
                    historia.append(
                        Paragraph(
                            '<b>Obs.:</b> '
                            + limpio(
                                solicitud.observaciones
                            ),
                            estilo_pequeno
                        )
                    )

                if numero < len(solicitudes):
                    historia.append(
                        Spacer(1, 0.05 * cm)
                    )
        else:
            historia.append(
                Paragraph(
                    'No hay solicitudes de estudio guardadas en esta consulta.',
                    estilo_texto_65
                )
            )

        secciones_agregadas += 1

    if incluir_indicaciones:
        if secciones_agregadas:
            historia.append(
                Spacer(1, 0.12 * cm)
            )

        historia.append(
            Paragraph(
                'INDICACIONES MÉDICAS',
                estilo_titulo
            )
        )

        if indicacion and indicacion.indicaciones:
            historia.append(
                Paragraph(
                    limpio(
                        indicacion.indicaciones
                    ).replace(
                        '\n',
                        '<br/>'
                    ),
                    estilo_texto_65
                )
            )
        else:
            historia.append(
                Paragraph(
                    'No hay indicaciones médicas guardadas en esta consulta.',
                    estilo_texto_65
                )
            )

        secciones_agregadas += 1

    historia.append(
        Spacer(1, 0.18 * cm)
    )

    firma = None

    if perfil_medico:
        firma = imagen_desde_campo(
            perfil_medico.firma,
            3.4 * cm,
            1.05 * cm,
        )

    firma_contenido = []

    if firma:
        firma_contenido.append(firma)
    else:
        firma_contenido.append(
            Spacer(1, 0.75 * cm)
        )

    firma_contenido.extend([
        Paragraph(
            '_______________________________',
            estilo_centrado
        ),
        Paragraph(
            '<b>'
            + limpio(
                obtener_nombre_usuario(
                    medico_documento
                )
            )
            + '</b>',
            estilo_centrado
        ),
    ])

    datos_medico = []

    if perfil_medico and perfil_medico.especialidad:
        datos_medico.append(
            limpio(
                perfil_medico.especialidad
            )
        )

    if perfil_medico and perfil_medico.cedula_profesional:
        datos_medico.append(
            'Céd. Prof. '
            + limpio(
                perfil_medico.cedula_profesional
            )
        )

    if datos_medico:
        firma_contenido.append(
            Paragraph(
                ' | '.join(datos_medico),
                estilo_centrado
            )
        )

    tabla_firma = Table(
        [['', firma_contenido, '']],
        colWidths=[
            5.5 * cm,
            8.15 * cm,
            5.5 * cm,
        ],
    )

    tabla_firma.setStyle(
        TableStyle([
            ('ALIGN', (1, 0), (1, 0), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ])
    )

    historia.append(
        KeepTogether([tabla_firma])
    )

    pie = []

    if institucion.direccion:
        pie.append(
            limpio(institucion.direccion)
        )

    if telefonos:
        pie.append(
            limpio(
                'Tel. ' + ' / '.join(telefonos)
            )
        )

    if institucion.email:
        pie.append(
            limpio(institucion.email)
        )

    if institucion.pie_documentos:
        pie.append(
            limpio(
                institucion.pie_documentos
            )
        )

    if pie:
        historia.append(
            Spacer(1, 0.08 * cm)
        )
        historia.append(
            Paragraph(
                ' · '.join(pie),
                estilo_centrado
            )
        )

    documento.build(historia)

    pdf = buffer.getvalue()
    buffer.close()

    respuesta = HttpResponse(
        pdf,
        content_type='application/pdf'
    )

    respuesta[
        'Content-Disposition'
    ] = (
        f'{response_disposition}; '
        f'filename="{nombre_archivo}"'
    )

    return respuesta


@login_required
def guardar_receta_medica(
    request,
    consulta_id
):
    membresia = obtener_membresia_usuario(request)

    if membresia is None:
        return redirect('panel_config')

    if membresia.rol not in [
        'MEDICO',
        'ADMIN',
    ]:
        return redirect('panel_config')

    consulta = get_object_or_404(
        Consulta.objects.select_related(
            'paciente',
            'medico',
        ),
        pk=consulta_id,
        paciente__institucion=membresia.institucion,
        estado='EN_CONSULTA',
    )

    if (
        membresia.rol != 'ADMIN'
        and consulta.medico_id
        and consulta.medico_id != request.user.id
    ):
        return redirect(
            'detalle_paciente',
            paciente_id=consulta.paciente_id
        )

    if request.method == 'POST':
        observaciones = (
            request.POST.get(
                'observaciones_receta',
                ''
            )
            .strip()
            or None
        )

        receta, _ = (
            RecetaMedica.objects
            .update_or_create(
                consulta=consulta,
                defaults={
                    'medico': request.user,
                    'observaciones': observaciones,
                }
            )
        )

        receta.medicamentos.all().delete()

        medicamentos = request.POST.getlist(
            'medicamento'
        )
        presentaciones = request.POST.getlist(
            'presentacion'
        )
        dosis = request.POST.getlist(
            'dosis'
        )
        vias = request.POST.getlist(
            'via'
        )
        frecuencias = request.POST.getlist(
            'frecuencia'
        )
        cantidades = request.POST.getlist(
            'cantidad'
        )
        duraciones = request.POST.getlist(
            'duracion'
        )
        indicaciones = request.POST.getlist(
            'indicaciones_medicamento'
        )

        for indice, nombre in enumerate(
            medicamentos,
            start=1
        ):
            nombre = nombre.strip()

            if not nombre:
                continue

            def valor_lista(lista, posicion):
                try:
                    valor = lista[posicion].strip()
                except IndexError:
                    return None

                return valor or None

            posicion = indice - 1

            MedicamentoReceta.objects.create(
                receta=receta,
                medicamento=nombre,
                presentacion=valor_lista(
                    presentaciones,
                    posicion
                ),
                dosis=valor_lista(
                    dosis,
                    posicion
                ),
                via=valor_lista(
                    vias,
                    posicion
                ),
                frecuencia=valor_lista(
                    frecuencias,
                    posicion
                ),
                cantidad=valor_lista(
                    cantidades,
                    posicion
                ),
                duracion=valor_lista(
                    duraciones,
                    posicion
                ),
                indicaciones=valor_lista(
                    indicaciones,
                    posicion
                ),
                orden=indice,
            )

    return redirect(
        'detalle_paciente',
        paciente_id=consulta.paciente_id
    )


@login_required
def guardar_indicacion_medica(
    request,
    consulta_id
):
    membresia = obtener_membresia_usuario(request)

    if membresia is None:
        return redirect('panel_config')

    if membresia.rol not in [
        'MEDICO',
        'ADMIN',
    ]:
        return redirect('panel_config')

    consulta = get_object_or_404(
        Consulta.objects.select_related(
            'paciente',
            'medico',
        ),
        pk=consulta_id,
        paciente__institucion=membresia.institucion,
        estado='EN_CONSULTA',
    )

    if (
        membresia.rol != 'ADMIN'
        and consulta.medico_id
        and consulta.medico_id != request.user.id
    ):
        return redirect(
            'detalle_paciente',
            paciente_id=consulta.paciente_id
        )

    if request.method == 'POST':
        indicaciones = (
            request.POST.get(
                'indicaciones_medicas',
                ''
            )
            .strip()
        )

        if indicaciones:
            IndicacionMedica.objects.update_or_create(
                consulta=consulta,
                defaults={
                    'medico': request.user,
                    'indicaciones': indicaciones,
                }
            )
        else:
            IndicacionMedica.objects.filter(
                consulta=consulta
            ).delete()

    return redirect(
        'detalle_paciente',
        paciente_id=consulta.paciente_id
    )


@login_required
def guardar_solicitud_estudio(
    request,
    consulta_id
):
    membresia = obtener_membresia_usuario(request)

    if membresia is None:
        return redirect('panel_config')

    if membresia.rol not in [
        'MEDICO',
        'ADMIN',
    ]:
        return redirect('panel_config')

    consulta = get_object_or_404(
        Consulta.objects.select_related(
            'paciente',
            'medico',
        ),
        pk=consulta_id,
        paciente__institucion=membresia.institucion,
        estado='EN_CONSULTA',
    )

    if (
        membresia.rol != 'ADMIN'
        and consulta.medico_id
        and consulta.medico_id != request.user.id
    ):
        return redirect(
            'detalle_paciente',
            paciente_id=consulta.paciente_id
        )

    if request.method == 'POST':
        tipo = (
            request.POST.get(
                'tipo_solicitud',
                ''
            )
            .strip()
        )

        prioridad = (
            request.POST.get(
                'prioridad_solicitud',
                'RUTINA'
            )
            .strip()
            or 'RUTINA'
        )

        motivo_clinico = (
            request.POST.get(
                'motivo_clinico',
                ''
            )
            .strip()
            or None
        )

        observaciones = (
            request.POST.get(
                'observaciones_solicitud',
                ''
            )
            .strip()
            or None
        )

        tipos_validos = {
            opcion[0]
            for opcion in SolicitudEstudio.TIPO_CHOICES
        }

        prioridades_validas = {
            opcion[0]
            for opcion in SolicitudEstudio.PRIORIDAD_CHOICES
        }

        if tipo in tipos_validos:
            if prioridad not in prioridades_validas:
                prioridad = 'RUTINA'

            nombres = request.POST.getlist(
                'estudio_nombre'
            )
            detalles = request.POST.getlist(
                'estudio_detalle'
            )
            indicaciones = request.POST.getlist(
                'estudio_indicaciones'
            )

            nombres_limpios = [
                nombre.strip()
                for nombre in nombres
                if nombre.strip()
            ]

            if nombres_limpios:
                with transaction.atomic():
                    solicitud = (
                        SolicitudEstudio.objects
                        .create(
                            consulta=consulta,
                            medico=request.user,
                            tipo=tipo,
                            prioridad=prioridad,
                            motivo_clinico=motivo_clinico,
                            observaciones=observaciones,
                        )
                    )

                    for indice, nombre in enumerate(
                        nombres,
                        start=1
                    ):
                        nombre = nombre.strip()

                        if not nombre:
                            continue

                        posicion = indice - 1

                        def valor_lista(lista):
                            try:
                                valor = (
                                    lista[posicion]
                                    .strip()
                                )
                            except IndexError:
                                return None

                            return valor or None

                        EstudioSolicitado.objects.create(
                            solicitud=solicitud,
                            nombre=nombre,
                            region_o_detalle=valor_lista(
                                detalles
                            ),
                            indicaciones=valor_lista(
                                indicaciones
                            ),
                            orden=indice,
                        )

    return redirect(
        'detalle_paciente',
        paciente_id=consulta.paciente_id
    )


@login_required
def guardar_consulta_clinica(
    request,
    consulta_id
):
    membresia = obtener_membresia_usuario(request)

    if membresia is None:
        return redirect('panel_config')

    if membresia.rol not in [
        'MEDICO',
        'ADMIN',
    ]:
        return redirect('panel_config')

    consulta = get_object_or_404(
        Consulta.objects.select_related(
            'paciente',
            'medico',
        ),
        pk=consulta_id,
        paciente__institucion=membresia.institucion,
        estado='EN_CONSULTA',
    )

    if (
        membresia.rol != 'ADMIN'
        and consulta.medico_id
        and consulta.medico_id != request.user.id
    ):
        return redirect(
            'detalle_paciente',
            paciente_id=consulta.paciente_id
        )

    if request.method == 'POST':

        def entero(nombre):
            valor = (
                request.POST.get(
                    nombre,
                    ''
                )
                .strip()
            )

            if not valor:
                return None

            try:
                return int(valor)
            except (
                TypeError,
                ValueError,
            ):
                return None

        def decimal(nombre):
            valor = (
                request.POST.get(
                    nombre,
                    ''
                )
                .strip()
                .replace(
                    ',',
                    '.'
                )
            )

            if not valor:
                return None

            try:
                return float(valor)
            except (
                TypeError,
                ValueError,
            ):
                return None

        def texto(nombre):
            return (
                request.POST.get(
                    nombre,
                    ''
                )
                .strip()
                or None
            )

        consulta.medico = (
            consulta.medico
            or request.user
        )

        consulta.motivo_consulta = (
            texto('motivo_consulta')
        )

        consulta.presion_sistolica = (
            entero('presion_sistolica')
        )

        consulta.presion_diastolica = (
            entero('presion_diastolica')
        )

        consulta.frecuencia_cardiaca = (
            entero('frecuencia_cardiaca')
        )

        consulta.frecuencia_respiratoria = (
            entero('frecuencia_respiratoria')
        )

        consulta.temperatura = (
            decimal('temperatura')
        )

        consulta.saturacion_oxigeno = (
            entero('saturacion_oxigeno')
        )

        consulta.peso_kg = (
            decimal('peso_kg')
        )

        consulta.talla_cm = (
            decimal('talla_cm')
        )

        consulta.antecedentes = (
            texto('antecedentes')
        )

        consulta.exploracion_fisica = (
            texto('exploracion_fisica')
        )

        consulta.diagnostico = (
            texto('diagnostico')
        )

        consulta.plan_tratamiento = (
            texto('plan_tratamiento')
        )

        consulta.notas_medicas = (
            texto('notas_medicas')
        )

        consulta.save(
            update_fields=[
                'medico',
                'motivo_consulta',
                'presion_sistolica',
                'presion_diastolica',
                'frecuencia_cardiaca',
                'frecuencia_respiratoria',
                'temperatura',
                'saturacion_oxigeno',
                'peso_kg',
                'talla_cm',
                'antecedentes',
                'exploracion_fisica',
                'diagnostico',
                'plan_tratamiento',
                'notas_medicas',
            ]
        )

    return redirect(
        'detalle_paciente',
        paciente_id=consulta.paciente_id
    )


# =========================================================
# REPORTE FINAL DESDE EXPEDIENTE MÉDICO
# =========================================================

@login_required
def guardar_reporte_final_medico(
    request,
    estudio_id
):
    membresia = obtener_membresia_usuario(request)

    if membresia is None:
        return redirect('panel_config')

    if membresia.rol not in [
        'MEDICO',
        'ADMIN',
    ]:
        return redirect('panel_config')

    estudio = get_object_or_404(
        Estudio.objects.select_related(
            'paciente',
            'tipo_estudio',
            'reporte_final_por',
        ),
        pk=estudio_id,
        paciente__institucion=membresia.institucion,
    )

    if request.method == 'POST':
        reporte_final = (
            request.POST.get(
                'reporte_final',
                ''
            )
            .strip()
        )

        if reporte_final:
            estudio.reporte_final = reporte_final
            estudio.reporte_final_por = request.user
            estudio.fecha_reporte_final = timezone.now()
            estudio.estado_reporte = 'FINAL'

            estudio.save(
                update_fields=[
                    'reporte_final',
                    'reporte_final_por',
                    'fecha_reporte_final',
                    'estado_reporte',
                ]
            )

    return redirect(
        'detalle_paciente',
        paciente_id=estudio.paciente_id
    )


# =========================================================
# NUEVO ESTUDIO
# =========================================================

@login_required
def nuevo_estudio_paciente(
    request,
    paciente_id
):
    institucion = obtener_institucion_usuario(request)

    if institucion is None:
        return redirect('panel_config')

    paciente = get_object_or_404(
        Paciente,
        pk=paciente_id,
        institucion=institucion
    )

    if request.method == 'POST':

        estudio_form = EstudioForm(
            request.POST
        )

        if estudio_form.is_valid():

            estudio = (
                estudio_form.save(
                    commit=False
                )
            )

            estudio.paciente = (
                paciente
            )

            estudio.save()

            return redirect(
                'detalle_paciente',
                paciente_id=paciente.id
            )

    else:

        estudio_form = EstudioForm(
            initial={
                'estado':
                    'PENDIENTE',
            }
        )

    context = {
        'paciente':
            paciente,

        'estudio_form':
            estudio_form,
    }

    return render(
        request,
        'core/nuevo_estudio.html',
        context
    )


# =========================================================
# CONFIGURACIÓN
# =========================================================

@login_required
def panel_config(request):
    membresia = obtener_membresia_usuario(request)

    if membresia is not None:
        if membresia.rol == 'RECEPCION':
            return redirect(
                'panel_recepcion'
            )

        if membresia.rol == 'MEDICO':
            return redirect(
                'panel_medico'
            )

        if membresia.rol in [
            'RADIOLOGIA',
            'TECNICO',
        ]:
            return redirect(
                'panel_radiologo'
            )

        if (
            membresia.rol != 'ADMIN'
            and not request.user.is_superuser
        ):
            return redirect(
                'inicio'
            )

    elif not request.user.is_superuser:
        return redirect(
            'inicio'
        )

    institucion = (
        membresia.institucion
        if membresia is not None
        else None
    )

    guardado = False

    if (
        request.method == 'POST'
        and institucion is not None
    ):
        institucion.nombre = (
            request.POST.get(
                'nombre',
                ''
            )
            .strip()
            or institucion.nombre
        )

        institucion.nombre_comercial = (
            request.POST.get(
                'nombre_comercial',
                ''
            )
            .strip()
            or None
        )

        institucion.rfc = (
            request.POST.get(
                'rfc',
                ''
            )
            .strip()
            .upper()
            or None
        )

        institucion.telefono = (
            request.POST.get(
                'telefono',
                ''
            )
            .strip()
            or None
        )

        institucion.telefono_secundario = (
            request.POST.get(
                'telefono_secundario',
                ''
            )
            .strip()
            or None
        )

        institucion.email = (
            request.POST.get(
                'email',
                ''
            )
            .strip()
            or None
        )

        institucion.direccion = (
            request.POST.get(
                'direccion',
                ''
            )
            .strip()
            or None
        )

        institucion.horarios_servicio = (
            request.POST.get(
                'horarios_servicio',
                ''
            )
            .strip()
            or None
        )

        institucion.pie_documentos = (
            request.POST.get(
                'pie_documentos',
                ''
            )
            .strip()
            or None
        )

        logo = request.FILES.get(
            'logo'
        )

        if logo:
            institucion.logo = logo

        if request.POST.get(
            'eliminar_logo'
        ) == '1':
            if institucion.logo:
                institucion.logo.delete(
                    save=False
                )

            institucion.logo = None

        institucion.save()

        guardado = True

    context = {
        'membresia': membresia,
        'institucion': institucion,
        'guardado': guardado,
    }

    return render(
        request,
        'core/panel_config.html',
        context
    )


@login_required
def catalogo_servicios(request):
    membresia = obtener_membresia_usuario(request)

    if not puede_administrar_configuracion(
        request,
        membresia
    ):
        return redirect('panel_config')

    institucion = (
        membresia.institucion
        if membresia is not None
        else None
    )

    if institucion is None:
        messages.warning(
            request,
            'Tu usuario no tiene una institución asociada.'
        )
        return redirect('panel_config')

    busqueda = request.GET.get(
        'q',
        ''
    ).strip()

    tipo = request.GET.get(
        'tipo',
        ''
    ).strip()

    estado = request.GET.get(
        'estado',
        ''
    ).strip()

    servicios = (
        Servicio.objects
        .filter(institucion=institucion)
        .select_related(
            'institucion',
            'tipo_estudio',
        )
    )

    if busqueda:
        servicios = servicios.filter(
            Q(nombre__icontains=busqueda)
            | Q(tipo_estudio__codigo__icontains=busqueda)
            | Q(tipo_estudio__nombre__icontains=busqueda)
        )

    tipos_validos = {
        valor
        for valor, etiqueta
        in Servicio.TIPO_CHOICES
    }

    if tipo in tipos_validos:
        servicios = servicios.filter(tipo=tipo)

    if estado == 'ACTIVOS':
        servicios = servicios.filter(activo=True)
    elif estado == 'INACTIVOS':
        servicios = servicios.filter(activo=False)

    servicios = servicios.order_by(
        'tipo',
        'nombre',
    )

    paginador = Paginator(
        servicios,
        50
    )

    pagina = paginador.get_page(
        request.GET.get('pagina')
    )

    servicio_edicion = None
    servicio_edicion_id = request.GET.get(
        'editar'
    )

    if servicio_edicion_id:
        servicio_edicion = get_object_or_404(
            Servicio,
            pk=servicio_edicion_id,
            institucion=institucion,
        )

    resumen = {
        'total': Servicio.objects.filter(
            institucion=institucion
        ).count(),
        'activos': Servicio.objects.filter(
            institucion=institucion,
            activo=True,
        ).count(),
        'inactivos': Servicio.objects.filter(
            institucion=institucion,
            activo=False,
        ).count(),
    }

    context = {
        'membresia': membresia,
        'institucion': institucion,
        'pagina': pagina,
        'resumen': resumen,
        'busqueda': busqueda,
        'tipo_seleccionado': tipo,
        'estado_seleccionado': estado,
        'tipos_servicio': Servicio.TIPO_CHOICES,
        'tipos_estudio': TipoEstudio.objects.filter(
            activo=True
        ).order_by(
            'modalidad',
            'nombre',
        ),
        'servicio_edicion': servicio_edicion,
    }

    return render(
        request,
        'core/catalogo_servicios.html',
        context
    )


@login_required
def guardar_servicio(
    request,
    servicio_id=None
):
    if request.method != 'POST':
        return redirect('catalogo_servicios')

    membresia = obtener_membresia_usuario(request)

    if not puede_administrar_configuracion(
        request,
        membresia
    ):
        return redirect('panel_config')

    institucion = (
        membresia.institucion
        if membresia is not None
        else None
    )

    if institucion is None:
        messages.warning(
            request,
            'Tu usuario no tiene una institución asociada.'
        )
        return redirect('panel_config')

    servicio = None

    if servicio_id is not None:
        servicio = get_object_or_404(
            Servicio,
            pk=servicio_id,
            institucion=institucion,
        )

    nombre = request.POST.get(
        'nombre',
        ''
    ).strip()

    tipo = request.POST.get(
        'tipo',
        'OTRO'
    ).strip()

    precio_texto = request.POST.get(
        'precio_base',
        '0'
    ).strip()

    tipo_estudio_id = request.POST.get(
        'tipo_estudio',
        ''
    ).strip()

    tipos_validos = {
        valor
        for valor, etiqueta
        in Servicio.TIPO_CHOICES
    }

    errores = []

    if not nombre:
        errores.append(
            'Escribe el nombre del servicio.'
        )

    if tipo not in tipos_validos:
        errores.append(
            'Selecciona un tipo de servicio válido.'
        )

    try:
        precio_base = Decimal(precio_texto)

        if precio_base < 0:
            raise InvalidOperation

        if precio_base > Decimal('9999999999.99'):
            raise InvalidOperation

        precio_base = precio_base.quantize(
            Decimal('0.01')
        )
    except (InvalidOperation, ValueError):
        precio_base = Decimal('0.00')
        errores.append(
            'Escribe un precio válido mayor o igual a cero.'
        )

    tipo_estudio = None

    if tipo_estudio_id:
        tipo_estudio = TipoEstudio.objects.filter(
            pk=tipo_estudio_id,
            activo=True,
        ).first()

        if tipo_estudio is None:
            errores.append(
                'El tipo de estudio seleccionado no es válido.'
            )

    if errores:
        for error in errores:
            messages.error(
                request,
                error
            )

        return redirect('catalogo_servicios')

    if servicio is None:
        servicio = Servicio(
            institucion=institucion
        )

    servicio.nombre = nombre
    servicio.tipo = tipo
    servicio.tipo_estudio = tipo_estudio
    servicio.precio_base = precio_base
    servicio.precio_editable = (
        request.POST.get('precio_editable') == '1'
    )
    servicio.activo = (
        request.POST.get('activo') == '1'
    )
    servicio.save()

    messages.success(
        request,
        (
            'Servicio actualizado correctamente.'
            if servicio_id is not None
            else 'Servicio creado correctamente.'
        )
    )

    return redirect('catalogo_servicios')


@login_required
def cambiar_estado_servicio(
    request,
    servicio_id
):
    if request.method != 'POST':
        return redirect('catalogo_servicios')

    membresia = obtener_membresia_usuario(request)

    if not puede_administrar_configuracion(
        request,
        membresia
    ):
        return redirect('panel_config')

    institucion = (
        membresia.institucion
        if membresia is not None
        else None
    )

    if institucion is None:
        return redirect('panel_config')

    servicio = get_object_or_404(
        Servicio,
        pk=servicio_id,
        institucion=institucion,
    )

    servicio.activo = not servicio.activo
    servicio.save(
        update_fields=[
            'activo',
            'actualizado_el',
        ]
    )

    messages.success(
        request,
        (
            'Servicio activado correctamente.'
            if servicio.activo
            else 'Servicio desactivado correctamente.'
        )
    )

    return redirect('catalogo_servicios')


# =========================================================
# REGISTRO DESDE RECEPCIÓN
# =========================================================

@login_required
def registrar_estudio_recepcion(request):
    institucion = obtener_institucion_usuario(request)

    if institucion is None:
        return redirect('panel_config')

    if request.method == 'POST':

        paciente_form = PacienteForm(
            request.POST
        )

        destino_form = (
            DestinoAtencionForm(
                request.POST
            )
        )

        consulta_form = ConsultaForm(
            request.POST
        )

        estudio_form = EstudioForm(
            request.POST
        )

        formularios_principales_validos = (
            paciente_form.is_valid()
            and
            destino_form.is_valid()
        )

        if formularios_principales_validos:

            tipo_atencion = (
                destino_form.cleaned_data[
                    'tipo_atencion'
                ]
            )

            if tipo_atencion == 'CONSULTA':

                formulario_atencion_valido = (
                    consulta_form.is_valid()
                )

            else:

                formulario_atencion_valido = (
                    estudio_form.is_valid()
                )

            if formulario_atencion_valido:

                with transaction.atomic():

                    paciente = (
                        paciente_form.save(
                            commit=False
                        )
                    )

                    paciente.institucion = (
                        institucion
                    )

                    paciente.save()

                    if (
                        tipo_atencion
                        == 'CONSULTA'
                    ):

                        consulta = (
                            consulta_form.save(
                                commit=False
                            )
                        )

                        consulta.paciente = (
                            paciente
                        )

                        consulta.estado = (
                            'EN_ESPERA'
                        )

                        consulta.save()

                    elif (
                        tipo_atencion
                        == 'RADIOLOGIA'
                    ):

                        estudio = (
                            estudio_form.save(
                                commit=False
                            )
                        )

                        estudio.paciente = (
                            paciente
                        )

                        estudio.estado = (
                            'PENDIENTE'
                        )

                        estudio.save()

                return redirect(
                    'detalle_paciente',
                    paciente_id=paciente.id
                )

    else:

        paciente_form = PacienteForm()

        destino_form = (
            DestinoAtencionForm(
                initial={
                    'tipo_atencion':
                        'CONSULTA',
                }
            )
        )

        consulta_form = (
            ConsultaForm()
        )

        estudio_form = EstudioForm(
            initial={
                'estado':
                    'PENDIENTE',
            }
        )

    context = {
        'paciente_form':
            paciente_form,

        'destino_form':
            destino_form,

        'consulta_form':
            consulta_form,

        'estudio_form':
            estudio_form,
    }

    return render(
        request,
        'core/registrar_recepcion.html',
        context
    )
