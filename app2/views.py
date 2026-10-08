import datetime
import io

from django.db import models
from django.shortcuts import render, redirect, get_object_or_404
from urllib.parse import quote
from django.urls import reverse
from django.contrib import messages
from django.contrib.auth.hashers import check_password, make_password
from django.db.models import Q, Count, Sum, Max, Avg, F
from django.http import HttpResponse
from datetime import timedelta
from django.utils import timezone
from django.conf import settings
from .models import User_admin, AppConfig, Afiliado

import os
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.charts.barcharts import VerticalBarChart
from .crud import (
    crear_categoria,
    editar_categoria,
    obtener_categorias,
    crear_producto,
    obtener_productos,
    eliminar_producto,
    eliminar_categoria,
    actualizar_producto,
    obtener_usuarios_admin, 
    crear_usuario_admin, 
    actualizar_usuario_admin, 
    eliminar_usuario_admin,
    obtener_afiliados,
    crear_afiliado,
    actualizar_afiliado,
    eliminar_afiliado,
    convert_uploaded_image_to_webp,
)
from app1.models import Product, Orden, OrdenItem, Cliente, Category, ProductImage


def login(request):
    if request.method == 'POST':
        nombre = request.POST.get('nombre', '').strip()
        password = request.POST.get('password', '')

        try:
            user = User_admin.objects.get(nombre=nombre)
            if user.bloqueado:
                messages.error(request, 'Usuario bloqueado')
            elif user.password == password or check_password(password, user.password):
                request.session['user_admin_id'] = user.id
                return redirect('registro')
            else:
                messages.error(request, 'Contraseña incorrecta')
            return render(request, 'login.html')
        except User_admin.DoesNotExist:
            messages.error(request, 'Usuario no encontrado')
            return render(request, 'login.html')

    return render(request, 'login.html')


def registro(request):
    user_id = request.session.get('user_admin_id')
    if not user_id:
        messages.error(request, 'Debe iniciar sesión primero')
        return render(request, 'login.html')
    
    try:
        user = User_admin.objects.get(id=user_id)
    except User_admin.DoesNotExist:
        messages.error(request, 'Usuario no encontrado')
        return render(request, 'login.html')

    # --- PROCESAMIENTO DE FORMULARIOS (POST) ---


    if request.method == 'POST':

        # 1. CREAR CATEGORÍA (Con soporte multipadre)
        if 'crear_categoria' in request.POST:
            nombre_cat = request.POST.get('categoria_nombre', '').strip()
            padres_ids = request.POST.getlist('categoria_padres')
            icono_img = request.FILES.get('categoria_icono_img')
            if nombre_cat:
                try:
                    # Crear la categoría sin padres primero
                    nueva_categoria = Category.objects.create(nombre=nombre_cat)
                    # Asignar padres si hay
                    if padres_ids:
                        # Validar que la categoría no sea su propio padre (no aplica en creación, pero por seguridad)
                        padres_ids = [pid for pid in padres_ids if pid != str(nueva_categoria.id)]
                        nueva_categoria.padres.set(padres_ids)
                    # Guardar icono si aplica
                    if icono_img:
                        nueva_categoria.icono = icono_img
                        nueva_categoria.save()
                    messages.success(request, 'Categoría creada correctamente')
                except Exception as e:
                    messages.error(request, f'Error al crear la categoría: {e}')
            else:
                messages.error(request, 'El nombre de la categoría es obligatorio')

        if 'editar_categoria' in request.POST:
            cat_id = request.POST.get('editar_categoria_id')
            nuevo_nombre = request.POST.get('categoria_nombre', '').strip()
            nuevos_padres_ids = request.POST.getlist('categoria_padres')
            icono_img = request.FILES.get('categoria_icono_img')

            if cat_id and nuevo_nombre:
                try:
                    categoria = Category.objects.get(id=cat_id)
                    # Validación básica para evitar ciclos (una cat no puede ser su propio padre)
                    if nuevos_padres_ids and str(cat_id) in nuevos_padres_ids:
                        messages.error(request, 'Una categoría no puede ser su propio padre.')
                    else:
                        categoria.nombre = nuevo_nombre
                        if icono_img:
                            categoria.icono = icono_img
                        categoria.save()
                        # Asignar padres (puede ser vacío)
                        categoria.padres.set(nuevos_padres_ids)
                        messages.success(request, 'Categoría actualizada correctamente.')
                except Category.DoesNotExist:
                    messages.error(request, 'La categoría no existe.')
                except Exception as e:
                    messages.error(request, f'Error al actualizar: {e}')
            else:
                messages.error(request, 'Datos incompletos para editar.')

        # 2. CREAR PRODUCTO
        elif 'crear_producto' in request.POST:
                nombre = request.POST.get('nombre', '').strip()
                precio = request.POST.get('precio', '0')
                descripcion = request.POST.get('descripcion', '')
                categoria_ids = request.POST.getlist('categoria_ids') or None
                imagenes = request.FILES.getlist('imagenes')
                por_peso = request.POST.get('por_peso', '') == 'on'
                precios_por_peso_peso = request.POST.getlist('precios_por_peso_peso[]')
                precios_por_peso_precio = request.POST.getlist('precios_por_peso_precio[]')

                if nombre:
                    from app1.models import Product, PrecioPorPeso
                    from django.utils import timezone
                    producto = Product.objects.create(
                        nombre=nombre,
                        precio=precio,
                        descripcion=descripcion,
                        creado=timezone.now(),
                        por_peso=por_peso
                    )
                    if categoria_ids:
                        producto.categorias.set(categoria_ids)
                    # Guardar imágenes si aplica (tu lógica original)
                    # ...existing code...
                    # Guardar precios por peso si corresponde
                    if por_peso and precios_por_peso_peso and precios_por_peso_precio:
                        for peso, precio_peso in zip(precios_por_peso_peso, precios_por_peso_precio):
                            try:
                                peso_val = float(peso)
                                precio_val = float(precio_peso)
                                if peso_val > 0 and precio_val > 0:
                                    PrecioPorPeso.objects.create(producto=producto, peso=peso_val, precio=precio_val)
                            except Exception:
                                continue
                    messages.success(request, 'Producto creado correctamente.')
                else:
                    messages.error(request, 'El nombre del producto es obligatorio.')

        # 3. ELIMINAR PRODUCTO
        elif 'eliminar_producto' in request.POST:
            pid = request.POST.get('eliminar_producto')
            if pid:
                eliminar_producto(pid)
                messages.success(request, 'Producto eliminado')

        # 4. ELIMINAR CATEGORÍA
        elif 'eliminar_categoria' in request.POST:
            cid = request.POST.get('eliminar_categoria')
            if cid:
                eliminar_categoria(cid)
                messages.success(request, 'Categoría eliminada')

        # Patrón PRG (Post-Redirect-Get) para evitar reenvíos al refrescar
        return redirect(reverse('registro'))

    # --- MÉTODO GET (Renderizar página) ---
    
    # Asegúrate que 'obtener_categorias()' devuelva el queryset correctamente.
    # Si quieres optimizar la carga del árbol jerárquico (N+1 problem):
    # categorias = Category.objects.prefetch_related('subcategorias__subcategorias').all()
    categorias = obtener_categorias()
    productos = obtener_productos()
    
    return render(request, 'registro.html', {
        'productos': productos,
        'categorias': categorias,
    })


