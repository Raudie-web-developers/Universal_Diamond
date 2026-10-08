from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.urls import reverse
from django.contrib import messages
from .models import Category, Product
from . import crud
import random
from django.conf import settings
from urllib.parse import quote
from decimal import Decimal
from app2.models import AppConfig, Afiliado
from django.utils import timezone
from .nivoda import NivodaAPI

class MockProduct:
    def __init__(self, data):
        self.id = data.get("diamond_id") or data.get("id")
        self.nivoda_id = self.id
        self.is_diamond = True
        self.shape = data.get("shape") or 'ROUND'
        self.carats = data.get("carats") or 0.0
        self.color = data.get("color") or '-'
        self.clarity = data.get("clarity") or '-'
        self.lab = data.get("lab") or 'GIA'
        self.cert_number = data.get("cert_number") or ''
        self.precio = data.get("price") or 0.0
        self.image_url = data.get("image") or ''
        self.video_url = data.get("video") or ''
        self.v360_url = data.get("v360") or ''
        self.cut = data.get("cut") or '-'
        self.polish = data.get("polish") or '-'
        self.cert_pdf = data.get("pdf_url") or ''
        
        self.nombre = f"Diamante {self.carats} ct {self.shape} ({self.color}/{self.clarity} - {self.lab})"
        self.descripcion = f"Diamante certificado por {self.lab}. Certificado #: {self.cert_number or 'N/A'}"

    @property
    def imagen_display_url(self):
        return self.image_url

    @property
    def pk(self):
        return self.id


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


def _get_cart_count(request):
    cart = request.session.get('orden', {}) or {}
    try:
        total = 0
        for v in cart.values():
            if isinstance(v, dict):
                total += int(v.get('cantidad', 0))
            else:
                total += int(v)
        return total
    except Exception:
        return 0


from django.db.models import Sum, Min


from .nivoda import NivodaAPI
import json
from math import ceil

def index(request):
    cart_count = _get_cart_count(request)
    whatsapp_url = get_whatsapp_url()
    whatsapp_number = get_whatsapp_empresa()
    whatsapp_number_clean = ''.join(ch for ch in whatsapp_number if ch.isdigit()) if whatsapp_number else ''

    from django.db.models import Case, When, Value, IntegerField, Q
    # Featured diamonds from local DB prioritizing items with real images
    featured_diamonds = Product.objects.filter(is_diamond=True).annotate(
        has_valid_img=Case(
            When(
                (Q(imagen__isnull=False) & ~Q(imagen='')) |
                (Q(image_url__isnull=False) & ~Q(image_url='') & ~Q(image_url__icontains='aHR0c')),
                then=Value(1)
            ),
            default=Value(0),
            output_field=IntegerField()
        )
    ).order_by('-has_valid_img', '-carats')[:6]

    shapes_grid = [
        {'name': 'Round', 'code': 'ROUND', 'icon': '💎'},
        {'name': 'Oval', 'code': 'OVAL', 'icon': '🥚'},
        {'name': 'Cushion', 'code': 'CUSHION', 'icon': '🔲'},
        {'name': 'Princess', 'code': 'PRINCESS', 'icon': '⬛'},
        {'name': 'Emerald', 'code': 'EMERALD', 'icon': '▭'},
        {'name': 'Radiant', 'code': 'RADIANT', 'icon': '🔹'},
        {'name': 'Pear', 'code': 'PEAR', 'icon': '💧'},
        {'name': 'Marquise', 'code': 'MARQUISE', 'icon': '👁️'},
    ]

    return render(request, 'index.html', {
        'featured_diamonds': featured_diamonds,
        'shapes_grid': shapes_grid,
        'cart_count': cart_count,
        'whatsapp_url': whatsapp_url,
        'whatsapp_number': whatsapp_number,
        'whatsapp_number_clean': whatsapp_number_clean,
    })


