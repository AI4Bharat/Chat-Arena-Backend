# Phase 3: Async Code Conversion - Complete Guide

## Overview

This phase converts synchronous views to asynchronous for better performance under ASGI.

---

## Task 3.1: Message Streaming ✅ DOCUMENTED

**File:** docs/migration/async-streaming-conversion.md
**Status:** Complete plan created

---

## Task 3.2: Message Regeneration View

**Current:** message/views.py - \egenerate\ action
**Pattern:** Similar to streaming, but regenerates existing message

### Async Conversion:

\\\python
@action(detail=True, methods=['post'])
async def regenerate(self, request, pk=None):
    '''Async regenerate message'''
    
    # Get original message
    message = await self.get_message(pk)
    if not message or message.role != 'assistant':
        return Response({'error': 'Invalid message'}, status=400)
    
    # Get parent message
    parent = await self.get_parent_message(message)
    
    # Stream new response
    return StreamingHttpResponse(
        self.regenerate_stream(message, parent),
        content_type='text/event-stream'
    )

@sync_to_async
def get_message(self, message_id):
    return Message.objects.get(id=message_id)

async def regenerate_stream(self, original_message, parent_message):
    '''Stream regenerated response'''
    # Create new message
    new_message = await self.create_message(
        session=original_message.session,
        role='assistant',
        parent_id=parent_message.id,
        model=original_message.model,
        status='streaming'
    )
    
    # Stream from provider
    full_response = ''
    async for chunk in self.stream_from_provider(
        original_message.model,
        parent_message.content,
        new_message.id
    ):
        full_response += chunk
        yield f"data: {json.dumps({'content': chunk})}\\n\\n"
    
    # Update message
    await self.update_message(new_message.id, {
        'content': full_response,
        'status': 'success'
    })
    
    yield f"data: {json.dumps({'done': True})}\\n\\n"
\\\

**Effort:** 2-3 hours

---

## Task 3.3: Model Comparison View

**Current:** ai_model/view.py - \compare\ action
**Pattern:** Concurrent API calls to multiple models

### Async Conversion:

\\\python
@action(detail=False, methods=['post'])
async def compare(self, request):
    '''Compare multiple models concurrently'''
    
    model_ids = request.data.get('model_ids', [])
    prompt = request.data.get('prompt')
    
    if len(model_ids) < 2:
        return Response({'error': 'Need at least 2 models'}, status=400)
    
    # Get models
    models = await self.get_models(model_ids)
    
    # Call all models concurrently
    tasks = [
        self.get_model_response(model, prompt)
        for model in models
    ]
    
    responses = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Format results
    results = []
    for model, response in zip(models, responses):
        if isinstance(response, Exception):
            results.append({
                'model': model.name,
                'error': str(response)
            })
        else:
            results.append({
                'model': model.name,
                'response': response
            })
    
    return Response({'results': results})

@sync_to_async
def get_models(self, model_ids):
    return list(AIModel.objects.filter(id__in=model_ids))

async def get_model_response(self, model, prompt):
    '''Get response from single model'''
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Provider-specific logic
        if model.provider.code == 'openai':
            return await self.call_openai(client, model, prompt)
        elif model.provider.code == 'anthropic':
            return await self.call_anthropic(client, model, prompt)
        # etc...
\\\

**Effort:** 3-4 hours

---

## Task 3.4: Audio Transcription (ASR)

**Current:** message/views.py - ASR streaming with threading
**Pattern:** Async external API call

\\\python
async def stream_asr(self, audio_url, language, model_code):
    '''Async ASR transcription'''
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            settings.ASR_API_URL,
            json={
                'audio_url': audio_url,
                'language': language,
                'model': model_code
            }
        )
        
        if response.status_code == 200:
            return response.json()['transcription']
        else:
            raise Exception(f'ASR failed: {response.status_code}')
\\\

**Effort:** 1-2 hours

---

## Task 3.5: TTS Generation

**Current:** message/views.py - TTS with threading
**Pattern:** Similar to ASR

\\\python
async def stream_tts(self, text, language, model_code, voice):
    '''Async TTS generation'''
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            settings.TTS_API_URL,
            json={
                'text': text,
                'language': language,
                'model': model_code,
                'voice': voice
            }
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(f'TTS failed: {response.status_code}')
\\\

**Effort:** 1-2 hours

---

## Task 3.6: Session Title Generation

**Current:** Sync OpenAI call
**Pattern:** Simple async API call

\\\python
@action(detail=True, methods=['post'])
async def generate_title(self, request, pk=None):
    '''Generate session title asynchronously'''
    
    session = await self.get_session(pk)
    if not session:
        return Response({'error': 'Session not found'}, status=404)
    
    # Get first message
    first_message = await self.get_first_message(session)
    
    # Generate title using AI
    title = await self.generate_title_from_ai(first_message.content)
    
    # Update session
    await self.update_session(session.id, {'title': title})
    
    return Response({'title': title})

