import uuid

from django.db import migrations, models
from django.utils import timezone


def preparar_esquema(apps, schema_editor):
    """
    SQLite: agregar las columnas directamente, evitando que Django
    reconstruya las tablas con un UUID único por defecto.
    """
    connection = schema_editor.connection

    with connection.cursor() as cursor:
        for table in ("core_paciente", "core_estudio"):
            cursor.execute(f"PRAGMA table_info({table})")
            columns = {row[1] for row in cursor.fetchall()}

            if "sync_id" not in columns:
                cursor.execute(
                    f"ALTER TABLE {table} ADD COLUMN sync_id char(32)"
                )

            if "actualizado_el" not in columns:
                cursor.execute(
                    f"ALTER TABLE {table} ADD COLUMN actualizado_el datetime"
                )

        # Generar un UUID diferente para cada registro existente.
        Paciente = apps.get_model("core", "Paciente")
        Estudio = apps.get_model("core", "Estudio")

        now = timezone.now()

        for obj in Paciente.objects.all().iterator():
            sync_id = uuid.uuid4().hex
            actualizado = now.isoformat(sep=" ")
            cursor.execute(
                f"UPDATE core_paciente SET sync_id = '{sync_id}', actualizado_el = '{actualizado}' WHERE id = {int(obj.pk)}"
            )

        for obj in Estudio.objects.all().iterator():
            sync_id = uuid.uuid4().hex
            actualizado = now.isoformat(sep=" ")
            cursor.execute(
                f"UPDATE core_estudio SET sync_id = '{sync_id}', actualizado_el = '{actualizado}' WHERE id = {int(obj.pk)}"
            )

        cursor.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS
            core_paciente_sync_id_unique
            ON core_paciente(sync_id)
            """
        )

        cursor.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS
            core_estudio_sync_id_unique
            ON core_estudio(sync_id)
            """
        )


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0044_modulo_limpieza_operativa"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(preparar_esquema, migrations.RunPython.noop),
            ],
            state_operations=[
                migrations.AddField(
                    model_name="paciente",
                    name="sync_id",
                    field=models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        unique=True,
                        verbose_name="Identificador de sincronización",
                    ),
                ),
                migrations.AddField(
                    model_name="paciente",
                    name="actualizado_el",
                    field=models.DateTimeField(auto_now=True),
                ),
                migrations.AddField(
                    model_name="estudio",
                    name="sync_id",
                    field=models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        unique=True,
                        verbose_name="Identificador de sincronización",
                    ),
                ),
                migrations.AddField(
                    model_name="estudio",
                    name="actualizado_el",
                    field=models.DateTimeField(auto_now=True),
                ),
            ],
        ),
    ]