def get_whatsapp_empresa():
    telefono_ventas = AppConfig.get_valor('WHATSAPP_EMPRESA')
    if not telefono_ventas:
        telefono_ventas = getattr(settings, 'WHATSAPP_EMPRESA', '')
    return (telefono_ventas or '').strip()


def get_whatsapp_url():
    telefono_ventas = get_whatsapp_empresa()
    if not telefono_ventas:
        return None
    cleaned = ''.join(ch for ch in telefono_ventas if ch.isdigit())
    if cleaned.startswith('0'):
        cleaned = '58' + cleaned.lstrip('0')
    return f'https://wa.me/{cleaned}'


def personalizada(request):
    return render(request, 'personalizada.html', {
        'whatsapp_url': get_whatsapp_url(),
        'whatsapp_number': get_whatsapp_empresa(),
        'cart_count': 0,
    })


def vip(request):
    return render(request, 'vip.html', {
        'whatsapp_url': get_whatsapp_url(),
        'whatsapp_number': get_whatsapp_empresa(),
        'cart_count': 0,
    })


def control_productos(request):
    user_id = request.session.get('user_admin_id')
    if not user_id:
        messages.error(request, 'Debe iniciar sesión primero')
        return redirect('login')

    try:
        user = User_admin.objects.get(id=user_id)
    except User_admin.DoesNotExist:
        messages.error(request, 'Usuario no encontrado')
        return redirect('login')


    if request.method == 'POST':
        if 'editar_producto' in request.POST:
            producto_id = request.POST.get('editar_producto_id')
            imagenes_nuevas = request.FILES.getlist('imagenes_extras')
            nombre = request.POST.get('nombre', '').strip()
            precio = request.POST.get('precio', '0')
            descripcion = request.POST.get('descripcion', '')
            categoria_ids = request.POST.getlist('categoria_ids') or None
            por_peso = request.POST.get('por_peso', '') == 'on'
            precios_por_peso_peso = request.POST.getlist('precios_por_peso_peso[]')
            precios_por_peso_precio = request.POST.getlist('precios_por_peso_precio[]')

            try:
                from app1.models import PrecioPorPeso
                producto = Product.objects.get(id=producto_id)
                producto.nombre = nombre
                producto.precio = precio
                producto.descripcion = descripcion
                producto.por_peso = por_peso
                if categoria_ids:
                    producto.categorias.set(categoria_ids)
                producto.save()
                # Guardar imágenes si aplica (tu lógica original)
                # ...existing code...
                # Actualizar precios por peso
                if por_peso:
                    # Eliminar los precios por peso actuales
                    producto.precios_por_peso.all().delete()
                    for peso, precio_peso in zip(precios_por_peso_peso, precios_por_peso_precio):
                        try:
                            peso_val = float(peso)
                            precio_val = float(precio_peso)
                            if peso_val > 0 and precio_val > 0:
                                PrecioPorPeso.objects.create(producto=producto, peso=peso_val, precio=precio_val)
                        except Exception:
                            continue
                else:
                    # Si se desactiva por_peso, eliminar todos los precios por peso
                    producto.precios_por_peso.all().delete()
                messages.success(request, 'Producto actualizado correctamente.')
            except Product.DoesNotExist:
                messages.error(request, 'Producto no encontrado.')
            except Exception as e:
                messages.error(request, f'Error al actualizar producto: {e}')

        elif 'toggle_agotado' in request.POST:
            pid = request.POST.get('toggle_agotado')
            producto = get_object_or_404(Product, id=pid)
            producto.agotado = not producto.agotado
            producto.save()
            messages.success(request, f'Estado de "{producto.nombre}" actualizado.')

        elif 'eliminar_producto' in request.POST:
            pid = request.POST.get('eliminar_producto')
            try:
                producto = Product.objects.get(id=pid)
                nombre_producto = producto.nombre
                # Eliminar imagen si existe
                if producto.imagen:
                    producto.imagen.delete(save=False)
                # Eliminar el producto
                producto.delete()
                messages.success(request, f'Producto "{nombre_producto}" eliminado.')
            except Product.DoesNotExist:
                messages.error(request, 'Producto no encontrado.')

        # Siempre redirigir después de un POST exitoso
        return redirect(reverse('control_productos'))

    # --- Lógica GET para inventario de diamantes (EN VIVO) ---
    from app1.nivoda import NivodaAPI
    from app1.views import MockProduct

    q = request.GET.get('q', '').strip()
    shape_filter = request.GET.get('shape', '').strip()
    lab_filter = request.GET.get('lab', '').strip()
    page = int(request.GET.get('page', 1))

    limit = 20
    offset = (page - 1) * limit

    # We cannot search Nivoda effectively by cert_number or name easily with just one field, 
    # but let's assume we can filter by ID if it looks like one, or just ignore 'q' for now
    # Wait, Nivoda doesn't have a direct "search text" field in the GraphQL we mapped.
    # For now, we will just use shape and lab filters.

    shapes_param = [shape_filter.upper()] if shape_filter else None
    labs_param = [lab_filter.upper()] if lab_filter else ['GIA', 'HRD', 'IGI']

    try:
        api_res = NivodaAPI.search_diamonds(
            shapes=shapes_param,
            labs=labs_param,
            limit=limit,
            offset=offset
        )
        diamonds_list = [MockProduct(item) for item in api_res.get('items', [])]
    except Exception as e:
        print(f"Error calling Nivoda API in control panel: {e}")
        diamonds_list = []

    # Pagination math based on true total_count from API
    api_total_count = api_res.get("total_count", 0)
    import math
    total_pages = math.ceil(api_total_count / limit) if api_total_count > 0 else 1
    total_count = "{:,}".format(api_total_count)

    page_obj_has_previous = page > 1
    page_obj_has_next = page < total_pages
    page_obj_previous_page_number = page - 1
    page_obj_next_page_number = page + 1
    page_obj_number = page

    query_params = request.GET.copy()
    if 'page' in query_params:
        query_params.pop('page')
    url_params = query_params.urlencode()

    return render(request, 'control_productos.html', {
        'productos': diamonds_list,
        'page': page_obj_number,
        'has_prev': page_obj_has_previous,
        'has_next': page_obj_has_next,
        'prev_page': page_obj_previous_page_number,
        'next_page': page_obj_next_page_number,
        'total_pages': total_pages,
        'total_count': total_count,
        'url_params': url_params,
        'q': q,
        'shape_filter': shape_filter,
        'lab_filter': lab_filter,
    })
    
