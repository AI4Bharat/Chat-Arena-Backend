from django.contrib import admin
from .models import Leaderboard

# Register your models here.
@admin.register(Leaderboard)
class LeaderboardAdmin(admin.ModelAdmin):
    # This makes the list view much more readable
    list_display = ('benchmark_name', 'language', 'arena_type', 'organization', 'updated_at')
    
    # Adds filters to the right sidebar
    list_filter = ('arena_type', 'organization', 'language')
    
    # Allows you to search by benchmark name
    search_fields = ('benchmark_name',)

from .models import LeaderboardDrilldown

@admin.register(LeaderboardDrilldown)
class LeaderboardDrilldownAdmin(admin.ModelAdmin):
    list_display = ('model_name', 'leaderboard', 'has_domain_summary', 'has_benchmark_breakdown')
    list_filter = ('leaderboard__language', 'leaderboard__arena_type')
    search_fields = ('model_name',)
    
    def has_domain_summary(self, obj):
        return bool(obj.domain_summary)
    has_domain_summary.boolean = True
    
    def has_benchmark_breakdown(self, obj):
        return bool(obj.benchmark_breakdown)
    has_benchmark_breakdown.boolean = True