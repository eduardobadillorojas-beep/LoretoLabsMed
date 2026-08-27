from django.conf import settings
from django.db import models
from django.utils import timezone
from decimal import Decimal
import uuid


def generar_folio_cobro():
    fecha = timezone.now().strftime('%Y%m%d')
    aleatorio = uuid.uuid4().hex[:8].upper()
    return f'CB-{fecha}-{aleatorio}'


def generar_folio_credito():
    fecha = timezone.now().strftime('%Y%m%d')
    aleatorio = uuid.uuid4().hex[:8].upper()
    return f'CR-{fecha}-{aleatorio}'


def generar_folio_abono():
    fecha = timezone.now().strftime('%Y%m%d')
    aleatorio = uuid.uuid4().hex[:8].upper()
    return f'AB-{fecha}-{aleatorio}'


def generar_folio_corte_caja():
    fecha = timezone.now().strftime('%Y%m%d')
    aleatorio = uuid.uuid4().hex[:8].upper()
    return f'CC-{fecha}-{aleatorio}'


class Institucion(models.Model):
    nombre = models.CharField(
        max_length=200,
        verbose_name='Nombre de la institución'
    )

    nombre_comercial = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        verbose_name='Nombre comercial'
    )

    rfc = models.CharField(
        max_length=13,
        blank=True,
        null=True,
        verbose_name='RFC'
    )

    telefono = models.CharField(
        max_length=20,
        blank=True,
        null=True
    )

    email = models.EmailField(
        blank=True,
        null=True
    )

    direccion = models.TextField(
        blank=True,
        null=True
    )

    logo = models.ImageField(
        upload_to='instituciones/logos/',
        blank=True,
        null=True,
        verbose_name='Logo institucional'
    )

    telefono_secundario = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        verbose_name='Teléfono secundario'
    )

    horarios_servicio = models.TextField(
        blank=True,
        null=True,
        verbose_name='Horarios de servicio'
    )

    pie_documentos = models.TextField(
        blank=True,
        null=True,
        verbose_name='Pie de documentos'
    )

    activa = models.BooleanField(
        default=True
    )

    creada_el = models.DateTimeField(
        auto_now_add=True
    )

    actualizada_el = models.DateTimeField(
        auto_now=True
    )

    def __str__(self):
        return self.nombre


class MembresiaInstitucion(models.Model):
    ROL_CHOICES = [
        ('ADMIN', 'Administrador'),
        ('RECEPCION', 'Recepción'),
        ('MEDICO', 'Médico'),
        ('RADIOLOGIA', 'Radiología'),
        ('TECNICO', 'Técnico'),
        ('ENFERMERIA', 'Enfermería'),
        ('OTRO', 'Otro'),
    ]

    institucion = models.ForeignKey(
        Institucion,
        on_delete=models.CASCADE,
        related_name='membresias'
    )

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='membresias_institucion'
    )

    rol = models.CharField(
        max_length=20,
        choices=ROL_CHOICES,
        default='OTRO'
    )

    activa = models.BooleanField(
        default=True
    )

    creada_el = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['institucion', 'usuario'],
                name='unique_usuario_por_institucion'
            )
        ]

    def __str__(self):
        return f'{self.usuario.username} - {self.institucion.nombre}'


class PerfilMedico(models.Model):
    institucion = models.ForeignKey(
        Institucion,
        on_delete=models.CASCADE,
        related_name='perfiles_medicos'
    )

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='perfiles_medicos'
    )

    especialidad = models.CharField(
        max_length=150,
        blank=True,
        null=True,
        verbose_name='Especialidad'
    )

    cedula_profesional = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name='Cédula profesional'
    )

    telefono_profesional = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        verbose_name='Teléfono profesional'
    )

    firma = models.ImageField(
        upload_to='medicos/firmas/',
        blank=True,
        null=True,
        verbose_name='Firma digitalizada'
    )

    activo = models.BooleanField(
        default=True
    )

    creado_el = models.DateTimeField(
        auto_now_add=True
    )

    actualizado_el = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['institucion', 'usuario'],
                name='unique_perfil_medico_por_institucion'
            )
        ]

    def __str__(self):
        nombre = self.usuario.get_full_name() or self.usuario.username
        return f'{nombre} - {self.institucion.nombre}'


class Paciente(models.Model):
    institucion = models.ForeignKey(
        Institucion,
        on_delete=models.PROTECT,
        related_name='pacientes',
        verbose_name='Institución'
    )

    GENERO_CHOICES = [
        ('M', 'Masculino'),
        ('F', 'Femenino'),
        ('O', 'Otro'),
    ]

    identificacion = models.CharField(
        max_length=20,
        unique=True,
        blank=True,
        editable=False,
        verbose_name='Registro interno'
    )

    nombre = models.CharField(
        max_length=100
    )

    apellido = models.CharField(
        max_length=100
    )

    fecha_nacimiento = models.DateField()

    genero = models.CharField(
        max_length=1,
        choices=GENERO_CHOICES
    )

    telefono = models.CharField(
        max_length=20,
        blank=True,
        null=True
    )

    creado_el = models.DateTimeField(
        auto_now_add=True
    )

    def save(self, *args, **kwargs):
        nuevo_paciente = self.pk is None

        super().save(*args, **kwargs)

        if nuevo_paciente and not self.identificacion:
            numero_registro = self.pk + 99999
            self.identificacion = str(numero_registro)

            Paciente.objects.filter(
                pk=self.pk
            ).update(
                identificacion=self.identificacion
            )

    def __str__(self):
        return (
            f'{self.identificacion} - '
            f'{self.nombre} {self.apellido}'
        )


