from collections import Counter
import calendar
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path
import hashlib
import json
import logging
import secrets
import textwrap
from html.parser import HTMLParser
from urllib.parse import quote
from xml.sax.saxutils import escape

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.db.models import Count, Prefetch, Q, Sum
from django.db.models.functions import TruncMonth
from django.core.paginator import Paginator
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.html import strip_tags
from django.views.decorators.http import require_POST

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
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
    EntregaDigitalEstudio,
    EntregaResultadoEstudio,
    EliminacionSerieDicom,
    EstudioSolicitado,
    EquipoRadiologico,
    IndicacionMedica,
    InstanciaDicom,
    MedicamentoReceta,
    MembresiaInstitucion,
    MantenimientoEquipoRadiologico,
    PruebaControlCalidadEquipo,
    ReporteFallaEquipo,
    RegistroControlCalidadEquipo,
    SeguimientoFallaEquipo,
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
            # ReportLab trata ``br`` como una etiqueta XML vacía. Aunque
            # ``<br>`` es válido en HTML, su parser exige ``<br/>`` y puede
            # lanzar "No content allowed in br tag" al generar el PDF.
            if tag == 'br':
                self.partes.append('<br/>')
            else:
                self.partes.append(f'<{tag}>')

    def handle_startendtag(self, tag, attrs):
        if tag in self.etiquetas_permitidas:
            self.partes.append('<br/>' if tag == 'br' else f'<{tag}/>')

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


def decimal_dicom(dataset, nombre):
    """Convierte un valor numérico DICOM sin fallar con MultiValue o texto."""
    valor = getattr(dataset, nombre, None)
    if valor in (None, ''):
        return None
    if isinstance(valor, (list, tuple)):
        valor = valor[0] if valor else None
    try:
        return float(str(valor).split('\\')[0].strip())
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
        'kvp': decimal_dicom(dataset, 'KVP'),
        'exposure_mas': decimal_dicom(dataset, 'Exposure'),
        'exposure_uas': decimal_dicom(dataset, 'ExposureInuAs'),
        'exposure_time_ms': decimal_dicom(dataset, 'ExposureTime'),
        'xray_tube_current_ma': decimal_dicom(dataset, 'XRayTubeCurrent'),
        'view_position': valor_dicom(dataset, 'ViewPosition'),
        'ctdi_vol': decimal_dicom(dataset, 'CTDIvol'),
        # Algunos equipos/RDSR exponen DLP mediante este keyword; si no existe,
        # queda vacío y se solicita únicamente al finalizar.
        'dlp': decimal_dicom(dataset, 'DoseLengthProduct'),
        'contrast_agent': valor_dicom(dataset, 'ContrastBolusAgent'),
        'contrast_route': valor_dicom(dataset, 'ContrastBolusRoute'),
        'contrast_volume_ml': decimal_dicom(dataset, 'ContrastBolusVolume'),
        'accession_number': valor_dicom(dataset, 'AccessionNumber'),
        'referring_physician': valor_dicom(dataset, 'ReferringPhysicianName'),
        'sop_class_uid': valor_dicom(dataset, 'SOPClassUID'),
        'transfer_syntax_uid': transfer_syntax,
    }
    archivo.seek(0)
    return {'dataset': dataset, 'hash_sha256': digest.hexdigest(), 'tamano_bytes': tamano, 'metadatos': metadatos, **requeridos}


def _numero_metadato(valor):
    try:
        return float(valor) if valor not in (None, '') else None
    except (TypeError, ValueError):
        return None


def _representativo(valores):
    """Devuelve el valor más frecuente, sin inventar promedios clínicos."""
    limpios = [round(valor, 3) for valor in valores if valor is not None]
    return Counter(limpios).most_common(1)[0][0] if limpios else None


def sincronizar_bitacora_desde_dicom(estudio):
    """Completa campos vacíos usando solo encabezados ya guardados, nunca píxeles."""
    consulta_metadatos = InstanciaDicom.objects.filter(
        serie__estudio_dicom__estudio=estudio
    ).values_list('metadatos', flat=True)
    if not consulta_metadatos.exists():
        bitacora = crear_bitacora_radiologica(estudio)
        if bitacora is None:
            return None
        aplicados = []
        if not bitacora.numero_exposiciones and estudio.tipo_estudio.numero_exposiciones_sugerido:
            bitacora.numero_exposiciones = estudio.tipo_estudio.numero_exposiciones_sugerido
            aplicados.append('numero_exposiciones')
        if not bitacora.proyecciones and estudio.tipo_estudio.proyecciones_sugeridas:
            bitacora.proyecciones = estudio.tipo_estudio.proyecciones_sugeridas
            aplicados.append('proyecciones')
        if aplicados:
            bitacora.origen_parametros = 'PLANTILLA'
            bitacora.parametros_dicom = {
                'instancias_analizadas': 0,
                'plantilla_tipo_estudio': estudio.tipo_estudio.nombre,
                'campos_aplicados': aplicados,
            }
            bitacora.parametros_extraidos_el = timezone.now()
            bitacora.save()
        return bitacora

    bitacora = crear_bitacora_radiologica(estudio)
    if bitacora is None:
        return None

    kvps = [_numero_metadato(item.get('kvp')) for item in metadatos]
    mas = []
    ctdis = []
    dlps = []
    proyecciones = []
    agentes = []
    vias = []
    volumenes = []
    modalidades = []
    cantidad_instancias = 0

    for item in consulta_metadatos.iterator(chunk_size=250):
        cantidad_instancias += 1
        valor_mas = _numero_metadato(item.get('exposure_mas'))
        if valor_mas is None:
            uas = _numero_metadato(item.get('exposure_uas'))
            valor_mas = uas / 1000 if uas is not None else None
        if valor_mas is None:
            tiempo = _numero_metadato(item.get('exposure_time_ms'))
            corriente = _numero_metadato(item.get('xray_tube_current_ma'))
            if tiempo is not None and corriente is not None:
                valor_mas = tiempo * corriente / 1000
        mas.append(valor_mas)
        ctdis.append(_numero_metadato(item.get('ctdi_vol')))
        dlps.append(_numero_metadato(item.get('dlp')))
        modalidades.append((item.get('modality') or '').upper())
        for candidato in (item.get('view_position'), item.get('series_description')):
            texto = (candidato or '').strip()
            if texto and texto not in proyecciones:
                proyecciones.append(texto)
        for destino, clave in ((agentes, 'contrast_agent'), (vias, 'contrast_route')):
            texto = (item.get(clave) or '').strip()
            if texto and texto not in destino:
                destino.append(texto)
        volumenes.append(_numero_metadato(item.get('contrast_volume_ml')))

    modalidad_rx = bitacora.modalidad in {'RX', 'MASTO', 'DXA'} or any(
        valor in {'CR', 'DX', 'RX', 'MG'} for valor in modalidades
    )
    detectados = {
        'kvp': _representativo(kvps),
        'mas': _representativo(mas),
        'numero_exposiciones': cantidad_instancias if modalidad_rx else None,
        'proyecciones': ', '.join(proyecciones[:12]) or None,
        'ctdi_vol': _representativo(ctdis),
        'dlp': _representativo(dlps),
        'contraste_nombre': ', '.join(agentes) or None,
        'contraste_via': ', '.join(vias) or None,
        'contraste_volumen_ml': _representativo(volumenes),
    }
    campos_plantilla = []
    if detectados['numero_exposiciones'] is None:
        detectados['numero_exposiciones'] = estudio.tipo_estudio.numero_exposiciones_sugerido
        if detectados['numero_exposiciones'] is not None:
            campos_plantilla.append('numero_exposiciones')
    if detectados['proyecciones'] is None:
        detectados['proyecciones'] = estudio.tipo_estudio.proyecciones_sugeridas or None
        if detectados['proyecciones'] is not None:
            campos_plantilla.append('proyecciones')
    if agentes or any(valor is not None for valor in volumenes):
        detectados['uso_contraste'] = True

    actualizados = []
    for campo, valor in detectados.items():
        if valor is not None and getattr(bitacora, campo) in (None, ''):
            setattr(bitacora, campo, valor)
            actualizados.append(campo)

    bitacora.parametros_dicom = {
        'instancias_analizadas': cantidad_instancias,
        'valores_kvp': sorted({valor for valor in kvps if valor is not None}),
        'valores_mas': sorted({valor for valor in mas if valor is not None}),
        'valores_ctdi_vol': sorted({valor for valor in ctdis if valor is not None}),
        'valores_dlp': sorted({valor for valor in dlps if valor is not None}),
        'proyecciones_detectadas': proyecciones,
        'campos_desde_plantilla': campos_plantilla,
        'campos_aplicados': actualizados,
    }
    bitacora.parametros_extraidos_el = timezone.now()
    bitacora.origen_parametros = (
        'MIXTO'
        if campos_plantilla or bitacora.origen_parametros in {'MANUAL', 'MIXTO'}
        else 'DICOM'
    )
    bitacora.save()
    return bitacora


def crear_bitacora_radiologica(estudio):
    modalidad_original = (
        estudio.tipo_estudio.modalidad
    )

    modalidades_bitacora = {
        'RX': 'RX',
        'TAC': 'TAC',
        'FLUORO': 'FLUORO',
        'MASTO': 'MASTO',
        'USG': 'USG',
        'RM': 'RM',
        'DXA': 'DXA',
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

            if membresia.rol == 'MANTENIMIENTO':
                return redirect('equipos_incidencias_institucionales')

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
        'tipos_estudio': TipoEstudio.objects.filter(activo=True).order_by('modalidad', 'nombre'),
        'fallas_abiertas': ReporteFallaEquipo.objects.filter(
            institucion=institucion
        ).exclude(estado='CERRADA').count(),
    }

    return render(
        request,
        'core/panel_radiologo.html',
        context
    )


@login_required
@require_POST
def registrar_paciente_radiologia(request):
    membresia = obtener_membresia_usuario(request)
    if membresia is None or membresia.rol not in ['TECNICO', 'RADIOLOGIA', 'ADMIN']:
        return HttpResponse('No tienes permiso para registrar pacientes desde Radiología.', status=403)

    nombre = request.POST.get('nombre', '').strip().upper()
    apellido = request.POST.get('apellido', '').strip().upper()
    nacimiento_texto = request.POST.get('fecha_nacimiento', '').strip()
    genero = request.POST.get('genero', '').strip()
    telefono = request.POST.get('telefono', '').strip()
    medico = request.POST.get('medico_solicitante', '').strip()
    descripcion = request.POST.get('descripcion', '').strip()

    try:
        fecha_nacimiento = date.fromisoformat(nacimiento_texto)
    except ValueError:
        messages.error(request, 'Revisa la fecha de nacimiento.')
        return redirect('panel_radiologo')

    tipo_estudio = get_object_or_404(
        TipoEstudio,
        pk=request.POST.get('tipo_estudio'),
        activo=True,
    )
    if not nombre or not apellido or genero not in {'M', 'F', 'O'}:
        messages.error(request, 'Completa nombre, apellidos y género.')
        return redirect('panel_radiologo')

    coincidencias = Paciente.objects.filter(
        institucion=membresia.institucion,
        nombre__iexact=nombre,
        apellido__iexact=apellido,
        fecha_nacimiento=fecha_nacimiento,
    )
    if coincidencias.exists() and request.POST.get('confirmar_duplicado') != '1':
        registros = ', '.join(coincidencias.values_list('identificacion', flat=True)[:5])
        messages.warning(
            request,
            f'Posible duplicado: ya existe este nombre y fecha (registro {registros}). '
            'Búscalo primero o marca “crear aunque exista coincidencia”.'
        )
        return redirect(f"{reverse('panel_radiologo')}?q={quote(nombre)}")

    with transaction.atomic():
        paciente = Paciente.objects.create(
            institucion=membresia.institucion,
            nombre=nombre,
            apellido=apellido,
            fecha_nacimiento=fecha_nacimiento,
            genero=genero,
            telefono=telefono or None,
            creado_por=request.user,
            origen_registro='RADIOLOGIA',
        )
        estudio = Estudio.objects.create(
            paciente=paciente,
            tipo_estudio=tipo_estudio,
            medico_solicitante=medico or None,
            descripcion=descripcion or 'Paciente y estudio registrados desde Radiología.',
            estado='PENDIENTE',
        )

    messages.success(request, f'Paciente {paciente.identificacion} registrado. El estudio quedó en espera.')
    return redirect('estudio_radiologia', estudio_id=estudio.id)


