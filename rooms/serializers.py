from rest_framework import serializers
from .models import Room

from decimal import Decimal
from rest_framework import serializers
from django.core.cache import cache
from django.utils import timezone
from .models import Room, Booking, UserProfile

class RoomSerializer(serializers.ModelSerializer):
    class Meta:
        model = Room
        fields = '__all__'

    def validate_price_per_hour(self, value):
        if value <= 0:
            raise serializers.ValidationError("Стоимость часа должна быть больше нуля.")
        return value


class UserProfileSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    email = serializers.CharField(source='user.email', read_only=True)

    class Meta:
        model = UserProfile
        fields = ['id', 'username', 'email', 'phone_number', 'balance']
        read_only_fields = ('balance',)


class BookingSerializer(serializers.ModelSerializer):
    room_name = serializers.CharField(source='room.name', read_only=True)

    class Meta:
        model = Booking
        fields = ['id', 'room', 'room_name', 'start_time', 'end_time', 'total_price', 'status', 'created_at']
        read_only_fields = ['user', 'total_price', 'status', 'created_at']

    def validate(self, data):
        room = data['room']
        start_time = data['start_time']
        end_time = data['end_time']
        now = timezone.now()

        if start_time < now:
            raise serializers.ValidationError({"start_time": "Нельзя бронировать на прошедшее время."})

        if not room.is_active:
            raise serializers.ValidationError({"room": "Эта комната неактивна и недоступна для бронирования."})

        if start_time >= end_time:
            raise serializers.ValidationError("Время окончания должно быть позже времени начала.")
        
        duration_hours = (end_time - start_time).total_seconds() / 3600
        if not (1 <= duration_hours <= 12):
            raise serializers.ValidationError("Продолжительность бронирования должна составлять от 1 до 12 часов.")

        overlapping = Booking.objects.filter(room=room, status__in=['pending', 'confirmed']
        )
        if self.instance:
            overlapping = overlapping.exclude(pk=self.instance.pk)
            
        if overlapping.exists():
            raise serializers.ValidationError("Выбранное время пересекается с другим бронированием.")

        user = self.context['request'].user
        total_price = room.price_per_hour * int(round(duration_hours))
        
        data['calculated_price'] = room.price_per_hour * Decimal(str(duration_hours))
        
        if user.profile.balance < data['calculated_price']:
            raise serializers.ValidationError({"balance": "Недостаточно средств на внутреннем балансе."})

        return data

    def create(self, validated_data):
        price = validated_data.pop('calculated_price')
        user = self.context['request'].user

        profile = user.profile
        profile.balance -= price
        profile.save()

        validated_data['user'] = user
        validated_data['total_price'] = price
        return super().create(validated_data)