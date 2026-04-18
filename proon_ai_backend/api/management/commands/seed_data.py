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
            'name': 'Plum',
            'scientific_name': 'Prunus domestica',
            'description': 'Plum is a stone fruit that requires proper ripeness detection for optimal harvest quality.',
            'accuracy': 98.9,
            'latency_ms': 15,
        },
        'labels': [
            {
                'key': 'unripe',
                'rule': {
                    'ripeness_score': 20,
                    'ripeness_label': 'Not Ready',
                    'peak_window': '3-5 days',
                    'status': 'Unripe',
                    'quick_tips': [
                        'Continue monitoring daily',
                        'Keep plant well-watered',
                        'Ensure adequate sunlight (6+ hours/day)',
                    ],
                    'detection_detail': 'Buds are tightly closed with no signs of readiness. Plant requires more time to mature.',
                    'recommendations': [
                        'Ensure adequate sunlight (6+ hours/day)',
                        'Maintain soil moisture but avoid waterlogging',
                        'Check back in 3-5 days',
                    ],
                    'reference_image_url': '',
                },
            },
            {
                'key': 'unaffected',
                'rule': {
                    'ripeness_score': 50,
                    'ripeness_label': 'Healthy',
                    'peak_window': '5-7 days',
                    'status': 'Normal',
                    'quick_tips': [
                        'Plant is healthy and developing normally',
                        'Monitor for any changes',
                        'Continue regular care',
                    ],
                    'detection_detail': 'Plant is in good health with no visible issues. Growth is progressing normally.',
                    'recommendations': [
                        'Maintain current care routine',
                        'Monitor for pest damage',
                        'Continue regular watering',
                    ],
                    'reference_image_url': '',
                },
            },
            {
                'key': 'spotted',
                'rule': {
                    'ripeness_score': 65,
                    'ripeness_label': 'Ready',
                    'peak_window': '2-3 days',
                    'status': 'Spotted',
                    'quick_tips': [
                        'Spots indicate ripeness',
                        'Harvest within 24-48 hours for best quality',
                        'Handle carefully to avoid further damage',
                    ],
                    'detection_detail': 'Plant shows signs of maturity with visible blemishes indicating peak ripeness.',
                    'recommendations': [
                        'Harvest within 24-48 hours',
                        'Handle carefully to avoid damaging remaining spots',
                        'Store at room temperature',
                    ],
                    'reference_image_url': '',
                },
            },
            {
                'key': 'rotten',
                'rule': {
                    'ripeness_score': 100,
                    'ripeness_label': 'Overripe/Decaying',
                    'peak_window': 'Harvest immediately',
                    'status': 'Rotten',
                    'quick_tips': [
                        'Remove immediately to prevent spread',
                        'Check surrounding plants',
                        'Do not consume',
                    ],
                    'detection_detail': 'Plant shows signs of decay or rot. This is beyond peak ripeness and unsuitable for use.',
                    'recommendations': [
                        'Remove from plants immediately',
                        'Dispose of properly',
                        'Check nearby plants for infection',
                    ],
                    'reference_image_url': '',
                },
            },
            {
                'key': 'cracked',
                'rule': {
                    'ripeness_score': 70,
                    'ripeness_label': 'Damaged - Harvest Soon',
                    'peak_window': '1-2 days',
                    'status': 'Cracked',
                    'quick_tips': [
                        'Cracks indicate stress or overripeness',
                        'Harvest as soon as possible',
                        'Use within 24 hours',
                    ],
                    'detection_detail': 'Plant shows visible cracks or splits. May be due to overripeness or environmental stress.',
                    'recommendations': [
                        'Harvest within 24 hours',
                        'Use immediately for best quality',
                        'Store carefully to prevent further damage',
                    ],
                    'reference_image_url': '',
                },
            },
            {
                'key': 'bruised',
                'rule': {
                    'ripeness_score': 60,
                    'ripeness_label': 'Ripe with Damage',
                    'peak_window': '1-2 days',
                    'status': 'Bruised',
                    'quick_tips': [
                        'Bruises indicate physical damage',
                        'Harvest and use immediately',
                        'Handle with care',
                    ],
                    'detection_detail': 'Plant shows bruising from physical damage. Still usable but should be harvested soon.',
                    'recommendations': [
                        'Harvest immediately',
                        'Use within 24-48 hours',
                        'Handle very gently to prevent further damage',
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