@login_required
def equipos_incidencias_institucionales(request):
    """Ventanilla institucional para reportar y atender fallas de cualquier área."""
    membresia = obtener_membresia_usuario(request)
    if membresia is None or not membresia.activa:
        return redirect('panel_config')

    institucion = membresia.institucion
    puede_gestionar = request.user.is_superuser or membresia.rol in ['ADMIN', 'MANTENIMIENTO']
    equipos = EquipoRadiologico.objects.filter(
        institucion=institucion, activo=True
    ).order_by('area', 'nombre')

    if request.method == 'POST':
        accion = request.POST.get('accion', '')
        if accion == 'registrar_equipo':
            if not puede_gestionar:
                return HttpResponse('Solo Mantenimiento o Administración puede registrar equipos.', status=403)
            nombre = request.POST.get('nombre', '').strip()
            tipo = request.POST.get('tipo', '')
            area = request.POST.get('area', '')
            if not nombre or tipo not in dict(EquipoRadiologico.TIPO_CHOICES) or area not in dict(EquipoRadiologico.AREA_CHOICES):
                messages.error(request, 'Completa nombre, tipo y área con valores válidos.')
            else:
                EquipoRadiologico.objects.create(
                    institucion=institucion, nombre=nombre, tipo=tipo, area=area,
                    marca=request.POST.get('marca', '').strip() or None,
                    modelo=request.POST.get('modelo', '').strip() or None,
                    numero_serie=request.POST.get('numero_serie', '').strip() or None,
                    ubicacion=request.POST.get('ubicacion', '').strip() or None,
                )
                messages.success(request, 'Equipo institucional registrado.')
            return redirect('equipos_incidencias_institucionales')

        if accion == 'reportar':
            equipo = get_object_or_404(equipos, pk=request.POST.get('equipo'))
            titulo = request.POST.get('titulo', '').strip()
            descripcion = request.POST.get('descripcion', '').strip()
            prioridad = request.POST.get('prioridad', 'MEDIA')
            area = request.POST.get('area_reportada', equipo.area)
            evidencia = request.FILES.get('evidencia')
            if evidencia:
                extensiones = {'.jpg', '.jpeg', '.png', '.webp', '.pdf', '.doc', '.docx'}
                if evidencia.size > 10 * 1024 * 1024 or Path(evidencia.name).suffix.lower() not in extensiones:
                    messages.error(request, 'La evidencia debe ser imagen, PDF o Word y pesar máximo 10 MB.')
                    return redirect('equipos_incidencias_institucionales')
            if not titulo or not descripcion or prioridad not in dict(ReporteFallaEquipo.PRIORIDAD_CHOICES) or area not in dict(EquipoRadiologico.AREA_CHOICES):
                messages.error(request, 'Completa equipo, área, título, descripción y prioridad.')
                return redirect('equipos_incidencias_institucionales')
            falla = ReporteFallaEquipo.objects.create(
                institucion=institucion, equipo=equipo, area_reportada=area,
                ubicacion_reportada=request.POST.get('ubicacion_reportada', '').strip(),
                titulo=titulo, descripcion=descripcion, prioridad=prioridad,
                evidencia=evidencia, reportada_por=request.user,
            )
            SeguimientoFallaEquipo.objects.create(
                falla=falla, estado='REPORTADA',
                nota='Incidencia reportada y notificada a Mantenimiento y Administración.',
                registrado_por=request.user,
            )
            messages.success(request, f'Incidencia {falla.folio} registrada correctamente.')
            return redirect('equipos_incidencias_institucionales')

        if accion == 'seguimiento':
            if not puede_gestionar:
                return HttpResponse('Solo Mantenimiento o Administración puede gestionar incidencias.', status=403)
            falla = get_object_or_404(ReporteFallaEquipo, pk=request.POST.get('falla'), institucion=institucion)
            estado = request.POST.get('estado', '')
            nota = request.POST.get('nota', '').strip()
            if estado not in dict(ReporteFallaEquipo.ESTADO_CHOICES) or not nota:
                messages.error(request, 'Selecciona el estado y escribe la acción realizada.')
                return redirect('equipos_incidencias_institucionales')
            falla.estado = estado
            falla.asignada_a = request.user
            falla.cerrada_el = timezone.now() if estado == 'CERRADA' else None
            falla.save(update_fields=['estado', 'asignada_a', 'cerrada_el', 'actualizada_el'])
            if estado == 'FUERA_SERVICIO':
                falla.equipo.estado_operativo = 'FUERA_SERVICIO'
            elif estado == 'EN_REVISION':
                falla.equipo.estado_operativo = 'EN_REVISION'
            elif estado in ['RESUELTA', 'CERRADA'] and not ReporteFallaEquipo.objects.filter(
                equipo=falla.equipo
            ).exclude(pk=falla.pk).exclude(estado__in=['RESUELTA', 'CERRADA']).exists():
                falla.equipo.estado_operativo = 'OPERATIVO'
            falla.equipo.save(update_fields=['estado_operativo'])
            SeguimientoFallaEquipo.objects.create(
                falla=falla, estado=estado, nota=nota, registrado_por=request.user
            )
            messages.success(request, f'Seguimiento de {falla.folio} guardado.')
            return redirect('equipos_incidencias_institucionales')

    incidencias = ReporteFallaEquipo.objects.filter(institucion=institucion)
    area_filtro = request.GET.get('area', '').strip()
    estado_filtro = request.GET.get('estado', '').strip()
    prioridad_filtro = request.GET.get('prioridad', '').strip()
    if area_filtro in dict(EquipoRadiologico.AREA_CHOICES):
        incidencias = incidencias.filter(area_reportada=area_filtro)
    if estado_filtro in dict(ReporteFallaEquipo.ESTADO_CHOICES):
        incidencias = incidencias.filter(estado=estado_filtro)
    if prioridad_filtro in dict(ReporteFallaEquipo.PRIORIDAD_CHOICES):
        incidencias = incidencias.filter(prioridad=prioridad_filtro)

    regreso = {'MEDICO': 'panel_medico', 'RECEPCION': 'panel_recepcion',
               'RADIOLOGIA': 'panel_radiologo', 'TECNICO': 'panel_radiologo'}.get(membresia.rol, 'panel_config')
    return render(request, 'core/equipos_incidencias_institucionales.html', {
        'membresia': membresia, 'institucion': institucion, 'equipos': equipos,
        'incidencias': incidencias.select_related('equipo', 'reportada_por', 'asignada_a').prefetch_related('seguimientos')[:150],
        'areas': EquipoRadiologico.AREA_CHOICES, 'tipos_equipo': EquipoRadiologico.TIPO_CHOICES,
        'prioridades': ReporteFallaEquipo.PRIORIDAD_CHOICES, 'estados': ReporteFallaEquipo.ESTADO_CHOICES,
        'puede_gestionar': puede_gestionar, 'regreso': regreso,
        'area_filtro': area_filtro, 'estado_filtro': estado_filtro, 'prioridad_filtro': prioridad_filtro,
        'abiertas': ReporteFallaEquipo.objects.filter(institucion=institucion).exclude(estado__in=['RESUELTA', 'CERRADA']).count(),
        'criticas': ReporteFallaEquipo.objects.filter(institucion=institucion, prioridad='CRITICA').exclude(estado__in=['RESUELTA', 'CERRADA']).count(),
        'fuera_servicio': equipos.filter(estado_operativo='FUERA_SERVICIO').count(),
    })


