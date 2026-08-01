from django.contrib import admin
from django.urls import path
from core import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.inicio, name='inicio'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('medicos/', views.panel_medico, name='panel_medico'),
    path('radiologia/', views.panel_radiologo, name='panel_radiologo'),
    path('recepcion/', views.panel_recepcion, name='panel_recepcion'),
    path('configuracion/', views.panel_config, name='panel_config'),
]
]