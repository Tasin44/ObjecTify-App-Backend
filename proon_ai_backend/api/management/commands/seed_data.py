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
            'name': 'Sprouts',
            'scientific_name': 'Brassica oleracea var. gemmifera',
            'description': 'Brussels sprouts are a member of the Gemmifera cultivar group of wild cabbage.',
            'accuracy': 98.9,
            'latency_ms': 15,
        },
        'labels': [
            {
                'key': 'Sprouts',
                'rule': {
                    'ripeness_score': 86,
                    'ripeness_label': 'Very High',
                    'peak_window': 'Harvest within 3–5 days',
                    'status': 'Classified',
                    'quick_tips': [
                        'Twist-test: separates clearly → ready to pick',
                        'Cool to 0–2°C within 4h of harvest',
                        'Avoid storing near ethylene-producing fruit',
                    ],
                    'detection_detail': (
                        'Brussels sprouts detected at peak ripeness. The sprout heads are firm '
                        'and tightly packed, indicating full maturity. Optimal flavor and nutrition '
                        'are achieved at this stage. Begin harvesting from the bottom of the stalk '
                        'upward, as lower sprouts mature first. Delay beyond 5 days risks yellowing '
                        'and bitterness.'
                    ),
                    'recommendations': [
                        'Harvest from bottom of stalk upward — lower sprouts mature first',
                        'Avoid storing near ethylene-producing produce (apples, bananas)',
                        'Store unwashed in refrigerator for up to 5 days',
                        'Prune yellowing leaves around sprout clusters to improve airflow',
                    ],
                    'reference_image_url': '',
                },
            }
        ],
    },
    # ---------- Add future plant models below as the client provides more labels ----------
    # {
    #     'category': {
    #         'name': 'Apple',
    #         'scientific_name': 'Malus domestica',
    #         'description': 'Apple tree used in fruit ripeness and pruning detection.',
    #         'accuracy': 98.9,
    #         'latency_ms': 15,
    #     },
    #     'labels': [
    #         {
    #             'key': 'Apple_Ripe',
    #             'rule': { ... }
    #         },
    #         {
    #             'key': 'Apple_Unripe',
    #             'rule': { ... }
    #         },
    #     ],
    # },
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
            cat_data = item['category']
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

                rule_data = label_data['rule']
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
