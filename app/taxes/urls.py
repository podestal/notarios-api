from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("catalogos", views.CatalogosViewSet, basename="catalogos")
router.register(
    "codigos-unitarios",
    views.CodigosUnitariosViewSet,
    basename="codigos-unitarios",
)

urlpatterns = router.urls