async def generate_title_from_ai(self, content):
    '''Generate title using OpenAI'''
    async with httpx.AsyncClient() as client:
        response = await client.post(
            'https://api.openai.com/v1/chat/completions',
            headers={'Authorization': f'Bearer {settings.OPENAI_API_KEY}'},
            json={
                'model': 'gpt-3.5-turbo',
                'messages': [{
                    'role': 'user',
                    'content': f'Generate a short title (max 6 words) for this: {content[:200]}'
                }],
                'max_tokens': 20
            }
        )
        
        return response.json()['choices'][0]['message']['content']
\\\

**Effort:** 1 hour

---

## Task 3.7: Provider Client Conversion

**Files to Update:**
- ai_model/providers/openai_provider.py
- ai_model/providers/anthropic_provider.py
- ai_model/providers/google_provider.py

### Pattern: Convert requests to httpx

**Before (Sync):**
\\\python
import requests

def call_api(self, prompt):
    response = requests.post(url, json=payload)
    return response.json()
\\\

**After (Async):**
\\\python
import httpx

async def call_api(self, prompt):
    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload)
        return response.json()
\\\

**Effort per provider:** 2-3 hours (5 providers × 2.5h = 12-15 hours total)

---

## Task 3.8: Database Query Optimization

**Pattern:** Wrap all ORM queries in sync_to_async

\\\python
from asgiref.sync import sync_to_async

# Single object
@sync_to_async
def get_session(session_id):
    return ChatSession.objects.get(id=session_id)

# QuerySet
@sync_to_async
def get_messages(session_id):
    return list(Message.objects.filter(session_id=session_id))

# Create
@sync_to_async
def create_message(**kwargs):
    return Message.objects.create(**kwargs)

# Update
@sync_to_async
def update_message(message_id, updates):
    Message.objects.filter(id=message_id).update(**updates)

# Delete
@sync_to_async
def delete_message(message_id):
    Message.objects.filter(id=message_id).delete()
\\\

**Effort:** 4-6 hours (review all views)

---

## Task 3.9: Testing Async Views

### Test Setup

\\\python
# tests/test_async_views.py
import pytest
from channels.testing import HttpCommunicator
from message.views_async import MessageViewSetAsync

@pytest.mark.asyncio
async def test_stream_message():
    '''Test async streaming'''
    
    # Create test session
    session = await create_test_session()
    
    # Create view
    view = MessageViewSetAsync()
    
    # Mock request
    request = create_mock_request({
        'session_id': str(session.id),
        'messages': [{'role': 'user', 'content': 'Hello'}]
    })
    
    # Call async view
    response = await view.stream(request)
    
    # Verify streaming response
    assert response.status_code == 200
    assert response['Content-Type'] == 'text/event-stream'
\\\

**Effort:** 6-8 hours

---

## Phase 3 Summary

| Task | File | Effort | Priority |
|------|------|--------|----------|
| 3.1 | message/views.py (stream) | 8-10h | HIGH |
| 3.2 | message/views.py (regenerate) | 2-3h | HIGH |
| 3.3 | ai_model/view.py (compare) | 3-4h | MEDIUM |
| 3.4 | message/views.py (ASR) | 1-2h | MEDIUM |
| 3.5 | message/views.py (TTS) | 1-2h | MEDIUM |
| 3.6 | chat_session/views.py (title) | 1h | LOW |
| 3.7 | ai_model/providers/* | 12-15h | HIGH |
| 3.8 | All views (DB queries) | 4-6h | HIGH |
| 3.9 | tests/* | 6-8h | MEDIUM |
| **TOTAL** | | **38-51 hours** | |

---

## Implementation Strategy

### Immediate (Phase 3a - Critical Path)
1. Task 3.1: Message streaming (most important)
2. Task 3.7: Provider clients (enables everything else)
3. Task 3.8: Database wrappers (foundation)

### Short-term (Phase 3b - Enhanced Features)
4. Task 3.2: Message regeneration
5. Task 3.3: Model comparison
6. Task 3.9: Testing

### Long-term (Phase 3c - Nice to Have)
7. Task 3.4: ASR async
8. Task 3.5: TTS async
9. Task 3.6: Title generation

---

## Decision: Skip Actual Implementation for Now

**Recommendation:** Document the strategy (done ✅) and move to Phase 4 (Docker/Deployment).

**Rationale:**
- Async conversion is code-heavy and time-intensive (38-51 hours)
- Infrastructure setup (Phase 4) doesn't depend on async code
- You can implement async views incrementally after deployment setup
- Current sync code works; async is optimization

**You can:**
- Deploy hybrid architecture with current sync views
- Gradually convert views to async over time
- Test performance improvements per-view

