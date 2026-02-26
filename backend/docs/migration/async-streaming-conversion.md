# Async Streaming View Conversion

## Current Implementation Analysis

**File:** message/views.py
**Method:** MessageViewSet.stream()

### Current Architecture:
1. **Sync view** using threading for concurrent streams
2. Uses \queue.Queue()\ to coordinate threads
3. Two threads (\stream_model_a\, \stream_model_b\) for compare mode
4. Blocks on \	hread.join()\ waiting for completion
5. Uses \equests\ (sync) for HTTP calls to AI providers

### Problems:
- Thread overhead (creates 2+ threads per request)
- Queue blocking wastes resources
- Cannot handle many concurrent requests efficiently
- \	hread.join()\ blocks the worker

---

## Async Conversion Strategy

### Phase 1: Create Async Version (Keep Sync for Now)

Create \message/views_async.py\ with async streaming views:

\\\python
# message/views_async.py
from rest_framework.viewsets import ViewSet
from rest_framework.decorators import action
from rest_framework.response import Response
from django.http import StreamingHttpResponse
from asgiref.sync import sync_to_async
import asyncio
import httpx
import json

class MessageViewSetAsync(ViewSet):
    '''Async version of MessageViewSet for streaming'''
    
    @action(detail=False, methods=['post'])
    async def stream(self, request):
        '''Async streaming endpoint'''
        
        # Parse request data
        session_id = request.data.get('session_id')
        if not session_id:
            return Response({'error': 'session_id required'}, status=400)
        
        # Database queries wrapped in sync_to_async
        session = await self.get_session(session_id, request.user)
        if not session:
            return Response({'error': 'Session not found'}, status=404)
        
        # Determine streaming mode
        if session.mode == 'direct':
            return StreamingHttpResponse(
                self.stream_direct_mode(request, session),
                content_type='text/event-stream'
            )
        elif session.mode == 'compare':
            return StreamingHttpResponse(
                self.stream_compare_mode(request, session),
                content_type='text/event-stream'
            )
    
    @sync_to_async
    def get_session(self, session_id, user):
        from chat_session.models import ChatSession
        try:
            return ChatSession.objects.get(id=session_id, user=user)
        except ChatSession.DoesNotExist:
            return None
    
    async def stream_direct_mode(self, request, session):
        '''Stream single model response'''
        # Get user message
        messages = request.data.get('messages', [])
        user_message_data = next((m for m in messages if m['role'] == 'user'), None)
        
        if not user_message_data:
            yield f"data: {json.dumps({'error': 'No user message'})}\\n\\n"
            return
        
        # Create user message in DB
        user_message = await self.create_message(
            session=session,
            role='user',
            content=user_message_data['content']
        )
        
        # Create assistant message placeholder
        assistant_message = await self.create_message(
            session=session,
            role='assistant',
            content='',
            parent_id=user_message.id,
            model=session.model_a,
            status='streaming'
        )
        
        # Stream from AI provider
        full_response = ''
        async for chunk in self.stream_from_provider(
            session.model_a,
            user_message_data['content'],
            assistant_message.id
        ):
            full_response += chunk
            yield f"a0:{json.dumps({'content': chunk})}\\n"
        
        # Update message
        await self.update_message(assistant_message.id, {
            'content': full_response,
            'status': 'success'
        })
        
        yield f"ad:{json.dumps({'finishReason': 'stop'})}\\n"
    
    async def stream_compare_mode(self, request, session):
        '''Stream two models concurrently'''
        messages = request.data.get('messages', [])
        user_message_data = next((m for m in messages if m['role'] == 'user'), None)
        
        if not user_message_data:
            yield f"data: {json.dumps({'error': 'No user message'})}\\n\\n"
            return
        
        # Create user message
        user_message = await self.create_message(
            session=session,
            role='user',
            content=user_message_data['content']
        )
        
        # Create assistant messages for both models
        assistant_msg_a = await self.create_message(
            session=session,
            role='assistant',
            content='',
            parent_id=user_message.id,
            model=session.model_a,
            participant='a',
            status='streaming'
        )
        
        assistant_msg_b = await self.create_message(
            session=session,
            role='assistant',
            content='',
            parent_id=user_message.id,
            model=session.model_b,
            participant='b',
            status='streaming'
        )
        
        # Stream both models concurrently using asyncio.Queue
        queue = asyncio.Queue()
        
        # Create tasks for both streams
        task_a = asyncio.create_task(
            self.stream_model(
                session.model_a,
                user_message_data['content'],
                assistant_msg_a.id,
                'a',
                queue
            )
        )
        
        task_b = asyncio.create_task(
            self.stream_model(
                session.model_b,
                user_message_data['content'],
                assistant_msg_b.id,
                'b',
                queue
            )
        )
        
        # Stream chunks as they arrive
        active_streams = {'a', 'b'}
        
        while active_streams:
            participant, chunk = await queue.get()
            
            if chunk is None:
                # Stream finished
                active_streams.discard(participant)
                yield f"{participant}d:{json.dumps({'finishReason': 'stop'})}\\n"
            else:
                yield f"{participant}0:{json.dumps({'content': chunk})}\\n"
        
        # Wait for both tasks to complete
        await asyncio.gather(task_a, task_b)
    
    async def stream_model(self, model, content, message_id, participant, queue):
        '''Stream a single model's response into queue'''
        full_response = ''
        
        try:
            async for chunk in self.stream_from_provider(model, content, message_id):
                full_response += chunk
                await queue.put((participant, chunk))
            
            # Update message
            await self.update_message(message_id, {
                'content': full_response,
                'status': 'success'
            })
        
        except Exception as e:
            await self.update_message(message_id, {
                'status': 'error',
                'metadata': {'error': str(e)}
            })
            await queue.put((participant, {'error': str(e)}))
        
        finally:
            # Signal completion
            await queue.put((participant, None))
    
    async def stream_from_provider(self, model, content, message_id):
        '''Stream from AI provider (OpenAI, Anthropic, etc.)'''
        # Get provider
        provider_code = model.provider.code if model.provider else 'openai'
        
        if provider_code == 'openai':
            async for chunk in self.stream_openai(model, content):
                yield chunk
        
        elif provider_code == 'anthropic':
            async for chunk in self.stream_anthropic(model, content):
                yield chunk
        
        # Add other providers...
    
    async def stream_openai(self, model, content):
        '''Stream from OpenAI'''
        async with httpx.AsyncClient(timeout=60.0) as client:
            url = 'https://api.openai.com/v1/chat/completions'
            headers = {
                'Authorization': f'Bearer {settings.OPENAI_API_KEY}',
                'Content-Type': 'application/json'
            }
            payload = {
                'model': model.model_code,
                'messages': [{'role': 'user', 'content': content}],
                'stream': True
            }
            
            async with client.stream('POST', url, json=payload, headers=headers) as response:
                async for line in response.aiter_lines():
                    if line.startswith('data: '):
                        data = line[6:]
                        if data == '[DONE]':
                            break
                        
                        try:
                            chunk_data = json.loads(data)
                            content_chunk = chunk_data['choices'][0]['delta'].get('content', '')
                            if content_chunk:
                                yield content_chunk
                        except json.JSONDecodeError:
                            continue
    
    async def stream_anthropic(self, model, content):
        '''Stream from Anthropic'''
        async with httpx.AsyncClient(timeout=60.0) as client:
            url = 'https://api.anthropic.com/v1/messages'
            headers = {
                'x-api-key': settings.ANTHROPIC_API_KEY,
                'anthropic-version': '2023-06-01',
                'Content-Type': 'application/json'
            }
            payload = {
                'model': model.model_code,
                'messages': [{'role': 'user', 'content': content}],
                'max_tokens': 2000,
                'stream': True
            }
            
            async with client.stream('POST', url, json=payload, headers=headers) as response:
                async for line in response.aiter_lines():
                    if line.startswith('data: '):
                        data = line[6:]
                        try:
                            event = json.loads(data)
                            if event['type'] == 'content_block_delta':
                                chunk = event['delta'].get('text', '')
                                if chunk:
                                    yield chunk
                        except json.JSONDecodeError:
                            continue
    
    @sync_to_async
    def create_message(self, **kwargs):
        from message.models import Message
        return Message.objects.create(**kwargs)
    
    @sync_to_async
    def update_message(self, message_id, updates):
        from message.models import Message
        Message.objects.filter(id=message_id).update(**updates)
