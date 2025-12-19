from django.core.management.base import BaseCommand
from ai_model.models import AIModel
from datetime import date

class Command(BaseCommand):
    help = 'Populates release_date for AI models'

    def handle(self, *args, **kwargs):
        release_dates = {
            "GPT-5.2": "2025-12-11",
            "gemini-3-flash-preview": "2025-12-01", # Late 2025
            "Gemini 3 Pro": "2025-11-18", # ~2025-11-18
            "Claude Haiku 4.5": "2025-10-15",
            "Claude Sonnet 4.5": "2025-09-30", # ~2025-09-30
            "GPT-5": "2025-08-07",
            "Claude Opus 4.1": "2025-08-05",
            "gemini-2.5-pro": "2025-06-05",
            "Sarvam-M": "2025-05-23",
            "Qwen3-30B-A3B": "2025-05-01", # ~2025-05-01
            "Llama-4-Scout-17B": "2025-04-05",
            "Llama-4-Maverick-17B": "2025-04-05",
            "gemini-2.5-flash": "2025-07-01", # 2025 mid-year
            "Llama-3.3-70B-Instruct": "2024-12-06",
            "Llama-3.2-3B-Instruct": "2024-09-25",
            "GPT4o mini": "2024-07-18",
            "Meta-Llama-3.1-70B-Instruct": "2024-07-23",
            "Meta-Llama-3.1-8B-Instruct": "2024-07-23",
            "GPT-4": "2023-03-14",
            "GPT 3.5": "2022-11-30",
            "Llama 4 Scout 17B 16E Instruct": "2025-04-05",
            "Llama 4 Maverick 17B 128E Instruct": "2025-04-05",
            "Meta Llama 3.1 70B Instruct Turbo": "2024-07-23",
            "Meta Llama 3.1 8B Instruct Turbo": "2024-07-23",
            "Llama 3.3 70B Instruct Turbo": "2024-12-06",
            "Gemini 2.5 Flash Lite": "2025-07-01", # Assuming similar to Flash
            "AI4Bharat Conformer": "2024-01-01", # Approximate/Placeholder
            "AI4Bharat Conformer 2": "2024-06-01", # Approximate/Placeholder
            "gemma 3 27b it": "2025-10-15", # Based on created_at or general timeframe
            "gemma 3 12b it": "2025-10-15",
            "IBM Granite 4": "2025-12-01",
        }

        # Helper to normalize names for comparison
        def normalize(s):
            return s.lower().replace('-', '').replace(' ', '').replace('_', '').replace('.', '')

        # Create a mapping of normalized key -> date_str
        normalized_dates = {normalize(k): v for k, v in release_dates.items()}
        
        count = 0
        models = AIModel.objects.all()
        for model in models:
            norm_name = normalize(model.display_name)
            norm_code = normalize(model.model_code)
            
            date_str = normalized_dates.get(norm_name) or normalized_dates.get(norm_code)
            
            if date_str:
                try:
                    year, month, day = map(int, date_str.split('-'))
                    model.release_date = date(year, month, day)
                    model.save()
                    count += 1
                    self.stdout.write(self.style.SUCCESS(f'Updated {model.display_name} to {date_str}'))
                except ValueError:
                    self.stdout.write(self.style.ERROR(f'Invalid date format for {model.display_name}: {date_str}'))
            else:
                self.stdout.write(self.style.WARNING(f'No date found for {model.display_name} (norm: {norm_name})'))

        self.stdout.write(self.style.SUCCESS(f'Successfully updated {count} models'))
