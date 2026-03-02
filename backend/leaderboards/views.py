from django.shortcuts import render
from django.http import JsonResponse
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from .models import Leaderboard
from .serializers import UserContributorSerializer

# Create your views here.
def get_leaderboard_api(request, arena_type, sub_arena=None):
    org_param = request.GET.get('org', 'ai4b')
    language_param = request.GET.get('language', 'Overall')
    
    filters = {
        'arena_type': arena_type,
        'organization': org_param,
        'language': language_param
    }
    
    if sub_arena:
        filters['benchmark_name'] = sub_arena

    leaderboard_entry = Leaderboard.objects.filter(**filters).first()
    
    if leaderboard_entry:
        return JsonResponse(leaderboard_entry.leaderboard_json, safe=False)
    else:
        error_msg = f"No leaderboard found for Type: {arena_type}, Org: {org_param}, Language: {language_param}"
        if sub_arena:
             error_msg += f", Sub Arena: {sub_arena}"
        return JsonResponse(
            {"error": error_msg}, 
            status=404
        )

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


def get_leaderboard_languages(request, arena_type, sub_arena=None):
    org_param = request.GET.get('org', 'ai4b')
    filters = {
        'arena_type': arena_type,
        'organization': org_param
    }
    if sub_arena:
        filters['benchmark_name'] = sub_arena

    languages = Leaderboard.objects.filter(**filters).values_list('language', flat=True).distinct()
    
    return JsonResponse(list(languages), safe=False)