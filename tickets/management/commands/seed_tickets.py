import random
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from tickets.models import Ticket

User = get_user_model()


BILLING_TITLES = [
    "Invoice not received",
    "Payment failed on checkout",
    "Double charge on my credit card",
]

ACCOUNT_TITLES = [
    "Cannot reset password",
    "Account locked after login attempts",
    "Email change not working",
]

BUG_TITLES = [
    "Error 500 on dashboard",
    "Mobile app crashes on startup",
    "Search returns no results",
]

FEATURE_TITLES = [
    "Request for dark mode",
    "Add export to CSV option",
    "Support for SSO login",
]

OTHER_TITLES = [
    "General question about pricing",
    "Feedback on user interface",
    "Issue not categorized",
]


class Command(BaseCommand):
    help = "Crea ticket demo sintetici per la sandbox ML/analytics"

    def add_arguments(self, parser):
        parser.add_argument(
            "--n",
            type=int,
            default=200,
            help="Numero di ticket demo da creare (default: 200)",
        )

    def handle(self, *args, **options):
        n = options["n"]

        demo_user, created = User.objects.get_or_create(
            username="demo",
            defaults={
                "email": "demo@example.com",
            },
        )
        if created:
            demo_user.set_password("changeme-demo-password")
            demo_user.save()
            self.stdout.write(self.style.SUCCESS("Created demo user: demo"))
        else:
            self.stdout.write("Demo user already exists: demo")

        # Solo per la demo: puliamo tutto
        Ticket.objects.all().delete()

        now = timezone.now()

        status_choices = [s[0] for s in Ticket.STATUS_CHOICES]
        priority_choices = [p[0] for p in Ticket.PRIORITY_CHOICES]
        category_choices = [c[0] for c in Ticket.CATEGORY_CHOICES]

        for i in range(n):
            category = random.choice(category_choices)
            status = random.choice(status_choices)
            priority = random.choice(priority_choices)

            # created_at in una finestra negli ultimi 90 giorni
            days_ago = random.randint(0, 90)
            created_at = now - timedelta(days=days_ago)

            resolved_at = None
            if status in ("RESOLVED", "CLOSED"):
                hours_to_resolve = random.randint(1, 72)
                resolved_at = created_at + timedelta(hours=hours_to_resolve)

            title = f"Synthetic ticket {i+1} about {category}"
            description = (
                f"Synthetic ticket {i+1} about {category}. "
                "Auto-generated for demo."
            )

            # 1) primo save: lascia che Django gestisca auto_now_add su created_at
            ticket = Ticket.objects.create(
                title=title,
                description=description,
                status=status,
                priority=priority,
                category=category,
                created_by=demo_user,
                assigned_to=None,
            )

            # 2) secondo save: forziamo created_at / resolved_at in modo consistente
            ticket.created_at = created_at
            ticket.resolved_at = resolved_at
            ticket.save(update_fields=["created_at", "resolved_at"])

        self.stdout.write(self.style.SUCCESS(f"Created {n} synthetic tickets"))