def tienda(request):
    from django.db.models import Q, Case, When, Value, IntegerField
    from django.core.paginator import Paginator

    # Retrieve diamond filter parameters from GET
    selected_type = (request.GET.get('tipo') or request.GET.get('type') or request.GET.get('diamond_type') or '').lower().strip()
    selected_subtipo = (request.GET.get('subtipo') or request.GET.get('subtype') or '').lower().strip()

    selected_shapes = request.GET.getlist('shape')
    if not selected_shapes and request.GET.get('shape'):
        selected_shapes = [request.GET.get('shape')]

    selected_colors = request.GET.getlist('color')
    selected_clarities = request.GET.getlist('clarity')
    selected_cuts = request.GET.getlist('cut')
    selected_labs = request.GET.getlist('lab')

    has_image = request.GET.get('has_image', '1') == '1'
    has_video = request.GET.get('has_video') == '1'
    returnable = request.GET.get('returnable') == '1'
    express = request.GET.get('express') == '1'

    def _get_float(key, default=None):
        val = request.GET.get(key, '').strip()
        if val:
            try:
                return float(val)
            except ValueError:
                pass
        return default

    min_carats = _get_float('min_carats')
    max_carats = _get_float('max_carats')
    min_price = _get_float('min_price')
    max_price = _get_float('max_price')

    order_by = request.GET.get('order_by', 'price')
    order_dir = request.GET.get('order_dir', 'ASC')

    try:
        page = int(request.GET.get('page', '1'))
        if page < 1:
            page = 1
    except ValueError:
        page = 1

    limit = 12
    offset = (page - 1) * limit

    # Check if we should query Nivoda API directly
    is_diamond_query = True

    if is_diamond_query:
        # Determine labs parameter based on type
        labs_param = [l.upper() for l in selected_labs if l]
        if not labs_param:
            if selected_type in ('natural', 'melee_natural'):
                labs_param = ['GIA', 'HRD']
            elif selected_type in ('lab_grown', 'lab', 'melee_lab'):
                labs_param = ['IGI']
            else:
                labs_param = ['GIA', 'HRD', 'IGI'] # default to reliable labs

        min_carats_param = min_carats
        max_carats_param = max_carats

        if selected_type in ('melee_natural', 'melee_lab'):
            if max_carats_param is None or max_carats_param > 0.20:
                max_carats_param = 0.20
        else:
            if min_carats_param is None or min_carats_param <= 0.20:
                min_carats_param = 0.21

        try:
            api_res = NivodaAPI.search_diamonds(
                shapes=selected_shapes,
                min_carats=min_carats_param,
                max_carats=max_carats_param,
                colors=selected_colors,
                clarities=selected_clarities,
                cuts=selected_cuts,
                labs=labs_param,
                min_price=min_price,
                max_price=max_price,
                has_image=has_image,
                has_v360=has_video,
                limit=limit * 2, # Fetch extra for frontend backups
                offset=offset,
                order_by=order_by,
                order_dir=order_dir
            )
            diamonds_list = [MockProduct(item) for item in api_res.get('items', [])]
        except Exception as e:
            print(f"Error calling Nivoda API: {e}")
            diamonds_list = []

        # Pagination math based on true total_count from API
        api_total_count = api_res.get("total_count", 0)
        import math
        total_pages = math.ceil(api_total_count / limit) if api_total_count > 0 else 1
        total_count = "{:,}".format(api_total_count) # format with commas

        page_obj_has_previous = page > 1
        page_obj_has_next = page < total_pages
        page_obj_previous_page_number = page - 1
        page_obj_next_page_number = page + 1
        page_obj_number = page
        
    else:
        # Local DB Query for non-diamond products (or fallback if no type selected)
        qs = Product.objects.filter(is_diamond=False)

        selected_shapes_upper = [s.upper() for s in selected_shapes if s]
        if selected_shapes_upper:
            qs = qs.filter(shape__in=selected_shapes_upper)

        if min_price is not None:
            qs = qs.filter(precio__gte=min_price)
        if max_price is not None:
            qs = qs.filter(precio__lte=max_price)

        if order_by == 'carats':
            order_field = '-carats' if order_dir.upper() == 'DESC' else 'carats'
        else:
            order_field = '-precio' if order_dir.upper() == 'DESC' else 'precio'

        qs = qs.order_by(order_field)

        paginator = Paginator(qs, limit)
        page_obj = paginator.get_page(page)
        
        diamonds_list = page_obj.object_list
        total_count = paginator.count
        total_pages = paginator.num_pages
        page_obj_has_previous = page_obj.has_previous()
        page_obj_has_next = page_obj.has_next()
        page_obj_previous_page_number = page_obj.previous_page_number() if page_obj.has_previous() else 1
        page_obj_next_page_number = page_obj.next_page_number() if page_obj.has_next() else 1
        page_obj_number = page_obj.number

    cart_count = _get_cart_count(request)
    whatsapp_url = get_whatsapp_url()
    whatsapp_number = get_whatsapp_empresa()

    all_shapes = ['ROUND', 'OVAL', 'CUSHION', 'PRINCESS', 'EMERALD', 'RADIANT', 'PEAR', 'MARQUISE', 'HEART', 'ASSCHER']
    all_colors = ['D', 'E', 'F', 'G', 'H', 'I', 'J', 'K']
    all_clarities = ['FL', 'IF', 'VVS1', 'VVS2', 'VS1', 'VS2', 'SI1', 'SI2', 'I1']
    all_cuts = ['IDEAL', 'EXCELLENT', 'VERY_GOOD', 'GOOD']
    all_labs = ['GIA', 'IGI', 'HRD', 'EGL']

    # Custom banner info for selected section
    if selected_type == 'natural':
        banner_info = {
            'title': 'Diamantes Naturales',
            'desc': 'Diamantes 100% naturales de mina certificados internacionalmente por GIA, HRD e IGI.',
            'action_text': 'Explorar Diamantes Naturales →',
            'bg_type': 'natural'
        }
    elif selected_type in ('lab_grown', 'lab'):
        banner_info = {
            'title': 'Diamantes de Laboratorio',
            'desc': 'Diamantes cultivados (Lab-Grown) de idéntica pureza, brillo y dureza con certificación oficial.',
            'action_text': 'Explorar Lab-Grown →',
            'bg_type': 'lab'
        }
    elif selected_type == 'melee_natural':
        banner_info = {
            'title': 'Melee Naturales',
            'desc': 'Diamantes naturales de calibre fino (≤ 0.20 ct) ideales para pavé, montura y engastes de precisión.',
            'action_text': 'Explorar Melee Naturales →',
            'bg_type': 'melee_natural'
        }
    elif selected_type == 'melee_lab':
        banner_info = {
            'title': 'Melee de Laboratorio',
            'desc': 'Diamantes melee cultivados (≤ 0.20 ct) calibrados para producción y diseños modernos.',
            'action_text': 'Explorar Melee Laboratorio →',
            'bg_type': 'melee_lab'
        }
    else:
        banner_info = {
            'title': 'Tienda de Diamantes',
            'desc': 'Explora nuestro inventario completo de diamantes naturales y lab-grown certificados por GIA, IGI y HRD.',
            'action_text': 'Explorar Catálogo →',
            'bg_type': 'tienda'
        }

    query_params = request.GET.copy()
    if 'page' in query_params:
        query_params.pop('page')
    url_params = query_params.urlencode()

    return render(request, 'tienda.html', {
        'diamonds': diamonds_list,
        'total_count': total_count,
        'page': page_obj_number,
        'total_pages': total_pages,
        'has_prev': page_obj_has_previous,
        'has_next': page_obj_has_next,
        'prev_page': page_obj_previous_page_number,
        'next_page': page_obj_next_page_number,
        'url_params': url_params,
        'selected_tipo': selected_type,
        'selected_subtipo': selected_subtipo,
        'selected_shapes': selected_shapes,
        'selected_colors': selected_colors,
        'selected_clarities': selected_clarities,
        'selected_cuts': selected_cuts,
        'selected_labs': selected_labs,
        'has_image': has_image,
        'has_video': has_video,
        'returnable': returnable,
        'express': express,
        'min_carats': min_carats or '',
        'max_carats': max_carats or '',
        'min_price': min_price or '',
        'max_price': max_price or '',
        'order_by': order_by,
        'order_dir': order_dir,
        'all_shapes': all_shapes,
        'all_colors': all_colors,
        'all_clarities': all_clarities,
        'all_cuts': all_cuts,
        'all_labs': all_labs,
        'cart_count': cart_count,
        'whatsapp_url': whatsapp_url,
        'whatsapp_number': whatsapp_number,
        'banner_info': banner_info,
    })


