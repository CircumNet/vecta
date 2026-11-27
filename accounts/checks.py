from django.apps import apps
from django.core.checks import Error, register
from django.db import DatabaseError, connection


@register()
def database_schema_is_current(app_configs, **kwargs):
    """
    Fail fast, with a clear message, when the database was created by an older build of Vecta
    (a table exists but lacks columns the code expects). Without this, the first request that touches
    the missing column dies with a generic server error.
    """
    errors = []
    try:
        existing = set(connection.introspection.table_names())
        for label in ("accounts", "leave"):
            for model in apps.get_app_config(label).get_models():
                table = model._meta.db_table
                if table not in existing:
                    continue  # not migrated yet: Django's own "unapplied migrations" notice covers that
                with connection.cursor() as cur:
                    have = {c.name for c in connection.introspection.get_table_description(cur, table)}
                missing = [f.column for f in model._meta.local_concrete_fields if f.column not in have]
                if missing:
                    errors.append(Error(
                        f"The database table '{table}' is missing column(s): {', '.join(missing)}. "
                        "It was created by an older version of Vecta.",
                        hint="Development: delete db.sqlite3, then run `python manage.py migrate`. "
                             "Production: restore a backup taken before the upgrade and apply the migrations shipped with that release.",
                        id="vecta.E001",
                    ))
    except DatabaseError:
        pass
    return errors
