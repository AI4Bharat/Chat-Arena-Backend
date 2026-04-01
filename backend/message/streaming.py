import json
import asyncio
from typing import AsyncGenerator, Dict, Optional
from django.http import StreamingHttpResponse


class StreamingManager:
    """Manage streaming responses"""
    
    @staticmethod
    def create_streaming_response(generator) -> StreamingHttpResponse:
        """Create a streaming HTTP response from an async generator"""
        def event_stream():
            try:
                for data in generator:
                    # Format as Server-Sent Events
                    yield f"data: {json.dumps(data)}\n\n"
                
                # Send completion event
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                
            except Exception as e:
                # Send error event
                yield f"data: {json.dumps({'type': 'error', 'error': 'An error occurred while streaming the response.'})}\n\n"
        
        # # Convert async generator to sync for Django
        # def sync_wrapper():
        #     loop = asyncio.new_event_loop()
        #     asyncio.set_event_loop(loop)
            
        #     try:
        #         async_gen = event_stream()
        #         while True:
        #             try:
        #                 yield loop.run_until_complete(async_gen.__anext__())
        #             except StopAsyncIteration:
        #                 break
        #     finally:
        #         loop.close()
        
        response = StreamingHttpResponse(
            event_stream(),
            content_type='text/event-stream'
        )
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'  # Disable Nginx buffering
        
        return response
    
    @staticmethod
    async def stream_with_retry(
        generator: AsyncGenerator,
        max_retries: int = 3,
        retry_delay: float = 1.0
    ) -> AsyncGenerator[Dict, None]:
        """Stream with automatic retry on failure"""
        retries = 0
        
        while retries < max_retries:
            try:
                async for item in generator:
                    yield item
                break
                
            except Exception as e:
                retries += 1
                if retries >= max_retries:
                    yield {
                        'type': 'error',
                        'error': 'An error occurred while streaming the response.'
                    }
                    break

                yield {
                    'type': 'retry',
                    'attempt': retries,
                    'error': 'Retrying due to an error.'
                }
                
                await asyncio.sleep(retry_delay * retries)