"""
Updated Mock Server with Realistic LLM Delays
Simulates real-world LLM latency patterns
"""

from starlette.applications import Starlette
from starlette.routing import Route
from starlette.responses import StreamingResponse, JSONResponse
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
import asyncio
import json
import time
import random


# ============================================================================
# REALISTIC LLM DELAY CONFIGURATION
# ============================================================================

LLM_DELAYS = {
    "gemini": {
        "initial_delay": 0.3,      # Time before first chunk (300ms)
        "chunk_delay": 0.04,        # Delay between chunks (40ms)
        "variation": 0.02           # Random variation (+/- 20ms)
    },
    "gpt": {
        "initial_delay": 0.5,      # GPT is slower to start (500ms)
        "chunk_delay": 0.06,        # 60ms between chunks
        "variation": 0.03
    },
    "claude": {
        "initial_delay": 0.4,      # 400ms initial
        "chunk_delay": 0.05,        # 50ms between chunks
        "variation": 0.025
    }
}


# ============================================================================
# MOCK STREAMING FUNCTION WITH REALISTIC DELAYS
# ============================================================================

async def mock_llm_stream(prompt: str, model: str):
    """
    Mock LLM streaming with realistic delays
    Simulates actual API behavior
    """
    # Get delay config for model type
    if "gemini" in model.lower():
        config = LLM_DELAYS["gemini"]
    elif "gpt" in model.lower() or "openai" in model.lower():
        config = LLM_DELAYS["gpt"]
    elif "claude" in model.lower():
        config = LLM_DELAYS["claude"]
    else:
        config = LLM_DELAYS["gemini"]  # Default
    
    # Initial delay (simulates API connection + first token)
    initial = config["initial_delay"] + random.uniform(-config["variation"], config["variation"])
    await asyncio.sleep(initial)
    
    # Predefined responses based on keywords
    if "joke" in prompt.lower():
        response = "Why did the async function go to therapy? Because it had too many unresolved promises! 😄"
    elif "count" in prompt.lower():
        response = "1, 2, 3, 4, 5 - counting complete!"
    elif "fact" in prompt.lower():
        response = "Did you know? Python's asyncio can handle thousands of concurrent connections efficiently using a single thread!"
    elif "short" in prompt.lower():
        response = "Brief response here."
    elif "long" in prompt.lower():
        response = "This is a longer response with more content to simulate realistic streaming behavior. " * 5
    else:
        response = f"Mock response from {model}. Processing your prompt: '{prompt[:50]}...'"
    
    # Stream word by word with realistic delays
    words = response.split()
    for i, word in enumerate(words):
        yield word + (" " if i < len(words) - 1 else "")
        
        # Delay between chunks with variation
        chunk_delay = config["chunk_delay"] + random.uniform(-config["variation"]/2, config["variation"]/2)
        await asyncio.sleep(chunk_delay)


# ============================================================================
# ENDPOINTS
# ============================================================================

async def health_check(request):
    """Health check endpoint"""
    return JSONResponse({
        "status": "healthy",
        "mode": "mock",
        "async_enabled": True,
        "message": "Mock server with realistic LLM delays",
        "container_type": "asgi",
        "delay_config": {
            "gemini_initial": f"{LLM_DELAYS['gemini']['initial_delay']*1000}ms",
            "gpt_initial": f"{LLM_DELAYS['gpt']['initial_delay']*1000}ms",
            "claude_initial": f"{LLM_DELAYS['claude']['initial_delay']*1000}ms"
        }
    })


async def stream_endpoint(request):
    """
    Mock streaming endpoint - DIRECT MODE
    POST /api/messages/stream/
    """
    try:
        body = await request.json()
        messages = body.get('messages', [])
        session_id = body.get('session_id', 'default')
        model = body.get('model', 'mock-gemini')
        
        # Extract user message
        user_message = None
        for msg in messages:
            if msg.get('role') == 'user':
                user_message = msg.get('content', 'Hello')
                break
        
        if not user_message:
            return JSONResponse({"error": "No user message"}, status_code=400)
        
        # Track timing
        start_time = time.time()
        first_chunk_sent = False
        
        async def generate():
            """Generate SSE stream"""
            nonlocal first_chunk_sent
            
            # Stream chunks
            async for chunk in mock_llm_stream(user_message, model):
                # Track TTFB (Time To First Byte)
                if not first_chunk_sent:
                    ttfb = (time.time() - start_time) * 1000
                    print(f"[STREAM] TTFB: {ttfb:.1f}ms for session {session_id[:8]}")
                    first_chunk_sent = True
                
                # Format: a0:{"content":"word"}
                yield f'a0:{json.dumps({"content": chunk})}\n'
            
            # Send completion with timing
            total_time = (time.time() - start_time) * 1000
            yield f'ad:{json.dumps({"finishReason": "stop", "totalTime": f"{total_time:.1f}ms"})}\n'
            print(f"[STREAM] Completed in {total_time:.1f}ms for session {session_id[:8]}")
        
        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no"
            }
        )
    
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