# Nueva vista: listar solicitudes de cotización
def solicitudes_ordenes(request):
    # --- 1. Autenticación (Código original) ---
    user_id = request.session.get('user_admin_id')
    if not user_id:
        messages.error(request, 'Debe iniciar sesión primero')
        return redirect('login')

    try:
        User_admin.objects.get(id=user_id)
    except Exception:
        messages.error(request, 'Usuario no encontrado')
        return redirect('login')

    # --- 2. QuerySet Base ---
    # Obtenemos la consulta base optimizada
    ordenes_qs = Orden.objects.select_related('cliente').prefetch_related('items__producto').all().order_by('-creado')

    # --- 3. Lógica de Filtros ---
    
    # A) Filtro de Texto (Buscador)
    query = (request.GET.get('q') or '').strip()
    if query:
        q_filters = (
            Q(cliente__nombre__icontains=query) |
            Q(cliente__correo__icontains=query) |
            Q(cliente__telefono__icontains=query)
        )

        if query.isdigit():
            q_filters = q_filters | Q(id=int(query))
        else:
            # también permite buscar texto parcial en estado
            q_filters = q_filters | Q(estado__icontains=query)

        ordenes_qs = ordenes_qs.filter(q_filters)

    # B) Filtro de Estado
    estado = request.GET.get('estado')
    if estado:
        # Usamos iexact para ignorar mayúsculas/minúsculas (ej: 'Pendiente' == 'pendiente')
        ordenes_qs = ordenes_qs.filter(estado__iexact=estado)

    # --- 4. Procesamiento de Datos (Usando el total guardado) ---
    solicitudes = []
    
    # Iteramos solo sobre las ordenes que pasaron los filtros
    for c in ordenes_qs:
        solicitudes.append({
            'orden': c,
            'items': list(c.items.all()),
            'subtotal': float(c.total),
        })

    # --- 5. Renderizado ---
    context = {
        'solicitudes': solicitudes,
        'SHOW_PRICES': True, # Variable para controlar si se ven columnas de precios en el HTML
    }

    return render(request, 'solicitudes_cotizacion.html', context)


def clientes_registrados(request):
    # 1. Autenticación de administrador
    user_id = request.session.get('user_admin_id')
    if not user_id:
        messages.error(request, 'Debe iniciar sesión primero')
        return redirect('login')

    try:
        User_admin.objects.get(id=user_id)
    except User_admin.DoesNotExist:
        messages.error(request, 'Usuario no encontrado')
        return redirect('login')

    q = request.GET.get('q', '').strip()
    clientes = Cliente.objects.all().order_by('-creado')
    if q:
        clientes = clientes.filter(
            Q(nombre__icontains=q) | Q(correo__icontains=q) | Q(telefono__icontains=q)
        )

    return render(request, 'clientes.html', {
        'clientes': clientes,
        'q': q,
    })


