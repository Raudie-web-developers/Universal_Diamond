import os
import sys
import django
import time
import concurrent.futures
from decimal import Decimal

# Configurar el entorno de Django
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'proyecto.settings')
django.setup()

from app1.models import Product
from app1.nivoda import NivodaAPI, unwrap_nivoda_360_url

# Configuraciones de rendimiento
CONCURRENT_WORKERS = 5 # No muy alto para no ser baneados por Rate Limit
BATCH_SIZE = 50 # El límite máximo impuesto por Nivoda por petición
DB_BULK_SIZE = 2000 # Cuantos objetos guardar en BD de golpe

def fetch_page(offset):
    """
    Descarga una sola página desde la API de Nivoda y maneja reintentos automáticamente.
    """
    retries = 3
    for attempt in range(retries):
        try:
            res = NivodaAPI.search_diamonds(
                has_v360=True,
                has_image=True,
                limit=BATCH_SIZE,
                offset=offset
            )
            return res.get('items', [])
        except Exception as e:
            if attempt < retries - 1:
                print(f"[!] Error en offset {offset}: {e}. Reintentando en 3s...")
                time.sleep(3)
            else:
                print(f"[X] Falló definitivamente el offset {offset} tras {retries} intentos: {e}")
                return []

def map_raw_to_product(item):
    """
    Mapea el diccionario crudo devuelto por la API a una instancia NO GUARDADA de Product.
    """
    n_id = item.get('id') or item.get('diamond_id')
    if not n_id:
        return None

    shape = item.get('shape') or 'ROUND'
    carats = item.get('carats') or 0.0
    color = item.get('color') or '-'
    clarity = item.get('clarity') or '-'
    lab = item.get('lab') or 'GIA'

    title = f"Diamante {carats} ct {shape} ({color}/{clarity} - {lab})"
    desc = f"Diamante certificado por {lab}. Certificado #: {item.get('cert_number') or 'N/A'}"
    price_dec = Decimal(str(item.get('price', 0)))
    carats_dec = Decimal(str(carats)) if carats else Decimal('0')

    img_url = item.get('image') or ''
    video_link = item.get('video') or ''
    v360_raw = (item.get('v360') or {}).get('url') if isinstance(item.get('v360'), dict) else item.get('v360')
    v360_link = unwrap_nivoda_360_url(v360_raw)
    if not v360_link and video_link and ('loupe360' in video_link or 'vision360' in video_link or '360' in video_link):
        v360_link = video_link

    carats_val = float(carats) if carats else 0.0
    if carats_val <= 0.20:
        d_type = 'MELEE_LAB' if (lab or '').upper() == 'IGI' else 'MELEE_NATURAL'
    else:
        d_type = 'LAB_GROWN' if (lab or '').upper() == 'IGI' else 'NATURAL'

    return Product(
        nivoda_id=n_id,
        nombre=title,
        descripcion=desc,
        precio=price_dec,
        shape=shape,
        carats=carats_dec,
        color=color,
        clarity=clarity,
        cut=item.get('cut') or '-',
        polish=item.get('polish') or '-',
        symmetry=item.get('symmetry') or '-',
        lab=lab,
        cert_number=item.get('cert_number') or '',
        cert_pdf=item.get('pdf_url') or '',
        image_url=img_url,
        video_url=video_link,
        v360_url=v360_link,
        diamond_type=d_type,
        is_diamond=True,
    )

import threading

def main():
    print("=== INICIANDO SINCRONIZACIÓN ULTRARRÁPIDA ===")
    
    # Cargar IDs existentes para evitar duplicados sin hacer update_or_create lentos
    print("[*] Cargando inventario existente en memoria para comprobación de duplicados...")
    existing_ids = set(Product.objects.filter(is_diamond=True, nivoda_id__isnull=False).values_list('nivoda_id', flat=True))
    print(f"[*] {len(existing_ids)} diamantes ya existen en la base de datos local.")

    print(f"[*] Comenzando descargas concurrentes con {CONCURRENT_WORKERS} hilos...")
    
    new_products_buffer = []
    total_inserted = 0
    pages_processed = 0
    start_time = time.time()

    current_offset = 0
    offset_lock = threading.Lock()
    end_reached = False
    
    def worker():
        nonlocal current_offset, end_reached, new_products_buffer, total_inserted, pages_processed
        while not end_reached:
            with offset_lock:
                if end_reached:
                    break
                offset = current_offset
                current_offset += BATCH_SIZE
            
            items = fetch_page(offset)
            
            if not items:
                # Si una página (que no falló del todo por red) viene vacía, llegamos al final de la BD de Nivoda
                end_reached = True
                print(f"[*] Fin del catálogo detectado en el offset {offset}.")
                break
                
            with offset_lock:
                pages_processed += 1
                for item in items:
                    n_id = item.get('id') or item.get('diamond_id')
                    if n_id and n_id not in existing_ids:
                        prod = map_raw_to_product(item)
                        if prod:
                            new_products_buffer.append(prod)
                            existing_ids.add(n_id)
                
                # Inserción Masiva
                if len(new_products_buffer) >= DB_BULK_SIZE:
                    print(f"[*] Guardando lote masivo en BD ({len(new_products_buffer)} nuevos diamantes)...")
                    Product.objects.bulk_create(new_products_buffer, batch_size=999)
                    total_inserted += len(new_products_buffer)
                    new_products_buffer = []

                if pages_processed % 10 == 0:
                    elapsed = time.time() - start_time
                    print(f"Progreso: {pages_processed} páginas procesadas - Insertados: {total_inserted} - Tiempo: {elapsed:.1f}s")

    threads = []
    for _ in range(CONCURRENT_WORKERS):
        t = threading.Thread(target=worker)
        t.start()
        threads.append(t)
        
    for t in threads:
        t.join()
                
    # Guardar cualquier remanente que no alcanzó a llenar el buffer
    if new_products_buffer:
        print(f"[*] Guardando último lote en BD ({len(new_products_buffer)} diamantes)...")
        Product.objects.bulk_create(new_products_buffer, batch_size=999)
        total_inserted += len(new_products_buffer)

    total_time = time.time() - start_time
    print("\n=== RESUMEN ===")
    print(f"Diamantes descargados y agregados exitosamente: {total_inserted}")
    print(f"Total de páginas consultadas: {pages_processed}")
    print(f"Tiempo total: {total_time:.2f} segundos.")
    print("¡Sincronización finalizada!")

if __name__ == '__main__':
    main()