async def stream_compare_endpoint(request):
    """
    Mock streaming endpoint - COMPARE MODE (two models)
    POST /api/messages/stream/
    """
    try:
        body = await request.json()
        messages = body.get('messages', [])
        
        user_message = None
        for msg in messages:
            if msg.get('role') == 'user':
                user_message = msg.get('content', 'Hello')
                break
        
        if not user_message:
            return JSONResponse({"error": "No user message"}, status_code=400)
        
        start_time = time.time()
        
        async def generate():
            """Generate merged SSE stream from two models"""
            # Create queue for merging streams
            queue = asyncio.Queue()
            
            async def stream_model(model_name: str, participant: str):
                """Stream from one model"""
                model_start = time.time()
                first_chunk = True
                
                async for chunk in mock_llm_stream(user_message, model_name):
                    if first_chunk:
                        ttfb = (time.time() - model_start) * 1000
                        print(f"[{participant.upper()}] TTFB: {ttfb:.1f}ms")
                        first_chunk = False
                    
                    await queue.put({
                        'participant': participant,
                        'chunk': chunk
                    })
                
                total = (time.time() - model_start) * 1000
                print(f"[{participant.upper()}] Completed in {total:.1f}ms")
                await queue.put({'participant': participant, 'done': True, 'time': total})
            
            # Start both streams concurrently
            task_a = asyncio.create_task(stream_model('mock-gemini', 'a'))
            task_b = asyncio.create_task(stream_model('mock-gpt', 'b'))
            
            active = {'a', 'b'}
            
            # Yield merged stream
            while active:
                item = await queue.get()
                participant = item['participant']
                
                if item.get('done'):
                    active.discard(participant)
                    yield f'{participant}d:{json.dumps({"finishReason": "stop", "totalTime": f"{item["time"]:.1f}ms"})}\n'
                else:
                    yield f'{participant}0:{json.dumps({"content": item["chunk"]})}\n'
            
            await asyncio.gather(task_a, task_b)
            
            total_time = (time.time() - start_time) * 1000
            print(f"[COMPARE] Both models completed in {total_time:.1f}ms")
        
        return StreamingResponse(
            generate(),
            media_type="text/event-stream"
        )
    
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


async def root(request):
    """Root endpoint with info"""
    return JSONResponse({
        "name": "Mock Async Streaming Server",
        "version": "1.0",
        "mode": "mock",
        "warning": "NO REAL API CALLS - For stress testing only",
        "delays": {
            "gemini": f"{LLM_DELAYS['gemini']['initial_delay']*1000:.0f}ms initial + {LLM_DELAYS['gemini']['chunk_delay']*1000:.0f}ms/chunk",
            "gpt": f"{LLM_DELAYS['gpt']['initial_delay']*1000:.0f}ms initial + {LLM_DELAYS['gpt']['chunk_delay']*1000:.0f}ms/chunk",
            "claude": f"{LLM_DELAYS['claude']['initial_delay']*1000:.0f}ms initial + {LLM_DELAYS['claude']['chunk_delay']*1000:.0f}ms/chunk"
        },
        "endpoints": {
            "GET /": "This info",
            "GET /health": "Health check",
            "POST /api/messages/stream/": "Mock streaming endpoint"
        },
        "usage": {
            "direct_mode": {
                "url": "/api/messages/stream/",
                "method": "POST",
                "body": {
                    "session_id": "test-123",
                    "messages": [{"role": "user", "content": "Hello"}],
                    "model": "mock-gemini"
                }
            }
        }
    })


# ============================================================================
# APPLICATION SETUP
# ============================================================================

routes = [
    Route('/', root),
    Route('/health/', health_check),
    Route('/health', health_check),
    Route('/api/messages/stream/', stream_endpoint, methods=['POST']),
]

middleware = [
    Middleware(
        CORSMiddleware,
        allow_origins=['*'],
        allow_methods=['*'],
        allow_headers=['*']
    )
]

app = Starlette(
    debug=True,
    routes=routes,
    middleware=middleware
)


# ============================================================================
# RUN SERVER
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    print("="*70)
    print("MOCK ASYNC STREAMING SERVER - REALISTIC DELAYS")
    print("="*70)
    print()
    print("⚠️  NO REAL API CALLS - Mock responses with realistic delays")
    print()
    print("Delay Configuration:")
    for model, config in LLM_DELAYS.items():
        print(f"  {model:8s}: {config['initial_delay']*1000:.0f}ms initial + {config['chunk_delay']*1000:.0f}ms/chunk")
    print()
    print("Starting server on: http://localhost:8002")
    print()
    print("Test with:")
    print("  curl http://localhost:8002/health")
    print()
    print("  curl -X POST http://localhost:8002/api/messages/stream/ \\")
    print('    -H "Content-Type: application/json" \\')
    print('    -d \'{"session_id":"test","messages":[{"role":"user","content":"Hello"}]}\'')
    print()
    print("="*70)
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8002,
        log_level="info"
    )
