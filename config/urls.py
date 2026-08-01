from django.contrib import admin
from django.urls import path
from core.views import (
    inicio, login_view, 
    panel_medico, panel_radiologo, 
    panel_recepcion, panel_config
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', inicio, name='inicio'),
    path('login/', login_view, name='login'),
    
    # Rutas para los módulos
    path('medicos/', panel_medico, name='medicos'),
    path('radiologia/', panel_radiologo, name='radiologia'),
    path('recepcion/', panel_recepcion, name='recepcion'),
    path('configuracion/', panel_config, name='configuracion'),
]