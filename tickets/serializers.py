from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Ticket

User = get_user_model()


class TicketSerializer(serializers.ModelSerializer):
    """
    Serializza i Ticket in JSON e fa da ponte tra ORM e API REST.

    Viene usato sia per la lista/dettaglio dei ticket, sia nelle azioni extra
    (assign, transition, ecc.).
    """
    created_by = serializers.StringRelatedField(read_only=True)
    assigned_to = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), allow_null=True, required=False
    )

    class Meta:
        model = Ticket
        fields = [
            "id",
            "title",
            "description",
            "status",
            "priority",
            "category",
            "created_by",
            "assigned_to",
            "created_at",
            "updated_at",
            "resolved_at",
        ]
        read_only_fields = ("created_at", "updated_at", "resolved_at", "created_by")

    def create(self, validated_data):
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            validated_data["created_by"] = request.user
        return super().create(validated_data)

    def update(self, instance, validated_data):
        # Puoi aggiungere logica custom se vuoi, per ora delega a ModelSerializer
        return super().update(instance, validated_data)
