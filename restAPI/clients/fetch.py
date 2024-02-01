from django.db.models import Q
from rest_framework.authentication import TokenAuthentication
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from backend.models import Client
from .serializers import ClientReturnedSerializer
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

search_param = openapi.Parameter(
    "search",
    openapi.IN_QUERY,
    description="A search string for a client name, email or id",
    type=openapi.TYPE_STRING,
    required=False,
)

user_response = openapi.Response("Clients List", ClientReturnedSerializer)


@swagger_auto_schema(
    manual_parameters=[search_param],
    method="GET",
    responses={200: user_response},
)
@api_view(["GET"])
@authentication_classes([TokenAuthentication])
@permission_classes([IsAuthenticated])
def fetch_all_clients(request):
    search_text = request.GET.get("search")

    clients = Client.objects.filter(user=request.user, active=True)

    if search_text:
        clients = clients.filter(
            Q(name__icontains=search_text)
            | Q(email__icontains=search_text)
            | Q(id__icontains=search_text)
        )

    serializer = ClientReturnedSerializer(clients, many=True)
    return Response(serializer.data)