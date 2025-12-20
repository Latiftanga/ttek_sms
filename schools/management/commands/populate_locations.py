import sys
from django.core.management.base import BaseCommand
from django.db import transaction
from locations.models import Region, District

class Command(BaseCommand):
    help = 'Populates the database with all 16 Regions and their Districts in Ghana'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.WARNING('Starting locations population...'))

        # Full Data Structure (Region Code, Region Name, [List of Districts])
        GHANA_DATA = [
            ("AH", "Ahafo", [
                "Asunafo North Municipal", "Asunafo South", "Asutifi North", 
                "Asutifi South", "Tano North Municipal", "Tano South Municipal"
            ]),
            ("AS", "Ashanti", [
                "Adansi Asokwa", "Adansi North", "Adansi South", "Afigya Kwabre North", 
                "Afigya Kwabre South", "Ahafo Ano North Municipal", "Ahafo Ano South East", 
                "Ahafo Ano South West", "Akrofuom", "Amansie Central", "Amansie South", 
                "Amansie West", "Asante Akim Central Municipal", "Asante Akim North", 
                "Asante Akim South Municipal", "Asokore Mampong Municipal", "Asokwa Municipal", 
                "Atwima Kwanwoma", "Atwima Mponua", "Atwima Nwabiagya North", 
                "Atwima Nwabiagya South Municipal", "Bekwai Municipal", "Bosome Freho", 
                "Bosomtwe", "Ejisu Municipal", "Ejura Sekyedumase Municipal", "Juaben Municipal", 
                "Kumasi Metropolitan", "Kwabre East Municipal", "Kwadaso Municipal", 
                "Mampong Municipal", "Obuasi East", "Obuasi Municipal", "Offinso Municipal", 
                "Offinso North", "Oforikrom Municipal", "Old Tafo Municipal", 
                "Sekyere Afram Plains", "Sekyere Central", "Sekyere East", "Sekyere Kumawu", 
                "Sekyere South", "Suame Municipal"
            ]),
            ("BO", "Bono", [
                "Banda", "Berekum East Municipal", "Berekum West", "Dormaa Central Municipal", 
                "Dormaa East", "Dormaa West", "Jaman North", "Jaman South Municipal", 
                "Sunyani Municipal", "Sunyani West", "Tain", "Wenchi Municipal"
            ]),
            ("BE", "Bono East", [
                "Atebubu-Amantin Municipal", "Kintampo North Municipal", "Kintampo South", 
                "Nkoranza North", "Nkoranza South Municipal", "Pru East", "Pru West", 
                "Sene East", "Sene West", "Techiman Municipal", "Techiman North"
            ]),
            ("CP", "Central", [
                "Abura Asebu Kwamankese", "Agona East", "Agona West Municipal", 
                "Ajumako Enyan Essiam", "Asikuma Odoben Brakwa", "Assin Central Municipal", 
                "Assin North", "Assin South", "Awutu Senya East Municipal", "Awutu Senya West", 
                "Cape Coast Metropolitan", "Effutu Municipal", "Ekumfi", "Gomoa Central", 
                "Gomoa East", "Gomoa West", "Komenda Edina Eguafo Abirem Municipal", 
                "Mfantsiman Municipal", "Twifo Atti Morkwa", "Twifo Hemang Lower Denkyira", 
                "Upper Denkyira East Municipal", "Upper Denkyira West"
            ]),
            ("ER", "Eastern", [
                "Abuakwa North Municipal", "Abuakwa South Municipal", "Achiase", "Akuapem North Municipal", 
                "Akuapem South", "Akyemansa", "Asene Manso Akroso", "Asuogyaman", "Atiwa East", 
                "Atiwa West", "Ayensuano", "Birim Central Municipal", "Birim North", "Birim South", 
                "Denkyembour", "Fanteakwa North", "Fanteakwa South", "Kwaebibirem Municipal", 
                "Kwahu Afram Plains North", "Kwahu Afram Plains South", "Kwahu East", "Kwahu South", 
                "Kwahu West Municipal", "Lower Manya Krobo Municipal", "New Juaben North Municipal", 
                "New Juaben South Municipal", "Nsawam Adoagyire Municipal", "Okere", 
                "Suhum Municipal", "Upper Manya Krobo", "Upper West Akim", "West Akim Municipal", 
                "Yilo Krobo Municipal"
            ]),
            ("GA", "Greater Accra", [
                "Ablekuma Central Municipal", "Ablekuma North Municipal", "Ablekuma West Municipal", 
                "Accra Metropolitan", "Ada East", "Ada West", "Adentan Municipal", "Ashaiman Municipal", 
                "Ayawaso Central Municipal", "Ayawaso East Municipal", "Ayawaso North Municipal", 
                "Ayawaso West Municipal", "Ga Central Municipal", "Ga East Municipal", "Ga North Municipal", 
                "Ga South Municipal", "Ga West Municipal", "Korle Klottey Municipal", 
                "Kpone Katamanso Municipal", "Krowor Municipal", "La Dade Kotopon Municipal", 
                "La Nkwantanang Madina Municipal", "Ledzokuku Municipal", "Ningo Prampram", 
                "Okaikwei North Municipal", "Shai Osudoku", "Tema Metropolitan", "Tema West Municipal", 
                "Weija Gbawe Municipal"
            ]),
            ("NE", "North East", [
                "Bunkpurugu Nakpanduri", "Chereponi", "East Mamprusi Municipal", 
                "Mamprugu Moagduri", "West Mamprusi Municipal", "Yunyoo Nasuan"
            ]),
            ("NP", "Northern", [
                "Gushegu Municipal", "Karaga", "Kpandai", "Kumbungu", "Mion", "Nanton", 
                "Nanumba North Municipal", "Nanumba South", "Saboba", "Sagnarigu Municipal", 
                "Savelugu Municipal", "Tamale Metropolitan", "Tatale Sanguli", "Tolon", 
                "Yendi Municipal", "Zabzugu"
            ]),
            ("OT", "Oti", [
                "Biakoye", "Guan", "Jasikan Municipal", "Kadjebi", "Krachi East Municipal", 
                "Krachi Nchumuru", "Krachi West", "Nkwanta North", "Nkwanta South Municipal"
            ]),
            ("SV", "Savannah", [
                "Bole", "Central Gonja", "East Gonja Municipal", "North East Gonja", 
                "North Gonja", "Sawla-Tuna-Kalba", "West Gonja Municipal"
            ]),
            ("UE", "Upper East", [
                "Bawku Municipal", "Bawku West", "Binduri", "Bolgatanga East", 
                "Bolgatanga Municipal", "Bongo", "Builsa North Municipal", "Builsa South", 
                "Garu", "Kassena Nankana Municipal", "Kassena Nankana West", "Nabdam", 
                "Pusiga", "Talensi", "Tempane"
            ]),
            ("UW", "Upper West", [
                "Daffiama Bussie Issa", "Jirapa Municipal", "Lambussie Karni", 
                "Lawra Municipal", "Nadowli Kaleo", "Nandom Municipal", 
                "Sissala East Municipal", "Sissala West", "Wa East", 
                "Wa Municipal", "Wa West"
            ]),
            ("TV", "Volta", [
                "Adaklu", "Afadzato South", "Agotime Ziope", "Akatsi North", "Akatsi South", 
                "Anloga", "Central Tongu", "Ho Municipal", "Ho West", "Hohoe Municipal", 
                "Keta Municipal", "Ketu North Municipal", "Ketu South Municipal", 
                "Kpando Municipal", "North Dayi", "North Tongu", "South Dayi", "South Tongu"
            ]),
            ("WP", "Western", [
                "Ahanta West Municipal", "Amenfi Central", "Amenfi East Municipal", 
                "Amenfi West Municipal", "Effia Kwesimintsim Municipal", "Ellembelle", 
                "Jomoro Municipal", "Mpohor", "Nzema East Municipal", "Prestea Huni Valley Municipal", 
                "Sekondi Takoradi Metropolitan", "Shama", "Tarkwa Nsuaem Municipal", "Wassa East"
            ]),
            ("WN", "Western North", [
                "Aowin Municipal", "Bia East", "Bia West", "Bibiani Anhwiaso Bekwai Municipal", 
                "Bodi", "Juaboso", "Sefwi Akontombra", "Sefwi Wiawso Municipal", "Suaman"
            ])
        ]

        try:
            with transaction.atomic():
                for code, name, district_names in GHANA_DATA:
                    # 1. Create or Get the Region
                    region, created = Region.objects.get_or_create(
                        code=code,
                        defaults={'name': name}
                    )
                    
                    if created:
                        self.stdout.write(f"Created Region: {name}")
                    else:
                        # Update name if it changed (optional)
                        region.name = name
                        region.save()

                    # 2. Prepare Districts for Bulk Create
                    districts_to_create = []
                    existing_districts = set(
                        District.objects.filter(region=region).values_list('name', flat=True)
                    )

                    for district_name in district_names:
                        if district_name not in existing_districts:
                            districts_to_create.append(
                                District(name=district_name, region=region)
                            )

                    # 3. Bulk Create Districts
                    if districts_to_create:
                        District.objects.bulk_create(districts_to_create)
                        self.stdout.write(f" -> Added {len(districts_to_create)} districts to {name}")
                    else:
                        self.stdout.write(f" -> No new districts for {name}")

            self.stdout.write(self.style.SUCCESS('Successfully populated all Regions and Districts!'))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error populating data: {str(e)}'))