class TipoEstudio(models.Model):
    MODALIDAD_CHOICES = [
        ('RX', 'Radiografía'),
        ('TAC', 'Tomografía'),
        ('USG', 'Ultrasonido'),
        ('MASTO', 'Mastografía'),
        ('FLUORO', 'Fluoroscopia'),
        ('RM', 'Resonancia magnética'),
        ('DXA', 'Densitometría'),
    ]

    codigo = models.CharField(
        max_length=20,
        unique=True
    )

    nombre = models.CharField(
        max_length=150
    )

    modalidad = models.CharField(
        max_length=20,
        choices=MODALIDAD_CHOICES
    )

    activo = models.BooleanField(
        default=True
    )

    tiempo_estimado = models.PositiveIntegerField(
        default=10,
        verbose_name='Tiempo estimado en minutos'
    )

    def __str__(self):
        return (
            f'{self.codigo} - '
            f'{self.nombre}'
        )


class EquipoRadiologico(models.Model):
    TIPO_CHOICES = [
        ('RX', 'Radiografía'),
        ('TAC', 'Tomografía'),
        ('FLUORO', 'Fluoroscopia'),
        ('MASTO', 'Mastografía'),
        ('PORTATIL', 'Rayos X portátil'),
        ('OTRO', 'Otro'),
    ]

    nombre = models.CharField(
        max_length=100,
        verbose_name='Nombre del equipo'
    )

    tipo = models.CharField(
        max_length=20,
        choices=TIPO_CHOICES
    )

    marca = models.CharField(
        max_length=100,
        blank=True,
        null=True
    )

    modelo = models.CharField(
        max_length=100,
        blank=True,
        null=True
    )

    numero_serie = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name='Número de serie'
    )

    ubicacion = models.CharField(
        max_length=150,
        blank=True,
        null=True
    )

    activo = models.BooleanField(
        default=True
    )

    creado_el = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return self.nombre


class Consulta(models.Model):
    ESTADO_CHOICES = [
        ('EN_ESPERA', 'En espera'),
        ('EN_CONSULTA', 'En consulta'),
        ('FINALIZADA', 'Finalizada'),
        ('CANCELADA', 'Cancelada'),
    ]

    paciente = models.ForeignKey(
        Paciente,
        on_delete=models.CASCADE,
        related_name='consultas'
    )

    medico = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='consultas_medicas',
        blank=True,
        null=True
    )

    motivo_consulta = models.TextField(
        blank=True,
        null=True,
        verbose_name='Motivo de consulta'
    )

    # =========================
    # SIGNOS VITALES
    # =========================

    presion_sistolica = models.PositiveIntegerField(
        blank=True,
        null=True,
        verbose_name='TA sistólica'
    )

    presion_diastolica = models.PositiveIntegerField(
        blank=True,
        null=True,
        verbose_name='TA diastólica'
    )

    frecuencia_cardiaca = models.PositiveIntegerField(
        blank=True,
        null=True,
        verbose_name='Frecuencia cardiaca'
    )

    frecuencia_respiratoria = models.PositiveIntegerField(
        blank=True,
        null=True,
        verbose_name='Frecuencia respiratoria'
    )

    temperatura = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        blank=True,
        null=True,
        verbose_name='Temperatura °C'
    )

    saturacion_oxigeno = models.PositiveIntegerField(
        blank=True,
        null=True,
        verbose_name='SpO₂'
    )

    peso_kg = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        blank=True,
        null=True,
        verbose_name='Peso kg'
    )

    talla_cm = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        blank=True,
        null=True,
        verbose_name='Talla cm'
    )

    # =========================
    # NOTA MÉDICA
    # =========================

    antecedentes = models.TextField(
        blank=True,
        null=True,
        verbose_name='Antecedentes'
    )

    exploracion_fisica = models.TextField(
        blank=True,
        null=True,
        verbose_name='Exploración física'
    )

    diagnostico = models.TextField(
        blank=True,
        null=True,
        verbose_name='Diagnóstico'
    )

    plan_tratamiento = models.TextField(
        blank=True,
        null=True,
        verbose_name='Plan y tratamiento'
    )

    notas_medicas = models.TextField(
        blank=True,
        null=True,
        verbose_name='Notas médicas'
    )

    estado = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        default='EN_ESPERA'
    )

    fecha_llegada = models.DateTimeField(
        auto_now_add=True
    )

    fecha_inicio = models.DateTimeField(
        blank=True,
        null=True
    )

    fecha_finalizacion = models.DateTimeField(
        blank=True,
        null=True
    )

    @property
    def imc(self):
        if not self.peso_kg or not self.talla_cm:
            return None

        talla_m = float(self.talla_cm) / 100

        if talla_m <= 0:
            return None

        return round(
            float(self.peso_kg) / (talla_m ** 2),
            2
        )

    def __str__(self):
        return (
            f'{self.paciente.nombre} '
            f'{self.paciente.apellido} - '
            f'{self.get_estado_display()}'
        )


