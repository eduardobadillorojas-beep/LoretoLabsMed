from django.urls import path
from .views import recepcion_dashboard

urlpatterns = [
    path('', recepcion_dashboard, name='recepcion'),
]