def procesar_orden(request, orden_id):
    # 1. Verificar autenticación
    user_id = request.session.get('user_admin_id')
    if not user_id:
        messages.error(request, 'Debe iniciar sesión primero')
        return redirect('login')

    # 2. Verificar que el usuario existe
    try:
        User_admin.objects.get(id=user_id)
    except User_admin.DoesNotExist:
        messages.error(request, 'Usuario no encontrado')
        return redirect('login')

    # 3. Obtener la orden
    orden = get_object_or_404(Orden, id=orden_id)

    # 4. Actualizar estado a 'procesado' si está pendiente
    if orden.estado.lower() in ['pendiente', 'nuevo', 'en revisión']:
        orden.estado = 'procesado'
        orden.save()
        messages.success(request, f"Orden #{orden.id} marcada como PROCESADA.")
    else:
        messages.info(request, f"Orden #{orden.id} ya tiene estado '{orden.estado}'.")

    # 5. Retornar al listado de solicitudes (historial)
    return redirect('solicitudes_ordenes')


def marcar_orden_venta(request, orden_id):
    user_id = request.session.get('user_admin_id')
    if not user_id:
        messages.error(request, 'Debe iniciar sesión primero')
        return redirect('login')

    try:
        User_admin.objects.get(id=user_id)
    except User_admin.DoesNotExist:
        messages.error(request, 'Usuario no encontrado')
        return redirect('login')

    orden = get_object_or_404(Orden, id=orden_id)
    orden.es_venta = True
    orden.estado = 'venta_confirmada'
    orden.fecha_venta = timezone.now()
    orden.save()

    messages.success(request, f"Orden #{orden.id} marcada como VENTA confirmada.")
    return redirect('solicitudes_ordenes')


def marcar_orden_no_venta(request, orden_id):
    user_id = request.session.get('user_admin_id')
    if not user_id:
        messages.error(request, 'Debe iniciar sesión primero')
        return redirect('login')

    try:
        User_admin.objects.get(id=user_id)
    except User_admin.DoesNotExist:
        messages.error(request, 'Usuario no encontrado')
        return redirect('login')

    orden = get_object_or_404(Orden, id=orden_id)
    orden.es_venta = False
    orden.estado = 'no_vendido'
    orden.save()

    messages.success(request, f"Orden #{orden.id} marcada como NO venta.")
    return redirect('solicitudes_ordenes')


def configuracion_whatsapp(request):
    user_id = request.session.get('user_admin_id')
    if not user_id:
        messages.error(request, 'Debe iniciar sesión primero')
        return redirect('login')

    try:
        User_admin.objects.get(id=user_id)
    except User_admin.DoesNotExist:
        messages.error(request, 'Usuario no encontrado')
        return redirect('login')

    from .crud import obtener_config, guardar_config
    whatsapp_empresa = obtener_config('WHATSAPP_EMPRESA', '')
    default_saludo = "Hola, deseo solicitar la compra/apartado de la siguiente orden de diamantes en Universal Diamond."
    whatsapp_saludo = obtener_config('WHATSAPP_SALUDO', default_saludo)

    nivoda_url = obtener_config('NIVODA_API_URL', 'https://intg-customer-staging.nivodaapi.net/api/diamonds')
    nivoda_user = obtener_config('NIVODA_USERNAME', 'testaccount@sample.com')
    nivoda_pass = obtener_config('NIVODA_PASSWORD', 'staging-nivoda-22')
    nivoda_markup = obtener_config('NIVODA_MARKUP_PERCENT', '0')

    if request.method == 'POST':
        # Formulario del número de WhatsApp
        if 'guardar_numero' in request.POST:
            nuevo_numero = request.POST.get('whatsapp_empresa', '').strip()
            if not nuevo_numero:
                messages.error(request, 'El número de WhatsApp es obligatorio.')
            else:
                guardar_config('WHATSAPP_EMPRESA', nuevo_numero)
                messages.success(request, 'Número de WhatsApp actualizado.')
                whatsapp_empresa = nuevo_numero

        # Formulario del saludo de WhatsApp
        elif 'guardar_saludo' in request.POST:
            nuevo_saludo = request.POST.get('whatsapp_saludo', '').strip()
            if nuevo_saludo:
                guardar_config('WHATSAPP_SALUDO', nuevo_saludo)
                messages.success(request, 'Saludo de WhatsApp actualizado.')
                whatsapp_saludo = nuevo_saludo
            else:
                guardar_config('WHATSAPP_SALUDO', default_saludo)
                messages.success(request, 'Saludo de WhatsApp restablecido al valor por defecto.')
                whatsapp_saludo = default_saludo

        # Formulario de credenciales Nivoda B2B API
        elif 'guardar_nivoda' in request.POST:
            url_val = request.POST.get('nivoda_api_url', '').strip()
            user_val = request.POST.get('nivoda_username', '').strip()
            pass_val = request.POST.get('nivoda_password', '').strip()
            markup_val = request.POST.get('nivoda_markup_percent', '0').strip()

            guardar_config('NIVODA_API_URL', url_val)
            guardar_config('NIVODA_USERNAME', user_val)
            guardar_config('NIVODA_PASSWORD', pass_val)
            guardar_config('NIVODA_MARKUP_PERCENT', markup_val)

            nivoda_url = url_val
            nivoda_user = user_val
            nivoda_pass = pass_val
            nivoda_markup = markup_val

            messages.success(request, 'Configuración de Nivoda API actualizada con éxito.')

    return render(request, 'configuracion_whatsapp.html', {
        'whatsapp_empresa': whatsapp_empresa,
        'whatsapp_saludo': whatsapp_saludo,
        'nivoda_url': nivoda_url,
        'nivoda_user': nivoda_user,
        'nivoda_pass': nivoda_pass,
        'nivoda_markup': nivoda_markup,
    })


