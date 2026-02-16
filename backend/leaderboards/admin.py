from django.contrib import admin
from .models import Leaderboard

# Register your models here.
@admin.register(Leaderboard)
class LeaderboardAdmin(admin.ModelAdmin):
    list_display = ('benchmark_name', 'language', 'arena_type', 'organization', 'updated_at')
    list_filter = ('arena_type', 'organization', 'language')
    search_fields = ('benchmark_name',)