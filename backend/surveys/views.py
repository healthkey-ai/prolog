from django.http import JsonResponse


def health(request):
    return JsonResponse({"service": "PROlog", "status": "ok"})
