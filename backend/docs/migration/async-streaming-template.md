# Async Message Streaming View - Template
# Location: chat_session/views.py (or wherever your streaming view is)

from django.http import StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from asgiref.sync import sync_to_async
import json
import asyncio
import httpx  # Async HTTP client

class MessageStreamView(APIView):
    '''
    Async streaming view for AI message generation
    '''
    permission_classes = [IsAuthenticated]
    
    async def post(self, request, *args, **kwargs):
        '''
        Stream AI responses asynchronously
        '''
        # Get request data
        session_id = request.data.get('session_id')
        message_text = request.data.get('message')
        model_name = request.data.get('model')
        
        # Database queries need sync_to_async wrapper
        session = await self.get_session(session_id)
        if not session:
            return JsonResponse({'error': 'Session not found'}, status=404)
        
        # Create async streaming response
        return StreamingHttpResponse(
            self.stream_response(session, message_text, model_name),
            content_type='text/event-stream'
        )
    
    @sync_to_async
    def get_session(self, session_id):
        '''Wrap sync database query'''
        from chat_session.models import ChatSession
        try:
            return ChatSession.objects.get(id=session_id)
        except ChatSession.DoesNotExist:
            return None
    
    @sync_to_async
    def create_message(self, session, text, role='user'):
        '''Create message record'''
        from chat_session.models import Message
        return Message.objects.create(
            session=session,
            text=text,
            role=role
        )
    
    async def stream_response(self, session, message_text, model_name):
        '''
        Async generator that streams AI responses
        '''
        # Save user message
        user_message = await self.create_message(session, message_text, role='user')
        
        # Get AI provider client (example: OpenAI)
        async with httpx.AsyncClient(timeout=60.0) as client:
            # Prepare API request
            api_url = 'https://api.openai.com/v1/chat/completions'
            headers = {
                'Authorization': f'Bearer {settings.OPENAI_API_KEY}',
                'Content-Type': 'application/json'
            }
            payload = {
                'model': model_name,
                'messages': [{'role': 'user', 'content': message_text}],
                'stream': True
            }
            
            # Stream the response
            full_response = ''
            async with client.stream('POST', api_url, json=payload, headers=headers) as response:
                async for line in response.aiter_lines():
                    if line.startswith('data: '):
                        data = line[6:]  # Remove 'data: ' prefix
                        
                        if data == '[DONE]':
                            break
                        
                        try:
                            chunk = json.loads(data)
                            content = chunk['choices'][0]['delta'].get('content', '')
                            
                            if content:
                                full_response += content
                                # Yield chunk to client
                                yield f'data: {json.dumps({\"content\": content})}\\n\\n'
                        
                        except json.JSONDecodeError:
                            continue
            
            # Save AI response
            await self.create_message(session, full_response, role='assistant')
            
            # Send final event
            yield f'data: {json.dumps({\"done\": True})}\\n\\n'


# Alternative: Function-based view
@csrf_exempt
async def stream_message_view(request):
    '''
    Function-based async streaming view
    '''
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    # Parse JSON body
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    
    session_id = data.get('session_id')
    message = data.get('message')
    
    # Helper function for database query
    @sync_to_async
    def get_session(sid):
        from chat_session.models import ChatSession
        return ChatSession.objects.get(id=sid)
    
    # Async generator
    async def generate():
        session = await get_session(session_id)
        
        # Your streaming logic here
        for i in range(10):
            await asyncio.sleep(0.1)
            yield f'data: {json.dumps({\"chunk\": i})}\\n\\n'
        
        yield 'data: [DONE]\\n\\n'
    
    return StreamingHttpResponse(
        generate(),
        content_type='text/event-stream'
    )


# ============================================================================
# Key Patterns for Async Conversion
# ============================================================================

# 1. Database queries must be wrapped
@sync_to_async
def db_query():
    return Model.objects.filter(...)

# 2. Use httpx instead of requests
async with httpx.AsyncClient() as client:
    response = await client.post(url, json=data)

# 3. Use async/await for I/O operations
result = await some_async_function()

# 4. Use async generators for streaming
async def stream_generator():
    async for item in async_source:
        yield item

# 5. Don't mix sync and async incorrectly
# BAD:  def sync_view(): await async_func()  # Error!
# GOOD: async def async_view(): await async_func()  # Correct

