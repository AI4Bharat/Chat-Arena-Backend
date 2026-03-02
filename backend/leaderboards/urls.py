from django.urls import path
from . import views

urlpatterns = [
    path('leaderboard/contributors/', views.TopContributorsView.as_view(), name='top_contributors'),
    path('leaderboard/<str:arena_type>/languages/', views.get_leaderboard_languages, name='get_leaderboard_languages'),
    path('leaderboard/<str:arena_type>/<str:sub_arena>/languages/', views.get_leaderboard_languages, name='get_leaderboard_languages_sub'),
    path('leaderboard/<str:arena_type>/<str:sub_arena>/', views.get_leaderboard_api, name='get_leaderboard_api_sub'),
    path('leaderboard/<str:arena_type>/', views.get_leaderboard_api, name='get_leaderboard_api'),
]