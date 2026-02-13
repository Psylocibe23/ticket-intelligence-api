"""
Views REST per:
- gestione dei ticket (CRUD + azioni di workflow),
- endpoint ML (train e predict),
- endpoint di analytics (trend per categoria e MTTR).
"""
from datetime import timedelta

from django.utils import timezone
from django.db.models import Count, Avg, F, ExpressionWrapper, DurationField
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema, OpenApiParameter

from .models import Ticket
from .serializers import TicketSerializer
from .ml_utils import train_model, predict_category_for_ticket, get_similar_tickets


class TicketViewSet(viewsets.ModelViewSet):
    """
    ViewSet principale per i ticket:
    - CRUD standard (list, retrieve, create, update, delete)
    - azioni extra: assign, transition, ml_predict, similar
    """
    queryset = Ticket.objects.all().select_related("created_by", "assigned_to")
    serializer_class = TicketSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """
        Applica filtri dinamici in base ai parametri di query:
        - ?status=open/closed/...
        - ?assigned_to=me -> solo ticket assegnati all'utente corrente
        - ?ordering=created_at o -created_at, ecc.
        """
        qs = super().get_queryset()

        status_param = self.request.query_params.get("status")
        if status_param:
            qs = qs.filter(status=status_param)

        assigned_to_me = self.request.query_params.get("assigned_to")
        if assigned_to_me == "me" and self.request.user.is_authenticated:
            qs = qs.filter(assigned_to=self.request.user)

        ordering = self.request.query_params.get("ordering")
        if ordering:
            qs = qs.order_by(ordering)
        else:
            qs = qs.order_by("-created_at")

        return qs

    @action(detail=True, methods=["post"])
    def assign(self, request, pk=None):
        """
        POST /api/tickets/{id}/assign/
        Body: {"assigned_to": user_id}

        Assegna il ticket a un utente specifico.
        """
        ticket = self.get_object()
        assignee_id = request.data.get("assigned_to")
        if assignee_id is None:
            return Response({"detail": "assigned_to required"}, status=400)
        ticket.assigned_to_id = assignee_id
        ticket.save()
        return Response(TicketSerializer(ticket, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def transition(self, request, pk=None):
        """
        POST /api/tickets/{id}/transition/
        Body: {"status": "IN_PROGRESS" | "RESOLVED" | "CLOSED" | ...}

        Aggiorna lo stato del ticket nel workflow.
        """
        ticket = self.get_object()
        new_status = request.data.get("status")
        if new_status not in dict(Ticket.STATUS_CHOICES):
            return Response({"detail": "Invalid status"}, status=400)
        ticket.status = new_status
        ticket.save()
        return Response(TicketSerializer(ticket, context={"request": request}).data)

    @action(detail=True, methods=["post"], url_path="ml_predict")
    def ml_predict(self, request, pk=None):
        """
        POST /api/tickets/{id}/ml_predict/

        Usa il modello ML per suggerire una categoria per il ticket.
        Salva direttamente la categoria suggerita sul ticket.
        """
        ticket = self.get_object()
        result = predict_category_for_ticket(ticket)
        if result is None:
            return Response({"detail": "Model not trained"}, status=400)

        suggested_category = result["category"]
        ticket.category = suggested_category
        ticket.save(update_fields=["category"])

        return Response(result)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="top",
                type=int,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Numero massimo di ticket simili da restituire (default 5, max 20).",
            )
        ]
    )
    @action(detail=True, methods=["get"], url_path="similar")
    def similar(self, request, pk=None):
        """
        GET /api/tickets/{id}/similar/?top=5

        Ritorna i ticket più simili (TF-IDF + cosine similarity)
        al ticket indicato.
        """
        raw_top = request.query_params.get("top", "5")

        try:
            top = int(raw_top)
        except ValueError:
            top = 5

        # clamp per evitare valori assurdi (es. top=100000)
        if top < 1:
            top = 1
        if top > 20:
            top = 20

        ticket = self.get_object()
        data = get_similar_tickets(ticket, top_k=top)
        return Response(data)


class TrainModelView(APIView):
    """
    POST /api/ml/train/

    Allena il modello ML sui ticket esistenti (con category valorizzata).
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        info = train_model()
        if info is None:
            return Response(
                {"detail": "No data (or only one class) available for training"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(info, status=status.HTTP_200_OK)


class AnalyticsTrendsView(APIView):
    """
    GET /api/analytics/trends/?days=30

    Ritorna il numero di ticket per categoria negli ultimi N giorni.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="days",
                type=int,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Finestra temporale in giorni (default 30, max 365).",
            )
        ]
    )
    def get(self, request):
        raw_days = request.query_params.get("days", "30")
        try:
            days = int(raw_days)
        except ValueError:
            days = 30

        if days < 1:
            days = 1
        if days > 365:
            days = 365

        since = timezone.now() - timedelta(days=days)
        qs = Ticket.objects.filter(created_at__gte=since)

        agg = (
            qs.values("category")
            .annotate(count=Count("id"))
            .order_by("-count")
        )
        return Response(
            {
                "from": since,
                "to": timezone.now(),
                "by_category": list(agg),
            }
        )


class AnalyticsMttrView(APIView):
    """
    GET /api/analytics/mttr/?days=30

    Calcola il Mean Time To Resolve (in secondi) dei ticket
    risolti negli ultimi N giorni.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="days",
                type=int,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Finestra temporale in giorni (default 30, max 365).",
            )
        ]
    )
    def get(self, request):
        raw_days = request.query_params.get("days", "30")
        try:
            days = int(raw_days)
        except ValueError:
            days = 30

        if days < 1:
            days = 1
        if days > 365:
            days = 365

        since = timezone.now() - timedelta(days=days)

        qs = Ticket.objects.filter(
            created_at__gte=since,
            resolved_at__isnull=False,
        )

        # Mean Time To Resolve: media di (resolved_at - created_at)
        resolution_time = ExpressionWrapper(
            F("resolved_at") - F("created_at"),
            output_field=DurationField(),
        )

        agg = qs.aggregate(avg_resolution=Avg(resolution_time))
        return Response(
            {
                "from": since,
                "to": timezone.now(),
                "mttr_seconds": agg["avg_resolution"].total_seconds()
                if agg["avg_resolution"] is not None
                else None,
            }
        )
