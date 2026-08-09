from django.db import models
from django.db import models


class Category(models.Model):
    def es_subcategoria(self):
            return self.padres.exists()
    nombre = models.CharField(max_length=120, unique=True)
    icono = models.ImageField(upload_to='categorias/iconos/', blank=True, null=True, help_text="Imagen de icono para la categoría")
    # Ahora una categoría puede tener varios padres
    padres = models.ManyToManyField('self', symmetrical=False, blank=True, related_name='subcategorias')

    class Meta:
        verbose_name = 'Categoría'
        verbose_name_plural = 'Categorías'

    def __str__(self):
        padres = self.padres.all()
        if padres.exists():
            return f"{' / '.join([p.nombre for p in padres])} > {self.nombre}"
        return self.nombre

class Product(models.Model):
    nombre = models.CharField(max_length=200)
    descripcion = models.TextField(blank=True)
    precio = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    categorias = models.ManyToManyField('Category', blank=True, related_name='productos')
    imagen = models.ImageField(upload_to='productos/', null=True, blank=True)
    creado = models.DateTimeField(null=True, blank=True)
    agotado = models.BooleanField(default=False)
    por_peso = models.BooleanField(default=False, help_text="¿El producto se vende por peso?")
    
    # Nivoda Diamond fields
    nivoda_id = models.CharField(max_length=150, null=True, blank=True, db_index=True)
    shape = models.CharField(max_length=50, null=True, blank=True)
    carats = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    color = models.CharField(max_length=20, null=True, blank=True)
    clarity = models.CharField(max_length=20, null=True, blank=True)
    cut = models.CharField(max_length=20, null=True, blank=True)
    polish = models.CharField(max_length=50, null=True, blank=True)
    symmetry = models.CharField(max_length=50, null=True, blank=True)
    lab = models.CharField(max_length=20, null=True, blank=True)
    cert_number = models.CharField(max_length=100, null=True, blank=True)
    cert_pdf = models.URLField(max_length=500, null=True, blank=True)
    image_url = models.URLField(max_length=500, null=True, blank=True)
    video_url = models.URLField(max_length=500, null=True, blank=True)
    v360_url = models.URLField(max_length=500, null=True, blank=True)
    is_diamond = models.BooleanField(default=True)

    def get_precios_por_peso(self):
        """Devuelve los precios por peso asociados a este producto, si aplica."""
        if not self.por_peso:
            return None
        return self.precios_por_peso.all()


    def __str__(self):
        return self.nombre

    @property
    def price(self):
        return self.precio

    @property
    def tiene_360(self):
        return bool(self.v360_url or self.video_url)

    @property
    def media_embed_url(self):
        return self.v360_url or self.video_url or ""

    @property
    def imagen_display_url(self):
        if self.imagen:
            return self.imagen.url
        if self.image_url:
            return self.image_url
        return ""

    @property
    def portada(self):
        portada_obj = self.imagenes.filter(is_portada=True).first()
        if portada_obj:
            return portada_obj.imagen
        if self.imagen:
            return self.imagen
        return None

class ProductImage(models.Model):
    product = models.ForeignKey(Product, related_name='imagenes', on_delete=models.CASCADE)
    imagen = models.ImageField(upload_to='productos/')
    is_portada = models.BooleanField(default=False)
    orden = models.PositiveIntegerField(default=0)
    creado = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['orden', 'creado']

    def __str__(self):
        return f"Imagen #{self.id} para {self.product.nombre} {'(portada)' if self.is_portada else ''}"


class Cliente(models.Model):
    nombre = models.CharField(max_length=200)
    correo = models.EmailField()
    telefono = models.CharField(max_length=40, blank=True)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Cliente'
        verbose_name_plural = 'Clientes'

    def __str__(self):
        return f"{self.nombre} <{self.correo}>"

class Orden(models.Model):
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='ordenes')
    mensaje = models.TextField(blank=True)
    creado = models.DateTimeField(null=True, blank=True)
    estado = models.CharField(max_length=30, default='pendiente')  # pendiente, procesado, finalizado, etc.
    es_venta = models.BooleanField(default=False)
    fecha_venta = models.DateTimeField(null=True, blank=True)
    codigo_afiliado = models.CharField(max_length=64, blank=True, null=True)
    descuento_afiliado = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)  # Nuevo campo para el monto total

    class Meta:
        verbose_name = 'Orden'
        verbose_name_plural = 'Órdenes'
        ordering = ['-creado']
        db_table = 'app1_cotizacion'  # Conserva tabla histórica de cotizaciones

    def __str__(self):
        return f"Orden #{self.id} - {self.cliente.nombre}"
    
class OrdenItem(models.Model):
    orden = models.ForeignKey(
        Orden,
        on_delete=models.CASCADE,
        related_name='items',
        db_column='cotizacion_id',
    )
    producto = models.ForeignKey(Product, on_delete=models.CASCADE)
    cantidad = models.PositiveIntegerField(default=1)
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    detalles_diamante = models.TextField(null=True, blank=True) # JSON con especificaciones del diamante snapshot

    class Meta:
        db_table = 'app1_cotizacionitem'  # Conserva tabla histórica de cotizacionitems

    def __str__(self):
        return f"{self.cantidad} x {self.producto.nombre} (orden #{self.orden_id})"


# Compatibilidad con referencia antigua
Cotizacion = Orden
CotizacionItem = OrdenItem

# Nuevo modelo para multi-precio por peso
class PrecioPorPeso(models.Model):
    producto = models.ForeignKey(Product, related_name='precios_por_peso', on_delete=models.CASCADE)
    peso = models.DecimalField(max_digits=7, decimal_places=2, help_text="Peso en gramos")
    precio = models.DecimalField(max_digits=10, decimal_places=2, help_text="Precio para este peso")

    class Meta:
        unique_together = ('producto', 'peso')
        verbose_name = 'Precio por Peso'
        verbose_name_plural = 'Precios por Peso'
        ordering = ['peso']

    def __str__(self):
        return f"{self.producto.nombre} - {self.peso}g: ${self.precio}"
