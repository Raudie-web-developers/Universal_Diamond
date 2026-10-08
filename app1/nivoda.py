import urllib.request
import urllib.error
import json
import time
from typing import Dict, Any, Optional

import base64

def unwrap_nivoda_360_url(url: Optional[str]) -> str:
    """
    Decodes Nivoda's S3 base64 proxy URL into the real 360 degree interactive rotation viewer link.
    """
    if not url or not isinstance(url, str):
        return ""
    if "amazonaws.com/" in url:
        try:
            part = url.split("amazonaws.com/")[-1].split("?")[0].strip("/")
            missing_padding = len(part) % 4
            if missing_padding:
                part += '=' * (4 - missing_padding)
            decoded = base64.b64decode(part).decode('utf-8', errors='ignore').strip()
            if decoded.startswith("http://") or decoded.startswith("https://"):
                return decoded
        except Exception:
            pass
    return url

# Default Staging credentials
DEFAULT_API_URL = "https://intg-customer-staging.nivodaapi.net/api/diamonds"
DEFAULT_USERNAME = "testaccount@sample.com"
DEFAULT_PASSWORD = "staging-nivoda-22"

class NivodaAPI:
    """
    Client for Nivoda B2B GraphQL API
    """
    _token = None
    _token_expiry = 0

    @classmethod
    def get_config(cls) -> Dict[str, str]:
        from app2.models import AppConfig
        url = AppConfig.get_valor('NIVODA_API_URL', DEFAULT_API_URL).strip()
        username = AppConfig.get_valor('NIVODA_USERNAME', DEFAULT_USERNAME).strip()
        password = AppConfig.get_valor('NIVODA_PASSWORD', DEFAULT_PASSWORD).strip()
        markup_pct = AppConfig.get_valor('NIVODA_MARKUP_PERCENT', '0').strip()
        return {
            'url': url or DEFAULT_API_URL,
            'username': username or DEFAULT_USERNAME,
            'password': password or DEFAULT_PASSWORD,
            'markup_percent': float(markup_pct) if markup_pct else 0.0
        }

    @classmethod
    def get_token(cls, force_refresh: bool = False) -> str:
        current_time = time.time()
        if not force_refresh and cls._token and current_time < cls._token_expiry:
            return cls._token

        config = cls.get_config()
        query = """
        query {
          authenticate {
            username_and_password(username: "%s", password: "%s") {
              token
            }
          }
        }
        """ % (config['username'], config['password'])

        req = urllib.request.Request(
            config['url'],
            data=json.dumps({"query": query}).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "UniversalDiamond/1.0"},
            method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                res = json.loads(resp.read().decode())
                token = res.get("data", {}).get("authenticate", {}).get("username_and_password", {}).get("token")
                if not token:
                    raise ValueError(f"Could not authenticate with Nivoda API: {res}")
                cls._token = token
                # Cache token for 12 hours (43200 seconds)
                cls._token_expiry = current_time + 43200
                return cls._token
        except Exception as e:
            cls._token = None
            cls._token_expiry = 0
            raise RuntimeError(f"Nivoda Auth Error: {str(e)}")

    @classmethod
    def _post_query(cls, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        config = cls.get_config()
        token = cls.get_token()

        payload = {"query": query}
        if variables:
            payload["variables"] = variables

        req = urllib.request.Request(
            config['url'],
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
                "User-Agent": "UniversalDiamond/1.0"
            },
            method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                res = json.loads(resp.read().decode())
                if "errors" in res and not res.get("data"):
                    raise ValueError(res["errors"][0]["message"])
                return res
        except urllib.error.HTTPError as e:
            # If 401/403, clear token and retry once
            if e.code in (401, 403):
                token = cls.get_token(force_refresh=True)
                req.headers["Authorization"] = f"Bearer {token}"
                with urllib.request.urlopen(req, timeout=30) as resp:
                    return json.loads(resp.read().decode())
            error_body = e.read().decode()
            raise RuntimeError(f"Nivoda API HTTP {e.code}: {error_body}")
        except Exception as e:
            raise RuntimeError(f"Nivoda API Request Failed: {str(e)}")

    @classmethod
    def search_diamonds(
        cls,
        shapes: Optional[list] = None,
        min_carats: Optional[float] = None,
        max_carats: Optional[float] = None,
        colors: Optional[list] = None,
        clarities: Optional[list] = None,
        cuts: Optional[list] = None,
        labs: Optional[list] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        has_v360: bool = False,
        has_image: bool = False,
        has_certpdf: bool = False,
        limit: int = 12,
        offset: int = 0,
        order_by: str = "price",
        order_dir: str = "ASC"
    ) -> Dict[str, Any]:
        """
        Query diamonds live from Nivoda B2B GraphQL API
        """
        query_input = {}
        if shapes:
            query_input["shapes"] = [s.upper() for s in shapes if s]

        if has_v360:
            query_input["has_v360"] = True
        if has_image:
            query_input["has_image"] = True
        if has_certpdf:
            query_input["has_certpdf"] = True

        # Carats filter -> sizes (FloatRange list)
        if min_carats is not None or max_carats is not None:
            carats_filter = {}
            carats_filter["from"] = float(min_carats) if min_carats is not None and min_carats > 0 else 0.0
            carats_filter["to"] = float(max_carats) if max_carats is not None and max_carats > 0 else 100.0
            query_input["sizes"] = [carats_filter]

        if colors:
            query_input["color"] = [c.upper() for c in colors if c]
        if clarities:
            query_input["clarity"] = [cl.upper() for cl in clarities if cl]
        if cuts:
            query_input["cut"] = [ct.upper() for ct in cuts if ct]
        if labs:
            query_input["certificate_lab"] = [l.upper() for l in labs if l]

        if min_price is not None or max_price is not None:
            price_filter = {}
            price_filter["from"] = int(min_price) if min_price is not None and min_price > 0 else 0
            price_filter["to"] = int(max_price) if max_price is not None and max_price > 0 else 100000000
            query_input["dollar_value"] = price_filter

        graphql_query = """
        query SearchDiamonds($query: DiamondQuery, $offset: Int, $limit: Int, $order: DiamondOrder) {
          diamonds_by_query_count(query: $query)
          diamonds_by_query(query: $query, offset: $offset, limit: $limit, order: $order) {
            items {
              id
              price
              discount
              markup_price
              diamond {
                id
                video
                image
                v360 {
                  url
                }
                certificate {
                  id
                  lab
                  certNumber
                  shape
                  carats
                  color
                  clarity
                  cut
                  polish
                  symmetry
                  pdfUrl
                  depthPercentage
                  table
                }
              }
            }
          }
        }
        """

        order_input = None
        if order_by in ("price", "carats", "carat", "size"):
            field = "price" if order_by == "price" else "size"
            direction = "ASC" if order_dir.upper() == "ASC" else "DESC"
            order_input = {"type": field, "direction": direction}

        variables = {
            "query": query_input,
            "offset": max(0, offset),
            "limit": min(50, max(1, limit))
        }
        if order_input:
            variables["order"] = order_input

        res = cls._post_query(graphql_query, variables)
        data = res.get("data", {}).get("diamonds_by_query", {})

        config = cls.get_config()
        markup_factor = 1.0 + (config['markup_percent'] / 100.0)

        raw_items = data.get("items", [])
        formatted_items = []
        for item in raw_items:
            dm = item.get("diamond", {}) or {}
            cert = dm.get("certificate", {}) or {}

            raw_price = item.get("markup_price") or item.get("price") or 0.0
            final_price = round(raw_price * markup_factor, 2)

            v360_obj = dm.get("v360")
            v360_url = v360_obj.get("url") if isinstance(v360_obj, dict) else v360_obj

            formatted_items.append({
                "id": item.get("id"),
                "diamond_id": dm.get("id"),
                "raw_price": raw_price,
                "price": final_price,
                "video": dm.get("video") or cert.get("video"),
                "image": dm.get("image") or cert.get("image"),
                "v360": v360_url or cert.get("v360"),
                "shape": cert.get("shape") or "ROUND",
                "carats": cert.get("carats") or 0.0,
                "color": cert.get("color") or "-",
                "clarity": cert.get("clarity") or "-",
                "cut": cert.get("cut") or "-",
                "polish": cert.get("polish") or "-",
                "symmetry": cert.get("symmetry") or "-",
                "lab": cert.get("lab") or "GIA",
                "cert_number": cert.get("certNumber") or "",
                "pdf_url": cert.get("pdfUrl") or "",
                "depth": cert.get("depthPercentage"),
                "table": cert.get("table"),
            })

        true_total = res.get("data", {}).get("diamonds_by_query_count")
        fallback_total = data.get("total_count", len(formatted_items))

        return {
            "total_count": true_total if true_total is not None else fallback_total,
            "items": formatted_items
        }

    @classmethod
    def get_diamond_by_id(cls, diamond_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch single diamond by ID
        """
        graphql_query = """
        query GetDiamond($diamond_id: ID!) {
          get_diamond_by_id(diamond_id: $diamond_id) {
            id
            price
            discount
            markup_price
            diamond {
              id
              video
              image
              v360 {
                url
              }
              certificate {
                id
                lab
                certNumber
                shape
                carats
                color
                clarity
                cut
                polish
                symmetry
                pdfUrl
                depthPercentage
                table
                girdle
                culetSize
                comments
              }
            }
          }
        }
        """

        try:
            res = cls._post_query(graphql_query, {"diamond_id": diamond_id})
            item = res.get("data", {}).get("get_diamond_by_id")
            if not item:
                return None

            dm = item.get("diamond", {}) or {}
            cert = dm.get("certificate", {}) or {}

            config = cls.get_config()
            markup_factor = 1.0 + (config['markup_percent'] / 100.0)

            raw_price = item.get("markup_price") or item.get("price") or 0.0
            final_price = round(raw_price * markup_factor, 2)

            v360_obj = dm.get("v360")
            v360_url = v360_obj.get("url") if isinstance(v360_obj, dict) else v360_obj

            return {
                "id": item.get("id"),
                "diamond_id": dm.get("id"),
                "raw_price": raw_price,
                "price": final_price,
                "video": dm.get("video") or cert.get("video"),
                "image": dm.get("image") or cert.get("image"),
                "v360": v360_url or cert.get("v360"),
                "shape": cert.get("shape") or "ROUND",
                "carats": cert.get("carats") or 0.0,
                "color": cert.get("color") or "-",
                "clarity": cert.get("clarity") or "-",
                "cut": cert.get("cut") or "-",
                "polish": cert.get("polish") or "-",
                "symmetry": cert.get("symmetry") or "-",
                "lab": cert.get("lab") or "GIA",
                "cert_number": cert.get("certNumber") or "",
                "pdf_url": cert.get("pdfUrl") or "",
                "depth": cert.get("depthPercentage"),
                "table": cert.get("table"),
                "girdle": cert.get("girdle"),
                "culet": cert.get("culetSize"),
                "comments": cert.get("comments"),
            }
        except Exception as e:
            print(f"Error fetching diamond {diamond_id}: {e}")
            return None

    @classmethod
    def sync_diamonds_to_db(
        cls,
        limit: int = 100,
        offset: int = 0,
        shapes: Optional[list] = None,
        min_carats: Optional[float] = None,
        max_carats: Optional[float] = None,
        ignore_repeats: bool = False,
    ) -> Dict[str, Any]:
        """
        Download diamonds from Nivoda API and store/update them in local Django database Product table.
        """
        import time
        from app1.models import Product
        from decimal import Decimal

        res_total = None
        fetched_total = 0
        created_count = 0
        updated_count = 0
        current_offset = offset
        batch_size = 50

        # Cargar IDs existentes si ignoramos repetidos para validación rápida en BD
        existing_ids = set()
        if ignore_repeats:
            existing_ids = set(Product.objects.filter(is_diamond=True, nivoda_id__isnull=False).values_list('nivoda_id', flat=True))

        while True:
            # Determinamos si ya llegamos a la meta
            target_reached = (created_count >= limit) if ignore_repeats else (fetched_total >= limit)
            if target_reached:
                break

            fetch_limit = min(batch_size, limit - (created_count if ignore_repeats else fetched_total))
            # Nivoda API no deja pedir más de 50 a la vez, si fetch_limit es mayor lo limitamos.
            fetch_limit = min(50, fetch_limit)

            try:
                res = cls.search_diamonds(
                    shapes=shapes,
                    min_carats=min_carats,
                    max_carats=max_carats,
                    has_v360=True,
                    has_image=True,
                    limit=fetch_limit,
                    offset=current_offset
                )
            except Exception as e:
                print(f"Error fetching at offset {current_offset}: {e}")
                time.sleep(3)
                break # Si falla abortamos el loop, guardamos lo que tenemos
                
            if res_total is None:
                res_total = res

            items = res.get("items", [])
            if not items:
                break

            current_offset += len(items)
            fetched_total += len(items)

            for item in items:
                # Meta alcanzada en pleno bucle?
                if (ignore_repeats and created_count >= limit) or (not ignore_repeats and (created_count + updated_count) >= limit):
                    break

                n_id = item.get('id') or item.get('diamond_id')
                if not n_id:
                    continue

                if ignore_repeats and n_id in existing_ids:
                    continue # Saltar repetidos por completo, no actualizarlos ni contarlos

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

                prod, created = Product.objects.update_or_create(
                    nivoda_id=n_id,
                    defaults={
                        'nombre': title,
                        'descripcion': desc,
                        'precio': price_dec,
                        'shape': shape,
                        'carats': carats_dec,
                        'color': color,
                        'clarity': clarity,
                        'cut': item.get('cut') or '-',
                        'polish': item.get('polish') or '-',
                        'symmetry': item.get('symmetry') or '-',
                        'lab': lab,
                        'cert_number': item.get('cert_number') or '',
                        'cert_pdf': item.get('pdf_url') or '',
                        'image_url': img_url,
                        'video_url': video_link,
                        'v360_url': v360_link,
                        'diamond_type': d_type,
                        'is_diamond': True,
                    }
                )
                if created:
                    created_count += 1
                    existing_ids.add(n_id)
                else:
                    updated_count += 1
            
            # Prevención contra el Rate Limiting 502 Bad Gateway
            time.sleep(1.5)

        return {
            'total_fetched': fetched_total,
            'total_api_count': (res_total or {}).get('total_count', fetched_total),
            'created': created_count,
            'updated': updated_count,
        }