@login_required
def mantenimiento_equipos_radiologia(request):
    membresia = obtener_membresia_usuario(request)
    if membresia is None or membresia.rol not in ['TECNICO', 'RADIOLOGIA', 'ADMIN', 'MANTENIMIENTO']:
        return redirect('panel_config')

    institucion = membresia.institucion
    equipos = EquipoRadiologico.objects.filter(
        Q(institucion=institucion) | Q(institucion__isnull=True)
    ).prefetch_related('mantenimientos', 'fallas').order_by('nombre')

    if request.method == 'POST':
        accion = request.POST.get('accion')
        if accion == 'equipo':
            nombre = request.POST.get('nombre', '').strip()
            tipo = request.POST.get('tipo', '')
            if not nombre or tipo not in dict(EquipoRadiologico.TIPO_CHOICES):
                messages.error(request, 'Completa el nombre y tipo del equipo.')
            else:
                EquipoRadiologico.objects.create(
                    institucion=institucion,
                    nombre=nombre,
                    tipo=tipo,
                    marca=request.POST.get('marca', '').strip() or None,
                    modelo=request.POST.get('modelo', '').strip() or None,
                    numero_serie=request.POST.get('numero_serie', '').strip() or None,
                    ubicacion=request.POST.get('ubicacion', '').strip() or None,
                )
                messages.success(request, 'Equipo registrado correctamente.')
        elif accion == 'mantenimiento':
            equipo = get_object_or_404(equipos, pk=request.POST.get('equipo'))
            tipo_mantenimiento = request.POST.get('tipo_mantenimiento', '')
            proveedor = request.POST.get('proveedor_ingeniero', '').strip()
            informe = request.POST.get('informe_servicio', '').strip()
            if tipo_mantenimiento not in dict(MantenimientoEquipoRadiologico.TIPO_CHOICES) or not proveedor or not informe:
                messages.error(request, 'Completa tipo, proveedor o ingeniero e informe del servicio.')
                return redirect('mantenimiento_equipos_radiologia')
            try:
                fecha_servicio = date.fromisoformat(request.POST.get('fecha_servicio', ''))
                proximo_texto = request.POST.get('proximo_mantenimiento', '').strip()
                proximo = date.fromisoformat(proximo_texto) if proximo_texto else None
            except ValueError:
                messages.error(request, 'Revisa las fechas del mantenimiento.')
                return redirect('mantenimiento_equipos_radiologia')
            MantenimientoEquipoRadiologico.objects.create(
                equipo=equipo,
                tipo=tipo_mantenimiento,
                fecha_servicio=fecha_servicio,
                proveedor_ingeniero=proveedor,
                informe_servicio=informe,
                proximo_mantenimiento=proximo,
                documento=request.FILES.get('documento'),
                registrado_por=request.user,
            )
            messages.success(request, 'Mantenimiento agregado a la bitácora del equipo.')
        elif accion == 'falla':
            equipo = get_object_or_404(equipos, pk=request.POST.get('equipo'))
            titulo = request.POST.get('titulo', '').strip()
            descripcion = request.POST.get('descripcion_falla', '').strip()
            prioridad = request.POST.get('prioridad', 'MEDIA')
            if not titulo or not descripcion or prioridad not in dict(ReporteFallaEquipo.PRIORIDAD_CHOICES):
                messages.error(request, 'Completa el título, descripción y prioridad de la falla.')
                return redirect('mantenimiento_equipos_radiologia')
            falla = ReporteFallaEquipo.objects.create(
                institucion=institucion, equipo=equipo, titulo=titulo,
                descripcion=descripcion, prioridad=prioridad, reportada_por=request.user,
            )
            SeguimientoFallaEquipo.objects.create(
                falla=falla, estado='REPORTADA', nota='Falla reportada y notificada al área de mantenimiento.', registrado_por=request.user,
            )
            messages.success(request, 'Falla reportada. El aviso quedó registrado con fecha y hora.')
        elif accion == 'seguimiento':
            if membresia.rol not in ['ADMIN', 'MANTENIMIENTO']:
                return HttpResponse('Solo Mantenimiento o Administración puede actualizar la atención.', status=403)
            falla = get_object_or_404(ReporteFallaEquipo, pk=request.POST.get('falla'), institucion=institucion)
            estado = request.POST.get('estado_falla', '')
            nota = request.POST.get('nota_seguimiento', '').strip()
            if estado not in dict(ReporteFallaEquipo.ESTADO_CHOICES) or not nota:
                messages.error(request, 'Selecciona el estado y escribe una nota de seguimiento.')
                return redirect('mantenimiento_equipos_radiologia')
            falla.estado = estado
            falla.asignada_a = request.user
            falla.cerrada_el = timezone.now() if estado == 'CERRADA' else None
            falla.save(update_fields=['estado', 'asignada_a', 'cerrada_el', 'actualizada_el'])
            if estado == 'FUERA_SERVICIO':
                falla.equipo.estado_operativo = 'FUERA_SERVICIO'
            elif estado == 'EN_REVISION':
                falla.equipo.estado_operativo = 'EN_REVISION'
            elif estado in ['RESUELTA', 'CERRADA']:
                hay_otras_activas = ReporteFallaEquipo.objects.filter(
                    equipo=falla.equipo
                ).exclude(pk=falla.pk).exclude(estado__in=['RESUELTA', 'CERRADA']).exists()
                if not hay_otras_activas:
                    falla.equipo.estado_operativo = 'OPERATIVO'
            falla.equipo.save(update_fields=['estado_operativo'])
            SeguimientoFallaEquipo.objects.create(
                falla=falla, estado=estado, nota=nota, registrado_por=request.user,
            )
            messages.success(request, 'Seguimiento guardado en el historial de la falla.')
        elif accion == 'estado_equipo':
            if membresia.rol not in ['ADMIN', 'MANTENIMIENTO']:
                return HttpResponse('Solo Mantenimiento o Administración puede cambiar el estado del equipo.', status=403)
            equipo = get_object_or_404(equipos, pk=request.POST.get('equipo'))
            estado_equipo = request.POST.get('estado_operativo', '')
            if estado_equipo not in dict(EquipoRadiologico.ESTADO_OPERATIVO_CHOICES):
                messages.error(request, 'Selecciona un estado operativo válido.')
                return redirect('mantenimiento_equipos_radiologia')
            equipo.estado_operativo = estado_equipo
            equipo.save(update_fields=['estado_operativo'])
            messages.success(request, f'Estado de {equipo.nombre} actualizado.')
        return redirect('mantenimiento_equipos_radiologia')

    fallas = ReporteFallaEquipo.objects.filter(institucion=institucion)
    filtro_equipo = request.GET.get('equipo', '').strip()
    filtro_estado = request.GET.get('estado', '').strip()
    filtro_prioridad = request.GET.get('prioridad', '').strip()
    if filtro_equipo.isdigit():
        fallas = fallas.filter(equipo_id=filtro_equipo)
    if filtro_estado in dict(ReporteFallaEquipo.ESTADO_CHOICES):
        fallas = fallas.filter(estado=filtro_estado)
    if filtro_prioridad in dict(ReporteFallaEquipo.PRIORIDAD_CHOICES):
        fallas = fallas.filter(prioridad=filtro_prioridad)

    hoy = timezone.localdate()
    alertas = []
    for equipo in equipos:
        if equipo.estado_operativo != 'OPERATIVO':
            alertas.append({'nivel': 'danger' if equipo.estado_operativo == 'FUERA_SERVICIO' else 'warning', 'texto': f'{equipo.nombre}: {equipo.get_estado_operativo_display()}.'})
        ultimo = equipo.mantenimientos.all()[0] if equipo.mantenimientos.all() else None
        if ultimo and ultimo.proximo_mantenimiento:
            dias = (ultimo.proximo_mantenimiento - hoy).days
            if dias < 0:
                alertas.append({'nivel': 'danger', 'texto': f'{equipo.nombre}: mantenimiento vencido hace {abs(dias)} día(s).'})
            elif dias <= 30:
                alertas.append({'nivel': 'warning', 'texto': f'{equipo.nombre}: mantenimiento programado en {dias} día(s).'})

    pruebas_por_vencer = PruebaControlCalidadEquipo.objects.filter(
        institucion=institucion,
        activa=True,
        proxima_fecha__lte=hoy + timedelta(days=30),
    ).select_related('equipo').order_by('proxima_fecha')[:20]
    for prueba in pruebas_por_vencer:
        dias = (prueba.proxima_fecha - hoy).days
        if dias < 0:
            texto = f'{prueba.equipo.nombre}: prueba “{prueba.nombre}” vencida hace {abs(dias)} día(s).'
            nivel = 'danger'
        else:
            texto = f'{prueba.equipo.nombre}: prueba “{prueba.nombre}” programada en {dias} día(s).'
            nivel = 'warning'
        alertas.append({'nivel': nivel, 'texto': texto})

    return render(request, 'core/mantenimiento_equipos_radiologia.html', {
        'membresia': membresia,
        'equipos': equipos,
        'tipos_equipo': EquipoRadiologico.TIPO_CHOICES,
        'tipos_mantenimiento': MantenimientoEquipoRadiologico.TIPO_CHOICES,
        'fallas': fallas.select_related(
            'equipo', 'reportada_por', 'asignada_a'
        ).prefetch_related('seguimientos')[:100],
        'estados_falla': ReporteFallaEquipo.ESTADO_CHOICES,
        'prioridades_falla': ReporteFallaEquipo.PRIORIDAD_CHOICES,
        'puede_gestionar_fallas': membresia.rol in ['ADMIN', 'MANTENIMIENTO'],
        'estados_operativos': EquipoRadiologico.ESTADO_OPERATIVO_CHOICES,
        'alertas': alertas,
        'filtro_equipo': filtro_equipo,
        'filtro_estado': filtro_estado,
        'filtro_prioridad': filtro_prioridad,
    })


@login_required
def bitacora_mantenimiento_pdf(request):
    membresia = obtener_membresia_usuario(request)
    if membresia is None or membresia.rol not in ['TECNICO', 'RADIOLOGIA', 'ADMIN', 'MANTENIMIENTO']:
        return HttpResponse('No tienes permiso para consultar esta bitácora.', status=403)

    institucion = membresia.institucion
    equipos = EquipoRadiologico.objects.filter(
        Q(institucion=institucion) | Q(institucion__isnull=True)
    ).prefetch_related('mantenimientos', 'fallas__seguimientos').order_by('nombre')
    respuesta = HttpResponse(content_type='application/pdf')
    respuesta['Content-Disposition'] = 'inline; filename="bitacora_equipos_mantenimiento.pdf"'
    lienzo = pdf_canvas.Canvas(respuesta, pagesize=letter)
    ancho, alto = letter

    def encabezado():
        y = alto - 45
        if institucion.logo:
            try:
                with institucion.logo.storage.open(institucion.logo.name, 'rb') as archivo_logo:
                    logo = ImageReader(BytesIO(archivo_logo.read()))
                lienzo.drawImage(logo, 42, alto - 82, width=55, height=42, preserveAspectRatio=True, mask='auto')
            except Exception:
                logger.exception('No fue posible cargar el logo en la bitácora de mantenimiento.')
        lienzo.setFont('Helvetica-Bold', 15)
        lienzo.drawString(110, y, institucion.nombre_comercial or institucion.nombre)
        lienzo.setFont('Helvetica', 8)
        lienzo.drawString(110, y - 14, institucion.direccion or 'Dirección no especificada')
        lienzo.drawString(110, y - 26, f'Teléfono: {institucion.telefono or "No especificado"}')
        lienzo.line(42, alto - 92, ancho - 42, alto - 92)
        lienzo.setFont('Helvetica-Bold', 13)
        lienzo.drawString(42, alto - 115, 'BITÁCORA DE EQUIPOS, MANTENIMIENTO E INCIDENCIAS')
        lienzo.setFont('Helvetica', 8)
        lienzo.drawRightString(ancho - 42, alto - 115, timezone.localtime().strftime('Generada: %d/%m/%Y %H:%M'))
        return alto - 138

    y = encabezado()
    for equipo in equipos:
        if y < 120:
            lienzo.showPage(); y = encabezado()
        lienzo.setFont('Helvetica-Bold', 11)
        lienzo.drawString(42, y, f'{equipo.nombre} — {equipo.get_estado_operativo_display()}')
        y -= 13
        lienzo.setFont('Helvetica', 8)
        datos = f'{equipo.get_tipo_display()} | Marca: {equipo.marca or "—"} | Modelo: {equipo.modelo or "—"} | Serie: {equipo.numero_serie or "—"} | Ubicación: {equipo.ubicacion or "—"}'
        for linea in textwrap.wrap(datos, 105):
            lienzo.drawString(50, y, linea); y -= 10
        for mantenimiento in equipo.mantenimientos.all():
            texto = f'MANTENIMIENTO {mantenimiento.fecha_servicio:%d/%m/%Y} · {mantenimiento.get_tipo_display()} · {mantenimiento.proveedor_ingeniero}. {mantenimiento.informe_servicio}'
            if mantenimiento.proximo_mantenimiento:
                texto += f' Próximo: {mantenimiento.proximo_mantenimiento:%d/%m/%Y}.'
            for indice, linea in enumerate(textwrap.wrap(texto, 100)):
                if y < 55:
                    lienzo.showPage(); y = encabezado()
                lienzo.setFont('Helvetica-Bold' if indice == 0 else 'Helvetica', 8)
                lienzo.drawString(58, y, linea); y -= 10
        for falla in equipo.fallas.all():
            texto = f'INCIDENCIA {timezone.localtime(falla.reportada_el):%d/%m/%Y %H:%M} · {falla.get_prioridad_display()} · {falla.get_estado_display()} · {falla.titulo}. {falla.descripcion}'
            for indice, linea in enumerate(textwrap.wrap(texto, 100)):
                if y < 55:
                    lienzo.showPage(); y = encabezado()
                lienzo.setFont('Helvetica-Bold' if indice == 0 else 'Helvetica', 8)
                lienzo.drawString(58, y, linea); y -= 10
            for paso in falla.seguimientos.all():
                detalle = f'  {timezone.localtime(paso.creado_el):%d/%m/%Y %H:%M} · {paso.get_estado_display()}: {paso.nota}'
                for linea in textwrap.wrap(detalle, 96):
                    lienzo.setFont('Helvetica', 7); lienzo.drawString(66, y, linea); y -= 9
        y -= 10
    lienzo.save()
    return respuesta


def _sumar_meses(fecha_base, meses):
    mes_indice = fecha_base.month - 1 + meses
    anio = fecha_base.year + mes_indice // 12
    mes = mes_indice % 12 + 1
    dia = min(fecha_base.day, calendar.monthrange(anio, mes)[1])
    return date(anio, mes, dia)


def _proxima_fecha_control(fecha_base, periodicidad):
    if periodicidad == 'DIARIA':
        return fecha_base + timedelta(days=1)
    if periodicidad == 'SEMANAL':
        return fecha_base + timedelta(days=7)
    meses = {'MENSUAL': 1, 'TRIMESTRAL': 3, 'SEMESTRAL': 6, 'ANUAL': 12}
    return _sumar_meses(fecha_base, meses.get(periodicidad, 1))


def _fecha_hora_local_control(valor):
    try:
        momento = datetime.fromisoformat((valor or '').strip())
    except (TypeError, ValueError):
        return timezone.now()
    if timezone.is_naive(momento):
        momento = timezone.make_aware(momento, timezone.get_current_timezone())
    return momento


