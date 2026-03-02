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
    path('pai/resubmit/<str:job_id>', views.resubmit_job, name='pai-resubmit'),
    path('pai/job/<str:job_id>', views.get_job_dataset, name='pai-job-dataset'),
    path('pai/audio/<str:audio_id>', views.get_audio_file, name='pai-audio-file'),
    path('pai/metrics/<str:job_id>', views.get_job_metrics, name='pai-metrics'),
    path('pai/download/<str:job_id>', views.get_download_link, name='pai-download'),
]
