import json
import asyncio
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async

from .models import Job
from .views import _sync_job_status_from_pai

class JobStatusConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope.get('user')
        if not user or user.is_anonymous:
            await self.close(code=4003)
            return

        self.user = user
        self.room_group_name = f'user_jobs_{self.user.id}'

        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()

        # Start the background polling task
        self.polling_task = asyncio.create_task(self.poll_active_jobs())

    async def disconnect(self, close_code):
        # Leave room group
        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )
        
        # Stop polling
        if hasattr(self, 'polling_task') and not self.polling_task.done():
            self.polling_task.cancel()

    @sync_to_async
    def get_active_jobs(self):
        """Fetch all active processing jobs for the user."""
        active_statuses = [
            'SUBMITTING', 'SUBMITTED', 'PROCESSING', 
            'SENTENCE_GENERATED', 'AUDIO_GENERATED', 
            'AUDIO_VERIFIED', 'DATASET_GENERATED'
        ]
        return list(Job.objects.filter(
            created_by=self.user,
            status__in=active_statuses
        ))

    @sync_to_async
    def sync_and_format_job(self, job):
        """Sync a single job with PAI and format it for the frontend."""
        # This calls the existing _sync_job_status_from_pai which fetches over HTTP
        # and saves to the DB if there's a change
        updated_job = _sync_job_status_from_pai(job)
        
        # Format the job payload exactly like the list_jobs API view does
        payload = updated_job.payload or {}
        if isinstance(payload, dict) and 'language' in payload:
            config = payload
        else:
            config = payload.get('config', payload if isinstance(payload, dict) else {})
            
        sentence_config = config.get('sentence', {})
        
        return {
            'jobId': updated_job.job_id,
            'language': config.get('language') or payload.get('language') or 'Unknown',
            'size': config.get('size') or payload.get('size') or 0,
            'status': updated_job.status,
            'progress': updated_job.progress_percentage,
            'currentStage': updated_job.current_step or 'Pending',
            'createdAt': updated_job.created_at.isoformat() if updated_job.created_at else None,
            'completedAt': updated_job.updated_at.isoformat() if updated_job.status == 'COMPLETED' and updated_job.updated_at else None,
            'errorMessage': updated_job.error.get('message', '') if updated_job.error else None,
            'category': sentence_config.get('category') or config.get('category') or '',
            'generationAttempts': updated_job.generation_attempts or 0,
        }

    async def poll_active_jobs(self):
        """Background loop that occasionally checks PAI and pushes updates."""
        try:
            first_run = True
            while True:
                # 1. Fetch user's active jobs from the DB
                active_jobs = await self.get_active_jobs()
                
                # 2. Iterate through them and sync with PAI
                updated_job_data_list = []
                for job in active_jobs:
                    # Capture old status
                    old_status = job.status
                    old_progress = job.progress_percentage
                    
                    # Sync and format
                    job_dto = await self.sync_and_format_job(job)
                    
                    # If status or progress changed, or it's the first run, push it down the websocket
                    if first_run or job_dto['status'] != old_status or job_dto['progress'] != old_progress:
                        updated_job_data_list.append(job_dto)
                
                # 3. If any jobs changed (or first run), broadcast them
                if updated_job_data_list:
                    await self.channel_layer.group_send(
                        self.room_group_name,
                        {
                            'type': 'jobs_update',
                            'jobs': updated_job_data_list
                        }
                    )
                first_run = False
                
                # 4. Wait a few seconds before polling again
                await asyncio.sleep(4)
                
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"Error in WebSocket polling loop: {e}")

    # Receive job update events from the group
    async def jobs_update(self, event):
        jobs = event['jobs']

        # Send message to WebSocket
        await self.send(text_data=json.dumps({
            'type': 'jobs_update',
            'jobs': jobs
        }))
