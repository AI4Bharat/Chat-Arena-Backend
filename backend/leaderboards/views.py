from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from .models import Leaderboard

# Create your views here.
def get_leaderboard_api(request, arena_type):
    org_param = request.GET.get('org', 'ai4bharat')
    leaderboard_entry = Leaderboard.objects.filter(
        arena_type=arena_type,
        organization=org_param
    ).first()
    if leaderboard_entry:
        return JsonResponse(leaderboard_entry.leaderboard_json, safe=False)
    else:
        return JsonResponse(
            {"error": f"No leaderboard found for Type: {arena_type}, Org: {org_param}"}, 
            status=404
        )