class RecetaMedica(models.Model):
    consulta = models.OneToOneField(
        Consulta,
        on_delete=models.CASCADE,
        related_name='receta_medica'
    )

    medico = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='recetas_medicas_emitidas',
        blank=True,
        null=True
    )

    observaciones = models.TextField(
        blank=True,
        null=True,
        verbose_name='Observaciones de la receta'
    )

    creada_el = models.DateTimeField(
        auto_now_add=True
    )

    actualizada_el = models.DateTimeField(
        auto_now=True
    )

    def __str__(self):
        return (
            f'Receta - {self.consulta.paciente.nombre} '
            f'{self.consulta.paciente.apellido}'
        )


class MedicamentoReceta(models.Model):
    VIA_CHOICES = [
        ('ORAL', 'Oral'),
        ('SUBLINGUAL', 'Sublingual'),
        ('TOPICA', 'Tópica'),
        ('INHALADA', 'Inhalada'),
        ('OFTALMICA', 'Oftálmica'),
        ('OTICA', 'Ótica'),
        ('NASAL', 'Nasal'),
        ('RECTAL', 'Rectal'),
        ('VAGINAL', 'Vaginal'),
        ('INTRAMUSCULAR', 'Intramuscular'),
        ('INTRAVENOSA', 'Intravenosa'),
        ('SUBCUTANEA', 'Subcutánea'),
        ('OTRA', 'Otra'),
    ]

    receta = models.ForeignKey(
        RecetaMedica,
        on_delete=models.CASCADE,
        related_name='medicamentos'
    )

    medicamento = models.CharField(
        max_length=200
    )

    presentacion = models.CharField(
        max_length=150,
        blank=True,
        null=True,
        verbose_name='Presentación'
    )

    dosis = models.CharField(
        max_length=150,
        blank=True,
        null=True
    )

    via = models.CharField(
        max_length=30,
        choices=VIA_CHOICES,
        blank=True,
        null=True,
        verbose_name='Vía de administración'
    )

    frecuencia = models.CharField(
        max_length=150,
        blank=True,
        null=True
    )

    cantidad = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name='Cantidad total'
    )

    duracion = models.CharField(
        max_length=150,
        blank=True,
        null=True,
        verbose_name='Duración'
    )

    indicaciones = models.TextField(
        blank=True,
        null=True,
        verbose_name='Indicaciones del medicamento'
    )

    orden = models.PositiveIntegerField(
        default=1
    )

    class Meta:
        ordering = [
            'orden',
            'id',
        ]

    def __str__(self):
        return self.medicamento


class IndicacionMedica(models.Model):
    consulta = models.OneToOneField(
        Consulta,
        on_delete=models.CASCADE,
        related_name='indicacion_medica'
    )

    medico = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='indicaciones_medicas_emitidas',
        blank=True,
        null=True
    )

    indicaciones = models.TextField(
        verbose_name='Indicaciones médicas'
    )

    creada_el = models.DateTimeField(
        auto_now_add=True
    )

    actualizada_el = models.DateTimeField(
        auto_now=True
    )

    def __str__(self):
        return (
            f'Indicaciones - {self.consulta.paciente.nombre} '
            f'{self.consulta.paciente.apellido}'
        )


class SolicitudEstudio(models.Model):
    TIPO_CHOICES = [
        ('LABORATORIO', 'Laboratorio clínico'),
        ('IMAGEN', 'Imagenología'),
        ('PATOLOGIA', 'Patología'),
        ('CARDIOLOGIA', 'Cardiología'),
        ('OTRO', 'Otro estudio o procedimiento'),
    ]

    PRIORIDAD_CHOICES = [
        ('RUTINA', 'Rutina'),
        ('PREFERENTE', 'Preferente'),
        ('URGENTE', 'Urgente'),
    ]

    consulta = models.ForeignKey(
        Consulta,
        on_delete=models.CASCADE,
        related_name='solicitudes_estudio'
    )

    medico = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='solicitudes_estudio_emitidas',
        blank=True,
        null=True
    )

    tipo = models.CharField(
        max_length=30,
        choices=TIPO_CHOICES
    )

    prioridad = models.CharField(
        max_length=20,
        choices=PRIORIDAD_CHOICES,
        default='RUTINA'
    )

    motivo_clinico = models.TextField(
        blank=True,
        null=True,
        verbose_name='Motivo clínico / diagnóstico presuntivo'
    )

    observaciones = models.TextField(
        blank=True,
        null=True
    )

    creada_el = models.DateTimeField(
        auto_now_add=True
    )

    actualizada_el = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        ordering = [
            '-creada_el',
        ]

    def __str__(self):
        return (
            f'Solicitud - {self.get_tipo_display()} - '
            f'{self.consulta.paciente.nombre} '
            f'{self.consulta.paciente.apellido}'
        )