def productos(request, producto_id=None):
    diamond_id = request.GET.get('diamond_id') or request.GET.get('id')
    producto = None

    if diamond_id:
        from django.db.models import Q
        producto = Product.objects.filter(Q(id=int(diamond_id) if str(diamond_id).isdigit() else 0) | Q(nivoda_id=diamond_id)).first()
        
        # If not found locally, fetch from live API and cache it
        if not producto:
            diamond_data = NivodaAPI.get_diamond_by_id(diamond_id)
            if diamond_data:
                from decimal import Decimal
                carats = diamond_data.get('carats', 0.0)
                shape = diamond_data.get('shape', 'ROUND')
                lab = diamond_data.get('lab', 'GIA')
                title = f"Diamante {carats} ct {shape} ({diamond_data.get('color', '-')}/{diamond_data.get('clarity', '-')} - {lab})"
                producto = Product.objects.create(
                    nivoda_id=diamond_id,
                    nombre=title,
                    descripcion=f"Diamante certificado por {lab}. Certificado #: {diamond_data.get('cert_number', 'N/A')}",
                    precio=Decimal(str(diamond_data.get('price', 0))),
                    shape=shape,
                    carats=Decimal(str(carats)) if carats else Decimal('0'),
                    color=diamond_data.get('color', ''),
                    clarity=diamond_data.get('clarity', ''),
                    cut=diamond_data.get('cut', ''),
                    lab=lab,
                    cert_number=diamond_data.get('cert_number', ''),
                    cert_pdf=diamond_data.get('pdf_url', ''),
                    image_url=diamond_data.get('image', ''),
                    video_url=diamond_data.get('video', ''),
                    v360_url=diamond_data.get('v360', ''),
                    is_diamond=True,
                )
    elif producto_id:
        producto = get_object_or_404(Product, id=producto_id)

    if not producto:
        messages.error(request, 'El diamante solicitado no se encuentra disponible.')
        return redirect('tienda')

    sugeridos = Product.objects.filter(is_diamond=True).exclude(id=producto.id).order_by('?')[:4]

    cart_count = _get_cart_count(request)
    whatsapp_url = get_whatsapp_url()
    whatsapp_number = get_whatsapp_empresa()

    return render(request, 'productos.html', {
        'diamond': producto,
        'producto': producto,
        'sugeridos': sugeridos,
        'cart_count': cart_count,
        'whatsapp_url': whatsapp_url,
        'whatsapp_number': whatsapp_number,
    })


