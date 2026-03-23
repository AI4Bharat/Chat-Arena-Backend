from django.shortcuts import render
from django.http import JsonResponse
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from django.db.models import Q
from django.views.decorators.cache import cache_page
from django.utils.decorators import method_decorator
from .models import Leaderboard
from .serializers import UserContributorSerializer
from ai_model.models import AIModel

# Create your views here.
@cache_page(60 * 15)
def get_leaderboard_api(request, arena_type, sub_arena=None):
    org_param = request.GET.get('org', 'ai4b')
    language_param = request.GET.get('language', 'Overall')
    
    filters = {
        'arena_type': arena_type,
        'organization': org_param,
        'language': language_param,
        'is_active': True
    }
    
    if sub_arena:
        filters['benchmark_name'] = sub_arena

    leaderboard_entry = Leaderboard.objects.filter(**filters).first()
    
    if leaderboard_entry:
        leaderboard_data = leaderboard_entry.leaderboard_json
        
        # Enrich data with organization and url from AIModel
        if isinstance(leaderboard_data, list):
            model_names = [item.get('model') for item in leaderboard_data if isinstance(item, dict) and 'model' in item]
            
            # Single query using OR logic for efficiency
            ai_models_queryset = AIModel.objects.filter(
                Q(model_name__in=model_names) | Q(model_code__in=model_names)
            )
            
            # Build a single lookup map (Mapping both name and code to the object)
            lookup_map = {}
            for m in ai_models_queryset:
                lookup_map[m.model_name] = m
                lookup_map[m.model_code] = m
            
            for item in leaderboard_data:
                if isinstance(item, dict):
                    m_name = item.get('model')
                    ai_info = lookup_map.get(m_name)
                    
                    if ai_info:
                        # Use .get() or 'or' to prevent overwriting existing valid data
                        item['organization'] = item.get('organization') or ai_info.provider
                        item['url'] = item.get('url') or ai_info.url
                        item['display_name'] = item.get('display_name') or ai_info.display_name
                        item['license'] = item.get('license') or ai_info.license
        
        response_payload = {
            "last_updated": leaderboard_entry.calculated_at.isoformat() if leaderboard_entry.calculated_at else None,
            "data": leaderboard_data
        }
        
        return JsonResponse(response_payload)
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
    
    @method_decorator(cache_page(60 * 15))
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


@cache_page(60 * 15)
def get_leaderboard_languages(request, arena_type, sub_arena=None):
    org_param = request.GET.get('org', 'ai4b')
    filters = {
        'arena_type': arena_type,
        'organization': org_param,
        'is_active': True
    }
    if sub_arena:
        filters['benchmark_name'] = sub_arena

    languages = Leaderboard.objects.filter(**filters).values_list('language', flat=True).distinct()
    
    return JsonResponse(list(languages), safe=False)
