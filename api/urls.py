from django.urls import path

from . import views


urlpatterns = [
    path(
        'catalogo/estudios/',
        views.catalogo_estudios,
        name='api_catalogo_estudios',
    ),
    path(
        'sync/estado/',
        views.sync_estado,
        name='api_sync_estado',
    ),
    path(
        'sync/usuarios/',
        views.sync_usuarios,
        name='api_sync_usuarios',
    ),
    path(
        'sync/push/',
        views.sync_push,
        name='api_sync_push',
    ),
    path(
        'sync/pull/',
        views.sync_pull,
        name='api_sync_pull',
    ),
]
