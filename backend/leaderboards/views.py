from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from .models import Leaderboard, LeaderboardDrilldown
from .serializers import UserContributorSerializer

# Create your views here.
def get_leaderboard_api(request, arena_type):
    org_param = request.GET.get('org', 'ai4b')
    language_param = request.GET.get('language', 'Overall')
    
    leaderboard_entry = Leaderboard.objects.filter(
        arena_type=arena_type,
        organization=org_param,
        language=language_param
    ).first()
    
    if leaderboard_entry:
        data = leaderboard_entry.leaderboard_json
        if isinstance(data, list):
            for row in data:
                if isinstance(row, dict):
                    row['leaderboard_id'] = leaderboard_entry.id
        return JsonResponse(data, safe=False)
    else:
        return JsonResponse(
            {"error": f"No leaderboard found for Type: {arena_type}, Org: {org_param}, Language: {language_param}"}, 
            status=404
        )

def get_model_details(request, leaderboard_id, model_name):
    drilldown = get_object_or_404(
        LeaderboardDrilldown, 
        leaderboard_id=leaderboard_id, 
        model_name=model_name
    )
    
    data = {
        "model": drilldown.model_name,
        "domain_summary": drilldown.domain_summary,
        "benchmark_breakdown": drilldown.benchmark_breakdown
    }
    return JsonResponse(data)

from .services import calculate_top_contributors

class TopContributorsView(APIView):
    permission_classes = [AllowAny]
    def get(self, request):
        tenant_slug = request.query_params.get('tenant')
        language = request.query_params.get('language')
        arena_type_param = request.query_params.get('arena_type')

        try:
            results = calculate_top_contributors(
                tenant_slug=tenant_slug,
                language=language,
                arena_type=arena_type_param
            )
            serializer = UserContributorSerializer(results, many=True)
            return Response(serializer.data)
        except ValueError as e:
            if str(e) == "Tenant parameter is required":
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
            elif str(e) == "Invalid tenant":
                 return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)
            else:
                 return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
             return Response({"error": f"An unexpected error occurred: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def get_leaderboard_languages(request, arena_type):
    org_param = request.GET.get('org', 'ai4b')
    languages = Leaderboard.objects.filter(
        arena_type=arena_type,
        organization=org_param
    ).values_list('language', flat=True).distinct()
    
    return JsonResponse(list(languages), safe=False)