class EstudioSolicitado(models.Model):
    solicitud = models.ForeignKey(
        SolicitudEstudio,
        on_delete=models.CASCADE,
        related_name='estudios_solicitados'
    )

    nombre = models.CharField(
        max_length=250,
        verbose_name='Estudio solicitado'
    )

    region_o_detalle = models.CharField(
        max_length=250,
        blank=True,
        null=True,
        verbose_name='Región, muestra o detalle'
    )

    indicaciones = models.TextField(
        blank=True,
        null=True,
        verbose_name='Indicaciones específicas'
    )

    orden = models.PositiveIntegerField(
        default=1
    )

    class Meta:
        ordering = [
            'orden',
            'id',
        ]

    def __str__(self):
        return self.nombre


class Estudio(models.Model):
    ESTADO_CHOICES = [
        ('PENDIENTE', 'Pendiente'),
        ('EN_PROCESO', 'En proceso'),
        ('COMPLETADO', 'Completado'),
    ]

    ESTADO_REPORTE_CHOICES = [
        ('SIN_REPORTE', 'Sin reporte'),
        ('PRE_REPORTE', 'Pre-reporte'),
        ('POR_VALIDAR', 'Por validar'),
        ('FINAL', 'Reporte final'),
    ]

    paciente = models.ForeignKey(
        Paciente,
        on_delete=models.CASCADE,
        related_name='estudios'
    )

    consulta = models.ForeignKey(
        Consulta,
        on_delete=models.SET_NULL,
        related_name='estudios',
        blank=True,
        null=True
    )

    tipo_estudio = models.ForeignKey(
        TipoEstudio,
        on_delete=models.PROTECT,
        related_name='estudios'
    )

    medico_solicitante = models.CharField(
        max_length=150,
        blank=True,
        null=True,
        verbose_name='Médico solicitante'
    )

    descripcion = models.TextField(
        blank=True,
        null=True
    )

    estado = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        default='PENDIENTE'
    )

    tecnico = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='estudios_realizados',
        blank=True,
        null=True,
        verbose_name='Técnico radiólogo'
    )

    equipo = models.ForeignKey(
        EquipoRadiologico,
        on_delete=models.SET_NULL,
        related_name='estudios',
        blank=True,
        null=True,
        verbose_name='Equipo utilizado'
    )

    fecha_inicio = models.DateTimeField(
        blank=True,
        null=True
    )

    fecha_finalizacion = models.DateTimeField(
        blank=True,
        null=True
    )

    estado_reporte = models.CharField(
        max_length=20,
        choices=ESTADO_REPORTE_CHOICES,
        default='SIN_REPORTE',
        verbose_name='Estado del reporte'
    )

    pre_reporte = models.TextField(
        blank=True,
        null=True,
        verbose_name='Pre-reporte técnico'
    )

    pre_reporte_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='pre_reportes_radiologicos',
        blank=True,
        null=True,
        verbose_name='Pre-reporte elaborado por'
    )

    fecha_pre_reporte = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name='Fecha de pre-reporte'
    )

    reporte_final = models.TextField(
        blank=True,
        null=True,
        verbose_name='Reporte radiológico final'
    )

    reporte_final_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='reportes_radiologicos_finales',
        blank=True,
        null=True,
        verbose_name='Reporte final validado por'
    )

    fecha_reporte_final = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name='Fecha de reporte final'
    )

    fecha_creacion = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return (
            f'{self.tipo_estudio.nombre} - '
            f'{self.paciente.identificacion}'
        )


class ArchivoEstudio(models.Model):
    TIPO_ARCHIVO_CHOICES = [
        ('DICOM', 'DICOM'),
        ('IMAGEN', 'Imagen'),
        ('DOCUMENTO', 'Documento'),
        ('OTRO', 'Otro'),
    ]

    estudio = models.ForeignKey(
        Estudio,
        on_delete=models.CASCADE,
        related_name='archivos'
    )

    archivo = models.FileField(
        upload_to='estudios/%Y/%m/%d/',
        verbose_name='Archivo'
    )

    tipo_archivo = models.CharField(
        max_length=20,
        choices=TIPO_ARCHIVO_CHOICES,
        default='DICOM'
    )

    nombre_original = models.CharField(
        max_length=255,
        blank=True,
        null=True
    )

    subido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='archivos_estudio_subidos',
        blank=True,
        null=True
    )

    creado_el = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        ordering = [
            'creado_el',
        ]

    def __str__(self):
        return (
            f'{self.estudio.tipo_estudio.nombre} - '
            f'{self.nombre_original or self.archivo.name}'
        )


