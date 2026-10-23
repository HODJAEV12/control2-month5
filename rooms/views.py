from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.core.cache import cache
from .models import Room, Booking
from .serializers import RoomSerializer, BookingSerializer
from .permissions import IsAdminOrReadOnly, IsOwnerOrAdmin

class RoomViewSet(viewsets.ModelViewSet):
    queryset = Room.objects.all()
    serializer_class = RoomSerializer
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['is_active', 'capacity']
    search_fields = ['name', 'description']
    ordering_fields = ['price_per_hour', 'capacity']

    def list(self, request, *args, **kwargs):
        cache_key = 'room_list_cache'
        cached_data = cache.get(cache_key)
        if cached_data is not None:
            return Response(cached_data)
        
        response = super().list(request, *args, **kwargs)
        cache.set(cache_key, response.data, 60)
        return response

    def perform_create(self, serializer):
        serializer.save()
        cache.delete('room_list_cache')

    def perform_update(self, serializer):
        serializer.save()
        cache.delete('room_list_cache')

    def perform_destroy(self, instance):
        instance.delete()
        cache.delete('room_list_cache')


class BookingViewSet(viewsets.ModelViewSet):
    serializer_class = BookingSerializer
    permission_classes = [IsAuthenticated, IsOwnerOrAdmin]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['status', 'room']
    ordering_fields = ['start_time', 'created_at']

    def get_queryset(self):
        user = self.request.user
        qs = Booking.objects.select_related('room', 'user__profile')
        if user.is_staff:
            return qs
        return qs.filter(user=user)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        booking = self.get_object()
        if booking.status == 'cancelled':
            return Response({
                "detail": "Бронирование уже отменено."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        booking.status = 'cancelled'
        booking.save()

        profile = booking.user.profile
        profile.balance += booking.total_price
        profile.save()

        return Response({
            "detail": "Бронирование отменено, средства возвращены на баланс."
        }, status=status.HTTP_200_OK)