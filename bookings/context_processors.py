from .models import Booking


def pending_bookings_count(request):
    if not request.user.is_authenticated:
        return {}

    count = Booking.objects.filter(
        company=request.user,
        status=Booking.Status.PENDING,
    ).count()

    return {"pending_bookings_count": count}
