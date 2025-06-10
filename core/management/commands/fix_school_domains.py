from django.core.management.base import BaseCommand
from core.models import School


class Command(BaseCommand):
    help = 'Fix schools with missing or invalid subdomains'

    def handle(self, *args, **options):
        schools_fixed = 0

        for school in School.objects.all():
            needs_fix = False

            # Check if subdomain is None or empty
            if not school.subdomain and not school.domain:
                needs_fix = True

                # Generate proper code if needed
                if not school.code or school.code in ['', 'None']:
                    words = school.name.replace('.', '').split()
                    meaningful_words = [word for word in words if len(
                        word) > 1 or word.upper() in ['I', 'A']]
                    school.code = ''.join([word[0].upper()
                                          for word in meaningful_words[:3]])

                    if len(school.code) < 2:
                        first_word = words[0].replace(
                            '.', '') if words else 'SCH'
                        school.code = first_word[:3].upper()

                # Generate subdomain from clean code
                clean_code = ''.join(
                    c for c in school.code if c.isalnum()).lower()
                school.subdomain = clean_code if clean_code else 'school'

                school.save()

                self.stdout.write(
                    self.style.SUCCESS(
                        f'✓ Fixed {school.name}: Code={school.code}, Subdomain={school.subdomain}'
                    )
                )
                self.stdout.write(
                    self.style.SUCCESS(f'  Login URL: {school.get_login_url}')
                )
                schools_fixed += 1

        if schools_fixed == 0:
            self.stdout.write(
                self.style.SUCCESS(
                    '✓ All schools have valid domains/subdomains')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f'✓ Fixed {schools_fixed} school(s)')
            )
