from django.contrib import admin

from .models import LearningInsight, WeeklyLearningSummary


@admin.register(LearningInsight)
class LearningInsightAdmin(admin.ModelAdmin):
    list_display = ['id', 'student', 'insight_type', 'title', 'severity', 'actionable', 'acknowledged_at', 'generated_at']
    list_filter = ['insight_type', 'severity', 'actionable', 'generated_at']
    search_fields = ['student__username', 'title', 'description']
    readonly_fields = ['generated_at']
    date_hierarchy = 'generated_at'


@admin.register(WeeklyLearningSummary)
class WeeklyLearningSummaryAdmin(admin.ModelAdmin):
    list_display = ['id', 'student', 'week_start', 'total_study_minutes', 'modules_completed', 'exercises_completed', 'ai_interactions', 'generated_at']
    list_filter = ['week_start', 'generated_at']
    search_fields = ['student__username']
    readonly_fields = ['generated_at']
    date_hierarchy = 'week_start'
