# api/urls.py

from django.urls import path
from .views import get_route_data

urlpatterns = [
    path('route/', get_route_data, name='get_route_data'),
]
