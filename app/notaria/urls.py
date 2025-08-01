from rest_framework_nested import routers
from . import views

"""
URL configuration for the Notaria app.
This file defines the URL patterns for the Notaria app.
It includes the URL patterns for the Notaria app's views.
"""

router = routers.DefaultRouter()

router.register('usuarios', views.UsuariosViewSet, basename='usuarios')
router.register('permisos', views.PermisosUsuariosViewSet, basename='permisos')
router.register('kardex', views.KardexViewSet, basename='kardex')
router.register('tipokar', views.TipoKarViewSet, basename='tipokar')
router.register('contratantes', views.ContratantesViewSet,
                basename='contratantes')
router.register('contratantesxacto', views.ContratantesxactoViewSet)
router.register('cliente2', views.Cliente2ViewSet, basename='cliente2')
router.register('cliente', views.ClienteViewSet, basename='cliente')
router.register('tiposdeactos', views.TiposDeActosViewSet,
                basename='tiposdeactos')
router.register('abogados', views.TbAbogadoViewSet, basename='abogados')
router.register('actocondicion', views.ActoCondicionViewSet,
                basename='actocondicion')
router.register('detalleactos', views.DetalleActosKardexViewSet)
router.register('nacionalidades', views.NacionalidadesViewSet)
router.register('cargoprofe', views.CargoprofeViewSet)
router.register('profesiones', views.ProfesionesViewSet)
router.register('ubigeos', views.UbigeoViewSet)
router.register('sedes_registrales', views.SedesRegistralesViewSet)
router.register('representantes', views.RepresentantesViewSet)
router.register('patrimonial', views.PatrimonialViewSet)
router.register('detallevehicular', views.DetalleVehicularViewSet)
router.register('detallebienes', views.DetallebienesViewSet)
router.register('predios', views.PrediosViewSet)
router.register('detallemediopago', views.DetallemediopagoViewSet)
router.register('templates', views.TemplateViewSet)

# EXTRAPROTOCOLARES
router.register('legalizacion', views.LegalizacionViewSet)
router.register('permi_viaje', views.PermiViajeViewSet, basename='permi_viaje')
router.register('viaje_contratantes', views.ViajeContratantesViewSet)
router.register('ingreso_poderes', views.IngresoPoderesViewSet, basename='ingreso_poderes')
router.register('poderes_contratantes', views.PoderesContratantesViewSet, basename='poderes_contratantes')
router.register('ingreso_cartas', views.IngresoCartasViewSet, basename='ingreso_cartas')

urlpatterns = router.urls
