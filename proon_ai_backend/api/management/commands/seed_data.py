"""
Management command: python manage.py seed_data

Seeds the database with initial plant categories, detection labels,
and rule-based detection results for the Proon AI app.

Run this after migrations on a fresh setup.
"""
from django.core.management.base import BaseCommand
from api.models import PlantCategory, DetectionLabel, DetectionRule


SEED_DATA = [
    {
        'category': {
            'name': 'Apple',
            'scientific_name': 'Malus domestica',
            'description': 'Apple tree used for fruit ripeness detection and monitoring.',
            'accuracy': 98.9,
            'latency_ms': 15,
        },
        'labels': [],
    },
    {
        'category': None,
        'labels': [
            {
                'key': 'sprouts',
                'rule': {
                    'ripeness_score': 40,
                    'ripeness_label': 'Early Growth',
                    'peak_window': '4-7 days',
                    'status': 'Unclassified',
                    'quick_tips': [
                        'Keep soil moist but not waterlogged',
                        'Ensure 6+ hours of indirect sunlight',
                        'Monitor daily for healthy growth',
                    ],
                    'detection_detail': 'Sprouts detected. Growth is in an early stage and not yet ready for harvest.',
                    'recommendations': [
                        'Maintain consistent watering schedule',
                        'Check for pests or mold',
                        'Recheck in 4-7 days',
                    ],
                    'reference_image_url': '',
                },
            },
        ],
    },
]


class Command(BaseCommand):
    help = 'Seeds the database with initial Proon AI plant data and detection rules'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing data before seeding (use with caution)',
        )

    def handle(self, *args, **options):
        if options['clear']:
            self.stdout.write(self.style.WARNING('Clearing existing data...'))
            DetectionRule.objects.all().delete()
            DetectionLabel.objects.all().delete()
            PlantCategory.objects.all().delete()

        created_count = 0

        for item in SEED_DATA:
            cat_data = item.get('category')
            category = None
            if cat_data:
                category, cat_created = PlantCategory.objects.update_or_create(
                    name=cat_data['name'],
                    defaults=cat_data,
                )
                if cat_created:
                    self.stdout.write(f'  [OK] Created category: {category.name}')
                else:
                    self.stdout.write(f'  [UPDATE] Category: {category.name}')

            for label_data in item['labels']:
                label, label_created = DetectionLabel.objects.update_or_create(
                    label_key=label_data['key'],
                    defaults={'plant_category': category},
                )
                if label_created:
                    self.stdout.write(f'    [OK] Created label: {label.label_key}')

                rule_data = label_data.get('rule')
                if rule_data:
                    rule, rule_created = DetectionRule.objects.update_or_create(
                        label=label,
                        defaults=rule_data,
                    )
                    if rule_created:
                        self.stdout.write(f'    [OK] Created rule for: {label.label_key}')
                        created_count += 1
                    else:
                        self.stdout.write(f'    [UPDATE] Rule for: {label.label_key}')

        self.stdout.write(
            self.style.SUCCESS(
                f'\nSeeding complete! {created_count} new rules created.'
            )
        )
        self.stdout.write(
            '\nNext steps:\n'
            '  1. Run migrations: python manage.py migrate\n'
            '  2. Create superuser: python manage.py createsuperuser\n'
            '  3. Set GEMINI_API_KEY in .env\n'
            '  4. Start server: python manage.py runserver\n'
        )