\\\

---

## Phase 2: Update URL Routing

Add async routing in \message/urls.py\:

\\\python
from django.urls import path
from message.views_async import MessageViewSetAsync

# For ASGI containers only
async_router = DefaultRouter()
async_router.register(r'messages', MessageViewSetAsync, basename='message-async')

# Conditional routing based on CONTAINER_TYPE
if settings.CONTAINER_TYPE == 'asgi':
    # Use async views
    router = async_router
else:
    # Use sync views
    router = DefaultRouter()
    router.register(r'messages', MessageViewSet, basename='message')
\\\

---

## Phase 3: Testing

Test the async endpoint:

\\\ash
# Set ASGI mode
export CONTAINER_TYPE=asgi
export USE_ASYNC_VIEWS=True

# Start Uvicorn
uvicorn arena_backend.asgi:application --port 8001 --reload

# Test streaming
curl -X POST http://localhost:8001/api/messages/stream/ \\
  -H "Content-Type: application/json" \\
  -d '{
    "session_id": "...",
    "messages": [{"role": "user", "content": "Hello"}]
  }'
\\\

---

## Benefits of Async Version

1. **No Threading Overhead**: Uses async/await instead of threads
2. **Better Concurrency**: Can handle 100s of concurrent streams
3. **Resource Efficient**: Single event loop instead of thread pool
4. **True Parallelism**: asyncio.gather for concurrent provider calls
5. **Cleaner Code**: No queue.Queue(), no thread.join()

---

## Migration Path

1. ✅ Create async version alongside sync version
2. ✅ Test async version on ASGI server (port 8001)
3. ✅ Route ASGI traffic to async views
4. ✅ Keep sync views for WSGI containers
5. ⏳ Monitor performance and gradually shift traffic
6. ⏳ Eventually deprecate sync streaming (optional)

