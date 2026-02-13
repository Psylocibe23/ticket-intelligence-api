"""
URL di ingresso del progetto.

Qui registriamo:
- admin Django
- API REST per i ticket (via DRF router)
- endpoint ML (training modello)
- endpoint di analytics (trend, MTTR)
- documentazione OpenAPI/Swagger
"""
from django.contrib import admin
from django.urls import path, include
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter
from tickets.views import TicketViewSet, TrainModelView, AnalyticsTrendsView, AnalyticsMttrView

router = DefaultRouter()
router.register("tickets", TicketViewSet, basename="tickets")

# API REST per i ticket + endpoint ML/analytics
urlpatterns = [
    path("admin/", admin.site.urls),
    # Schema OpenAPI (machine-readable) e Swagger UI (documentazione interattiva)
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    # Endpoint dedicato al training del modello ML sui ticket esistenti
    path("api/ml/train/", TrainModelView.as_view(), name="ml-train"),
     # Endpoint di analytics sui ticket (trend per categoria + MTTR)
    path("api/analytics/trends/", AnalyticsTrendsView.as_view(), name="analytics-trends"),
    path("api/analytics/mttr/", AnalyticsMttrView.as_view(), name="analytics-mttr"),
    # API REST generata dal router per i ticket
    path("api/", include(router.urls)),
]