def orden_add(request):
    if request.method != 'POST':
        return redirect(request.META.get('HTTP_REFERER', reverse('tienda')))

    diamond_id = request.POST.get('diamond_id', '').strip()
    prod_id = request.POST.get('product_id', '').strip()

    try:
        qty = int(request.POST.get('cantidad', '1'))
        if qty < 1:
            qty = 1
    except (ValueError, TypeError):
        qty = 1

    cart = dict(request.session.get('orden', {}) or {})

    target_id = diamond_id or prod_id
    if not target_id:
        messages.error(request, 'Selección de producto inválida.')
        return redirect(request.META.get('HTTP_REFERER', reverse('tienda')))

    from django.db.models import Q
    prod = Product.objects.filter(Q(id=int(target_id) if str(target_id).isdigit() else 0) | Q(nivoda_id=target_id)).first()

    # If not found locally and looks like a Nivoda ID, fetch and cache
    if not prod and not str(target_id).isdigit():
        diamond_data = NivodaAPI.get_diamond_by_id(target_id)
        if diamond_data:
            from decimal import Decimal
            carats = diamond_data.get('carats', 0.0)
            shape = diamond_data.get('shape', 'ROUND')
            lab = diamond_data.get('lab', 'GIA')
            title = f"Diamante {carats} ct {shape} ({diamond_data.get('color', '-')}/{diamond_data.get('clarity', '-')} - {lab})"
            prod = Product.objects.create(
                nivoda_id=target_id,
                nombre=title,
                descripcion=f"Diamante certificado por {lab}. Certificado #: {diamond_data.get('cert_number', 'N/A')}",
                precio=Decimal(str(diamond_data.get('price', 0))),
                shape=shape,
                carats=Decimal(str(carats)) if carats else Decimal('0'),
                color=diamond_data.get('color', ''),
                clarity=diamond_data.get('clarity', ''),
                cut=diamond_data.get('cut', ''),
                lab=lab,
                cert_number=diamond_data.get('cert_number', ''),
                cert_pdf=diamond_data.get('pdf_url', ''),
                image_url=diamond_data.get('image', ''),
                video_url=diamond_data.get('video', ''),
                v360_url=diamond_data.get('v360', ''),
                is_diamond=True,
            )

    if not prod:
        messages.error(request, 'El diamante o producto seleccionado no está disponible.')
        return redirect(request.META.get('HTTP_REFERER', reverse('tienda')))

    key = str(prod.id)
    current = cart.get(key, 0)
    if isinstance(current, dict):
        current = current.get('cantidad', 0)
    cart[key] = int(current) + qty

    request.session['orden'] = cart
    request.session.modified = True
    messages.success(request, f"¡'{prod.nombre}' agregado a tu orden!")
    return redirect(request.META.get('HTTP_REFERER', reverse('tienda')))