class BitacoraRadiologica(models.Model):
    MODALIDAD_CHOICES = [
        ('RX', 'Radiografía'),
        ('TAC', 'Tomografía'),
        ('FLUORO', 'Fluoroscopia'),
        ('MASTO', 'Mastografía'),
        ('OTRA', 'Otra'),
    ]

    estudio = models.OneToOneField(
        Estudio,
        on_delete=models.PROTECT,
        related_name='bitacora_radiologica'
    )

    fecha_realizacion = models.DateTimeField(
        verbose_name='Fecha y hora de realización'
    )

    paciente_nombre = models.CharField(
        max_length=250
    )

    paciente_registro = models.CharField(
        max_length=20,
        blank=True,
        null=True
    )

    fecha_nacimiento = models.DateField(
        blank=True,
        null=True
    )

    edad = models.PositiveIntegerField(
        blank=True,
        null=True
    )

    genero = models.CharField(
        max_length=20,
        blank=True,
        null=True
    )

    modalidad = models.CharField(
        max_length=20,
        choices=MODALIDAD_CHOICES
    )

    estudio_nombre = models.CharField(
        max_length=200
    )

    medico_solicitante = models.CharField(
        max_length=150,
        blank=True,
        null=True
    )

    tecnico = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='bitacoras_radiologicas',
        blank=True,
        null=True
    )

    tecnico_nombre = models.CharField(
        max_length=150,
        blank=True,
        null=True
    )

    equipo = models.ForeignKey(
        EquipoRadiologico,
        on_delete=models.SET_NULL,
        related_name='bitacoras',
        blank=True,
        null=True
    )

    equipo_nombre = models.CharField(
        max_length=150,
        blank=True,
        null=True
    )

    # ==================================
    # PARÁMETROS DE RADIOGRAFÍA
    # ==================================

    kvp = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        blank=True,
        null=True,
        verbose_name='kVp'
    )

    mas = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        blank=True,
        null=True,
        verbose_name='mAs'
    )

    numero_exposiciones = models.PositiveIntegerField(
        blank=True,
        null=True,
        verbose_name='Número de exposiciones'
    )

    proyecciones = models.TextField(
        blank=True,
        null=True
    )

    # ==================================
    # PARÁMETROS DE TOMOGRAFÍA
    # ==================================

    ctdi_vol = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        blank=True,
        null=True,
        verbose_name='CTDIvol'
    )

    dlp = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        blank=True,
        null=True,
        verbose_name='DLP'
    )

    uso_contraste = models.BooleanField(
        blank=True,
        null=True,
        verbose_name='Uso de medio de contraste'
    )

    # ==================================
    # INFORMACIÓN GENERAL
    # ==================================

    observaciones = models.TextField(
        blank=True,
        null=True
    )

    creado_el = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        ordering = [
            '-fecha_realizacion',
        ]

        indexes = [
            models.Index(
                fields=['fecha_realizacion']
            ),
            models.Index(
                fields=['modalidad']
            ),
            models.Index(
                fields=[
                    'modalidad',
                    'fecha_realizacion',
                ]
            ),
        ]

    def __str__(self):
        return (
            f'{self.fecha_realizacion:%d/%m/%Y} - '
            f'{self.paciente_nombre} - '
            f'{self.estudio_nombre}'
        )


class Cita(models.Model):
    institucion = models.ForeignKey(
        Institucion,
        on_delete=models.PROTECT,
        related_name='citas',
        verbose_name='Institución'
    )

    AREA_CHOICES = [
        ('CONSULTA', 'Consulta médica'),
        ('TRAUMATOLOGIA', 'Traumatología'),
        ('DERMATOLOGIA', 'Dermatología'),
        ('ENDOCRINOLOGIA', 'Endocrinología'),
        ('RADIOLOGIA', 'Radiología'),
    ]

    ESTADO_CHOICES = [
        ('PROGRAMADA', 'Programada'),
        ('CONFIRMADA', 'Confirmada'),
        ('LLEGO', 'Paciente llegó'),
        ('EN_ESPERA', 'En espera'),
        ('EN_ATENCION', 'En atención'),
        ('FINALIZADA', 'Finalizada'),
        ('CANCELADA', 'Cancelada'),
        ('NO_ASISTIO', 'No asistió'),
    ]

    nombre_paciente = models.CharField(
        max_length=200,
        verbose_name='Nombre del paciente'
    )

    telefono = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        verbose_name='Teléfono'
    )

    paciente = models.ForeignKey(
        Paciente,
        on_delete=models.SET_NULL,
        related_name='citas',
        blank=True,
        null=True
    )

    area = models.CharField(
        max_length=30,
        choices=AREA_CHOICES,
        verbose_name='Área de atención'
    )

    medico_nombre = models.CharField(
        max_length=150,
        blank=True,
        null=True,
        verbose_name='Médico'
    )

    tipo_estudio = models.ForeignKey(
        TipoEstudio,
        on_delete=models.PROTECT,
        related_name='citas',
        blank=True,
        null=True,
        verbose_name='Estudio programado'
    )

    fecha_hora = models.DateTimeField(
        verbose_name='Fecha y hora'
    )

    duracion_minutos = models.PositiveIntegerField(
        default=30,
        verbose_name='Duración estimada en minutos'
    )

    motivo = models.TextField(
        blank=True,
        null=True,
        verbose_name='Motivo de la cita'
    )

    observaciones = models.TextField(
        blank=True,
        null=True,
        verbose_name='Observaciones internas'
    )

    estado = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        default='PROGRAMADA'
    )

    creada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='citas_creadas',
        blank=True,
        null=True
    )

    creado_el = models.DateTimeField(
        auto_now_add=True
    )

    actualizado_el = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        ordering = [
            'fecha_hora',
        ]

        indexes = [
            models.Index(
                fields=['fecha_hora']
            ),
            models.Index(
                fields=[
                    'area',
                    'estado',
                ]
            ),
        ]

    def __str__(self):
        return (
            f'{self.nombre_paciente} - '
            f'{self.get_area_display()} - '
            f'{self.fecha_hora:%d/%m/%Y %H:%M}'
        )


