from celery import shared_task
from django.utils import timezone
from datetime import timedelta
import logging
from feedback.models import Feedback
from model_metrics.models import ModelMetric, AIModel
from django.db.models import Count, Avg, Q
logger = logging.getLogger(__name__)
from feedback.utils import FeedbackMetrics, FeedbackValidator
from user.models import User
from feedback.analytics import FeedbackAnalyzer
from django.core.mail import send_mail
from django.conf import settings
from tenants.context import tenant_aware_task

@shared_task
@tenant_aware_task
def update_model_metrics_from_feedback():
    """Update model metrics based on recent feedback"""
    
    # Process feedback from last hour
    recent_feedback = Feedback.objects.filter(
        created_at__gte=timezone.now() - timedelta(hours=1)
    )
    
    # Update metrics for each model
    models_to_update = set()
    
    # Collect all models that received feedback
    for feedback in recent_feedback:
        if feedback.message and feedback.message.model:
            models_to_update.add(feedback.message.model_id)
        if feedback.session.model_a:
            models_to_update.add(feedback.session.model_a_id)
        if feedback.session.model_b:
            models_to_update.add(feedback.session.model_b_id)
    
    for model_id in models_to_update:
        # Calculate updated metrics
        
        try:
            model = AIModel.objects.get(id=model_id)
            
            # Get or create today's metric
            metric, created = ModelMetric.objects.get_or_create(
                model=model,
                category='overall',
                period='daily',
                calculated_at__date=timezone.now().date(),
                defaults={'calculated_at': timezone.now()}
            )
            
            # Update average rating
            ratings = Feedback.objects.filter(
                feedback_type='rating',
                rating__isnull=False,
                message__model=model,
                created_at__date=timezone.now().date()
            )
            
            if ratings.exists():
                metric.average_rating = ratings.aggregate(avg=Avg('rating'))['avg']
            
            # Update comparison stats
            comparisons = Feedback.objects.filter(
                feedback_type='preference',
                session__mode='compare',
                created_at__date=timezone.now().date()
            ).filter(
                Q(session__model_a=model) | Q(session__model_b=model)
            )
            
            metric.total_comparisons = comparisons.count()
            metric.wins = comparisons.filter(preferred_model=model).count()
            metric.losses = comparisons.exclude(
                preferred_model=model
            ).exclude(
                preferred_model__isnull=True
            ).count()
            metric.ties = metric.total_comparisons - metric.wins - metric.losses
            
            metric.save()
            
        except AIModel.DoesNotExist:
            logger.error(f"Model {model_id} not found")
    
    logger.info(f"Updated metrics for {len(models_to_update)} models")
    return len(models_to_update)


@shared_task
@tenant_aware_task
def detect_feedback_anomalies():
    """Detect unusual feedback patterns"""
    
    # Check for spam feedback
    recent_users = Feedback.objects.filter(
        created_at__gte=timezone.now() - timedelta(hours=1)
    ).values_list('user', flat=True).distinct()
    
    spam_users = []
    
    for user_id in recent_users:
        try:
            user = User.objects.get(id=user_id)
            validation = FeedbackValidator.validate_spam_feedback(user)
            
            if validation['is_spam']:
                spam_users.append({
                    'user_id': str(user_id),
                    'reasons': validation['reasons']
                })
        except User.DoesNotExist:
            continue
    
    if spam_users:
        logger.warning(f"Detected {len(spam_users)} users with spam feedback patterns")
    
    # Check for rating anomalies
    users_with_anomalies = []
    
    for user_id in recent_users[:100]:  # Limit to 100 users
        user_ratings = Feedback.objects.filter(
            user_id=user_id,
            feedback_type='rating',
            rating__isnull=False
        ).order_by('created_at').values_list('created_at', 'rating')
        
        if user_ratings:
            anomalies = FeedbackMetrics.detect_rating_anomalies(list(user_ratings))
            if anomalies:
                users_with_anomalies.append({
                    'user_id': str(user_id),
                    'anomalies': anomalies
                })
    
    return {
        'spam_users': spam_users,
        'users_with_anomalies': users_with_anomalies
    }


@shared_task
@tenant_aware_task
def generate_weekly_feedback_digest():
    """Generate weekly feedback digest for admin"""
    
    # Generate report for last 7 days
    end_date = timezone.now()
    start_date = end_date - timedelta(days=7)
    
    report = FeedbackAnalyzer.generate_feedback_report(start_date, end_date)
    
    # Format email content
    email_content = f"""
    Weekly Feedback Digest
    Period: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}
    
    Summary:
    - Total Feedback: {report['summary']['total_feedback']}
    - Unique Users: {report['summary']['unique_users']}
    - Unique Sessions: {report['summary']['unique_sessions']}
    
    Feedback Types:
    - Ratings: {report['feedback_types'].get('rating', {}).get('count', 0)}
    - Preferences: {report['feedback_types'].get('preference', {}).get('count', 0)}
    - Reports: {report['feedback_types'].get('report', {}).get('count', 0)}
    
    Top Performing Models:
    """
    
    # Add top models
    sorted_models = sorted(
        report['model_performance'].items(),
        key=lambda x: x[1].get('average_rating', 0) or 0,
        reverse=True
    )[:5]
    
    for model_name, stats in sorted_models:
        email_content += f"\n- {model_name}: Rating {stats.get('average_rating', 'N/A')}, Win Rate {stats.get('win_rate', 0):.1f}%"
    
    # Send email
    send_mail(
        subject='Weekly Feedback Digest',
        message=email_content,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=settings.ADMIN_EMAIL_LIST,
        fail_silently=False
    )
    
    logger.info("Weekly feedback digest sent")
    return "Digest sent successfully"


@shared_task
@tenant_aware_task
def cleanup_old_feedback():
    """Clean up old feedback data based on retention policy"""
    from .models import Feedback
    
    # Delete anonymous user feedback older than 90 days
    cutoff_date = timezone.now() - timedelta(days=90)
    
    old_feedback = Feedback.objects.filter(
        user__is_anonymous=True,
        created_at__lt=cutoff_date
    )
    
    count = old_feedback.count()
    old_feedback.delete()
    
    logger.info(f"Deleted {count} old anonymous feedback entries")
    return count


@shared_task
@tenant_aware_task
def calculate_feedback_consistency_scores():
    """Calculate consistency scores for users"""
    
    # Get users who have given feedback recently
    active_users = Feedback.objects.filter(
        created_at__gte=timezone.now() - timedelta(days=30)
    ).values_list('user', flat=True).distinct()[:100]
    
    consistency_report = []
    
    for user_id in active_users:
        try:
            user = User.objects.get(id=user_id)
            user_feedback = Feedback.objects.filter(user=user)
            
            # Validate preference consistency
            consistency = FeedbackValidator.validate_preference_consistency(user_feedback)
            
            if consistency.get('inconsistent_users'):
                consistency_report.append({
                    'user_id': str(user_id),
                    'consistency_details': consistency
                })
            
        except User.DoesNotExist:
            continue
    
    logger.info(f"Calculated consistency scores for {len(active_users)} users")
    
    return consistency_report