@login_required
def control_calidad_equipos_radiologia(request):
    membresia = obtener_membresia_usuario(request)
    roles = ['TECNICO', 'RADIOLOGIA', 'ADMIN', 'MANTENIMIENTO']
    if membresia is None or membresia.rol not in roles:
        return HttpResponse('No tienes permiso para consultar control de calidad.', status=403)
    institucion = membresia.institucion
    equipos = EquipoRadiologico.objects.filter(
        Q(institucion=institucion) | Q(institucion__isnull=True), activo=True
    ).order_by('nombre')

    if request.method == 'POST':
        accion = request.POST.get('accion')
        if accion == 'crear_prueba':
            equipo = get_object_or_404(equipos, pk=request.POST.get('equipo'))
            nombre = request.POST.get('nombre', '').strip()
            periodicidad = request.POST.get('periodicidad', '')
            tolerancia = request.POST.get('tolerancia', '').strip()
            try:
                proxima_fecha = date.fromisoformat(request.POST.get('proxima_fecha', ''))
            except ValueError:
                proxima_fecha = None
            if not nombre or periodicidad not in dict(PruebaControlCalidadEquipo.PERIODICIDAD_CHOICES) or not tolerancia or not proxima_fecha:
                messages.error(request, 'Completa equipo, prueba, periodicidad, tolerancia y primera fecha.')
            elif PruebaControlCalidadEquipo.objects.filter(
                institucion=institucion, equipo=equipo, nombre__iexact=nombre
            ).exists():
                messages.error(request, 'Ese equipo ya tiene una prueba con el mismo nombre.')
            else:
                PruebaControlCalidadEquipo.objects.create(
                    institucion=institucion,
                    equipo=equipo,
                    nombre=nombre,
                    descripcion=request.POST.get('descripcion', '').strip(),
                    periodicidad=periodicidad,
                    tolerancia=tolerancia,
                    unidad=request.POST.get('unidad', '').strip(),
                    proxima_fecha=proxima_fecha,
                    creado_por=request.user,
                )
                messages.success(request, 'Prueba de control de calidad programada.')

        elif accion == 'registrar_resultado':
            prueba = get_object_or_404(
                PruebaControlCalidadEquipo.objects.select_related('equipo'),
                pk=request.POST.get('prueba'),
                institucion=institucion,
                activa=True,
            )
            resultado = request.POST.get('resultado', '')
            observaciones = request.POST.get('observaciones', '').strip()
            if resultado not in dict(RegistroControlCalidadEquipo.RESULTADO_CHOICES):
                messages.error(request, 'Selecciona un resultado válido.')
                return redirect('control_calidad_equipos_radiologia')
            if resultado != 'APROBADO' and not observaciones:
                messages.error(request, 'Describe las observaciones o la causa del resultado.')
                return redirect('control_calidad_equipos_radiologia')
            evidencia = request.FILES.get('evidencia')
            if evidencia:
                extension = Path(evidencia.name).suffix.lower()
                permitidas = {'.pdf', '.jpg', '.jpeg', '.png', '.webp', '.doc', '.docx'}
                if extension not in permitidas or evidencia.size > 10 * 1024 * 1024:
                    messages.error(request, 'La evidencia debe ser PDF, imagen o Word y pesar máximo 10 MB.')
                    return redirect('control_calidad_equipos_radiologia')
            realizado_el = _fecha_hora_local_control(request.POST.get('realizado_el'))
            proxima_fecha = _proxima_fecha_control(
                timezone.localtime(realizado_el).date(), prueba.periodicidad
            )
            with transaction.atomic():
                registro = RegistroControlCalidadEquipo.objects.create(
                    prueba=prueba,
                    realizado_el=realizado_el,
                    valor_obtenido=request.POST.get('valor_obtenido', '').strip(),
                    unidad_aplicada=prueba.unidad,
                    tolerancia_aplicada=prueba.tolerancia,
                    resultado=resultado,
                    observaciones=observaciones,
                    evidencia=evidencia,
                    proxima_fecha_calculada=proxima_fecha,
                    realizado_por=request.user,
                )
                prueba.proxima_fecha = proxima_fecha
                prueba.save(update_fields=['proxima_fecha', 'actualizado_el'])
                if resultado == 'FUERA_TOLERANCIA':
                    falla = ReporteFallaEquipo.objects.create(
                        institucion=institucion,
                        equipo=prueba.equipo,
                        titulo=f'Control de calidad fuera de tolerancia: {prueba.nombre}',
                        descripcion=(
                            f'Tolerancia aplicada: {prueba.tolerancia}. '
                            f'Valor obtenido: {registro.valor_obtenido or "No especificado"} '
                            f'{prueba.unidad or ""}. Observaciones: {observaciones}'
                        ),
                        prioridad='ALTA',
                        reportada_por=request.user,
                    )
                    SeguimientoFallaEquipo.objects.create(
                        falla=falla,
                        estado='REPORTADA',
                        nota='Incidencia generada automáticamente por control de calidad fuera de tolerancia.',
                        registrado_por=request.user,
                    )
                    registro.falla_generada = falla
                    registro.save(update_fields=['falla_generada'])
                    if prueba.equipo.estado_operativo == 'OPERATIVO':
                        prueba.equipo.estado_operativo = 'OBSERVACION'
                        prueba.equipo.save(update_fields=['estado_operativo'])
            messages.success(
                request,
                'Resultado registrado.' + (
                    ' Se abrió una incidencia para Mantenimiento.'
                    if resultado == 'FUERA_TOLERANCIA' else ''
                )
            )
        return redirect('control_calidad_equipos_radiologia')

    filtro_equipo = request.GET.get('equipo', '').strip()
    filtro_estado = request.GET.get('estado', '').strip()
    filtro_desde = request.GET.get('desde', '').strip()
    filtro_hasta = request.GET.get('hasta', '').strip()
    pruebas_qs = PruebaControlCalidadEquipo.objects.filter(
        institucion=institucion, activa=True
    ).select_related('equipo', 'creado_por').prefetch_related('registros__realizado_por')
    if filtro_equipo.isdigit():
        pruebas_qs = pruebas_qs.filter(equipo_id=filtro_equipo)

    hoy = timezone.localdate()
    pruebas = []
    vencidas = proximas = vigentes = 0
    for prueba in pruebas_qs:
        dias = (prueba.proxima_fecha - hoy).days
        ultimo = prueba.registros.all()[0] if prueba.registros.all() else None
        if dias < 0:
            estado_programacion, etiqueta = 'VENCIDA', f'Vencida hace {abs(dias)} día(s)'
            vencidas += 1
        elif dias <= 30:
            estado_programacion, etiqueta = 'PROXIMA', 'Hoy' if dias == 0 else f'En {dias} día(s)'
            proximas += 1
        else:
            estado_programacion, etiqueta = 'VIGENTE', f'En {dias} día(s)'
            vigentes += 1
        prueba.estado_programacion = estado_programacion
        prueba.etiqueta_programacion = etiqueta
        prueba.ultimo_registro = ultimo
        if not filtro_estado or filtro_estado == estado_programacion:
            pruebas.append(prueba)

    registros = RegistroControlCalidadEquipo.objects.filter(
        prueba__institucion=institucion
    ).select_related('prueba', 'prueba__equipo', 'realizado_por', 'falla_generada')
    if filtro_equipo.isdigit():
        registros = registros.filter(prueba__equipo_id=filtro_equipo)
    desde_fecha = _fecha_filtro(filtro_desde, None)
    hasta_fecha = _fecha_filtro(filtro_hasta, None)
    if desde_fecha:
        registros = registros.filter(realizado_el__date__gte=desde_fecha)
    if hasta_fecha:
        registros = registros.filter(realizado_el__date__lte=hasta_fecha)

    return render(request, 'core/control_calidad_equipos_radiologia.html', {
        'membresia': membresia,
        'equipos': equipos,
        'pruebas': pruebas,
        'registros': registros[:100],
        'periodicidades': PruebaControlCalidadEquipo.PERIODICIDAD_CHOICES,
        'resultados': RegistroControlCalidadEquipo.RESULTADO_CHOICES,
        'filtro_equipo': filtro_equipo,
        'filtro_estado': filtro_estado,
        'filtro_desde': filtro_desde,
        'filtro_hasta': filtro_hasta,
        'vencidas': vencidas,
        'proximas': proximas,
        'vigentes': vigentes,
        'hoy_local': timezone.localtime().strftime('%Y-%m-%dT%H:%M'),
    })