def orden(request):
    cart = request.session.get('orden', {}) or {}
    items = []
    subtotal = Decimal('0.00')

    # Fetch DB products map
    db_pids = [int(k) for k in cart.keys() if k.isdigit()]
    prod_map = {p.id: p for p in Product.objects.filter(id__in=db_pids)}

    for key, entry in cart.items():
        if not key.isdigit():
            continue
        pid = int(key)
        prod = prod_map.get(pid)
        if not prod:
            continue
        cantidad = int(entry if not isinstance(entry, dict) else entry.get('cantidad', 1))
        precio_unit = prod.precio
        item_total = precio_unit * cantidad
        items.append({
            'key': key,
            'is_diamond': prod.is_diamond,
            'product': prod,
            'nombre': prod.nombre,
            'cantidad': cantidad,
            'precio_unit': precio_unit,
            'total': item_total,
            'precio': str(precio_unit),
        })
        subtotal += item_total

    codigo_descuento = request.session.get('codigo_descuento', '') or ''
    afiliado_valido = None
    descuento_porcentaje = Decimal('0.00')
    descuento_monto = Decimal('0.00')
    total_con_descuento = subtotal
    codigo_error = ''

    if codigo_descuento:
        afiliado_valido = Afiliado.objects.filter(codigo__iexact=codigo_descuento, activo=True).first()
        if afiliado_valido:
            descuento_porcentaje = Decimal(str(afiliado_valido.descuento))
            descuento_monto = (subtotal * descuento_porcentaje / Decimal('100')).quantize(Decimal('0.01'))
            total_con_descuento = (subtotal - descuento_monto).quantize(Decimal('0.01'))
        else:
            codigo_error = 'Código de descuento inválido o inactivo.'
            total_con_descuento = subtotal

    if request.method == 'POST':
        nombre = request.POST.get('nombre', '').strip()
        correo = request.POST.get('correo', '').strip()
        telefono = request.POST.get('telefono', '').strip()
        mensaje = request.POST.get('mensaje', '').strip()
        codigo_descuento = request.POST.get('codigo_descuento', '').strip().upper()
        request.session['codigo_descuento'] = codigo_descuento
        request.session.modified = True

        afiliado_valido = None
        descuento_porcentaje = Decimal('0.00')
        descuento_monto = Decimal('0.00')
        total_con_descuento = subtotal
        codigo_error = ''

        if codigo_descuento:
            afiliado_valido = Afiliado.objects.filter(codigo__iexact=codigo_descuento, activo=True).first()
            if afiliado_valido:
                descuento_porcentaje = Decimal(str(afiliado_valido.descuento))
                descuento_monto = (subtotal * descuento_porcentaje / Decimal('100')).quantize(Decimal('0.01'))
                total_con_descuento = (subtotal - descuento_monto).quantize(Decimal('0.01'))
            else:
                codigo_error = 'Código de descuento inválido o inactivo.'

        ctx_error = {
            'items': items,
            'subtotal': subtotal,
            'total_con_descuento': total_con_descuento,
            'descuento_porcentaje': descuento_porcentaje,
            'descuento_monto': descuento_monto,
            'codigo_descuento': codigo_descuento,
            'codigo_error': codigo_error,
            'cart_count': _get_cart_count(request),
            'whatsapp_url': get_whatsapp_url(),
            'whatsapp_number': get_whatsapp_empresa(),
            'SHOW_PRICES_CLIENTES': True,
        }

        if not nombre or not correo:
            messages.error(request, 'Nombre y correo son obligatorios para procesar la orden de diamantes.')
            return render(request, 'orden.html', ctx_error)

        if codigo_descuento and not afiliado_valido:
            messages.error(request, codigo_error)
            return render(request, 'orden.html', ctx_error)

        try:
            cliente = crud.crear_cliente(nombre, correo, telefono)
            items_payload = [
                {
                    'product_id': it['product'].id,
                    'cantidad': it['cantidad'],
                    'precio': it['precio'],
                }
                for it in items
            ]

            orden_obj = crud.crear_orden_desde_carrito(
                cliente,
                items_payload,
                mensaje=mensaje,
                codigo_afiliado=codigo_descuento,
                descuento_afiliado=descuento_porcentaje,
            )

            # Build WhatsApp message
            detalle_lines = []
            for it in items:
                p = it['product']
                c = it['cantidad']
                pu = float(it['precio_unit'])
                tot = float(it['total'])
                if p.is_diamond:
                    cert_txt = f" | Cert {p.lab}: {p.cert_number}" if p.cert_number else ""
                    detalle_lines.append(
                        f"💎 Diamante {p.carats} ct {p.shape} ({p.color}/{p.clarity}{cert_txt}) x{c} (${pu:,.2f}) = ${tot:,.2f}"
                    )
                else:
                    detalle_lines.append(
                        f"💍 {p.nombre} x{c} (${pu:,.2f}) = ${tot:,.2f}"
                    )

            productos_str = "\n".join(detalle_lines)
            total_whatsapp = float(total_con_descuento if afiliado_valido else subtotal)

            fecha_actual = timezone.now()
            if timezone.is_naive(fecha_actual):
                fecha_actual = timezone.make_aware(fecha_actual)
            fecha_str = timezone.localtime(fecha_actual).strftime('%d/%m/%Y %H:%M')

            saludo = AppConfig.get_valor('WHATSAPP_SALUDO', 'Hola, deseo solicitar la compra/apartado de la siguiente orden de diamantes en Universal Diamond.')
            texto_orden = (
                f"💎 *UNIVERSAL DIAMOND - ORDEN DE COMPRA*\n\n"
                f"🆔 Orden #: {orden_obj.id}\n"
                f"👤 Cliente: {nombre} ({correo})\n"
                f"📞 Teléfono: {telefono if telefono else 'N/A'}\n"
                f"📅 Fecha: {fecha_str}\n\n"
                f"🛒 Diamantes / Productos:\n{productos_str}\n\n"
                f"💵 Subtotal: ${float(subtotal):,.2f}\n"
                + (f"🏷️ Afiliado ({codigo_descuento}): -{descuento_porcentaje}%\n" if afiliado_valido else "")
                + f"💰 *TOTAL: ${total_whatsapp:,.2f} USD*\n\n"
                f"📝 Nota: {mensaje if mensaje else '-'}\n\n"
                f"✨ ¡Gracias por elegir Universal Diamond!"
            )

            telefono_ventas = AppConfig.get_valor('WHATSAPP_EMPRESA') or getattr(settings, 'WHATSAPP_EMPRESA', '')
            telefono_ventas = (telefono_ventas or '').strip()

            def _clean_phone(raw):
                cleaned = ''.join(ch for ch in raw if ch.isdigit())
                if cleaned.startswith('0'):
                    cleaned = '58' + cleaned.lstrip('0')
                return cleaned

            ventas_phone = _clean_phone(telefono_ventas) if telefono_ventas else ''
            whatsapp_url = f"https://wa.me/{ventas_phone}?text={quote(texto_orden)}" if ventas_phone else None

            request.session['orden'] = {}
            request.session.modified = True

            return render(request, 'orden_success.html', {
                'orden': orden_obj,
                'whatsapp_url': whatsapp_url,
                'cart_count': 0,
            })

        except Exception as e:
            print(f"Error procesando orden/WhatsApp: {e}")
            messages.error(request, f'Error al crear la orden: {e}')
            return render(request, 'orden.html', ctx_error)

    return render(request, 'orden.html', {
        'items': items,
        'subtotal': subtotal,
        'total_con_descuento': total_con_descuento,
        'descuento_porcentaje': descuento_porcentaje,
        'descuento_monto': descuento_monto,
        'codigo_descuento': codigo_descuento,
        'codigo_error': codigo_error,
        'cart_count': _get_cart_count(request),
        'whatsapp_url': get_whatsapp_url(),
        'whatsapp_number': get_whatsapp_empresa(),
        'SHOW_PRICES_CLIENTES': True,
    })