class SesionTrabajo(models.Model):
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='sesiones_trabajo'
    )

    inicio = models.DateTimeField(
        auto_now_add=True
    )

    ultima_actividad = models.DateTimeField(
        auto_now=True
    )

    fin = models.DateTimeField(
        blank=True,
        null=True
    )

    activa = models.BooleanField(
        default=True
    )

    ip_inicio = models.GenericIPAddressField(
        blank=True,
        null=True
    )

    ip_fin = models.GenericIPAddressField(
        blank=True,
        null=True
    )

    user_agent = models.TextField(
        blank=True,
        null=True
    )

    class Meta:
        ordering = [
            '-inicio',
        ]

        indexes = [
            models.Index(
                fields=[
                    'usuario',
                    'activa',
                ]
            ),
            models.Index(
                fields=['inicio']
            ),
        ]

    def __str__(self):
        return (
            f'{self.usuario.username} - '
            f'{self.inicio:%d/%m/%Y %H:%M}'
        )

    @property
    def duracion(self):
        if self.fin:
            return self.fin - self.inicio

        return None

# =========================================================
# CATÁLOGO DE SERVICIOS Y CUENTA DEL PACIENTE
# =========================================================

class Servicio(models.Model):
    TIPO_CHOICES = [
        ('CONSULTA', 'Consulta médica'),
        ('RX', 'Radiografía'),
        ('USG', 'Ultrasonido'),
        ('TAC', 'Tomografía'),
        ('MASTO', 'Mastografía'),
        ('RM', 'Resonancia magnética'),
        ('FLUORO', 'Fluoroscopia'),
        ('PROCEDIMIENTO', 'Procedimiento'),
        ('INMOVILIZACION', 'Inmovilización'),
        ('MATERIAL', 'Material'),
        ('OTRO', 'Otro'),
    ]

    institucion = models.ForeignKey(
        Institucion,
        on_delete=models.CASCADE,
        related_name='servicios',
        verbose_name='Institución'
    )

    tipo_estudio = models.ForeignKey(
        TipoEstudio,
        on_delete=models.SET_NULL,
        related_name='servicios_comerciales',
        blank=True,
        null=True,
        verbose_name='Tipo de estudio relacionado'
    )

    nombre = models.CharField(
        max_length=200,
        verbose_name='Nombre del servicio'
    )

    tipo = models.CharField(
        max_length=30,
        choices=TIPO_CHOICES,
        default='OTRO'
    )

    precio_base = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name='Precio base'
    )

    precio_editable = models.BooleanField(
        default=False,
        verbose_name='Permitir precio manual'
    )

    activo = models.BooleanField(
        default=True
    )

    creado_el = models.DateTimeField(
        auto_now_add=True
    )

    actualizado_el = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        ordering = ['tipo', 'nombre']
        indexes = [
            models.Index(
                fields=['institucion', 'tipo', 'activo']
            ),
        ]

    def __str__(self):
        return f'{self.nombre} - {self.institucion.nombre}'


class Cobro(models.Model):
    FORMA_PAGO_CHOICES = [
        ('EFECTIVO', 'Efectivo'),
        ('TARJETA', 'Tarjeta'),
        ('TRANSFERENCIA', 'Transferencia'),
        ('OTRO', 'Otro'),
        ('MIXTO', 'Pago mixto'),
    ]

    ESTADO_CHOICES = [
        ('PAGADO', 'Pagado'),
        ('CANCELADO', 'Cancelado'),
    ]

    DESTINO_CARGOS_CHOICES = [
        ('CANCELAR', 'Cancelar también los servicios'),
        ('REABRIR', 'Dejar los servicios pendientes para volver a cobrar'),
    ]

    folio = models.CharField(
        max_length=30,
        unique=True,
        default=generar_folio_cobro,
        editable=False
    )

    token_publico = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False
    )

    institucion = models.ForeignKey(
        Institucion,
        on_delete=models.PROTECT,
        related_name='cobros'
    )

    paciente = models.ForeignKey(
        Paciente,
        on_delete=models.PROTECT,
        related_name='cobros'
    )

    forma_pago = models.CharField(
        max_length=20,
        choices=FORMA_PAGO_CHOICES,
        default='EFECTIVO'
    )

    total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    monto_recibido = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        blank=True,
        null=True
    )

    cambio = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    telefono_envio = models.CharField(
        max_length=20,
        blank=True,
        null=True
    )

    estado = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        default='PAGADO'
    )

    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='cobros_registrados',
        blank=True,
        null=True
    )

    creado_el = models.DateTimeField(
        auto_now_add=True
    )

    cancelado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='cobros_cancelados',
        blank=True,
        null=True
    )

    cancelado_el = models.DateTimeField(
        blank=True,
        null=True
    )

    motivo_cancelacion = models.CharField(
        max_length=300,
        blank=True,
        null=True
    )

    forma_reembolso = models.CharField(
        max_length=20,
        choices=FORMA_PAGO_CHOICES,
        blank=True,
        null=True
    )

    monto_reembolsado = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    destino_cargos_cancelacion = models.CharField(
        max_length=20,
        choices=DESTINO_CARGOS_CHOICES,
        blank=True,
        null=True
    )

    class Meta:
        ordering = ['-creado_el']
        indexes = [
            models.Index(
                fields=['institucion', 'paciente', 'creado_el']
            ),
            models.Index(
                fields=['folio']
            ),
        ]

    def __str__(self):
        return f'{self.folio} - ${self.total:.2f}'