@login_required
def control_calidad_equipos_pdf(request):
    membresia = obtener_membresia_usuario(request)
    if membresia is None or membresia.rol not in ['TECNICO', 'RADIOLOGIA', 'ADMIN', 'MANTENIMIENTO']:
        return HttpResponse('No tienes permiso para consultar este informe.', status=403)
    institucion = membresia.institucion
    equipo_filtro = request.GET.get('equipo', '').strip()
    desde = request.GET.get('desde', '').strip()
    hasta = request.GET.get('hasta', '').strip()
    registros = RegistroControlCalidadEquipo.objects.filter(
        prueba__institucion=institucion
    ).select_related('prueba', 'prueba__equipo', 'realizado_por', 'falla_generada')
    if equipo_filtro.isdigit():
        registros = registros.filter(prueba__equipo_id=equipo_filtro)
    desde_fecha = _fecha_filtro(desde, None)
    hasta_fecha = _fecha_filtro(hasta, None)
    if desde_fecha:
        registros = registros.filter(realizado_el__date__gte=desde_fecha)
    if hasta_fecha:
        registros = registros.filter(realizado_el__date__lte=hasta_fecha)
    respuesta = HttpResponse(content_type='application/pdf')
    respuesta['Content-Disposition'] = 'inline; filename="control_calidad_equipos.pdf"'
    lienzo = pdf_canvas.Canvas(respuesta, pagesize=landscape(letter))
    ancho, alto = landscape(letter)

    def encabezado():
        y = alto - 35
        if institucion.logo:
            try:
                with institucion.logo.storage.open(institucion.logo.name, 'rb') as archivo_logo:
                    lienzo.drawImage(ImageReader(BytesIO(archivo_logo.read())), 35, alto - 67, 45, 34, preserveAspectRatio=True, mask='auto')
            except Exception:
                logger.exception('No fue posible cargar el logo en control de calidad.')
        lienzo.setFont('Helvetica-Bold', 13)
        lienzo.drawString(88, y, institucion.nombre_comercial or institucion.nombre)
        lienzo.setFont('Helvetica', 7)
        lienzo.drawString(88, y - 13, institucion.direccion or 'Dirección no especificada')
        lienzo.setFont('Helvetica-Bold', 11)
        lienzo.drawString(35, alto - 86, 'BITÁCORA DE CONTROL DE CALIDAD DE EQUIPOS')
        lienzo.setFont('Helvetica', 7)
        lienzo.drawRightString(ancho - 35, alto - 86, timezone.localtime().strftime('Generada: %d/%m/%Y %H:%M'))
        lienzo.line(35, alto - 93, ancho - 35, alto - 93)
        return alto - 111

    y = encabezado()
    for registro in registros[:1500]:
        if y < 70:
            lienzo.showPage(); y = encabezado()
        usuario = obtener_nombre_usuario(registro.realizado_por) or 'Usuario no disponible'
        lineas = [
            f'{timezone.localtime(registro.realizado_el):%d/%m/%Y %H:%M} · {registro.prueba.equipo.nombre} · {registro.prueba.nombre} · {registro.get_resultado_display()}',
            f'Valor: {registro.valor_obtenido or "—"} {registro.unidad_aplicada} | Tolerancia aplicada: {registro.tolerancia_aplicada} | Responsable: {usuario}',
            f'Observaciones: {registro.observaciones or "Sin observaciones"} | Próxima fecha: {registro.proxima_fecha_calculada:%d/%m/%Y}' + (' | Incidencia generada' if registro.falla_generada_id else ''),
        ]
        for indice, texto in enumerate(lineas):
            for linea in textwrap.wrap(texto, 125):
                if y < 45:
                    lienzo.showPage(); y = encabezado()
                lienzo.setFont('Helvetica-Bold' if indice == 0 else 'Helvetica', 7)
                lienzo.drawString(42 if indice == 0 else 50, y, linea); y -= 9
        lienzo.line(35, y, ancho - 35, y); y -= 9
    lienzo.save()
    return respuesta

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
        'entregas_resultado': estudio.entregas_resultado.select_related('registrado_por')[:10],
        'bitacora_operativa': BitacoraRadiologica.objects.filter(estudio=estudio).first(),
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
            if estudio.equipo and estudio.equipo.estado_operativo == 'FUERA_SERVICIO':
                messages.error(
                    request,
                    f'No se puede iniciar el estudio: {estudio.equipo.nombre} está fuera de servicio.'
                )
                return redirect('estudio_radiologia', estudio_id=estudio.id)
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
            sincronizar_bitacora_desde_dicom(estudio)
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

    perfil_usuario_actual = PerfilMedico.objects.filter(
        institucion=membresia.institucion,
        usuario=request.user,
        activo=True,
    ).first()
    puede_firmar_reporte = bool(
        perfil_usuario_actual
        and perfil_usuario_actual.cedula_profesional
        and perfil_usuario_actual.firma
        and membresia.rol in ['MEDICO', 'ADMIN']
    )
    reporte_esta_firmado = bool(
        reporte.estado == 'FINAL'
        and reporte.finalizado_por
        and perfil_reporte
        and perfil_reporte.cedula_profesional
        and perfil_reporte.firma
    )
    entregas_digitales = (
        estudio.entregas_digitales
        .select_related('creada_por', 'revocada_por')
        .order_by('-creada_el')[:20]
    )

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
            'puede_finalizar_reporte': puede_firmar_reporte,
            'puede_editar_reporte': reporte.estado != 'FINAL',
            'puede_reabrir_reporte': (
                reporte.estado == 'FINAL' and puede_firmar_reporte
            ),
            'reporte_esta_firmado': reporte_esta_firmado,
            'entregas_digitales': entregas_digitales,
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
    perfil_firmante = PerfilMedico.objects.filter(
        institucion=membresia.institucion,
        usuario=request.user,
        activo=True,
    ).first()
    puede_firmar = bool(
        perfil_firmante
        and perfil_firmante.cedula_profesional
        and perfil_firmante.firma
        and membresia.rol in ['MEDICO', 'ADMIN']
    )
    if finalizar and not puede_firmar:
        messages.error(
            request,
            'Para firmar el reporte se requiere un perfil médico activo con cédula y firma registradas.',
        )
        return redirect(destino)

    if accion == 'reabrir':
        if not puede_firmar:
            messages.error(
                request,
                'Se necesita un perfil médico activo con cédula profesional para editar un reporte final.',
            )
            return redirect(destino)
        with transaction.atomic():
            reporte = get_object_or_404(
                ReporteRadiologico.objects.select_for_update(),
                institucion=membresia.institucion,
                estudio=estudio,
            )
            RevisionReporteRadiologico.objects.get_or_create(
                reporte=reporte,
                version=reporte.version,
                defaults={
                    'estado': reporte.estado,
                    'hallazgos_html': reporte.hallazgos_html,
                    'impresion_html': reporte.impresion_html,
                    'modificado_por': request.user,
                    'datos_snapshot': reporte.datos_snapshot,
                },
            )
            reporte.version += 1
            reporte.estado = 'BORRADOR'
            reporte.finalizado_por = None
            reporte.finalizado_el = None
            reporte.save(update_fields=[
                'version', 'estado', 'finalizado_por',
                'finalizado_el', 'actualizado_el',
            ])
            estudio.estado_reporte = 'PRE_REPORTE'
            estudio.reporte_final_por = None
            estudio.fecha_reporte_final = None
            estudio.save(update_fields=[
                'estado_reporte', 'reporte_final_por',
                'fecha_reporte_final',
            ])
        messages.success(
            request,
            'El reporte quedó abierto para revisión médica. Deberá firmarse nuevamente.',
        )
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
            estudio.estado = 'COMPLETADO'
            if not estudio.fecha_finalizacion:
                estudio.fecha_finalizacion = reporte.finalizado_el
            estudio.save(update_fields=[
                'reporte_final', 'reporte_final_por',
                'fecha_reporte_final', 'estado_reporte',
                'estado', 'fecha_finalizacion',
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


def _parrafo_reporte_seguro(valor, estilo):
    """Crea un Paragraph sin permitir que HTML histórico rompa el PDF."""
    try:
        return Paragraph(_html_para_reportlab(valor), estilo)
    except (ValueError, TypeError):
        logger.exception(
            'Se corrigió contenido HTML incompatible al generar un reporte.'
        )
        texto = escape(texto_plano_reporte(valor) or '—')
        return Paragraph(texto.replace('\n', '<br/>'), estilo)


def _reporte_radiologico_pdf_enriquecido(
    request,
    estudio_id,
    institucion_autorizada=None,
):
    if institucion_autorizada is None:
        membresia = obtener_membresia_usuario(request)
        if membresia is None or membresia.rol not in [
            'TECNICO', 'RADIOLOGIA', 'MEDICO', 'ADMIN',
        ]:
            return redirect('panel_config')
        institucion_autorizada = membresia.institucion
    reporte = get_object_or_404(
        ReporteRadiologico.objects.select_related(
            'estudio__paciente', 'estudio__tipo_estudio',
            'institucion', 'finalizado_por', 'elaborado_por',
        ),
        estudio_id=estudio_id,
        institucion=institucion_autorizada,
    )
    estudio = reporte.estudio
    paciente = estudio.paciente
    institucion = reporte.institucion
    firmante = reporte.finalizado_por or reporte.elaborado_por
    perfil = PerfilMedico.objects.filter(
        institucion=institucion, usuario=firmante, activo=True,
    ).first() if firmante else None
    documento_firmado = bool(
        reporte.estado == 'FINAL'
        and firmante
        and perfil
        and perfil.cedula_profesional
        and perfil.firma
    )

    buffer = BytesIO()
    documento = SimpleDocTemplate(
        buffer, pagesize=letter, rightMargin=1.4 * cm, leftMargin=1.4 * cm,
        topMargin=1.0 * cm, bottomMargin=1.0 * cm,
        title='Reporte radiológico',
        author=(
            obtener_nombre_usuario(firmante)
            if documento_firmado else 'Loreto One'
        ),
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
            with campo.storage.open(campo.name, 'rb') as archivo_imagen:
                datos = archivo_imagen.read()
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
    ]], colWidths=[2.4 * cm, 9.8 * cm, 6.1 * cm])
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
        _parrafo_reporte_seguro(reporte.hallazgos_html, normal),
        Spacer(1, .65 * cm),
    ]
    if reporte.impresion_html:
        historia.extend([
            Paragraph('IMPRESIÓN DIAGNÓSTICA', subtitulo),
            _parrafo_reporte_seguro(reporte.impresion_html, normal),
            Spacer(1, .25 * cm),
        ])
    if documento_firmado:
        firma = imagen_campo(perfil.firma, 3.4 * cm, 1.05 * cm)
        firma_bloque = [firma or Spacer(1, .75 * cm)]
        firma_bloque.extend([
            Paragraph('_______________________________', centrado),
            Paragraph(f'<b>{escape(obtener_nombre_usuario(firmante))}</b>', centrado),
        ])
        datos_firma = []
        if perfil.especialidad:
            datos_firma.append(escape(perfil.especialidad))
        datos_firma.append('Céd. Prof. ' + escape(perfil.cedula_profesional))
        firma_bloque.append(Paragraph(' | '.join(datos_firma), centrado))
        tabla_firma = Table([['', firma_bloque, '']], colWidths=[5.1 * cm, 8.1 * cm, 5.1 * cm])
        tabla_firma.setStyle(TableStyle([('ALIGN', (1, 0), (1, 0), 'CENTER')]))
        historia.append(KeepTogether([tabla_firma]))
    else:
        historia.append(
            Paragraph('DOCUMENTO PENDIENTE DE FIRMA MÉDICA', centrado)
        )
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
            encabezado,
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
        if not documento_firmado:
            historia_respaldo.append(
                Paragraph('DOCUMENTO PENDIENTE DE FIRMA MÉDICA', centrado)
            )
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
    perfil = PerfilMedico.objects.filter(
        institucion=institucion,
        usuario=firmante,
        activo=True,
    ).first() if firmante else None
    documento_firmado = bool(
        reporte.estado == 'FINAL'
        and firmante
        and perfil
        and perfil.cedula_profesional
        and perfil.firma
    )
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
    if institucion.logo:
        try:
            with institucion.logo.storage.open(institucion.logo.name, 'rb') as archivo_logo:
                logo = ImageReader(BytesIO(archivo_logo.read()))
            lienzo.drawImage(
                logo,
                margen,
                y - 1.25 * cm,
                width=1.8 * cm,
                height=1.25 * cm,
                preserveAspectRatio=True,
                mask='auto',
            )
            y -= 1.35 * cm
        except Exception:
            logger.warning('No fue posible incluir el logo en el PDF de respaldo.')
    escribir(nombre_institucion, 14, True, 2)
    for dato in [
        institucion.direccion,
        'Tel. ' + institucion.telefono if institucion.telefono else '',
        institucion.email,
        institucion.horarios_servicio,
        'RFC: ' + institucion.rfc if institucion.rfc else '',
    ]:
        if dato:
            escribir(dato, 8, False, 1)
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
    if documento_firmado:
        if perfil.firma:
            try:
                with perfil.firma.storage.open(perfil.firma.name, 'rb') as archivo_firma:
                    firma = ImageReader(BytesIO(archivo_firma.read()))
                lienzo.drawImage(
                    firma,
                    margen,
                    y - 1.0 * cm,
                    width=3.4 * cm,
                    height=1.0 * cm,
                    preserveAspectRatio=True,
                    mask='auto',
                )
                y -= 1.1 * cm
            except Exception:
                logger.warning('No fue posible incluir la firma en el PDF de respaldo.')
        escribir('________________________________________', 9, False, 2)
        escribir(obtener_nombre_usuario(firmante), 9, True)
        escribir('Céd. Prof. ' + perfil.cedula_profesional, 8, False)
    else:
        escribir('DOCUMENTO PENDIENTE DE FIRMA MÉDICA', 8, True)
    lienzo.save()
    respuesta = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    disposicion = 'attachment' if request.GET.get('descargar') == '1' else 'inline'
    respuesta['Content-Disposition'] = (
        f'{disposicion}; filename="reporte_{paciente.identificacion}_{estudio.id}.pdf"'
    )
    return respuesta


def _sesion_entrega_valida(request, entrega):
    # El UUID funciona como credencial temporal (enlace llave). No se exige
    # una segunda clave para mantener el acceso sencillo para adultos mayores.
    return True


def _entrega_disponible(entrega):
    return bool(
        entrega.activa
        and (entrega.vence_el is None or entrega.vence_el > timezone.now())
        and entrega.bloqueada_el is None
        and entrega.estudio.estado == 'COMPLETADO'
        and entrega.estudio.reporte_radiologico.estado == 'FINAL'
    )


def _obtener_entrega_vigente(token):
    return get_object_or_404(
        EntregaDigitalEstudio.objects.select_related(
            'institucion', 'estudio__paciente', 'estudio__tipo_estudio',
            'estudio__reporte_radiologico',
        ),
        token=token,
    )


