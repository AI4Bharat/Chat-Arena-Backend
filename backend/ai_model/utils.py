from typing import Dict, List, Optional
from django.core.cache import cache
from django.db.models import F
import math
import logging
from ai_model.models import AIModel
import random
from model_metrics.models import ModelMetric
import markdown
import re

logger = logging.getLogger(__name__)


class EloRatingCalculator:
    """Calculate ELO ratings for model comparisons"""
    
    K_FACTOR = 32  # Standard K-factor for ELO
    
    @staticmethod
    def calculate_expected_score(rating_a: float, rating_b: float) -> float:
        """Calculate expected score for player A"""
        return 1 / (1 + math.pow(10, (rating_b - rating_a) / 400))
    
    @staticmethod
    def calculate_new_ratings(
        rating_a: float,
        rating_b: float,
        score_a: float,
        score_b: float = None
    ) -> tuple:
        """
        Calculate new ELO ratings
        score_a: 1 for win, 0.5 for tie, 0 for loss
        """
        if score_b is None:
            score_b = 1 - score_a
        
        expected_a = EloRatingCalculator.calculate_expected_score(rating_a, rating_b)
        expected_b = EloRatingCalculator.calculate_expected_score(rating_b, rating_a)
        
        new_rating_a = rating_a + EloRatingCalculator.K_FACTOR * (score_a - expected_a)
        new_rating_b = rating_b + EloRatingCalculator.K_FACTOR * (score_b - expected_b)
        
        return round(new_rating_a), round(new_rating_b)
    
    @staticmethod
    def update_model_ratings(model_a_id: str, model_b_id: str, result: str, category: str = 'overall'):
        """
        Update model ELO ratings based on comparison result
        result: 'a_wins', 'b_wins', or 'tie'
        """
        
        # Get current ratings
        metric_a = ModelMetric.objects.filter(
            model_id=model_a_id,
            category=category,
            period='all_time'
        ).order_by('-calculated_at').first()
        
        metric_b = ModelMetric.objects.filter(
            model_id=model_b_id,
            category=category,
            period='all_time'
        ).order_by('-calculated_at').first()
        
        rating_a = metric_a.elo_rating if metric_a else 1500
        rating_b = metric_b.elo_rating if metric_b else 1500
        
        # Calculate scores
        if result == 'a_wins':
            score_a, score_b = 1.0, 0.0
        elif result == 'b_wins':
            score_a, score_b = 0.0, 1.0
        else:  # tie
            score_a, score_b = 0.5, 0.5
        
        # Calculate new ratings
        new_rating_a, new_rating_b = EloRatingCalculator.calculate_new_ratings(
            rating_a, rating_b, score_a, score_b
        )
        
        # Update metrics
        for model_id, new_rating, metric, won, lost, tied in [
            (model_a_id, new_rating_a, metric_a, result == 'a_wins', result == 'b_wins', result == 'tie'),
            (model_b_id, new_rating_b, metric_b, result == 'b_wins', result == 'a_wins', result == 'tie')
        ]:
            if metric:
                ModelMetric.objects.filter(id=metric.id).update(
                    elo_rating=new_rating,
                    total_comparisons=F('total_comparisons') + 1,
                    wins=F('wins') + (1 if won else 0),
                    losses=F('losses') + (1 if lost else 0),
                    ties=F('ties') + (1 if tied else 0)
                )
            else:
                # Create new metric
                ModelMetric.objects.create(
                    model_id=model_id,
                    category=category,
                    period='all_time',
                    elo_rating=new_rating,
                    total_comparisons=1,
                    wins=1 if won else 0,
                    losses=1 if lost else 0,
                    ties=1 if tied else 0
                )
        
        return new_rating_a, new_rating_b


class ModelCostCalculator:
    """Calculate costs for model usage"""
    
    # Costs per 1K tokens (example rates)
    COST_PER_1K_TOKENS = {
        'gpt-4-turbo': {'input': 0.01, 'output': 0.03},
        'gpt-4': {'input': 0.03, 'output': 0.06},
        'gpt-3.5-turbo': {'input': 0.001, 'output': 0.002},
        'claude-3-opus': {'input': 0.015, 'output': 0.075},
        'claude-3-sonnet': {'input': 0.003, 'output': 0.015},
        'gemini-pro': {'input': 0.00025, 'output': 0.0005},
        # Add more models
    }
    
    @staticmethod
    def estimate_cost(model_code: str, input_tokens: int, output_tokens: int) -> Dict[str, float]:
        """Estimate cost for model usage"""
        if model_code not in ModelCostCalculator.COST_PER_1K_TOKENS:
            return {'input_cost': 0, 'output_cost': 0, 'total_cost': 0}
        
        rates = ModelCostCalculator.COST_PER_1K_TOKENS[model_code]
        input_cost = (input_tokens / 1000) * rates['input']
        output_cost = (output_tokens / 1000) * rates['output']
        
        return {
            'input_cost': round(input_cost, 6),
            'output_cost': round(output_cost, 6),
            'total_cost': round(input_cost + output_cost, 6)
        }



