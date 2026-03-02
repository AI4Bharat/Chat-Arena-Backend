"""
Mock Server with REAL LLM Delay Simulation
Updated with Claude Sonnet 4 support
Based on actual production LLM latency patterns
NO REAL API CALLS
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
# REALISTIC LLM DELAY CONFIGURATION (Based on Production Data)
# ============================================================================

REALISTIC_LLM_DELAYS = {
    "gemini-1.5-flash": {
        "initial_delay": 0.8,  # 800ms to first token
        "chunk_delay": 0.12,    # 120ms between chunks
        "variation": 0.05,      # ±50ms variation
        "response_length": (50, 150)
    },
    "gemini-1.5-pro": {
        "initial_delay": 1.2,
        "chunk_delay": 0.15,
        "variation": 0.08,
        "response_length": (100, 300)
    },
    "gpt-4o-mini": {
        "initial_delay": 1.0,
        "chunk_delay": 0.10,
        "variation": 0.06,
        "response_length": (80, 200)
    },
    "gpt-4o": {
        "initial_delay": 1.5,
        "chunk_delay": 0.18,
        "variation": 0.10,
        "response_length": (120, 400)
    },
    "claude-3-haiku": {
        "initial_delay": 0.9,
        "chunk_delay": 0.11,
        "variation": 0.05,
        "response_length": (60, 180)
    },
    "claude-3-sonnet": {
        "initial_delay": 1.3,
        "chunk_delay": 0.16,
        "variation": 0.08,
        "response_length": (100, 350)
    },
    "claude-sonnet-4": {
        "initial_delay": 1.1,    # 1100ms to first token (optimized)
        "chunk_delay": 0.14,      # 140ms between chunks
        "variation": 0.07,        # ±70ms variation
        "response_length": (100, 300)
    },
    "claude-4-opus": {
        "initial_delay": 1.6,    # 1600ms (slower, more capable)
        "chunk_delay": 0.20,
        "variation": 0.10,
        "response_length": (150, 500)
    }
}

# ============================================================================
# GENERATE REALISTIC RESPONSE TEXT
# ============================================================================

def generate_realistic_response(prompt: str, word_count: int) -> str:
    """Generate a realistic response of specified length"""
    
    # Response templates based on common patterns
    if "joke" in prompt.lower():
        base = "Here's a programming joke for you: Why do programmers prefer dark mode? Because light attracts bugs! "
    elif "explain" in prompt.lower() or "what" in prompt.lower() or "concept" in prompt.lower():
        base = "Let me explain that in detail. This is a complex topic that requires understanding several key concepts. "
    elif "code" in prompt.lower() or "python" in prompt.lower():
        base = "Here's a Python code example that demonstrates this concept. First, we'll import the necessary modules. "
    elif "list" in prompt.lower() or "steps" in prompt.lower():
        base = "Here are the key points to consider: First, we need to understand the fundamentals. "
    else:
        base = "Based on your question, here's a comprehensive response that covers the main aspects of the topic. "
    
    # Expand to reach word count
    filler_phrases = [
        "Additionally, it's important to note that ",
        "Furthermore, we should consider ",
        "Moreover, this approach helps ",
        "In practice, this means ",
        "To elaborate further, ",
        "It's worth mentioning that ",
        "Another key point is ",
        "This is particularly important because ",
        "Let me also add that ",
        "Building on this idea, "
    ]
    
    response = base
    current_words = len(response.split())
    
    while current_words < word_count:
        response += random.choice(filler_phrases)
        response += "the system handles these requirements efficiently and maintains optimal performance. "
        current_words = len(response.split())
    
    # Trim to exact word count
    words = response.split()[:word_count]
    return " ".join(words)

# ============================================================================
# MOCK STREAMING WITH REALISTIC LLM DELAYS
# ============================================================================

async def mock_llm_stream_realistic(prompt: str, model: str):
    """
    Mock LLM streaming with production-realistic delays
    Simulates actual API behavior patterns
    """
    
    # Get model config or default to gemini-flash
    config = REALISTIC_LLM_DELAYS.get(model, REALISTIC_LLM_DELAYS["gemini-1.5-flash"])
    
    # Initial delay (API connection + model processing + first token)
    initial = config["initial_delay"] + random.uniform(-config["variation"], config["variation"])
    await asyncio.sleep(initial)
    
    # Generate realistic response
    min_words, max_words = config["response_length"]
    word_count = random.randint(min_words, max_words)
    response = generate_realistic_response(prompt, word_count)
    
    # Stream word by word with realistic delays
    words = response.split()
    for i, word in enumerate(words):
        yield word + (" " if i < len(words) - 1 else "")
        
        # Delay between chunks with variation
        chunk_delay = config["chunk_delay"] + random.uniform(-config["variation"]/2, config["variation"]/2)
        
        # Occasional "thinking" pauses (simulates model reasoning)
        if i > 0 and i % 20 == 0:
            chunk_delay *= 1.5  # 50% longer pause every 20 words
        
        await asyncio.sleep(chunk_delay)
    
    # Send [DONE] marker
    yield "[DONE]"

# ============================================================================
# ENDPOINTS
# ============================================================================

async def health_check(request):
    """Health check endpoint"""
    return JSONResponse({
        "status": "healthy",
        "mode": "realistic_mock",
        "async_enabled": True,
        "message": "Mock server with REALISTIC LLM delays - Claude Sonnet 4 support",
        "container_type": "asgi",
        "delay_config": {
            model: {
                "initial": f"{config['initial_delay']*1000:.0f}ms",
                "chunk": f"{config['chunk_delay']*1000:.0f}ms",
                "response_words": f"{config['response_length'][0]}-{config['response_length'][1]}"
            }
            for model, config in REALISTIC_LLM_DELAYS.items()
        }
    })

async def stream_endpoint(request):
    """Mock streaming endpoint with realistic delays"""
    try:
        body = await request.json()
        messages = body.get('messages', [])
        session_id = body.get('session_id', 'default')
        model = body.get('model', 'gemini-1.5-flash')
        
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
        chunk_count = 0
        
        async def generate():
            """Generate SSE stream"""
            nonlocal first_chunk_sent, chunk_count
            
            # Stream chunks
            async for chunk in mock_llm_stream_realistic(user_message, model):
                chunk_count += 1
                
                # Track TTFB (Time To First Byte)
                if not first_chunk_sent:
                    ttfb = (time.time() - start_time) * 1000
                    print(f"[{model:20s}] TTFB: {ttfb:6.1f}ms | Session: {session_id[:8]}")
                    first_chunk_sent = True
                
                # Check for [DONE] marker
                if chunk == "[DONE]":
                    # Send [DONE] in SSE format
                    yield f'data: [DONE]\n\n'
                else:
                    # Format: data: {"content":"word"}
                    yield f'data: {json.dumps({"content": chunk})}\n\n'
            
            # Send completion with timing
            total_time = (time.time() - start_time) * 1000
            print(f"[{model:20s}] Done: {total_time:6.1f}ms | {chunk_count} chunks | Session: {session_id[:8]}")
        
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
    """Compare mode with two different models"""
    try:
        body = await request.json()
        messages = body.get('messages', [])
        model_a = body.get('model_a', 'gemini-1.5-flash')
        model_b = body.get('model_b', 'gpt-4o-mini')
        
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
            queue = asyncio.Queue()
            
            async def stream_model(model_name: str, participant: str):
                """Stream from one model"""
                model_start = time.time()
                first_chunk = True
                chunk_count = 0
                
                async for chunk in mock_llm_stream_realistic(user_message, model_name):
                    if chunk == "[DONE]":
                        continue
                    
                    chunk_count += 1
                    if first_chunk:
                        ttfb = (time.time() - model_start) * 1000
                        print(f"[{participant.upper()}:{model_name:15s}] TTFB: {ttfb:6.1f}ms")
                        first_chunk = False
                    
                    await queue.put({
                        'participant': participant,
                        'chunk': chunk
                    })
                
                total = (time.time() - model_start) * 1000
                print(f"[{participant.upper()}:{model_name:15s}] Done: {total:6.1f}ms | {chunk_count} chunks")
                await queue.put({'participant': participant, 'done': True, 'time': total, 'chunks': chunk_count})
            
            # Start both streams concurrently
            task_a = asyncio.create_task(stream_model(model_a, 'a'))
            task_b = asyncio.create_task(stream_model(model_b, 'b'))
            
            active = {'a', 'b'}
            
            # Yield merged stream
            while active:
                item = await queue.get()
                participant = item['participant']
                
                if item.get('done'):
                    active.discard(participant)
                    yield f'{participant}d:{json.dumps({"finishReason": "stop", "totalTime": f"{item["time"]:.1f}ms", "chunks": item["chunks"]})}\n'
                else:
                    yield f'{participant}0:{json.dumps({"content": item["chunk"]})}\n'
            
            await asyncio.gather(task_a, task_b)
            total_time = (time.time() - start_time) * 1000
            print(f"[COMPARE] Both completed in {total_time:.1f}ms")
        
        return StreamingResponse(
            generate(),
            media_type="text/event-stream"
        )
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)

async def root(request):
    """Root endpoint with info"""
    return JSONResponse({
        "name": "Realistic Mock LLM Server",
        "version": "3.0",
        "mode": "realistic_mock",
        "warning": "NO REAL API CALLS - Realistic LLM delay simulation",
        "supported_models": list(REALISTIC_LLM_DELAYS.keys()),
        "delays": {
            model: f"{config['initial_delay']*1000:.0f}ms initial + {config['chunk_delay']*1000:.0f}ms/chunk ({config['response_length'][0]}-{config['response_length'][1]} words)"
            for model, config in REALISTIC_LLM_DELAYS.items()
        },
        "endpoints": {
            "GET /": "This info",
            "GET /health": "Health check",
            "POST /api/messages/stream/": "Single model streaming",
            "POST /api/messages/stream/compare/": "Compare two models"
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
    Route('/api/messages/stream/compare/', stream_compare_endpoint, methods=['POST']),
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
    print("REALISTIC MOCK LLM SERVER - WITH CLAUDE SONNET 4")
    print("="*70)
    print()
    print("⚠️  NO REAL API CALLS - Realistic production delays")
    print()
    print("Supported Models:")
    for model, config in REALISTIC_LLM_DELAYS.items():
        print(f"  • {model:20s}: {config['initial_delay']*1000:4.0f}ms initial + {config['chunk_delay']*1000:3.0f}ms/chunk")
    print()
    print("✅ SSE Format: data: {JSON} with [DONE] marker")
    print()
    print("Starting server on: http://localhost:8002")
    print()
    print("="*70)
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8002,
        log_level="info"
    )
