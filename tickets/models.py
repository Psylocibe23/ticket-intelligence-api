from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()


class Ticket(models.Model):
    """
    Modello principale per i ticket di supporto.

    È mappato via ORM a una tabella nel database relazionale (PostgreSQL).
    Ogni istanza = una riga nella tabella.
    """
    STATUS_CHOICES = [
        ("OPEN", "Open"),
        ("IN_PROGRESS", "In progress"),
        ("RESOLVED", "Resolved"),
        ("CLOSED", "Closed"),
    ]

    PRIORITY_CHOICES = [
        ("LOW", "Low"),
        ("MEDIUM", "Medium"),
        ("HIGH", "High"),
    ]

    CATEGORY_CHOICES = [
        ("billing", "Billing"),
        ("account", "Account"),
        ("bug", "Bug"),
        ("feature", "Feature"),
        ("other", "Other"),
    ]

    title = models.CharField(max_length=200)
    description = models.TextField()

    # Metadati di business: stato nel workflow, priorità e categoria funzionale
    status = models.CharField(
        max_length=20, 
        choices=STATUS_CHOICES, 
        default="OPEN", 
        db_index=True,
        help_text="Stato del ticket nel workflow (open, in_progress, resolved, ...)",
    )
    priority = models.CharField(
        max_length=10, choices=PRIORITY_CHOICES, default="MEDIUM"
    )
    category = models.CharField(
        max_length=20,
        choices=CATEGORY_CHOICES,
        default="other",
        db_index=True,
        help_text="Categoria funzionale del ticket (es. billing, bug, question). Predetta anche dal modello ML.",
    )

    # Relazioni con gli utenti: chi ha creato il ticket e a chi è assegnato
    created_by = models.ForeignKey(
        User,
        related_name="created_tickets",
        on_delete=models.CASCADE,
    )
    assigned_to = models.ForeignKey(
        User,
        related_name="assigned_tickets",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_index=True,
    )

    # Timestamp di creazione/aggiornamento e, se presente, di risoluzione
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)


    def set_resolved_if_needed(self, old_status):
        # Mantiene coerente il campo resolved_at quando cambia lo status del ticket
        if old_status != "RESOLVED" and self.status == "RESOLVED":
            self.resolved_at = timezone.now()
        elif old_status == "RESOLVED" and self.status != "RESOLVED":
            self.resolved_at = None


    def save(self, *args, **kwargs):
        """
        Override di save per gestire automaticamente resolved_at
        quando lo status del ticket passa a RESOLVED o viene riaperto.
        """
        old_status = None
        if self.pk:
            old_status = Ticket.objects.filter(pk=self.pk).values_list("status", flat=True).first()
        super().save(*args, **kwargs)
        if old_status is not None:
            self.set_resolved_if_needed(old_status)
            super().save(update_fields=["resolved_at"])


    def __str__(self):
        return f"[{self.status}] {self.title[:40]}"