def gestion_usuarios(request):
    # 1. Verificación de Seguridad: Solo usuarios logueados
    user_id_sesion = request.session.get('user_admin_id')
    if not user_id_sesion:
        messages.error(request, 'Debe iniciar sesión primero')
        return redirect('login')

    # 2. Procesamiento de Acciones (POST)
    if request.method == 'POST':
        
        # --- A. CREAR USUARIO ---
        if 'crear_usuario' in request.POST:
            nombre = request.POST.get('nombre', '').strip()
            password = request.POST.get('password', '')
            email = request.POST.get('email', '').strip()
            telefono = request.POST.get('telefono', '').strip()

            try:
                crear_usuario_admin(nombre, password, email, telefono)
                messages.success(request, f'Administrador "{nombre}" creado con éxito.')
            except ValueError as e:
                # Captura errores de validación (nombre duplicado, email duplicado, etc.)
                messages.error(request, str(e))
            except Exception as e:
                # Captura cualquier otro error inesperado
                messages.error(request, f"Error inesperado al crear: {e}")

        # --- B. EDITAR USUARIO ---
        elif 'editar_usuario' in request.POST:
            uid = request.POST.get('usuario_id')
            nombre = request.POST.get('nombre', '').strip()
            email = request.POST.get('email', '').strip()
            telefono = request.POST.get('telefono', '').strip()
            password = request.POST.get('password', '') 
            bloqueado = 'bloqueado' in request.POST

            # Seguridad: No permitir que el admin actual se bloquee a sí mismo
            if uid and int(uid) == user_id_sesion and bloqueado:
                messages.warning(request, "Operación cancelada: No puedes bloquear tu propia cuenta mientras estás en sesión.")
                bloqueado = False

            try:
                actualizar_usuario_admin(
                    uid, 
                    nombre=nombre, 
                    email=email, 
                    telefono=telefono, 
                    password=password, 
                    bloqueado=bloqueado
                )
                messages.success(request, f"Datos de '{nombre}' actualizados correctamente.")
            except ValueError as e:
                # Captura errores de validación en la edición (ej: intentar usar el email de otro admin)
                messages.error(request, str(e))
            except Exception as e:
                messages.error(request, f"Error al actualizar: {e}")

        # --- C. ELIMINAR USUARIO ---
        elif 'eliminar_usuario' in request.POST:
            uid = request.POST.get('eliminar_usuario')
            
            if uid and int(uid) == user_id_sesion:
                messages.error(request, "No puedes eliminar tu propia cuenta mientras la estás usando.")
            else:
                try:
                    eliminar_usuario_admin(uid)
                    messages.success(request, "Usuario eliminado permanentemente.")
                except Exception as e:
                    messages.error(request, f"No se pudo eliminar el usuario: {e}")

        # Redirección tras POST (Patrón PRG)
        return redirect('usuarios')

    # 3. Carga de datos para mostrar la página (GET)
    usuarios = obtener_usuarios_admin()
    
    return render(request, 'gestion_usuarios.html', {
        'usuarios': usuarios,
        'user_id_sesion': user_id_sesion 
    })


def afiliados(request):
    user_id_sesion = request.session.get('user_admin_id')
    if not user_id_sesion:
        messages.error(request, 'Debe iniciar sesión primero')
        return redirect('login')

    if request.method == 'POST':
        if 'crear_afiliado' in request.POST:
            nombre = request.POST.get('nombre', '').strip()
            codigo = request.POST.get('codigo', '').strip().upper()
            descuento = request.POST.get('descuento', '0').strip()
            comision = request.POST.get('comision', '0').strip()
            try:
                crear_afiliado(nombre, codigo=codigo, descuento=descuento, comision=comision)
                messages.success(request, f'Afiliado "{nombre}" creado con éxito.')
            except ValueError as e:
                messages.error(request, str(e))
            except Exception as e:
                messages.error(request, f'Error inesperado al crear afiliado: {e}')

        elif 'editar_afiliado' in request.POST:
            afiliado_id = request.POST.get('afiliado_id')
            nombre = request.POST.get('nombre', '').strip()
            codigo = request.POST.get('codigo', '').strip().upper()
            descuento = request.POST.get('descuento', '0').strip()
            comision = request.POST.get('comision', '0').strip()
            activo = 'activo' in request.POST
            try:
                actualizar_afiliado(
                    afiliado_id,
                    nombre=nombre,
                    codigo=codigo,
                    descuento=descuento,
                    comision=comision,
                    activo=activo
                )
                messages.success(request, f'Afiliado "{nombre}" actualizado correctamente.')
            except ValueError as e:
                messages.error(request, str(e))
            except Exception as e:
                messages.error(request, f'Error inesperado al actualizar afiliado: {e}')

        elif 'eliminar_afiliado' in request.POST:
            afiliado_id = request.POST.get('eliminar_afiliado')
            try:
                eliminar_afiliado(afiliado_id)
                messages.success(request, 'Afiliado eliminado correctamente.')
            except Exception as e:
                messages.error(request, f'No se pudo eliminar el afiliado: {e}')

        return redirect('afiliados')

    afiliados = obtener_afiliados()
    return render(request, 'afiliados.html', {
        'afiliados': afiliados,
        'user_id_sesion': user_id_sesion,
    })