@login_required
@require_POST
def generar_entrega_digital_estudio(request, estudio_id):
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
    reporte = getattr(estudio, 'reporte_radiologico', None)
    if estudio.estado != 'COMPLETADO' or not reporte or reporte.estado != 'FINAL':
        messages.error(
            request,
            'La entrega digital requiere un estudio completado y un reporte firmado.',
        )
        return redirect('estudio_radiologia', estudio_id=estudio.id)
    vence_el = None
    if request.POST.get('usar_caducidad') == '1':
        try:
            dias = min(max(int(request.POST.get('vigencia_dias', 30)), 1), 3650)
        except (TypeError, ValueError):
            dias = 30
        vence_el = timezone.now() + timedelta(days=dias)
    telefono_original = request.POST.get('telefono_entrega') or estudio.paciente.telefono or ''
    destinatario = (
        request.POST.get('destinatario_entrega')
        or f'{estudio.paciente.nombre} {estudio.paciente.apellido}'
    ).strip()
    entrega = EntregaDigitalEstudio.objects.create(
        institucion=membresia.institucion,
        estudio=estudio,
        # Se conserva el campo por compatibilidad con la migración 0034,
        # pero el acceso actual se autoriza exclusivamente con el token UUID.
        codigo_hash=make_password(secrets.token_urlsafe(32)),
        vence_el=vence_el,
        destinatario=destinatario[:160],
        telefono_destino=''.join(c for c in telefono_original if c.isdigit())[:24],
        creada_por=request.user,
    )
    enlace = request.build_absolute_uri(
        reverse('entrega_digital_acceso', args=[entrega.token])
    )
    telefono = ''.join(
        caracter for caracter in (
            telefono_original
        )
        if caracter.isdigit()
    )
    if telefono and len(telefono) == 10:
        telefono = '52' + telefono
    mensaje = quote(
        f'Hola {estudio.paciente.nombre},\n\n'
        f'ya están disponibles las imágenes y el reporte de tu estudio '
        f'{estudio.tipo_estudio.nombre}, realizado en '
        f'{membresia.institucion.nombre_comercial or membresia.institucion.nombre}.\n\n'
        f'Para ver tus resultados abre este enlace:\n{enlace}\n\n'
        + (
            f'El enlace estará disponible hasta el {timezone.localtime(entrega.vence_el):%d/%m/%Y}. '
            if entrega.vence_el else
            'El enlace permanecerá disponible mientras la clínica no lo revoque. '
        )
        + 'No lo compartas con personas que no autorices.'
    )
    enlace_whatsapp = f'https://wa.me/{telefono}?text={mensaje}' if telefono else ''
    return render(request, 'core/entrega_digital_creada.html', {
        'entrega': entrega,
        'estudio': estudio,
        'enlace': enlace,
        'enlace_whatsapp': enlace_whatsapp,
    })


@login_required
@require_POST
def revocar_entrega_digital_estudio(request, entrega_id):
    membresia = obtener_membresia_usuario(request)
    if membresia is None or membresia.rol not in [
        'RADIOLOGIA', 'MEDICO', 'ADMIN',
    ]:
        return redirect('panel_config')
    entrega = get_object_or_404(
        EntregaDigitalEstudio,
        pk=entrega_id,
        institucion=membresia.institucion,
    )
    entrega.activa = False
    entrega.revocada_el = timezone.now()
    entrega.revocada_por = request.user
    entrega.save(update_fields=['activa', 'revocada_el', 'revocada_por'])
    messages.success(request, 'El enlace de entrega digital fue revocado.')
    return redirect('estudio_radiologia', estudio_id=entrega.estudio_id)


def entrega_digital_acceso(request, token):
    entrega = _obtener_entrega_vigente(token)
    if not _entrega_disponible(entrega):
        return render(request, 'core/entrega_digital_acceso.html', {
            'entrega': entrega,
            'disponible': False,
        }, status=410)
    entrega.accesos += 1
    entrega.ultimo_acceso_el = timezone.now()
    entrega.save(update_fields=['accesos', 'ultimo_acceso_el'])
    return redirect('entrega_digital_estudio', token=entrega.token)


def entrega_digital_estudio(request, token):
    entrega = _obtener_entrega_vigente(token)
    if not _entrega_disponible(entrega):
        return render(request, 'core/entrega_digital_acceso.html', {
            'entrega': entrega, 'disponible': False,
        }, status=410)
    series = []
    registro = EstudioDicom.objects.filter(estudio=entrega.estudio).first()
    if registro:
        for serie in registro.series.prefetch_related('instancias').all():
            imagenes = []
            for instancia in serie.instancias.all():
                total_frames = max(1, instancia.numero_frames or 1)
                for frame in range(total_frames):
                    url = reverse(
                        'entrega_digital_imagen',
                        args=[entrega.token, instancia.id],
                    )
                    if total_frames > 1:
                        url = f'{url}?frame={frame}'
                    imagenes.append({
                        'id': instancia.id,
                        'frame': frame,
                        'numero': instancia.numero_instancia,
                        'url': url,
                        'medir_url': reverse(
                            'entrega_digital_medir',
                            args=[entrega.token, instancia.id],
                        ),
                        'fotometria': instancia.interpretacion_fotometrica or '',
                    })
            if imagenes:
                series.append({
                    'nombre': serie.descripcion or 'Serie sin descripción',
                    'modalidad': serie.modalidad or 'DICOM',
                    'imagenes': imagenes,
                })
    return render(request, 'core/entrega_digital_estudio.html', {
        'entrega': entrega,
        'estudio': entrega.estudio,
        'paciente': entrega.estudio.paciente,
        'reporte': entrega.estudio.reporte_radiologico,
        'series': series,
    })


def entrega_digital_reporte_pdf(request, token):
    entrega = _obtener_entrega_vigente(token)
    if not _entrega_disponible(entrega):
        return HttpResponse('Este enlace ya no está disponible.', status=410)
    return _reporte_radiologico_pdf_enriquecido(
        request,
        entrega.estudio_id,
        institucion_autorizada=entrega.institucion,
    )


def entrega_digital_imagen(request, token, instancia_id):
    entrega = _obtener_entrega_vigente(token)
    if not _entrega_disponible(entrega):
        return HttpResponse(status=403)
    instancia = get_object_or_404(
        InstanciaDicom.objects.select_related('archivo_estudio'),
        pk=instancia_id,
        archivo_estudio__estudio=entrega.estudio,
        institucion=entrega.institucion,
    )
    try:
        with instancia.archivo_estudio.archivo.open('rb') as archivo:
            dataset = pydicom.dcmread(archivo)
            pixeles = dataset.pixel_array
        numero_frames = int(getattr(dataset, 'NumberOfFrames', 1) or 1)
        frame = max(0, min(int(request.GET.get('frame', 0)), numero_frames - 1))
        if numero_frames > 1:
            pixeles = pixeles[frame]
        muestras = int(getattr(dataset, 'SamplesPerPixel', 1) or 1)
        if muestras == 1:
            pixeles = apply_modality_lut(pixeles, dataset).astype(np.float64)
        minimo, maximo = float(np.nanmin(pixeles)), float(np.nanmax(pixeles))
        centro_dicom = getattr(dataset, 'WindowCenter', (minimo + maximo) / 2)
        ancho_dicom = getattr(dataset, 'WindowWidth', max(maximo - minimo, 1.0))
        if hasattr(centro_dicom, '__iter__') and not isinstance(centro_dicom, str):
            centro_dicom = centro_dicom[0]
        if hasattr(ancho_dicom, '__iter__') and not isinstance(ancho_dicom, str):
            ancho_dicom = ancho_dicom[0]
        centro = float(request.GET.get('wc', centro_dicom))
        ancho = max(float(request.GET.get('ww', ancho_dicom)), 1.0)
        inferior = centro - ancho / 2
        imagen_8bits = (
            np.clip((pixeles.astype(np.float64) - inferior) / ancho, 0, 1) * 255
        ).astype(np.uint8)
        if muestras == 1:
            if valor_dicom(dataset, 'PhotometricInterpretation') == 'MONOCHROME1':
                imagen_8bits = 255 - imagen_8bits
            imagen = PILImage.fromarray(imagen_8bits, mode='L')
        else:
            imagen = PILImage.fromarray(imagen_8bits)
        salida = BytesIO()
        imagen.save(salida, format='JPEG', quality=88, optimize=False)
        respuesta = HttpResponse(salida.getvalue(), content_type='image/jpeg')
        respuesta['Cache-Control'] = 'private, max-age=900'
        return respuesta
    except Exception as exc:
        logger.exception('No fue posible generar imagen de entrega. %s', exc)
        return HttpResponse('Imagen no disponible.', status=422)


