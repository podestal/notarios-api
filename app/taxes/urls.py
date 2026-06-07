from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("catalogos", views.CatalogosViewSet, basename="catalogos")
router.register("monedas", views.MonedasViewSet, basename="monedas")
router.register("tipos-igv", views.TiposIgvViewSet, basename="tipos-igv")
router.register(
    "codigos-unitarios",
    views.CodigosUnitariosViewSet,
    basename="codigos-unitarios",
)
router.register("documentos", views.DocumentosViewSet, basename="documentos")
router.register("personas", views.PersonasViewSet, basename="personas")
router.register("usuarios", views.UsuariosViewSet, basename="taxes-usuarios")

urlpatterns = router.urls
