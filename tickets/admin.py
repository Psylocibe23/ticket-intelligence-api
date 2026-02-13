from django.contrib import admin
from .models import Ticket


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "status", "priority", "category", "created_at", "assigned_to")
    list_filter = ("status", "priority", "category", "created_at")
    search_fields = ("title", "description")
