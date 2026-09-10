from celery import shared_task
from django.utils import timezone
from datetime import timedelta
import logging
from model_metrics.models import AIModel, ModelMetric
from feedback.models import Feedback
from django.db.models import Count, Avg, Q
logger = logging.getLogger(__name__)
from ai_model.utils import EloRatingCalculator
from ai_model.services import AIModelService
from tenants.context import tenant_aware_task

@shared_task
@tenant_aware_task
def calculate_model_metrics(period='daily'):
    """Calculate model metrics for the specified period"""
    
    # Determine time range
    now = timezone.now()
    if period == 'daily':
        start_time = now - timedelta(days=1)
    elif period == 'weekly':
        start_time = now - timedelta(weeks=1)
    elif period == 'monthly':
        start_time = now - timedelta(days=30)
    else:  # all_time
        start_time = None
    
    models = AIModel.objects.filter(is_active=True)
    
    for model in models:
        # Get feedback for this period
        feedback_query = Feedback.objects.filter(
            Q(session__model_a=model) | Q(session__model_b=model),
            feedback_type='preference'
        )
        
        if start_time:
            feedback_query = feedback_query.filter(created_at__gte=start_time)
        
        # Calculate wins, losses, ties
        wins = feedback_query.filter(preferred_model=model).count()
        total_comparisons = feedback_query.count()
        
        # Get losses (where the other model was preferred)
        losses = feedback_query.exclude(
            preferred_model=model
        ).exclude(
            preferred_model__isnull=True
        ).count()
        
        ties = total_comparisons - wins - losses
        
        # Calculate average rating
        avg_rating = Feedback.objects.filter(
            message__model=model,
            rating__isnull=False
        ).aggregate(
            avg=Avg('rating')
        )['avg']
        
        # Create or update metric
        ModelMetric.objects.create(
            model=model,
            category='overall',
            period=period,
            total_comparisons=total_comparisons,
            wins=wins,
            losses=losses,
            ties=ties,
            average_rating=avg_rating,
            calculated_at=now
        )
        
        logger.info(f"Calculated {period} metrics for {model.display_name}")
    
    return f"Calculated metrics for {models.count()} models"


@shared_task
@tenant_aware_task
def update_model_elo_ratings():
    """Update ELO ratings based on recent comparisons"""
    
    # Get recent feedback that hasn't been processed
    recent_feedback = Feedback.objects.filter(
        feedback_type='preference',
        session__mode='compare',
        metadata__elo_processed__isnull=True
    ).order_by('created_at')[:100]  # Process in batches
    
    for feedback in recent_feedback:
        if feedback.preferred_model:
            model_a = feedback.session.model_a
            model_b = feedback.session.model_b
            
            if feedback.preferred_model == model_a:
                result = 'a_wins'
            elif feedback.preferred_model == model_b:
                result = 'b_wins'
            else:
                result = 'tie'
            
            # Update ELO ratings
            EloRatingCalculator.update_model_ratings(
                str(model_a.id),
                str(model_b.id),
                result
            )
            
            # Mark as processed
            feedback.metadata['elo_processed'] = True
            feedback.save(update_fields=['metadata'])
    
    return f"Processed {recent_feedback.count()} feedback items"


@shared_task
@tenant_aware_task
def validate_all_models():
    """Validate all active models and update their status"""
    
    service = AIModelService()
    models = AIModel.objects.filter(is_active=True)
    
    invalid_models = []
    
    for model in models:
        try:
            validation = service.validate_model_configuration(model)
            if not validation['is_valid']:
                invalid_models.append(model.display_name)
                model.is_active = False
                model.config['last_validation_error'] = 'Model validation failed'
                model.save()
        except Exception as e:
            logger.error(f"Error validating {model.display_name}: {e}")
            model.config['last_validation_error'] = str(e)
            model.save()
    
    if invalid_models:
        logger.warning(f"Deactivated invalid models: {', '.join(invalid_models)}")
    
    return f"Validated {models.count()} models, {len(invalid_models)} deactivated"


@shared_task
@tenant_aware_task
def cleanup_old_metrics():
    """Clean up old metrics to prevent database bloat"""
    
    # Keep only the latest metric for each period/category combination
    cutoff_dates = {
        'daily': timezone.now() - timedelta(days=30),
        'weekly': timezone.now() - timedelta(weeks=12),
        'monthly': timezone.now() - timedelta(days=365),
    }
    
    deleted_count = 0
    
    for period, cutoff_date in cutoff_dates.items():
        old_metrics = ModelMetric.objects.filter(
            period=period,
            calculated_at__lt=cutoff_date
        )
        deleted_count += old_metrics.count()
        old_metrics.delete()
    
    logger.info(f"Deleted {deleted_count} old metrics")
    return f"Deleted {deleted_count} old metrics"