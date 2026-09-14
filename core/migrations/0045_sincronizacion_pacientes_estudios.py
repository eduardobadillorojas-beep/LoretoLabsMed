import uuid

from django.db import migrations, models
from django.utils import timezone


def preparar_esquema(apps, schema_editor):
    """
    Migración compatible con SQLite y PostgreSQL.

    No usamos AddField directamente sobre una columna UNIQUE con datos
    existentes, porque Django intentaría reconstruir la tabla y aplicar un
    mismo valor por defecto a todos los registros. Primero creamos las
    columnas sin restricción UNIQUE, llenamos cada registro con un UUID único
    y finalmente creamos índices únicos.
    """
    connection = schema_editor.connection
    quote = connection.ops.quote_name

    with connection.cursor() as cursor:
        for table in ("core_paciente", "core_estudio"):
            descripcion = connection.introspection.get_table_description(
                cursor, table
            )
            columns = {col.name for col in descripcion}

            if "sync_id" not in columns:
                if connection.vendor == "postgresql":
                    cursor.execute(
                        f'ALTER TABLE {quote(table)} '
                        f'ADD COLUMN {quote("sync_id")} uuid'
                    )
                else:
                    cursor.execute(
                        f'ALTER TABLE {quote(table)} '
                        f'ADD COLUMN {quote("sync_id")} char(32)'
                    )

            if "actualizado_el" not in columns:
                if connection.vendor == "postgresql":
                    cursor.execute(
                        f'ALTER TABLE {quote(table)} '
                        f'ADD COLUMN {quote("actualizado_el")} timestamptz'
                    )
                else:
                    cursor.execute(
                        f'ALTER TABLE {quote(table)} '
                        f'ADD COLUMN {quote("actualizado_el")} datetime'
                    )

        now = timezone.now().isoformat(sep=" ")

        for table in ("core_paciente", "core_estudio"):
            cursor.execute(
                f'SELECT {quote("id")} FROM {quote(table)} '
                f'WHERE {quote("sync_id")} IS NULL'
            )
            ids = [row[0] for row in cursor.fetchall()]

            for object_id in ids:
                sync_id = uuid.uuid4().hex
                # Los valores generados aquí contienen únicamente caracteres
                # seguros para SQL: UUID hexadecimal, fecha ISO y entero.
                cursor.execute(
                    f'UPDATE {quote(table)} '
                    f'SET {quote("sync_id")} = \'{sync_id}\', '
                    f'{quote("actualizado_el")} = \'{now}\' '
                    f'WHERE {quote("id")} = {int(object_id)}'
                )

            index_name = f"{table}_sync_id_unique"
            cursor.execute(
                f'CREATE UNIQUE INDEX IF NOT EXISTS {quote(index_name)} '
                f'ON {quote(table)} ({quote("sync_id")})'
            )


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0044_modulo_limpieza_operativa"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(
                    preparar_esquema,
                    migrations.RunPython.noop,
                ),
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
