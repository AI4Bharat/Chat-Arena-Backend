from celery import shared_task
from django.utils import timezone
from django.db.models import Count, Avg, Q
from datetime import timedelta
import logging
from ai_model.models import AIModel
from model_metrics.calculators import MetricsCalculator
from model_metrics.services import ModelMetricsService
from model_metrics.models import ModelMetric
from ai_model.models import AIModel
from django.core.mail import send_mail
from django.conf import settings
from model_metrics.aggregators import MetricsAggregator
logger = logging.getLogger(__name__)
from tenants.context import tenant_aware_task

@shared_task
@tenant_aware_task
def calculate_daily_metrics():
    """Calculate daily metrics for all active models"""
    
    active_models = AIModel.objects.filter(is_active=True)
    
    categories = ['overall', 'code', 'creative', 'reasoning', 'conversation']
    
    for model in active_models:
        for category in categories:
            try:
                MetricsCalculator.calculate_category_metrics(
                    model=model,
                    category=category,
                    period='daily'
                )
                logger.info(f"Calculated {category} daily metrics for {model.display_name}")
            except Exception as e:
                logger.error(f"Error calculating metrics for {model.display_name}: {e}")
    
    return f"Calculated metrics for {active_models.count()} models"


@shared_task
@tenant_aware_task
def calculate_weekly_metrics():
    """Calculate weekly metrics for all active models"""
    
    active_models = AIModel.objects.filter(is_active=True)
    
    for model in active_models:
        MetricsCalculator.calculate_category_metrics(
            model=model,
            category='overall',
            period='weekly'
        )
    
    return f"Calculated weekly metrics for {active_models.count()} models"


@shared_task
@tenant_aware_task
def update_leaderboard_cache():
    """Pre-calculate and cache leaderboard data"""
    
    categories = ['overall', 'code', 'creative', 'reasoning', 'conversation']
    periods = ['daily', 'weekly', 'all_time']
    
    for category in categories:
        for period in periods:
            # Generate leaderboard to cache it
            ModelMetricsService.get_leaderboard(
                category=category,
                period=period,
                limit=50
            )
    
    logger.info("Updated leaderboard cache")
    return "Leaderboard cache updated"


@shared_task
@tenant_aware_task
def detect_anomalous_metrics():
    """Detect anomalous metric changes"""
    
    # Check for sudden ELO changes
    recent_metrics = ModelMetric.objects.filter(
        calculated_at__gte=timezone.now() - timedelta(hours=24)
    )
    
    anomalies = []
    
    for metric in recent_metrics:
        # Get previous metric
        previous = ModelMetric.objects.filter(
            model=metric.model,
            category=metric.category,
            period=metric.period,
            calculated_at__lt=metric.calculated_at
        ).order_by('-calculated_at').first()
        
        if previous:
            elo_change = abs(metric.elo_rating - previous.elo_rating)
            
            # Flag large changes (>100 points)
            if elo_change > 100:
                anomalies.append({
                    'model': metric.model.display_name,
                    'category': metric.category,
                    'change': elo_change,
                    'direction': 'increase' if metric.elo_rating > previous.elo_rating else 'decrease'
                })
    
    if anomalies:
        logger.warning(f"Detected {len(anomalies)} anomalous metric changes: {anomalies}")
    
    return anomalies

@shared_task
@tenant_aware_task
def generate_metric_report():
    """Generate comprehensive metrics report"""
    
    # Get top models by category
    categories = ['overall', 'code', 'creative', 'reasoning']
    report_data = {
        'generated_at': timezone.now(),
        'top_models_by_category': {},
        'biggest_movers': [],
        'provider_summary': []
    }
    
    # Top models by category
    for category in categories:
        top_metrics = ModelMetric.objects.filter(
            category=category,
            period='all_time'
        ).order_by('model', '-calculated_at').distinct('model').order_by('-elo_rating')[:5]
        
        report_data['top_models_by_category'][category] = [
            {
                'model': m.model.display_name,
                'provider': m.model.provider,
                'elo_rating': m.elo_rating,
                'win_rate': (m.wins / m.total_comparisons * 100) if m.total_comparisons > 0 else 0
            }
            for m in top_metrics
        ]
    
    # Biggest movers (last 7 days)
    week_ago = timezone.now() - timedelta(days=7)
    
    for model in AIModel.objects.filter(is_active=True):
        current = ModelMetric.objects.filter(
            model=model,
            category='overall',
            period='all_time'
        ).order_by('-calculated_at').first()
        
        old = ModelMetric.objects.filter(
            model=model,
            category='overall',
            period='all_time',
            calculated_at__lte=week_ago
        ).order_by('-calculated_at').first()
        
        if current and old:
            change = current.elo_rating - old.elo_rating
            if abs(change) > 50:  # Significant change
                report_data['biggest_movers'].append({
                    'model': model.display_name,
                    'change': change,
                    'current_elo': current.elo_rating
                })
    
    # Sort biggest movers
    report_data['biggest_movers'].sort(key=lambda x: abs(x['change']), reverse=True)
    report_data['biggest_movers'] = report_data['biggest_movers'][:10]
    
    # Provider summary
    providers = AIModel.objects.filter(is_active=True).values_list('provider', flat=True).distinct()
    
    for provider in providers:
        summary = MetricsAggregator.aggregate_provider_metrics(provider)
        report_data['provider_summary'].append({
            'provider': provider,
            'average_elo': summary['average_elo'],
            'model_count': summary['model_count']
        })
    
    # Format email
    email_content = f"""
    Model Metrics Report - {timezone.now().strftime('%Y-%m-%d')}
    
    TOP MODELS BY CATEGORY:
    """
    
    for category, models in report_data['top_models_by_category'].items():
        email_content += f"\n{category.upper()}:\n"
        for i, model in enumerate(models, 1):
            email_content += f"  {i}. {model['model']} (ELO: {model['elo_rating']})\n"
    
    email_content += "\nBIGGEST MOVERS (Last 7 Days):\n"
    for mover in report_data['biggest_movers'][:5]:
        symbol = '📈' if mover['change'] > 0 else '📉'
        email_content += f"  {symbol} {mover['model']}: {mover['change']:+.0f} (now {mover['current_elo']})\n"
    
    # Send email
    send_mail(
        subject='Weekly Model Metrics Report',
        message=email_content,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=settings.ADMIN_EMAIL_LIST,
        fail_silently=False
    )
    
    logger.info("Metric report generated and sent")
    return "Report sent successfully"


@shared_task
@tenant_aware_task
def cleanup_old_metrics():
    """Clean up old metrics to save space"""
    
    # Keep only latest daily metrics for past 90 days
    cutoff_daily = timezone.now() - timedelta(days=90)
    old_daily = ModelMetric.objects.filter(
        period='daily',
        calculated_at__lt=cutoff_daily
    ).delete()
    
    # Keep only latest weekly metrics for past year
    cutoff_weekly = timezone.now() - timedelta(days=365)
    old_weekly = ModelMetric.objects.filter(
        period='weekly',
        calculated_at__lt=cutoff_weekly
    ).delete()
    
    logger.info(f"Cleaned up old metrics: {old_daily[0]} daily, {old_weekly[0]} weekly")
    return f"Deleted {old_daily[0] + old_weekly[0]} old metrics"