@require_POST
def entrega_digital_medir(request, token, instancia_id):
    entrega = _obtener_entrega_vigente(token)
    if not _entrega_disponible(entrega):
        return JsonResponse({'error': 'Este enlace ya no está disponible.'}, status=403)
    instancia = get_object_or_404(
        InstanciaDicom.objects.select_related('archivo_estudio'),
        pk=instancia_id,
        archivo_estudio__estudio=entrega.estudio,
        institucion=entrega.institucion,
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
        espaciado = getattr(dataset, 'PixelSpacing', None) or getattr(
            dataset, 'ImagerPixelSpacing', None
        )
        fila_mm = float(espaciado[0]) if espaciado else None
        columna_mm = float(espaciado[1]) if espaciado else None

        def punto(indice):
            return (
                max(0.0, min(float(puntos[indice]['x']), columnas - 1)),
                max(0.0, min(float(puntos[indice]['y']), filas - 1)),
            )

        if herramienta == 'distancia' and len(puntos) == 2:
            x1, y1 = punto(0); x2, y2 = punto(1)
            if fila_mm is not None and columna_mm is not None:
                valor = (((x2-x1)*columna_mm)**2 + ((y2-y1)*fila_mm)**2) ** .5
                return JsonResponse({'valor': valor, 'unidad': 'mm', 'calibrada': True})
            return JsonResponse({
                'valor': ((x2-x1)**2 + (y2-y1)**2) ** .5,
                'unidad': 'px', 'calibrada': False,
            })
        if herramienta == 'roi' and len(puntos) == 2:
            if int(getattr(dataset, 'SamplesPerPixel', 1) or 1) != 1:
                return JsonResponse({'error': 'La ROI requiere una imagen monocromática.'}, status=422)
            pixeles = dataset.pixel_array
            total_frames = int(getattr(dataset, 'NumberOfFrames', 1) or 1)
            if total_frames > 1:
                pixeles = pixeles[min(frame, total_frames - 1)]
            x1, y1 = punto(0); x2, y2 = punto(1)
            izquierda, derecha = sorted((int(round(x1)), int(round(x2))))
            arriba, abajo = sorted((int(round(y1)), int(round(y2))))
            valores = apply_modality_lut(pixeles, dataset).astype(np.float64)[
                arriba:max(abajo + 1, arriba + 1),
                izquierda:max(derecha + 1, izquierda + 1),
            ]
            modalidad = valor_dicom(dataset, 'Modality').upper()
            es_hu = modalidad == 'CT' and hasattr(dataset, 'RescaleSlope')
            return JsonResponse({
                'promedio': float(np.mean(valores)), 'minimo': float(np.min(valores)),
                'maximo': float(np.max(valores)), 'desviacion': float(np.std(valores)),
                'unidad': 'HU' if es_hu else 'valor de píxel',
            })
        return JsonResponse({'error': 'Medición no válida.'}, status=400)
    except Exception as exc:
        logger.exception('Error en medición pública DICOM. %s', exc)
        return JsonResponse({'error': 'No fue posible calcular la medición.'}, status=422)


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
        # La compresión baja reduce considerablemente el uso de CPU durante
        # cine y navegación rápida por series, sin alterar los píxeles.
        imagen.save(salida, format='PNG', optimize=False, compress_level=1)
        respuesta = HttpResponse(salida.getvalue(), content_type='image/png')
        respuesta['Cache-Control'] = 'private, max-age=900'
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

        bitacora = sincronizar_bitacora_desde_dicom(estudio)
        if bitacora:
            bitacora.fecha_realizacion = momento_actual
            repeticiones = multi_puesto(request, 'numero_repeticiones_rapido')
            incidencias = request.POST.get('incidencias_rapidas', '').strip()
            medio = request.POST.get('medio_entrega_rapido', 'PENDIENTE')
            if medio not in dict(BitacoraRadiologica.MEDIO_ENTREGA_CHOICES):
                medio = 'PENDIENTE'
            bitacora.numero_repeticiones = repeticiones
            bitacora.incidencias = incidencias or None
            bitacora.medio_entrega = medio
            if repeticiones or incidencias:
                bitacora.origen_parametros = (
                    'MIXTO' if bitacora.parametros_dicom else 'MANUAL'
                )
            bitacora.actualizado_por = request.user
            bitacora.save()
            if medio != 'PENDIENTE':
                entrega = EntregaResultadoEstudio.objects.create(
                    estudio=estudio,
                    medio=medio,
                    observaciones='Registrada al finalizar el estudio.',
                    registrado_por=request.user,
                )
                bitacora.fecha_entrega = entrega.fecha_entrega
                bitacora.entrega_registrada_por = request.user
                bitacora.save(update_fields=['fecha_entrega', 'entrega_registrada_por'])

        return redirect(
            'panel_radiologo'
        )

    return redirect(
        'estudio_radiologia',
        estudio_id=estudio.id
    )


@login_required
@require_POST
def registrar_entrega_resultado_radiologia(request, estudio_id):
    membresia = obtener_membresia_usuario(request)
    if membresia is None or membresia.rol not in ['TECNICO', 'RADIOLOGIA', 'ADMIN']:
        return HttpResponse('No tienes permiso para registrar entregas.', status=403)

    estudio = get_object_or_404(
        Estudio.objects.select_related('paciente', 'tipo_estudio'),
        pk=estudio_id,
        paciente__institucion=membresia.institucion,
        estado='COMPLETADO',
    )
    medio = request.POST.get('medio', '')
    if medio not in dict(EntregaResultadoEstudio.MEDIO_CHOICES):
        messages.error(request, 'Selecciona cómo se entregó el resultado.')
        return redirect('estudio_radiologia', estudio_id=estudio.id)

    with transaction.atomic():
        entrega = EntregaResultadoEstudio.objects.create(
            estudio=estudio,
            medio=medio,
            entregado_a=request.POST.get('entregado_a', '').strip(),
            observaciones=request.POST.get('observaciones_entrega', '').strip(),
            registrado_por=request.user,
        )
        bitacora = crear_bitacora_radiologica(estudio)
        if bitacora:
            bitacora.medio_entrega = medio
            bitacora.fecha_entrega = entrega.fecha_entrega
            bitacora.entrega_registrada_por = request.user
            bitacora.save(update_fields=[
                'medio_entrega', 'fecha_entrega', 'entrega_registrada_por'
            ])

    messages.success(request, 'Entrega registrada en la bitácora radiológica.')
    return redirect('estudio_radiologia', estudio_id=estudio.id)


def _decimal_opcional(valor):
    texto = (valor or '').strip().replace(',', '.')
    if not texto:
        return None
    try:
        numero = Decimal(texto)
        return numero if numero >= 0 else None
    except InvalidOperation:
        return None


def multi_puesto(request, nombre):
    try:
        return max(0, int(request.POST.get(nombre, 0) or 0))
    except (TypeError, ValueError):
        return 0


@login_required
@require_POST
def guardar_bitacora_operativa_radiologia(request, estudio_id):
    membresia = obtener_membresia_usuario(request)
    if membresia is None or membresia.rol not in ['TECNICO', 'RADIOLOGIA', 'ADMIN']:
        return HttpResponse('No tienes permiso para modificar esta bitácora.', status=403)
    estudio = get_object_or_404(
        Estudio.objects.select_related('paciente', 'tipo_estudio', 'tecnico', 'equipo'),
        pk=estudio_id,
        paciente__institucion=membresia.institucion,
    )
    bitacora = crear_bitacora_radiologica(estudio)
    if bitacora is None:
        messages.error(request, 'No fue posible crear la bitácora de este estudio.')
        return redirect('estudio_radiologia', estudio_id=estudio.id)

    opcion_contraste = request.POST.get('uso_contraste', '')
    campos = {
        'kvp': _decimal_opcional(request.POST.get('kvp')),
        'mas': _decimal_opcional(request.POST.get('mas')),
        'numero_exposiciones': multi_puesto(request, 'numero_exposiciones') or None,
        'proyecciones': request.POST.get('proyecciones', '').strip() or None,
        'numero_imagenes_impresas': multi_puesto(request, 'numero_imagenes_impresas'),
        'numero_repeticiones': multi_puesto(request, 'numero_repeticiones'),
        'motivo_repeticion': request.POST.get('motivo_repeticion', '').strip() or None,
        'ctdi_vol': _decimal_opcional(request.POST.get('ctdi_vol')),
        'dlp': _decimal_opcional(request.POST.get('dlp')),
        'contraste_nombre': request.POST.get('contraste_nombre', '').strip() or None,
        'contraste_lote': request.POST.get('contraste_lote', '').strip() or None,
        'contraste_volumen_ml': _decimal_opcional(request.POST.get('contraste_volumen_ml')),
        'contraste_via': request.POST.get('contraste_via', '').strip() or None,
        'reaccion_contraste': request.POST.get('reaccion_contraste', '').strip() or None,
        'verificacion_embarazo': request.POST.get('verificacion_embarazo', 'NO_APLICA'),
        'proteccion_radiologica': request.POST.get('proteccion_radiologica', '').strip() or None,
        'incidencias': request.POST.get('incidencias', '').strip() or None,
        'observaciones': request.POST.get('observaciones_bitacora', '').strip() or None,
        'actualizado_por': request.user,
    }
    if campos['verificacion_embarazo'] not in {'NO_APLICA', 'DESCARTADO', 'POSIBLE'}:
        campos['verificacion_embarazo'] = 'NO_APLICA'
    if opcion_contraste in {'SI', 'NO'}:
        campos['uso_contraste'] = opcion_contraste == 'SI'
    for nombre, valor in campos.items():
        setattr(bitacora, nombre, valor)
    bitacora.origen_parametros = 'MIXTO' if bitacora.parametros_dicom else 'MANUAL'
    bitacora.save()
    messages.success(request, 'Bitácora operativa actualizada correctamente.')
    return redirect('estudio_radiologia', estudio_id=estudio.id)


def _bitacoras_filtradas(request, institucion):
    qs = BitacoraRadiologica.objects.select_related(
        'estudio', 'estudio__paciente', 'estudio__tipo_estudio', 'tecnico', 'equipo'
    ).filter(estudio__paciente__institucion=institucion)
    desde = request.GET.get('desde', '').strip()
    hasta = request.GET.get('hasta', '').strip()
    modalidad = request.GET.get('modalidad', '').strip()
    equipo = request.GET.get('equipo', '').strip()
    if desde:
        qs = qs.filter(fecha_realizacion__date__gte=desde)
    if hasta:
        qs = qs.filter(fecha_realizacion__date__lte=hasta)
    if modalidad in dict(BitacoraRadiologica.MODALIDAD_CHOICES):
        qs = qs.filter(modalidad=modalidad)
    if equipo.isdigit():
        qs = qs.filter(equipo_id=equipo)
    return qs, {'desde': desde, 'hasta': hasta, 'modalidad_filtro': modalidad, 'equipo_filtro': equipo}


@login_required
def bitacora_radiologica_panel(request):
    membresia = obtener_membresia_usuario(request)
    if membresia is None or membresia.rol not in ['TECNICO', 'RADIOLOGIA', 'ADMIN']:
        return HttpResponse('No tienes permiso para consultar esta bitácora.', status=403)
    bitacoras, filtros = _bitacoras_filtradas(request, membresia.institucion)
    return render(request, 'core/bitacora_radiologica_panel.html', {
        'bitacoras': bitacoras[:300],
        'equipos': EquipoRadiologico.objects.filter(Q(institucion=membresia.institucion) | Q(institucion__isnull=True)).order_by('nombre'),
        'modalidades': BitacoraRadiologica.MODALIDAD_CHOICES,
        **filtros,
    })


@login_required
def bitacora_radiologica_pdf(request):
    membresia = obtener_membresia_usuario(request)
    if membresia is None or membresia.rol not in ['TECNICO', 'RADIOLOGIA', 'ADMIN']:
        return HttpResponse('No tienes permiso para consultar esta bitácora.', status=403)
    institucion = membresia.institucion
    bitacoras, _ = _bitacoras_filtradas(request, institucion)
    respuesta = HttpResponse(content_type='application/pdf')
    respuesta['Content-Disposition'] = 'inline; filename="bitacora_radiologica.pdf"'
    lienzo = pdf_canvas.Canvas(respuesta, pagesize=letter)
    ancho, alto = letter

    def cabecera():
        y = alto - 42
        if institucion.logo:
            try:
                with institucion.logo.storage.open(institucion.logo.name, 'rb') as archivo_logo:
                    lienzo.drawImage(ImageReader(BytesIO(archivo_logo.read())), 42, alto - 80, 54, 40, preserveAspectRatio=True, mask='auto')
            except Exception:
                logger.exception('No fue posible cargar el logo en la bitácora radiológica.')
        lienzo.setFont('Helvetica-Bold', 14); lienzo.drawString(88, y, institucion.nombre_comercial or institucion.nombre)
        lienzo.setFont('Helvetica', 8); lienzo.drawString(88, y - 13, institucion.direccion or 'Dirección no especificada')
        lienzo.drawString(88, y - 25, f'Teléfono: {institucion.telefono or "No especificado"}')
        lienzo.line(42, alto - 88, ancho - 42, alto - 88)
        lienzo.setFont('Helvetica-Bold', 12); lienzo.drawString(42, alto - 108, 'BITÁCORA RADIOLÓGICA OPERATIVA')
        lienzo.setFont('Helvetica', 7); lienzo.drawRightString(ancho - 42, alto - 108, timezone.localtime().strftime('%d/%m/%Y %H:%M'))
        return alto - 130

    y = cabecera()
    for item in bitacoras[:1000]:
        lineas = [
            f'{timezone.localtime(item.fecha_realizacion):%d/%m/%Y %H:%M} · {item.modalidad} · {item.paciente_nombre} · Reg. {item.paciente_registro or "—"}',
            f'Estudio: {item.estudio_nombre} | Médico: {item.medico_solicitante or "—"} | Técnico: {item.tecnico_nombre or "—"} | Equipo: {item.equipo_nombre or "—"}',
            f'Parámetros: kVp {item.kvp or "—"}; mAs {item.mas or "—"}; exposiciones {item.numero_exposiciones or "—"}; CTDIvol {item.ctdi_vol or "—"}; DLP {item.dlp or "—"}; repeticiones {item.numero_repeticiones}.',
            f'Contraste: {"Sí" if item.uso_contraste else "No"}; {item.contraste_nombre or "—"}; lote {item.contraste_lote or "—"}; volumen {item.contraste_volumen_ml or "—"} ml. Entrega: {item.get_medio_entrega_display()}.',
        ]
        if item.incidencias:
            lineas.append(f'Incidencias: {item.incidencias}')
        for indice, texto in enumerate(lineas):
            for linea in textwrap.wrap(texto, 112):
                if y < 55:
                    lienzo.showPage(); y = cabecera()
                lienzo.setFont('Helvetica-Bold' if indice == 0 else 'Helvetica', 7)
                lienzo.drawString(46 if indice == 0 else 54, y, linea); y -= 9
        lienzo.line(42, y, ancho - 42, y); y -= 10
    lienzo.save()
    return respuesta


def _fecha_filtro(valor, predeterminada):
    try:
        return date.fromisoformat((valor or '').strip())
    except (TypeError, ValueError):
        return predeterminada


def _tasa_repeticion(repeticiones, exposiciones):
    if not exposiciones:
        return None
    return round((repeticiones or 0) * 100 / exposiciones, 2)


def _filas_repeticiones(consulta, campos, etiqueta):
    filas = list(
        consulta.values(*campos).annotate(
            estudios=Count('id'),
            exposiciones=Sum('numero_exposiciones'),
            repeticiones=Sum('numero_repeticiones'),
        ).order_by('-repeticiones', '-estudios')[:12]
    )
    maximo = max([fila['repeticiones'] or 0 for fila in filas] or [1])
    for fila in filas:
        fila['nombre'] = fila.get(etiqueta) or 'Sin especificar'
        fila['tasa'] = _tasa_repeticion(fila['repeticiones'], fila['exposiciones'])
        fila['barra'] = round((fila['repeticiones'] or 0) * 100 / maximo) if maximo else 0
    return filas


def _datos_analisis_repeticiones(request, institucion):
    hoy = timezone.localdate()
    inicio_mes = hoy.replace(day=1)
    desde = _fecha_filtro(request.GET.get('desde'), inicio_mes)
    hasta = _fecha_filtro(request.GET.get('hasta'), hoy)
    if desde > hasta:
        desde, hasta = hasta, desde

    equipo = (request.GET.get('equipo') or '').strip()
    tecnico = (request.GET.get('tecnico') or '').strip()
    modalidad = (request.GET.get('modalidad') or '').strip()
    tipo_estudio = (request.GET.get('tipo_estudio') or '').strip()

    consulta = BitacoraRadiologica.objects.filter(
        estudio__paciente__institucion=institucion,
        fecha_realizacion__date__range=(desde, hasta),
    )
    if equipo.isdigit():
        consulta = consulta.filter(equipo_id=equipo)
    if tecnico.isdigit():
        consulta = consulta.filter(tecnico_id=tecnico)
    if modalidad in dict(BitacoraRadiologica.MODALIDAD_CHOICES):
        consulta = consulta.filter(modalidad=modalidad)
    if tipo_estudio.isdigit():
        consulta = consulta.filter(estudio__tipo_estudio_id=tipo_estudio)

    totales = consulta.aggregate(
        total_estudios=Count('id'),
        total_exposiciones=Sum('numero_exposiciones'),
        total_repeticiones=Sum('numero_repeticiones'),
    )
    total_estudios = totales['total_estudios'] or 0
    total_exposiciones = totales['total_exposiciones'] or 0
    total_repeticiones = totales['total_repeticiones'] or 0
    afectados = consulta.filter(numero_repeticiones__gt=0).count()
    tasa = _tasa_repeticion(total_repeticiones, total_exposiciones)
    porcentaje_afectados = round(afectados * 100 / total_estudios, 2) if total_estudios else 0

    if tasa is None:
        estado = 'SIN_DATOS'
        estado_texto = 'Faltan exposiciones para calcular la tasa'
    elif total_exposiciones < 20:
        estado = 'MUESTRA_CORTA'
        estado_texto = 'Muestra pequeña: interpretar con precaución'
    elif tasa > 10:
        estado = 'ALTO'
        estado_texto = 'Tasa elevada: requiere revisión interna'
    elif tasa > 5:
        estado = 'ATENCION'
        estado_texto = 'Tasa por encima del objetivo interno'
    else:
        estado = 'CONTROLADO'
        estado_texto = 'Dentro del objetivo interno del 5 %'

    por_equipo = _filas_repeticiones(consulta, ['equipo_id', 'equipo_nombre'], 'equipo_nombre')
    por_tecnico = _filas_repeticiones(consulta, ['tecnico_id', 'tecnico_nombre'], 'tecnico_nombre')
    por_estudio = _filas_repeticiones(consulta, ['estudio__tipo_estudio_id', 'estudio_nombre'], 'estudio_nombre')

    motivos = list(
        consulta.filter(numero_repeticiones__gt=0)
        .exclude(motivo_repeticion__isnull=True)
        .exclude(motivo_repeticion='')
        .values('motivo_repeticion')
        .annotate(casos=Count('id'), repeticiones=Sum('numero_repeticiones'))
        .order_by('-repeticiones', '-casos')[:10]
    )
    tendencia = list(
        consulta.annotate(mes=TruncMonth('fecha_realizacion'))
        .values('mes')
        .annotate(
            estudios=Count('id'),
            exposiciones=Sum('numero_exposiciones'),
            repeticiones=Sum('numero_repeticiones'),
        ).order_by('mes')
    )
    for fila in tendencia:
        fila['tasa'] = _tasa_repeticion(fila['repeticiones'], fila['exposiciones'])

    tecnicos = (
        BitacoraRadiologica.objects.filter(estudio__paciente__institucion=institucion)
        .exclude(tecnico__isnull=True).values('tecnico_id', 'tecnico_nombre').distinct()
        .order_by('tecnico_nombre')
    )
    return {
        'consulta': consulta,
        'desde': desde.isoformat(),
        'hasta': hasta.isoformat(),
        'equipo_filtro': equipo,
        'tecnico_filtro': tecnico,
        'modalidad_filtro': modalidad,
        'tipo_estudio_filtro': tipo_estudio,
        'total_estudios': total_estudios,
        'total_exposiciones': total_exposiciones,
        'total_repeticiones': total_repeticiones,
        'estudios_afectados': afectados,
        'tasa_repeticion': tasa,
        'porcentaje_afectados': porcentaje_afectados,
        'estado': estado,
        'estado_texto': estado_texto,
        'por_equipo': por_equipo,
        'por_tecnico': por_tecnico,
        'por_estudio': por_estudio,
        'motivos': motivos,
        'tendencia': tendencia,
        'equipos': EquipoRadiologico.objects.filter(
            Q(institucion=institucion) | Q(institucion__isnull=True)
        ).order_by('nombre'),
        'tecnicos': tecnicos,
        'tipos_estudio': TipoEstudio.objects.filter(activo=True).order_by('modalidad', 'nombre'),
        'modalidades': BitacoraRadiologica.MODALIDAD_CHOICES,
    }


@login_required
def analisis_repeticiones_radiologia(request):
    membresia = obtener_membresia_usuario(request)
    if membresia is None or membresia.rol not in ['TECNICO', 'RADIOLOGIA', 'ADMIN']:
        return HttpResponse('No tienes permiso para consultar este análisis.', status=403)
    datos = _datos_analisis_repeticiones(request, membresia.institucion)
    datos.pop('consulta', None)
    return render(request, 'core/analisis_repeticiones_radiologia.html', datos)


@login_required
def analisis_repeticiones_radiologia_pdf(request):
    membresia = obtener_membresia_usuario(request)
    if membresia is None or membresia.rol not in ['TECNICO', 'RADIOLOGIA', 'ADMIN']:
        return HttpResponse('No tienes permiso para consultar este análisis.', status=403)
    institucion = membresia.institucion
    datos = _datos_analisis_repeticiones(request, institucion)
    respuesta = HttpResponse(content_type='application/pdf')
    respuesta['Content-Disposition'] = 'inline; filename="analisis_repeticiones_radiologia.pdf"'
    lienzo = pdf_canvas.Canvas(respuesta, pagesize=landscape(letter))
    ancho, alto = landscape(letter)

    def cabecera():
        y = alto - 35
        if institucion.logo:
            try:
                with institucion.logo.storage.open(institucion.logo.name, 'rb') as archivo_logo:
                    lienzo.drawImage(ImageReader(BytesIO(archivo_logo.read())), 35, alto - 66, 45, 32, preserveAspectRatio=True, mask='auto')
            except Exception:
                logger.exception('No fue posible cargar el logo en el análisis de repeticiones.')
        lienzo.setFont('Helvetica-Bold', 13)
        lienzo.drawString(88, y, institucion.nombre_comercial or institucion.nombre)
        lienzo.setFont('Helvetica-Bold', 11)
        lienzo.drawString(35, alto - 84, 'ANÁLISIS DE REPETICIONES Y RECHAZOS RADIOGRÁFICOS')
        lienzo.setFont('Helvetica', 7)
        lienzo.drawRightString(ancho - 35, alto - 84, f"Periodo: {datos['desde']} a {datos['hasta']} · Generado: {timezone.localtime():%d/%m/%Y %H:%M}")
        lienzo.line(35, alto - 91, ancho - 35, alto - 91)
        return alto - 110

    y = cabecera()
    tasa_texto = f"{datos['tasa_repeticion']:.2f} %" if datos['tasa_repeticion'] is not None else 'No calculable'
    resumen = [
        f"Estudios: {datos['total_estudios']}",
        f"Exposiciones registradas: {datos['total_exposiciones']}",
        f"Repeticiones: {datos['total_repeticiones']}",
        f"Estudios afectados: {datos['estudios_afectados']} ({datos['porcentaje_afectados']:.2f} %)",
        f"Tasa de repetición: {tasa_texto}",
    ]
    lienzo.setFont('Helvetica-Bold', 9)
    lienzo.drawString(35, y, ' | '.join(resumen)); y -= 14
    lienzo.setFont('Helvetica', 8)
    lienzo.drawString(35, y, datos['estado_texto'] + '. El 5 % es un objetivo interno de seguimiento, no un límite regulatorio.'); y -= 22

    def tabla(titulo, filas):
        nonlocal y
        if y < 115:
            lienzo.showPage(); y = cabecera()
        lienzo.setFont('Helvetica-Bold', 9); lienzo.drawString(35, y, titulo); y -= 13
        lienzo.setFont('Helvetica-Bold', 7)
        lienzo.drawString(42, y, 'Elemento'); lienzo.drawString(430, y, 'Estudios')
        lienzo.drawString(500, y, 'Exposiciones'); lienzo.drawString(580, y, 'Repeticiones'); lienzo.drawString(665, y, 'Tasa')
        y -= 10
        for fila in filas:
            if y < 45:
                lienzo.showPage(); y = cabecera()
            lienzo.setFont('Helvetica', 7)
            lienzo.drawString(42, y, str(fila['nombre'])[:65])
            lienzo.drawRightString(470, y, str(fila['estudios'] or 0))
            lienzo.drawRightString(555, y, str(fila['exposiciones'] or 0))
            lienzo.drawRightString(640, y, str(fila['repeticiones'] or 0))
            lienzo.drawRightString(715, y, f"{fila['tasa']:.2f} %" if fila['tasa'] is not None else '—')
            y -= 10
        y -= 9

    tabla('Resultados por equipo', datos['por_equipo'])
    tabla('Resultados por técnico', datos['por_tecnico'])
    tabla('Resultados por tipo de estudio', datos['por_estudio'])
    if datos['motivos']:
        if y < 100:
            lienzo.showPage(); y = cabecera()
        lienzo.setFont('Helvetica-Bold', 9); lienzo.drawString(35, y, 'Motivos registrados'); y -= 13
        for motivo in datos['motivos']:
            lienzo.setFont('Helvetica', 7)
            texto = f"{motivo['repeticiones'] or 0} repetición(es) · {motivo['casos']} caso(s) · {motivo['motivo_repeticion']}"
            for linea in textwrap.wrap(texto, 120):
                if y < 40:
                    lienzo.showPage(); y = cabecera()
                lienzo.drawString(42, y, linea); y -= 9
    lienzo.save()
    return respuesta

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
            'reporte_radiologico__finalizado_por',
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
    usuarios_firmantes = []
    for estudio_item in estudios:
        try:
            reporte_relacionado = estudio_item.reporte_radiologico
        except ReporteRadiologico.DoesNotExist:
            reporte_relacionado = None
        if reporte_relacionado and reporte_relacionado.finalizado_por_id:
            usuarios_firmantes.append(reporte_relacionado.finalizado_por_id)
    perfiles_firmantes = {
        perfil.usuario_id: perfil
        for perfil in PerfilMedico.objects.filter(
            institucion=membresia.institucion,
            usuario_id__in=usuarios_firmantes,
            activo=True,
        )
    }

    for estudio_item in estudios:
        estudio_item.reporte_pdf_url = None
        try:
            reporte_item = estudio_item.reporte_radiologico
        except ReporteRadiologico.DoesNotExist:
            reporte_item = None
        perfil_firmante = (
            perfiles_firmantes.get(reporte_item.finalizado_por_id)
            if reporte_item and reporte_item.finalizado_por_id else None
        )
        estudio_item.reporte_firmado = bool(
            reporte_item
            and reporte_item.estado == 'FINAL'
            and perfil_firmante
            and perfil_firmante.cedula_profesional
            and perfil_firmante.firma
        )
        if reporte_item:
            estudio_item.reporte_pdf_url = reverse(
                'reporte_radiologico_pdf', args=[estudio_item.id],
            )
        if estudio_item.reporte_firmado:
            estado_evento = 'Completado · Reporte firmado'
        elif estudio_item.estado == 'COMPLETADO':
            estado_evento = 'Estudio realizado · Reporte pendiente'
        else:
            estado_evento = estudio_item.get_estado_display()
        historial_eventos.append({
            'fecha': estudio_item.fecha_creacion,
            'tipo': 'IMAGEN',
            'etiqueta': estudio_item.tipo_estudio.get_modalidad_display(),
            'titulo': estudio_item.tipo_estudio.nombre,
            'estado': estado_evento,
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
