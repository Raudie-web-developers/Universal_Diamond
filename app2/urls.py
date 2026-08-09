from django.urls import path
from . import views
from django.contrib.auth import views as auth_views
urlpatterns = [
    path('login/', views.login, name='login'),
    path('registro/', views.registro, name='registro'),
    path('control_productos/', views.control_productos, name='control_productos'),
    path('personalizada/', views.personalizada, name='personalizada'),
    path('vip/', views.vip, name='vip'),
    path('solicitudes/', views.solicitudes_ordenes, name='solicitudes_ordenes'),
    path('orden/procesar/<int:orden_id>/', views.procesar_orden, name='procesar_orden'),
    path('orden/venta/<int:orden_id>/', views.marcar_orden_venta, name='marcar_orden_venta'),
    path('orden/no-venta/<int:orden_id>/', views.marcar_orden_no_venta, name='marcar_orden_no_venta'),
    path('clientes/', views.clientes_registrados, name='clientes_registrados'),
    path('configuracion/whatsapp/', views.configuracion_whatsapp, name='configuracion_whatsapp'),
    path('usuarios/', views.gestion_usuarios, name='usuarios'),
    path('afiliados/', views.afiliados, name='afiliados'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('sincronizar_diamantes/', views.sincronizar_diamantes, name='sincronizar_diamantes'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),

]