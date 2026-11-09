from django.contrib import admin
from users.permissions import authorized_users
from data_security.adapters.persistence.fields import field_storage_enabled
from .models import (
    ExamLevelRule,
    TheoryQuestion, PracticeExam, PracticeExamQuestion,
    TheoryExam, TheoryExamQuestion, ExamRecord, ExamAnswer
)


@admin.register(ExamLevelRule)
class ExamLevelRuleAdmin(admin.ModelAdmin):
    list_display = ['id', 'grade', 'title', 'min_score', 'sort_order', 'is_active']
    list_filter = ['is_active']
    search_fields = ['grade', 'title', 'description']
    ordering = ['-min_score', 'sort_order']


@admin.register(TheoryQuestion)
class TheoryQuestionAdmin(admin.ModelAdmin):
    def get_queryset(self, request):
        rows = super().get_queryset(request)
        return rows.filter(security_state='sealed-v1') if field_storage_enabled() else rows

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))
        return fields + ['correct_answer'] if obj and obj.security_state != 'legacy-v0' else fields

    list_display = ['id', 'question_type', 'category', 'difficulty', 'points', 'is_active', 'created_at']
    list_filter = ['question_type', 'category', 'difficulty', 'is_active']
    search_fields = ['question_text']
    list_editable = ['points', 'is_active']
    readonly_fields = ['created_at', 'updated_at']

    fieldsets = (
        ('基本信息', {
            'fields': ('question_type', 'category', 'difficulty', 'is_active')
        }),
        ('题目内容', {
            'fields': ('question_text', 'options', 'correct_answer', 'explanation', 'points')
        }),
        ('时间信息', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(PracticeExam)
class PracticeExamAdmin(admin.ModelAdmin):
    list_display = ['id', 'title', 'status', 'duration', 'total_points', 'created_by', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['title', 'description']
    list_editable = ['status', 'duration']
    readonly_fields = ['created_at', 'updated_at']

    fieldsets = (
        ('基本信息', {
            'fields': ('title', 'description', 'status')
        }),
        ('考试设置', {
            'fields': ('duration', 'total_points', 'easy_count', 'medium_count', 'hard_count')
        }),
        ('创建信息', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(PracticeExamQuestion)
class PracticeExamQuestionAdmin(admin.ModelAdmin):
    list_display = ['id', 'exam', 'challenge', 'order']
    list_filter = ['exam']
    list_editable = ['order']


class TheoryExamQuestionInline(admin.TabularInline):
    model = TheoryExamQuestion
    extra = 0
    readonly_fields = ['question']


@admin.register(TheoryExam)
class TheoryExamAdmin(admin.ModelAdmin):
    list_display = ['id', 'title', 'status', 'duration', 'total_points', 'pass_score', 'max_attempts', 'created_by']
    list_filter = ['status', 'created_at']
    search_fields = ['title', 'description']
    list_editable = ['status', 'duration', 'pass_score', 'max_attempts']
    readonly_fields = ['created_at', 'updated_at']

    fieldsets = (
        ('基本信息', {
            'fields': ('title', 'description', 'status')
        }),
        ('考试设置', {
            'fields': ('duration', 'total_points', 'random_order', 'pass_score', 'max_attempts')
        }),
        ('创建信息', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    inlines = [TheoryExamQuestionInline]


@admin.register(TheoryExamQuestion)
class TheoryExamQuestionAdmin(admin.ModelAdmin):
    list_display = ['id', 'exam', 'question', 'order', 'points']
    list_filter = ['exam']
    list_editable = ['order', 'points']


class ExamAnswerInline(admin.TabularInline):
    model = ExamAnswer
    extra = 0
    readonly_fields = ['theory_question', 'practice_question', 'user_answer', 'is_correct', 'points_earned']


@admin.register(ExamRecord)
class ExamRecordAdmin(admin.ModelAdmin):
    def get_queryset(self, request):
        rows = super().get_queryset(request)
        if field_storage_enabled():
            course = request.GET.get('course', '')
            rows = rows.filter(user__in=authorized_users(request.user, int(course) if course.isdecimal() else None))
        return rows

    list_display = ['id', 'user', 'exam_type', 'theory_exam', 'practice_exam', 'status', 'score', 'is_passed', 'start_time']
    list_filter = ['exam_type', 'status', 'is_passed', 'created_at']
    search_fields = ['user__username']
    readonly_fields = ['start_time', 'created_at']
    inlines = [ExamAnswerInline]

    fieldsets = (
        ('考试信息', {
            'fields': ('user', 'exam_type', 'theory_exam', 'practice_exam', 'status')
        }),
        ('成绩信息', {
            'fields': ('score', 'total_points', 'correct_count', 'total_questions', 'is_passed')
        }),
        ('时间信息', {
            'fields': ('start_time', 'end_time', 'time_spent')
        }),
    )


@admin.register(ExamAnswer)
class ExamAnswerAdmin(admin.ModelAdmin):
    def get_queryset(self, request):
        rows = super().get_queryset(request)
        if field_storage_enabled():
            course = request.GET.get('course', '')
            rows = rows.filter(exam_record__user__in=authorized_users(request.user, int(course) if course.isdecimal() else None),
                               security_state='sealed-v1')
        return rows

    list_display = ['id', 'exam_record', 'theory_question', 'practice_question', 'user_answer', 'is_correct', 'points_earned']
    list_filter = ['is_correct']
    search_fields = ['exam_record__user__username']

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))
        return fields + ['user_answer'] if obj and obj.security_state != 'legacy-v0' else fields
    readonly_fields = ['created_at', 'updated_at']