class PagoCobro(models.Model):
    FORMA_PAGO_CHOICES = [
        ('EFECTIVO', 'Efectivo'),
        ('TARJETA', 'Tarjeta'),
        ('TRANSFERENCIA', 'Transferencia'),
        ('OTRO', 'Otro'),
    ]

    cobro = models.ForeignKey(
        Cobro,
        on_delete=models.CASCADE,
        related_name='pagos'
    )

    forma_pago = models.CharField(
        max_length=20,
        choices=FORMA_PAGO_CHOICES
    )

    monto = models.DecimalField(
        max_digits=12,
        decimal_places=2
    )

    referencia = models.CharField(
        max_length=100,
        blank=True,
        null=True
    )

    creado_el = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        ordering = ['pk']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(monto__gt=0),
                name='pago_cobro_monto_positivo'
            ),
        ]
        indexes = [
            models.Index(
                fields=['forma_pago', 'creado_el'],
                name='pago_forma_fecha_idx'
            ),
        ]

    def __str__(self):
        return (
            f'{self.cobro.folio} - '
            f'{self.get_forma_pago_display()} '
            f'${self.monto:.2f}'
        )


class CreditoPaciente(models.Model):
    ESTADO_CHOICES = [
        ('VIGENTE', 'Vigente'),
        ('LIQUIDADO', 'Liquidado'),
        ('VENCIDO', 'Vencido'),
        ('CANCELADO', 'Cancelado'),
    ]

    folio = models.CharField(max_length=30, unique=True, default=generar_folio_credito, editable=False)
    institucion = models.ForeignKey(Institucion, on_delete=models.PROTECT, related_name='creditos')
    paciente = models.ForeignKey(Paciente, on_delete=models.PROTECT, related_name='creditos')
    total = models.DecimalField(max_digits=12, decimal_places=2)
    saldo = models.DecimalField(max_digits=12, decimal_places=2)
    numero_cuotas = models.PositiveIntegerField(default=1)
    fecha_vencimiento = models.DateField()
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='VIGENTE')
    notas = models.CharField(max_length=300, blank=True, null=True)
    autorizado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, related_name='creditos_autorizados', blank=True, null=True)
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, related_name='creditos_registrados', blank=True, null=True)
    creado_el = models.DateTimeField(auto_now_add=True)
    actualizado_el = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-creado_el']
        indexes = [models.Index(fields=['institucion', 'paciente', 'estado'], name='credito_inst_pac_estado_idx')]

    @property
    def total_abonado(self):
        return (self.total - self.saldo).quantize(Decimal('0.01'))

    def __str__(self):
        return f'{self.folio} - {self.paciente} - ${self.saldo:.2f}'


class AbonoCredito(models.Model):
    FORMA_PAGO_CHOICES = PagoCobro.FORMA_PAGO_CHOICES
    folio = models.CharField(max_length=30, unique=True, default=generar_folio_abono, editable=False)
    token_publico = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    credito = models.ForeignKey(CreditoPaciente, on_delete=models.PROTECT, related_name='abonos')
    monto = models.DecimalField(max_digits=12, decimal_places=2)
    forma_pago = models.CharField(max_length=20, choices=FORMA_PAGO_CHOICES, default='EFECTIVO')
    referencia = models.CharField(max_length=100, blank=True, null=True)
    monto_recibido = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    cambio = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, related_name='abonos_credito_registrados', blank=True, null=True)
    creado_el = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['creado_el', 'pk']

    def __str__(self):
        return f'{self.folio} - ${self.monto:.2f}'


class PagoAbonoCredito(models.Model):
    FORMA_PAGO_CHOICES = PagoCobro.FORMA_PAGO_CHOICES
    abono = models.ForeignKey(AbonoCredito, on_delete=models.CASCADE, related_name='pagos')
    forma_pago = models.CharField(max_length=20, choices=FORMA_PAGO_CHOICES)
    monto = models.DecimalField(max_digits=12, decimal_places=2)
    referencia = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        ordering = ['pk']

    def __str__(self):
        return f'{self.abono.folio} - {self.get_forma_pago_display()} ${self.monto:.2f}'


