from django.conf import settings
from django.db import models


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