# Models that support multimodal inputs (images, documents, audio)
MULTIMODAL_MODELS_NAMES = [
  'GPT 5', 'GPT 5.2', 'GPT 5 Pro', 'GPT 4o'
]

class ModelSelector:
    """Select models based on various criteria"""
    
    # Academic-only models that should only be used in academic mode
    ACADEMIC_ONLY_MODELS = ['elevenlabs', 'indicparlertts']
    
    @staticmethod
    def get_random_models_for_comparison(
        exclude_ids: List[str] = None,
        category: Optional[str] = None,
        model_type: Optional[str] = None,
        requires_multimodal: bool = False,
        mode: Optional[str] = None,
        language: Optional[str] = None,
    ) -> tuple:
        """Get two random models for comparison"""
        from ai_model.tts_interactions import has_presynthesized_sentences
        
        queryset = AIModel.objects.filter(is_active=True)
        
        # Exclude academic-only models unless:
        # 1. Mode is academic AND
        # 2. Language has pre-synthesized sentences available
        if mode != 'academic' or not has_presynthesized_sentences(language):
            queryset = queryset.exclude(model_code__in=ModelSelector.ACADEMIC_ONLY_MODELS)
        
        if category:
            queryset = queryset.filter(capabilities__contains=[category])
        
        if exclude_ids:
            queryset = queryset.exclude(id__in=exclude_ids)

        if model_type:
            queryset = queryset.filter(model_type=model_type)

        if requires_multimodal:
            queryset = queryset.filter(display_name__in=MULTIMODAL_MODELS_NAMES)
        
        models = list(queryset)
        
        if len(models) < 2:
            if requires_multimodal:
                 # If explicit multimodal required but not enough found, log a warning and fall back (soft fail) or raise error?
                 # Raising error is safer to prevent sending image to a blind model
                 raise ValueError("Not enough multimodal models available for comparison")
            raise ValueError("Not enough models available for comparison")
        
        return random.sample(models, 2)
    
    @staticmethod
    def get_recommended_model(
        user_preferences: Dict,
        task_type: str = 'general'
    ) -> Optional['AIModel']:
        """Get recommended model based on user preferences and task"""
        
        # Start with active models
        queryset = AIModel.objects.filter(is_active=True)
        
        # Filter by task type if specified
        if task_type != 'general':
            queryset = queryset.filter(capabilities__contains=[task_type])
        
        # Get models with their latest metrics
        models_with_scores = []
        
        for model in queryset:
            metric = ModelMetric.objects.filter(
                model=model,
                category=task_type if task_type != 'general' else 'overall',
                period='all_time'
            ).order_by('-calculated_at').first()
            
            if metric:
                # Calculate score based on ELO rating and user preferences
                score = metric.elo_rating
                
                # Adjust score based on user preferences
                if user_preferences.get('prefer_fast_models') and model.model_code.endswith('-mini'):
                    score += 100
                if user_preferences.get('prefer_accurate_models') and 'turbo' not in model.model_code:
                    score += 50
                
                models_with_scores.append((model, score))
        
        # Sort by score and return the best
        if models_with_scores:
            models_with_scores.sort(key=lambda x: x[1], reverse=True)
            return models_with_scores[0][0]
        
        return queryset.first()


def count_tokens(text: str, model_code: str = None) -> int:
    """
    Estimate token count for text
    This is a simplified version - in production, use tiktoken or model-specific tokenizers
    """
    # Simple approximation: ~4 characters per token
    return len(text) // 4


def format_model_response(response: str, format_type: str = 'markdown') -> str:
    """Format model response based on type"""
    if format_type == 'markdown':
        # Already in markdown
        return response
    elif format_type == 'html':
        return markdown.markdown(response)
    elif format_type == 'plain':
        # Strip markdown formatting
        # Remove markdown links
        response = re.sub(r'$$([^$$]+)\]$[^$]+\)', r'\1', response)
        # Remove bold/italic
        response = re.sub(r'[*_]{1,2}([^*_]+)[*_]{1,2}', r'\1', response)
        # Remove headers
        response = re.sub(r'^#{1,6}\s+', '', response, flags=re.MULTILINE)
        return response
    
    return response