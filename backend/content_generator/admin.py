from django.contrib import admin
from .models import GeneratedTutorial, GeneratedQuiz, GeneratedDiagram, GeneratedCodeExercise


@admin.register(GeneratedTutorial)
class GeneratedTutorialAdmin(admin.ModelAdmin):
    list_display = ['id', 'title', 'difficulty', 'quality_score', 'is_approved', 'created_by', 'created_at']
    list_filter = ['difficulty', 'is_approved', 'created_at']
    search_fields = ['title', 'raw_content']
    readonly_fields = ['created_at', 'updated_at', 'content_type']


@admin.register(GeneratedQuiz)
class GeneratedQuizAdmin(admin.ModelAdmin):
    list_display = ['id', 'title', 'difficulty', 'question_count', 'quality_score', 'is_approved', 'created_at']
    list_filter = ['difficulty', 'is_approved', 'created_at']
    search_fields = ['title', 'raw_content']
    readonly_fields = ['created_at', 'updated_at', 'content_type']


@admin.register(GeneratedDiagram)
class GeneratedDiagramAdmin(admin.ModelAdmin):
    list_display = ['id', 'title', 'diagram_type', 'difficulty', 'quality_score', 'is_approved', 'created_at']
    list_filter = ['diagram_type', 'difficulty', 'is_approved', 'created_at']
    search_fields = ['title', 'raw_content']
    readonly_fields = ['created_at', 'updated_at', 'content_type']


@admin.register(GeneratedCodeExercise)
class GeneratedCodeExerciseAdmin(admin.ModelAdmin):
    list_display = ['id', 'title', 'language', 'difficulty', 'quality_score', 'is_approved', 'created_at']
    list_filter = ['language', 'difficulty', 'is_approved', 'created_at']
    search_fields = ['title', 'raw_content']
    readonly_fields = ['created_at', 'updated_at', 'content_type']
