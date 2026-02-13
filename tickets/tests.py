from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from rest_framework.test import APITestCase

from .models import Ticket
from .ml_utils import train_model, predict_category_for_ticket, get_similar_tickets


User = get_user_model()


class TicketModelTests(TestCase):
    """
    Test di base sul modello Ticket:
    - gestione di created_at / resolved_at
    - transizione di stato verso/da RESOLVED
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="user",
            email="user@example.com",
            password="supersecurepassword123",
        )

    def test_resolved_at_set_when_status_becomes_resolved(self):
        """
        Quando un ticket passa da NON RESOLVED a RESOLVED,
        resolved_at deve essere valorizzato (>= created_at).
        """
        ticket = Ticket.objects.create(
            title="Test ticket",
            description="Just a test",
            status="OPEN",
            priority="MEDIUM",
            category="other",
            created_by=self.user,
        )

        self.assertIsNone(ticket.resolved_at)

        ticket.status = "RESOLVED"
        ticket.save()

        ticket.refresh_from_db()
        self.assertIsNotNone(ticket.resolved_at)
        self.assertGreaterEqual(ticket.resolved_at, ticket.created_at)

    def test_resolved_at_cleared_when_ticket_reopened(self):
        """
        Quando un ticket RESOLVED viene riaperto,
        resolved_at deve tornare a None.
        """
        ticket = Ticket.objects.create(
            title="Resolved ticket",
            description="Already resolved",
            status="RESOLVED",
            priority="LOW",
            category="bug",
            created_by=self.user,
        )

        # Forziamo resolved_at per simulare un ticket già risolto
        now = timezone.now()
        ticket.resolved_at = now
        ticket.save(update_fields=["resolved_at"])

        ticket.status = "OPEN"
        ticket.save()
        ticket.refresh_from_db()

        self.assertIsNone(ticket.resolved_at)


class TicketAPITests(APITestCase):
    """
    Test sugli endpoint REST principali:
    - lista / filtro / ordinamento
    - azioni extra: assign, transition
    - ML: train, ml_predict, similar
    - Analytics: trends, mttr
    """

    def setUp(self):
        # Utente autenticato per le chiamate API
        self.user = User.objects.create_user(
            username="apiuser",
            email="apiuser@example.com",
            password="supersecurepassword123",
        )
        self.client.force_authenticate(user=self.user)

        # Creiamo un po' di ticket con categorie diverse
        self.ticket_billing = Ticket.objects.create(
            title="Billing issue",
            description="Card not working",
            status="OPEN",
            priority="HIGH",
            category="billing",
            created_by=self.user,
        )
        self.ticket_bug = Ticket.objects.create(
            title="Bug on dashboard",
            description="Error 500 when loading",
            status="OPEN",
            priority="MEDIUM",
            category="bug",
            created_by=self.user,
            assigned_to=self.user,
        )

        # Ticket già risolto, per testare MTTR/analytics
        base_time = timezone.now() - timedelta(hours=5)

        self.ticket_resolved = Ticket.objects.create(
            title="Old resolved ticket",
            description="Some resolved issue",
            status="RESOLVED",
            priority="LOW",
            category="feature",
            created_by=self.user,
        )

        # Forziamo i timestamp in modo che created_at < resolved_at
        self.ticket_resolved.created_at = base_time
        self.ticket_resolved.resolved_at = base_time + timedelta(hours=1)
        self.ticket_resolved.save(update_fields=["created_at", "resolved_at"])

    def test_ticket_list_basic(self):
        """
        GET /api/tickets/ deve tornare una lista paginata di ticket.
        """
        url = reverse("tickets-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        # PageNumberPagination: risposta del tipo {"count":..., "results":[...]}
        self.assertIn("results", response.data)
        self.assertGreaterEqual(len(response.data["results"]), 3)

    def test_ticket_list_filter_assigned_to_me(self):
        """
        GET /api/tickets/?assigned_to=me deve tornare solo
        i ticket assegnati all'utente corrente.
        """
        url = reverse("tickets-list")
        response = self.client.get(url, {"assigned_to": "me"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("results", response.data)

        ids = {item["id"] for item in response.data["results"]}
        self.assertIn(self.ticket_bug.id, ids)
        self.assertNotIn(self.ticket_billing.id, ids)

    def test_assign_action(self):
        """
        POST /api/tickets/{id}/assign/
        assegna il ticket ad un utente specifico.
        """
        url = reverse("tickets-assign", args=[self.ticket_billing.id])
        response = self.client.post(
            url, {"assigned_to": self.user.id}, format="json"
        )
        self.assertEqual(response.status_code, 200)

        self.ticket_billing.refresh_from_db()
        self.assertEqual(self.ticket_billing.assigned_to, self.user)

    def test_transition_action(self):
        """
        POST /api/tickets/{id}/transition/
        cambia lo stato del ticket.
        """
        url = reverse("tickets-transition", args=[self.ticket_billing.id])
        response = self.client.post(
            url, {"status": "IN_PROGRESS"}, format="json"
        )
        self.assertEqual(response.status_code, 200)

        self.ticket_billing.refresh_from_db()
        self.assertEqual(self.ticket_billing.status, "IN_PROGRESS")

    def test_ml_train_and_predict(self):
        """
        - POST /api/ml/train/ deve allenare il modello
        - l'azione ml_predict deve restituire una categoria con confidenza
        """
        # 1) train via API
        train_url = reverse("ml-train")
        train_response = self.client.post(train_url, format="json")
        self.assertEqual(train_response.status_code, 200)
        self.assertGreaterEqual(train_response.data["n_samples"], 2)
        self.assertGreaterEqual(train_response.data["n_classes"], 2)

        # 2) ml_predict su un ticket
        # NB: il nome corretto della route è tickets-ml-predict (trattino)
        predict_url = reverse("tickets-ml-predict", args=[self.ticket_billing.id])
        predict_response = self.client.post(predict_url, format="json")
        self.assertEqual(predict_response.status_code, 200)
        self.assertIn("category", predict_response.data)
        # se LogisticRegression con predict_proba, c'è anche confidence
        self.assertIn("confidence", predict_response.data)

    def test_similar_endpoint_with_top_param(self):
        """
        GET /api/tickets/{id}/similar/?top=1 deve rispettare il limite top.
        """
        # Alleniamo il modello (necessario per avere il tfidf nel pipeline)
        train_model()

        url = reverse("tickets-similar", args=[self.ticket_bug.id])
        response = self.client.get(url, {"top": 1})
        self.assertEqual(response.status_code, 200)
        # Deve ritornare al massimo 1 elemento
        self.assertLessEqual(len(response.data), 1)

    def test_analytics_trends(self):
        """
        GET /api/analytics/trends/?days=30 deve tornare
        un aggregato per categoria.
        """
        url = reverse("analytics-trends")
        response = self.client.get(url, {"days": 30})
        self.assertEqual(response.status_code, 200)
        self.assertIn("by_category", response.data)
        self.assertIsInstance(response.data["by_category"], list)
        # Almeno una categoria presente
        self.assertGreater(len(response.data["by_category"]), 0)

    def test_analytics_mttr_positive(self):
        """
        GET /api/analytics/mttr/?days=90 deve restituire un MTTR
        non nullo e positivo (abbiamo creato almeno un ticket risolto).
        """
        url = reverse("analytics-mttr")
        response = self.client.get(url, {"days": 90})
        self.assertEqual(response.status_code, 200)
        mttr = response.data["mttr_seconds"]
        self.assertIsNotNone(mttr)
        self.assertGreater(mttr, 0)
