from typing import Dict, List, Optional, AsyncGenerator
import asyncio
from django.conf import settings
from django.core.cache import cache
import logging

from ai_model.models import AIModel
from ai_model.providers.anthropic_provider import AnthropicProvider
from ai_model.providers.google_provider import GoogleAIProvider
from ai_model.providers.openai_provider import OpenAIProvider


logger = logging.getLogger(__name__)


class AIModelService:
    """Service for managing AI model interactions"""
    
    PROVIDER_CLASSES = {
        'openai': OpenAIProvider,
        'google': GoogleAIProvider,
        'anthropic': AnthropicProvider,
        # 'meta': MetaProvider,
        # 'mistral': MistralProvider,
    }
    
    def __init__(self):
        self._providers = {}
        self._initialize_providers()
    
    def _initialize_providers(self):
        """Initialize provider instances with API keys"""
        for provider_name, provider_class in self.PROVIDER_CLASSES.items():
            try:
                api_key = getattr(settings, f'{provider_name.upper()}_API_KEY', None)
                if api_key:
                    self._providers[provider_name] = provider_class(api_key)
            except Exception as e:
                logger.error(f"Failed to initialize provider {provider_name}: {e}")
    
    def get_provider(self, provider_name: str):
        """Get provider instance"""
        if provider_name not in self._providers:
            raise ValueError(f"Provider {provider_name} not initialized")
        return self._providers[provider_name]
    
    async def stream_completion(
        self,
        model: AIModel,
        messages: List[Dict[str, str]],
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """Stream completion from AI model"""
        provider = self.get_provider(model.provider)
        
        try:
            async with provider:
                async for chunk in provider.stream_completion(
                    messages=messages,
                    model=model.model_code,
                    **kwargs
                ):
                    yield chunk
        except Exception as e:
            logger.error(f"Error streaming from {model.model_code}: {e}")
            yield f"Error: {str(e)}"
    
    async def get_completion(
        self,
        model: AIModel,
        messages: List[Dict[str, str]],
        **kwargs
    ) -> str:
        """Get non-streaming completion from AI model"""
        provider = self.get_provider(model.provider)
        
        try:
            async with provider:
                return await provider.get_completion(
                    messages=messages,
                    model=model.model_code,
                    **kwargs
                )
        except Exception as e:
            logger.error(f"Error getting completion from {model.model_code}: {e}")
            return f"Error: {str(e)}"
    
    def validate_model_configuration(self, model: AIModel) -> Dict[str, any]:
        """Validate model configuration"""
        provider = self.get_provider(model.provider)
        
        is_valid = provider.validate_model(model.model_code)
        model_info = provider.get_model_info(model.model_code)
        
        return {
            'is_valid': is_valid,
            'model_info': model_info,
            'provider_available': model.provider in self._providers
        }
    
    @staticmethod
    def get_available_models_by_category(category: str) -> List[AIModel]:
        """Get available models for a specific category"""
        cache_key = f"models_by_category_{category}"
        cached_models = cache.get(cache_key)
        
        if cached_models:
            return cached_models
        
        models = AIModel.objects.filter(
            is_active=True,
            capabilities__contains=[category]
        ).select_related()
        
        cache.set(cache_key, list(models), timeout=3600)  # Cache for 1 hour
        return models
    
    @staticmethod
    async def compare_models(
        model_a: AIModel,
        model_b: AIModel,
        messages: List[Dict[str, str]],
        **kwargs
    ) -> Dict[str, AsyncGenerator[str, None]]:
        """Stream completions from two models simultaneously"""
        service = AIModelService()
        
        async def stream_with_label(model, label):
            async for chunk in service.stream_completion(model, messages, **kwargs):
                yield {'label': label, 'chunk': chunk, 'model_id': str(model.id)}
        
        # Create two streams
        stream_a = stream_with_label(model_a, 'a')
        stream_b = stream_with_label(model_b, 'b')
        
        # Merge streams
        async def merged_stream():
            queue = asyncio.Queue()
            
            async def queue_stream(stream, label):
                try:
                    async for item in stream:
                        await queue.put(item)
                except Exception as e:
                    await queue.put({'label': label, 'error': str(e)})
                finally:
                    await queue.put(None)
            
            # Start both streams
            task_a = asyncio.create_task(queue_stream(stream_a, 'a'))
            task_b = asyncio.create_task(queue_stream(stream_b, 'b'))
            
            # Yield items from queue
            completed = 0
            while completed < 2:
                item = await queue.get()
                if item is None:
                    completed += 1
                else:
                    yield item
            
            # Wait for tasks to complete
            await task_a
            await task_b
        
        return merged_stream()