def dashboard(request):
    # 1. Verificación de autenticación
    user_id = request.session.get('user_admin_id')
    if not user_id:
        messages.error(request, 'Debe iniciar sesión primero')
        return redirect('login')

    try:
        user = User_admin.objects.get(id=user_id)
    except User_admin.DoesNotExist:
        messages.error(request, 'Usuario no encontrado')
        return redirect('login')

    # 2. Estadísticas generales
    hoy = timezone.now().date()
    fecha_inicio_mes = hoy.replace(day=1)
    fecha_fin_mes = hoy

    # Filtros de rango de fecha desde interfaz (GET)
    desde_str = request.GET.get('desde', '').strip()
    hasta_str = request.GET.get('hasta', '').strip()

    def parse_date(value):
        try:
            return timezone.datetime.strptime(value, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            return None

    fecha_desde = parse_date(desde_str) or fecha_inicio_mes
    fecha_hasta = parse_date(hasta_str) or fecha_fin_mes
    fecha_hasta_original = fecha_hasta

    if request.method == 'POST' and request.POST.get('generar_pdf'):
        fecha_desde = parse_date(request.POST.get('desde', '').strip()) or fecha_inicio_mes
        fecha_hasta_original = parse_date(request.POST.get('hasta', '').strip()) or fecha_fin_mes
        fecha_hasta = fecha_hasta_original + timedelta(days=1)

        ventas_confirmadas_pdf = Orden.objects.filter(
            es_venta=True,
            fecha_venta__gte=fecha_desde,
            fecha_venta__lt=fecha_hasta,
        )
        total_ventas_pdf = ventas_confirmadas_pdf.aggregate(total=Sum('total'))['total'] or 0
        total_ordenes_pdf = ventas_confirmadas_pdf.count()
        ticket_promedio_pdf = total_ventas_pdf / total_ordenes_pdf if total_ordenes_pdf > 0 else 0

        productos_mas_vendidos_pdf = OrdenItem.objects.filter(
            orden__es_venta=True,
            orden__fecha_venta__gte=fecha_desde,
            orden__fecha_venta__lt=fecha_hasta,
        ).values(
            producto__nombre=F('producto__nombre')
        ).annotate(total_vendido=Sum('cantidad')).order_by('-total_vendido')[:10]

        afiliado_ventas_qs = ventas_confirmadas_pdf.exclude(codigo_afiliado__isnull=True).exclude(codigo_afiliado='')
        afiliados_por_codigo_pdf = afiliado_ventas_qs.values('codigo_afiliado').annotate(
            total_ventas=Sum('total'),
            ordenes=Count('id'),
            descuento_aplicado=Max('descuento_afiliado')
        ).order_by('-total_ventas')

        codigos_pdf = [item['codigo_afiliado'] for item in afiliados_por_codigo_pdf]
        afiliados_info_pdf = {
            afiliado['codigo']: {
                'nombre': afiliado['nombre'],
                'comision': float(afiliado['comision'] or 0),
            }
            for afiliado in Afiliado.objects.filter(codigo__in=codigos_pdf).values('codigo', 'nombre', 'comision')
        }

        afiliados_por_codigo_pdf = [
            {
                'codigo': item['codigo_afiliado'],
                'nombre': afiliados_info_pdf.get(item['codigo_afiliado'], {}).get('nombre', 'Sin nombre'),
                'comision_porcentaje': afiliados_info_pdf.get(item['codigo_afiliado'], {}).get('comision', 0),
                'ordenes': item['ordenes'],
                'total_ventas': float(item['total_ventas']),
                'total_comision': float(item['total_ventas']) * (afiliados_info_pdf.get(item['codigo_afiliado'], {}).get('comision', 0) / 100),
                'descuento_aplicado': item['descuento_aplicado'] or 0,
            }
            for item in afiliados_por_codigo_pdf
        ]

        total_comisiones_pdf = sum(item['total_comision'] for item in afiliados_por_codigo_pdf)

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            leftMargin=40,
            rightMargin=40,
            topMargin=60,
            bottomMargin=40,
        )

        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(name='ReportSubtitle', fontName='Helvetica', fontSize=10, leading=12, textColor=colors.HexColor('#6b7280')))
        styles.add(ParagraphStyle(name='ReportSection', fontName='Helvetica-Bold', fontSize=14, spaceAfter=10))
        styles.add(ParagraphStyle(name='ReportSmall', fontName='Helvetica', fontSize=9, leading=11))

        elements = []

        logo_path = os.path.join(settings.BASE_DIR, 'assets', 'images', 'logo.png')
        if os.path.exists(logo_path):
            logo = Image(logo_path, width=64, height=64)
            header_table = Table(
                [
                    [
                        logo,
                        Paragraph(
                            '<b>Informe de Ventas</b><br/>Resumen del periodo seleccionado con ventas, productos top y resultados por afiliado.',
                            styles['ReportSubtitle'],
                        ),
                    ]
                ],
                colWidths=[70, 430],
            )
            header_table.setStyle(
                TableStyle([
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('LEFTPADDING', (0, 0), (-1, -1), 0),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                ])
            )
            elements.append(header_table)
        else:
            elements.append(Paragraph('Informe de Ventas', styles['Title']))
            elements.append(Paragraph('Resumen del periodo seleccionado con ventas, productos top y resultados por afiliado.', styles['ReportSubtitle']))

        elements.append(Spacer(1, 14))
        elements.append(Paragraph('Resumen general', styles['ReportSection']))

        summary_data = [
            ['Métrica', 'Valor', 'Métrica', 'Valor'],
            ['Total ventas', f'${total_ventas_pdf:,.2f}', 'Órdenes vendidas', str(total_ordenes_pdf)],
            ['Ticket promedio', f'${ticket_promedio_pdf:,.2f}', 'Comisión total', f'${total_comisiones_pdf:,.2f}'],
        ]
        summary_table = Table(summary_data, colWidths=[120, 120, 120, 120])
        summary_table.setStyle(
            TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#111827')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d1d5db')),
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8fafc')),
            ])
        )
        elements.append(summary_table)
        elements.append(Spacer(1, 18))

        if productos_mas_vendidos_pdf:
            elements.append(Paragraph('Productos más vendidos', styles['ReportSection']))
            chart_data = [[float(item['total_vendido']) for item in productos_mas_vendidos_pdf[:6]]]
            chart_labels = [item['producto__nombre'][:18] for item in productos_mas_vendidos_pdf[:6]]
            drawing = Drawing(450, 200)
            chart = VerticalBarChart()
            chart.x = 40
            chart.y = 20
            chart.height = 140
            chart.width = 360
            chart.data = chart_data
            chart.strokeColor = colors.HexColor('#111827')
            chart.valueAxis.valueMin = 0
            max_value = float(max(chart_data[0])) if chart_data[0] else 0
            chart.valueAxis.valueMax = max_value * 1.2 if max_value > 0 else 10
            chart.valueAxis.valueStep = max(int(chart.valueAxis.valueMax / 5), 1)
            chart.categoryAxis.categoryNames = chart_labels
            chart.categoryAxis.labels.angle = 45
            chart.categoryAxis.labels.boxAnchor = 'ne'
            chart.categoryAxis.labels.fontName = 'Helvetica'
            chart.categoryAxis.labels.fontSize = 8
            chart.bars[0].fillColor = colors.HexColor('#4f46e5')
            drawing.add(chart)
            elements.append(drawing)
            elements.append(Spacer(1, 12))

            productos_table_data = [['#', 'Producto', 'Cantidad vendida']]
            for idx, producto in enumerate(productos_mas_vendidos_pdf[:10], start=1):
                productos_table_data.append([str(idx), producto['producto__nombre'], str(producto['total_vendido'])])
            producto_table = Table(productos_table_data, colWidths=[30, 330, 90])
            producto_table.setStyle(
                TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#111827')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('ALIGN', (-1, 1), (-1, -1), 'RIGHT'),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d1d5db')),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                ])
            )
            elements.append(producto_table)
            elements.append(Spacer(1, 18))
        else:
            elements.append(Paragraph('No hay productos vendidos en este rango.', styles['ReportSmall']))
            elements.append(Spacer(1, 18))

        elements.append(Paragraph('Ventas por afiliado', styles['ReportSection']))
        if afiliados_por_codigo_pdf:
            affiliate_chart_data = [[float(item['total_ventas']) for item in afiliados_por_codigo_pdf[:6]]]
            affiliate_labels = [item['nombre'][:18] for item in afiliados_por_codigo_pdf[:6]]
            affiliate_drawing = Drawing(450, 200)
            affiliate_chart = VerticalBarChart()
            affiliate_chart.x = 40
            affiliate_chart.y = 20
            affiliate_chart.height = 140
            affiliate_chart.width = 360
            affiliate_chart.data = affiliate_chart_data
            affiliate_chart.strokeColor = colors.HexColor('#111827')
            affiliate_chart.valueAxis.valueMin = 0
            max_aff = float(max(affiliate_chart_data[0])) if affiliate_chart_data[0] else 0
            affiliate_chart.valueAxis.valueMax = max_aff * 1.2 if max_aff > 0 else 10
            affiliate_chart.valueAxis.valueStep = max(int(affiliate_chart.valueAxis.valueMax / 5), 1)
            affiliate_chart.categoryAxis.categoryNames = affiliate_labels
            affiliate_chart.categoryAxis.labels.angle = 45
            affiliate_chart.categoryAxis.labels.boxAnchor = 'ne'
            affiliate_chart.categoryAxis.labels.fontName = 'Helvetica'
            affiliate_chart.categoryAxis.labels.fontSize = 8
            affiliate_chart.bars[0].fillColor = colors.HexColor('#0ea5e9')
            affiliate_drawing.add(affiliate_chart)
            elements.append(affiliate_drawing)
            elements.append(Spacer(1, 12))

            afiliado_table_data = [['Afiliado', 'Código', 'Comisión %', 'Total vendido', 'Pagar comisión']]
            for item in afiliados_por_codigo_pdf:
                afiliado_table_data.append([
                    item['nombre'],
                    item['codigo'],
                    f'{item["comision_porcentaje"]:.2f}%',
                    f'${item["total_ventas"]:.2f}',
                    f'${item["total_comision"]:.2f}',
                ])
            afiliado_table = Table(afiliado_table_data, colWidths=[180, 80, 80, 90, 120])
            afiliado_table.setStyle(
                TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#111827')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('ALIGN', (2, 1), (4, -1), 'RIGHT'),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d1d5db')),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                ])
            )
            elements.append(afiliado_table)
        else:
            elements.append(Paragraph('No se registraron ventas por afiliado en este rango.', styles['ReportSmall']))

        def add_page_number(canvas_obj, doc_obj):
            canvas_obj.setFont('Helvetica', 8)
            canvas_obj.drawRightString(letter[0] - 40, 20, f'Página {doc_obj.page}')

        doc.build(elements, onFirstPage=add_page_number, onLaterPages=add_page_number)
        buffer.seek(0)

        response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="informe_ventas.pdf"'
        return response

    # Ajustar fecha_hasta para incluir todo el día
    fecha_hasta = fecha_hasta + timedelta(days=1)

    # Consultar ventas confirmadas dentro del rango de fechas
    ventas_confirmadas = Orden.objects.filter(es_venta=True, fecha_venta__range=[fecha_desde, fecha_hasta])
    total_ventas_confirmadas = ventas_confirmadas.aggregate(total=Sum('total'))['total'] or 0

    # Total de órdenes dentro del rango de fechas
    ordenes_rango = Orden.objects.filter(creado__date__range=[fecha_desde, fecha_hasta])
    total_ordenes_mes = ordenes_rango.count()

    # Calcular ingresos, ticket promedio y tasa de conversión
    ingresos_mes = total_ventas_confirmadas
    ticket_promedio = ingresos_mes / ventas_confirmadas.count() if ventas_confirmadas.count() > 0 else 0

    # Asegurarse de que total_ordenes_mes no sea cero antes de calcular la tasa de conversión
    if total_ordenes_mes > 0:
        tasa_conversion = (ventas_confirmadas.count() / total_ordenes_mes) * 100
    else:
        tasa_conversion = 0

    # Validar valores para evitar errores en el contexto
    ingresos_mes = round(ingresos_mes, 2)
    ticket_promedio = round(ticket_promedio, 2)
    tasa_conversion = round(tasa_conversion, 1)  # Ajustar a un decimal

    # Órdenes por estado dentro del rango de fechas
    ordenes_por_estado = ordenes_rango.values('estado').annotate(count=Count('id')).order_by('-count')

    total_productos = Product.objects.count()
    productos_agotados = Product.objects.filter(agotado=True).count()
    productos_disponibles = total_productos - productos_agotados

    porcentaje_agotados = (productos_agotados / total_productos * 100) if total_productos > 0 else 0
    porcentaje_disponibles = 100 - porcentaje_agotados

    clientes_recientes = Cliente.objects.annotate(
        ultima_orden=Max('ordenes__creado'),
        total_gastado=Sum('ordenes__total', filter=Q(ordenes__es_venta=True)),
        num_ordenes=Count('ordenes', filter=Q(ordenes__es_venta=True))
    ).order_by('-ultima_orden')[:5]

    productos_mas_vendidos = OrdenItem.objects.filter(orden__es_venta=True).values(
        producto__nombre=F('producto__nombre')
    ).annotate(total_vendido=Sum('cantidad')).order_by('-total_vendido')[:10]

    total_clientes = Cliente.objects.count()
    total_ordenes_procesadas = Orden.objects.filter(estado__iexact='procesado').count()

    ultimos_12_meses = [
        {
            'mes': (hoy.replace(day=1) - timedelta(days=i * 30)).strftime('%b %Y'),
            'count': Orden.objects.filter(
                creado__year=(hoy - timedelta(days=i * 30)).year,
                creado__month=(hoy - timedelta(days=i * 30)).month
            ).count()
        }
        for i in range(12)
    ]

    context = {
        'fecha_desde': fecha_desde,
        'fecha_hasta': fecha_hasta - timedelta(days=1),  # Mostrar la fecha original en el contexto
        'total_ordenes_mes': total_ordenes_mes,
        'ingresos_mes': ingresos_mes,
        'ticket_promedio': ticket_promedio,
        'total_productos': total_productos,
        'productos_agotados': productos_agotados,
        'productos_disponibles': productos_disponibles,
        'porcentaje_agotados': round(porcentaje_agotados, 1),
        'porcentaje_disponibles': round(porcentaje_disponibles, 1),
        'total_clientes': total_clientes,
        'total_ordenes_procesadas': total_ordenes_procesadas,
        'clientes_recientes': clientes_recientes,
        'productos_mas_vendidos': productos_mas_vendidos,
        'ordenes_por_estado': list(ordenes_por_estado),
        'ultimos_12_meses': ultimos_12_meses,
    }

    return render(request, 'dashboard.html', context)


def sincronizar_diamantes(request):
    user_id = request.session.get('user_admin_id')
    if not user_id:
        messages.error(request, 'Debe iniciar sesión primero')
        return redirect('login')

    if request.method == 'POST':
        limit_str = request.POST.get('limit', '100')
        limit = int(limit_str) if limit_str.isdigit() else 100
        shapes = request.POST.getlist('shapes')
        ignore_repeats = request.POST.get('ignore_repeats') == '1'

        try:
            from app1.nivoda import NivodaAPI
            res = NivodaAPI.sync_diamonds_to_db(limit=limit, shapes=shapes, ignore_repeats=ignore_repeats)
            messages.success(
                request,
                f"¡Sincronización completada! {res['total_fetched']} diamantes procesados desde Nivoda API. "
                f"Nuevos en BD: {res['created']}, Actualizados: {res['updated']}."
            )
        except Exception as e:
            print(f"Error sincronizando diamantes: {e}")
            messages.error(request, f"Error durante la sincronización con Nivoda API: {e}")

    return redirect(request.META.get('HTTP_REFERER', reverse('control_productos')))


