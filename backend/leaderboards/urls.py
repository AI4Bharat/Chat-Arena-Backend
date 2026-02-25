from django.urls import path
from . import views

urlpatterns = [
    path('leaderboard/contributors/', views.TopContributorsView.as_view(), name='top_contributors'),
    path('leaderboard/<str:arena_type>/', views.get_leaderboard_api, name='get_leaderboard_api'),
    path('leaderboard/<str:arena_type>/languages/', views.get_leaderboard_languages, name='get_leaderboard_languages'),
]