class CorteCaja(models.Model):
    ESTADO_CHOICES = [
        ('ABIERTA', 'Abierta'),
        ('CERRADA', 'Cerrada'),
    ]

    folio = models.CharField(max_length=30, unique=True, default=generar_folio_corte_caja, editable=False)
    institucion = models.ForeignKey(Institucion, on_delete=models.PROTECT, related_name='cortes_caja')
    responsable = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='cortes_caja')
    estado = models.CharField(max_length=10, choices=ESTADO_CHOICES, default='ABIERTA')
    fondo_inicial = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    abierto_el = models.DateTimeField(auto_now_add=True)
    cerrado_el = models.DateTimeField(blank=True, null=True)
    total_cobros = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_abonos = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_reembolsos = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_neto = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_efectivo = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_tarjeta = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_transferencia = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_otro = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_entradas_efectivo = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_retiros_efectivo = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    reembolso_efectivo = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    efectivo_esperado = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    efectivo_contado = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    efectivo_entregado = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    efectivo_dejado = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    diferencia = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    numero_cobros = models.PositiveIntegerField(default=0)
    numero_abonos = models.PositiveIntegerField(default=0)
    numero_reembolsos = models.PositiveIntegerField(default=0)
    numero_movimientos = models.PositiveIntegerField(default=0)
    observaciones_apertura = models.CharField(max_length=300, blank=True, null=True)
    observaciones_cierre = models.CharField(max_length=500, blank=True, null=True)
    confirmacion_primera = models.BooleanField(default=False)
    confirmacion_segunda = models.BooleanField(default=False)

    class Meta:
        ordering = ['-abierto_el']
        constraints = [
            models.UniqueConstraint(
                fields=['institucion', 'responsable'],
                condition=models.Q(estado='ABIERTA'),
                name='una_caja_abierta_por_responsable'
            ),
        ]
        indexes = [
            models.Index(fields=['institucion', 'estado', 'abierto_el'], name='corte_inst_estado_fecha_idx'),
        ]

    def __str__(self):
        return f'{self.folio} - {self.get_estado_display()}'


class MovimientoCaja(models.Model):
    TIPO_CHOICES = [
        ('ENTRADA', 'Entrada extraordinaria'),
        ('RETIRO', 'Retiro de efectivo'),
    ]

    corte = models.ForeignKey(CorteCaja, on_delete=models.PROTECT, related_name='movimientos')
    tipo = models.CharField(max_length=10, choices=TIPO_CHOICES)
    monto = models.DecimalField(max_digits=12, decimal_places=2)
    motivo = models.CharField(max_length=300)
    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='movimientos_caja_registrados')
    creado_el = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['creado_el', 'pk']
        indexes = [
            models.Index(fields=['corte', 'tipo', 'creado_el'], name='mov_caja_corte_tipo_idx'),
        ]

    def __str__(self):
        return f'{self.corte.folio} - {self.get_tipo_display()} ${self.monto:.2f}'


class CargoPaciente(models.Model):
    ESTADO_CHOICES = [
        ('PENDIENTE', 'Pendiente'),
        ('CREDITO', 'A crédito'),
        ('PAGADO', 'Pagado'),
        ('CANCELADO', 'Cancelado'),
    ]

    ORIGEN_CHOICES = [
        ('RECEPCION', 'Recepción'),
        ('MEDICO', 'Médico'),
        ('RADIOLOGIA', 'Radiología'),
        ('TECNICO', 'Técnico radiológico'),
        ('ENFERMERIA', 'Enfermería'),
        ('SISTEMA', 'Sistema'),
        ('OTRO', 'Otro'),
    ]

    institucion = models.ForeignKey(
        Institucion,
        on_delete=models.PROTECT,
        related_name='cargos_pacientes',
        verbose_name='Institución'
    )

    paciente = models.ForeignKey(
        Paciente,
        on_delete=models.PROTECT,
        related_name='cargos',
        verbose_name='Paciente'
    )

    servicio = models.ForeignKey(
        Servicio,
        on_delete=models.SET_NULL,
        related_name='cargos',
        blank=True,
        null=True,
        verbose_name='Servicio del catálogo'
    )

    consulta = models.ForeignKey(
        Consulta,
        on_delete=models.SET_NULL,
        related_name='cargos',
        blank=True,
        null=True
    )

    estudio = models.ForeignKey(
        Estudio,
        on_delete=models.SET_NULL,
        related_name='cargos',
        blank=True,
        null=True
    )

    cobro = models.ForeignKey(
        Cobro,
        on_delete=models.SET_NULL,
        related_name='cargos',
        blank=True,
        null=True
    )

    credito = models.ForeignKey(
        CreditoPaciente,
        on_delete=models.SET_NULL,
        related_name='cargos',
        blank=True,
        null=True
    )

    descripcion = models.CharField(
        max_length=250,
        verbose_name='Concepto'
    )

    cantidad = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=1
    )

    precio_unitario = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name='Precio unitario'
    )

    estado = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        default='PENDIENTE'
    )

    origen = models.CharField(
        max_length=20,
        choices=ORIGEN_CHOICES,
        default='SISTEMA'
    )

    agregado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='cargos_agregados',
        blank=True,
        null=True,
        verbose_name='Agregado por'
    )

    notas = models.TextField(
        blank=True,
        null=True
    )

    creado_el = models.DateTimeField(
        auto_now_add=True
    )

    actualizado_el = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        ordering = ['-creado_el']
        indexes = [
            models.Index(
                fields=['institucion', 'paciente', 'estado']
            ),
            models.Index(
                fields=['creado_el']
            ),
        ]

    @property
    def subtotal(self):
        return self.cantidad * self.precio_unitario

    def __str__(self):
        return (
            f'{self.paciente.identificacion} - '
            f'{self.descripcion} - '
            f'${self.subtotal:.2f}'
        )
