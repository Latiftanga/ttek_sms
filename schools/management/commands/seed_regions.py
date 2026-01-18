"""
Management command to seed Ghana's 16 Regions and their Districts.
Run with: python manage.py seed_regions
"""
from django.core.management.base import BaseCommand
from schools.models import Region, District


# Ghana's 16 Regions with their codes and districts
GHANA_REGIONS = {
    'Ahafo': {
        'code': 'AH',
        'districts': [
            'Asunafo North Municipal',
            'Asunafo South',
            'Asutifi North',
            'Asutifi South',
            'Tano North Municipal',
            'Tano South Municipal',
        ]
    },
    'Ashanti': {
        'code': 'AS',
        'districts': [
            'Adansi Asokwa',
            'Adansi North',
            'Adansi South',
            'Afigya Kwabre North',
            'Afigya Kwabre South',
            'Ahafo Ano North Municipal',
            'Ahafo Ano South East',
            'Ahafo Ano South West',
            'Akrofuom',
            'Amansie Central',
            'Amansie South',
            'Amansie West',
            'Asante Akim Central Municipal',
            'Asante Akim North',
            'Asante Akim South Municipal',
            'Asokore Mampong Municipal',
            'Asokwa Municipal',
            'Atwima Kwanwoma',
            'Atwima Mponua',
            'Atwima Nwabiagya Municipal',
            'Atwima Nwabiagya North',
            'Bekwai Municipal',
            'Bosome Freho',
            'Bosomtwe',
            'Ejisu Municipal',
            'Ejura Sekyedumase Municipal',
            'Juaben Municipal',
            'Kumasi Metropolitan',
            'Kwabre East Municipal',
            'Kwadaso Municipal',
            'Mampong Municipal',
            'Nhyiaeso Municipal',
            'Obuasi East',
            'Obuasi Municipal',
            'Offinso Municipal',
            'Offinso North',
            'Oforikrom Municipal',
            'Old Tafo Municipal',
            'Sekyere Afram Plains',
            'Sekyere Central',
            'Sekyere East',
            'Sekyere Kumawu',
            'Sekyere South',
            'Suame Municipal',
            'Subin Municipal',
        ]
    },
    'Bono': {
        'code': 'BO',
        'districts': [
            'Banda',
            'Berekum East Municipal',
            'Berekum West',
            'Dormaa Central Municipal',
            'Dormaa East',
            'Dormaa West',
            'Jaman North',
            'Jaman South Municipal',
            'Sunyani Municipal',
            'Sunyani West',
            'Tain',
            'Wenchi Municipal',
        ]
    },
    'Bono East': {
        'code': 'BE',
        'districts': [
            'Atebubu-Amantin Municipal',
            'Kintampo North Municipal',
            'Kintampo South',
            'Nkoranza North',
            'Nkoranza South Municipal',
            'Pru East',
            'Pru West',
            'Sene East',
            'Sene West',
            'Techiman Municipal',
            'Techiman North',
        ]
    },
    'Central': {
        'code': 'CE',
        'districts': [
            'Abura Asebu Kwamankese',
            'Agona East',
            'Agona West Municipal',
            'Ajumako Enyan Essiam',
            'Asikuma Odoben Brakwa',
            'Assin Central Municipal',
            'Assin Fosu Municipal',
            'Assin North',
            'Assin South',
            'Awutu Senya',
            'Awutu Senya East Municipal',
            'Cape Coast Metropolitan',
            'Effutu Municipal',
            'Ekumfi',
            'Gomoa Central',
            'Gomoa East',
            'Gomoa West',
            'Hemang Lower Denkyira',
            'Komenda Edina Eguafo Abirem Municipal',
            'Mfantseman Municipal',
            'Twifo Atti Morkwa',
            'Twifo Hemang Lower Denkyira',
            'Upper Denkyira East Municipal',
            'Upper Denkyira West',
        ]
    },
    'Eastern': {
        'code': 'EA',
        'districts': [
            'Abuakwa North Municipal',
            'Abuakwa South Municipal',
            'Achiase',
            'Akuapem North Municipal',
            'Akuapem South',
            'Akyemansa',
            'Asene Manso Akroso',
            'Asuogyaman',
            'Atiwa East',
            'Atiwa West',
            'Ayensuano',
            'Birim Central Municipal',
            'Birim North',
            'Birim South',
            'Denkyembour',
            'Fanteakwa North',
            'Fanteakwa South',
            'Kwaebibirem Municipal',
            'Kwahu Afram Plains North',
            'Kwahu Afram Plains South',
            'Kwahu East',
            'Kwahu South',
            'Kwahu West Municipal',
            'Lower Manya Krobo Municipal',
            'New Juaben North Municipal',
            'New Juaben South Municipal',
            'Nsawam Adoagyiri Municipal',
            'Okere',
            'Suhum Municipal',
            'Upper Manya Krobo',
            'Upper West Akim',
            'West Akim Municipal',
            'Yilo Krobo Municipal',
        ]
    },
    'Greater Accra': {
        'code': 'GA',
        'districts': [
            'Ablekuma Central Municipal',
            'Ablekuma North Municipal',
            'Ablekuma West Municipal',
            'Accra Metropolitan',
            'Ada East',
            'Ada West',
            'Adenta Municipal',
            'Ashaiman Municipal',
            'Ayawaso Central Municipal',
            'Ayawaso East Municipal',
            'Ayawaso North Municipal',
            'Ayawaso West Municipal',
            'Ga Central Municipal',
            'Ga East Municipal',
            'Ga North Municipal',
            'Ga South Municipal',
            'Ga West Municipal',
            'Korle Klottey Municipal',
            'Kpone Katamanso Municipal',
            'Krowor Municipal',
            'La Dade Kotopon Municipal',
            'La Nkwantanang Madina Municipal',
            'Ledzokuku Municipal',
            'Ningo Prampram',
            'Okaikwei North Municipal',
            'Shai Osudoku',
            'Tema Metropolitan',
            'Tema West Municipal',
            'Weija Gbawe Municipal',
        ]
    },
    'North East': {
        'code': 'NE',
        'districts': [
            'Bunkpurugu Nakpanduri',
            'Chereponi',
            'East Mamprusi Municipal',
            'Mamprugu Moagduri',
            'West Mamprusi Municipal',
            'Yunyoo Nasuan',
        ]
    },
    'Northern': {
        'code': 'NR',
        'districts': [
            'Gushegu Municipal',
            'Karaga',
            'Kpandai',
            'Kumbungu',
            'Mion',
            'Nanton',
            'Nanumba North Municipal',
            'Nanumba South',
            'Saboba',
            'Sagnarigu Municipal',
            'Savelugu Municipal',
            'Tamale Metropolitan',
            'Tatale Sanguli',
            'Tolon',
            'Yendi Municipal',
            'Zabzugu',
        ]
    },
    'Oti': {
        'code': 'OT',
        'districts': [
            'Biakoye',
            'Guan',
            'Jasikan',
            'Kadjebi',
            'Krachi East Municipal',
            'Krachi Nchumuru',
            'Krachi West',
            'Nkwanta North',
            'Nkwanta South Municipal',
        ]
    },
    'Savannah': {
        'code': 'SV',
        'districts': [
            'Bole',
            'Central Gonja',
            'East Gonja Municipal',
            'North East Gonja',
            'North Gonja',
            'Sawla Tuna Kalba',
            'West Gonja Municipal',
        ]
    },
    'Upper East': {
        'code': 'UE',
        'districts': [
            'Bawku Municipal',
            'Bawku West',
            'Binduri',
            'Bolgatanga East',
            'Bolgatanga Municipal',
            'Bongo',
            'Builsa North Municipal',
            'Builsa South',
            'Garu',
            'Kassena Nankana East Municipal',
            'Kassena Nankana West',
            'Nabdam',
            'Pusiga',
            'Talensi',
            'Tempane',
        ]
    },
    'Upper West': {
        'code': 'UW',
        'districts': [
            'Daffiama Bussie Issa',
            'Jirapa Municipal',
            'Lambussie Karni',
            'Lawra Municipal',
            'Nadowli Kaleo',
            'Nandom Municipal',
            'Sissala East Municipal',
            'Sissala West',
            'Wa East',
            'Wa Municipal',
            'Wa West',
        ]
    },
    'Volta': {
        'code': 'VR',
        'districts': [
            'Adaklu',
            'Afadzato South',
            'Agotime Ziope',
            'Akatsi North',
            'Akatsi South',
            'Anloga',
            'Central Tongu',
            'Ho Municipal',
            'Ho West',
            'Hohoe Municipal',
            'Keta Municipal',
            'Ketu North Municipal',
            'Ketu South Municipal',
            'Kpando Municipal',
            'North Dayi',
            'North Tongu',
            'South Dayi',
            'South Tongu',
        ]
    },
    'Western': {
        'code': 'WR',
        'districts': [
            'Ahanta West Municipal',
            'Effia Kwesimintsim Municipal',
            'Ellembelle',
            'Jomoro',
            'Mpohor',
            'Nzema East Municipal',
            'Prestea Huni Valley Municipal',
            'Sekondi Takoradi Metropolitan',
            'Shama',
            'Tarkwa Nsuaem Municipal',
            'Wassa Amenfi Central',
            'Wassa Amenfi East Municipal',
            'Wassa Amenfi West',
            'Wassa East',
        ]
    },
    'Western North': {
        'code': 'WN',
        'districts': [
            'Aowin Municipal',
            'Bia East',
            'Bia West',
            'Bibiani Anhwiaso Bekwai Municipal',
            'Bodi',
            'Juaboso',
            'Sefwi Akontombra',
            'Sefwi Wiawso Municipal',
            'Suaman',
        ]
    },
}


class Command(BaseCommand):
    help = 'Seed Ghana regions and districts into the database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing regions and districts before seeding',
        )

    def handle(self, *args, **options):
        if options['clear']:
            self.stdout.write('Clearing existing regions and districts...')
            District.objects.all().delete()
            Region.objects.all().delete()
            self.stdout.write(self.style.WARNING('Cleared all regions and districts.'))

        regions_created = 0
        regions_updated = 0
        districts_created = 0

        for region_name, data in GHANA_REGIONS.items():
            region, created = Region.objects.update_or_create(
                name=region_name,
                defaults={'code': data['code']}
            )

            if created:
                regions_created += 1
                self.stdout.write(f'  Created region: {region_name} ({data["code"]})')
            else:
                regions_updated += 1

            for district_name in data['districts']:
                district, created = District.objects.get_or_create(
                    name=district_name,
                    region=region
                )
                if created:
                    districts_created += 1

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'Seeding complete!\n'
            f'  Regions: {regions_created} created, {regions_updated} already existed\n'
            f'  Districts: {districts_created} created'
        ))
        self.stdout.write(f'  Total regions: {Region.objects.count()}')
        self.stdout.write(f'  Total districts: {District.objects.count()}')