def validar_codigo_afiliado(request):
    codigo = (request.GET.get('codigo') or '').strip().upper()
    if not codigo:
        return JsonResponse({'valid': False, 'error': 'Ingresa un código de descuento.'})

    afiliado = Afiliado.objects.filter(codigo__iexact=codigo, activo=True).first()
    if not afiliado:
        return JsonResponse({'valid': False, 'error': 'Código inválido o inactivo.'})

    return JsonResponse({
        'valid': True,
        'codigo': afiliado.codigo,
        'descuento': float(afiliado.descuento),
    })


def guardar_contacto(request):
    if request.method == "POST":
        nombre      = request.POST.get('nombre', '').strip()
        telefono    = request.POST.get('telefono', '').strip()
        correo      = request.POST.get('correo', '').strip()
        motivo_form = request.POST.get('motivo')
        mensaje     = request.POST.get('mensaje', '').strip()

        motivos_map = {
            'cotizacion_repuestos': 'Solicitar Cotización de Repuestos',
            'soporte_tecnico':      'Soporte Técnico / Mantenimiento',
            'alquiler_equipos':     'Información sobre Alquiler de Equipos',
            'info_general':         'Consulta General',
            'otro':                 'Otro',
        }
        motivo_legible = motivos_map.get(motivo_form, 'No especificado')

        try:
            email_context = {
                'nombre': nombre, 'telefono': telefono,
                'correo': correo, 'motivo_legible': motivo_legible,
                'mensaje': mensaje,
            }
            html_content = render_to_string('emails/nuevo_contacto.html', email_context)
            text_content = strip_tags(html_content)

            subject = f'Nuevo Contacto desde la Web: {motivo_legible}'
            msg = EmailMultiAlternatives(
                subject, text_content,
                settings.EMAIL_HOST_USER, [settings.CORREO_VENTAS]
            )
            msg.attach_alternative(html_content, "text/html")
            msg.send()
            messages.success(request, '¡Gracias por contactarnos! Hemos recibido tu mensaje y te responderemos pronto.')

        except Exception as e:
            print(f"Error al enviar correo de contacto: {e}")
            messages.error(request, 'Hubo un error al enviar tu mensaje. Por favor, inténtalo de nuevo o contáctanos directamente.')

        return redirect('/#contacto')

    return redirect('/')