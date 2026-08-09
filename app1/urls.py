from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('producto/', views.productos, name='productos'),
    path('producto/<int:producto_id>/', views.productos, name='producto_detalle'),
    path('tienda/', views.tienda, name='tienda'),
    # Orden / carrito de orden
    path('carrito/', views.orden, name='carrito'),
    path('orden/', views.orden, name='orden'),
    path('orden/add/', views.orden_add, name='orden_add'),
    path('orden/validar-codigo-afiliado/', views.validar_codigo_afiliado, name='validar_codigo_afiliado'),
    # mantenemos rutas legacy
    path('guardar-contacto/', views.guardar_contacto, name='guardar_contacto'),
]