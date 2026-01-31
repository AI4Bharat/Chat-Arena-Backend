from django.urls import path
from . import views

urlpatterns = [
    path('pai/sample/sub_domain', views.sample_sub_domain, name='pai-sample-sub-domain'),
    path('pai/sample/topic_and_persona', views.sample_topic_and_persona, name='pai-sample-topic-persona'),
    path('pai/sample/scenario', views.sample_scenario, name='pai-sample-scenario'),
    path('pai/sample/sentence', views.sample_sentence, name='pai-sample-sentence'),
    path('pai/create', views.create_dataset_job, name='pai-create'),
    path('pai/jobs', views.list_jobs, name='pai-jobs'),
    path('pai/status/<str:job_id>', views.job_status, name='pai-status'),
]
