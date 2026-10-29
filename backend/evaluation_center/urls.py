from django.urls import path

from . import evaluation_views, operations_views, views

urlpatterns = [
    path('students/', views.StudentListView.as_view(), name='m8-students'),
    path('learning/', views.LearningView.as_view(), name='m8-learning'),
    path('attempts/<uuid:attempt_id>/', views.AttemptDetailView.as_view(), name='m8-attempt'),
    path('runtime/', views.RuntimeView.as_view(), name='m8-runtime'),
    path('todos/', operations_views.TodoListView.as_view(), name='m8-todos'),
    path('todos/sync/', operations_views.TodoSyncView.as_view(), name='m8-todo-sync'),
    path('todos/<uuid:todo_id>/', operations_views.TodoChangeView.as_view(), name='m8-todo-change'),
    path('receipts/', operations_views.ReceiptView.as_view(), name='m8-receipts'),
    path('runs/', evaluation_views.EvaluationRunsView.as_view(), name='m8-runs'),
    path('runs/<uuid:run_id>/', evaluation_views.EvaluationRunView.as_view(), name='m8-run'),
    path('runs/<uuid:run_id>/execute/', evaluation_views.EvaluationExecuteView.as_view(), name='m8-execute'),
    path('runs/<uuid:run_id>/interrupt/', evaluation_views.EvaluationInterruptView.as_view(), name='m8-interrupt'),
    path('reports/<uuid:report_id>/', evaluation_views.EvaluationReportView.as_view(), name='m8-report'),
]
