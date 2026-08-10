"""
Read-only diagnostic for attendance-percentage/total_school_days mismatches
on report cards - e.g. a term shows fewer total school days than were
actually recorded, because the term's date range, per-term school_days
override, or SchoolHoliday entries are undercounting relative to what
attendance was actually taken on.

Makes no writes - every query below is a plain .filter()/.count()/read.

Usage:
    python manage.py diagnose_attendance --schema=<tenant> --term-number 3
    python manage.py diagnose_attendance --schema=<tenant> --term-id <uuid>
    python manage.py diagnose_attendance --schema=<tenant> --term-number 3 --class-name "JHS 3A"
"""
import datetime

from django.core.management.base import BaseCommand
from django_tenants.utils import schema_context


class Command(BaseCommand):
    help = 'Diagnose why a term\'s report-card attendance total looks wrong (read-only)'

    def add_arguments(self, parser):
        parser.add_argument('--schema', type=str, required=True, help='Tenant schema name')
        parser.add_argument(
            '--term-number', type=int,
            help='Term number to inspect (e.g. 3 for Third Term) - picks the most recent match'
        )
        parser.add_argument('--term-id', type=str, help='Term UUID - takes priority over --term-number')
        parser.add_argument('--class-name', type=str, help='Limit the per-class section to one class')

    def handle(self, *args, **options):
        with schema_context(options['schema']):
            self._run(options)

    def _run(self, options):
        from academics.models import AttendanceSession, Class
        from core.models import SchoolHoliday, SchoolSettings, Term
        from core.utils import get_valid_school_days

        w = self.stdout.write

        w('=' * 70)
        w(f"TENANT: {options['schema']}")
        w('=' * 70)

        settings_obj = SchoolSettings.load()
        w(
            f'\nSchoolSettings.school_days (global default): '
            f'{settings_obj.school_days!r} -> weekdays {sorted(settings_obj.school_days_set)}'
        )
        w(f'SchoolSettings.allow_past_term_attendance: {settings_obj.allow_past_term_attendance}')

        w('\n--- All terms (for context) ---')
        for t in Term.objects.select_related('academic_year').order_by(
            'academic_year__start_date', 'term_number'
        ):
            w(
                f'  [{t.term_number}] {t.name} ({t.academic_year.name}) '
                f'{t.start_date} -> {t.end_date}  is_current={t.is_current}  '
                f'school_days={t.school_days!r}'
            )

        if options.get('term_id'):
            term = Term.objects.filter(pk=options['term_id']).first()
        elif options.get('term_number'):
            term = Term.objects.filter(term_number=options['term_number']).order_by('-start_date').first()
        else:
            term = Term.get_current()

        if not term:
            self.stderr.write(
                '\nCould not find the target term - pass --term-id explicitly and re-run.'
            )
            return

        w('\n' + '=' * 70)
        w(f'TARGET TERM: {term.name}  ({term.start_date} -> {term.end_date})')
        w('=' * 70)
        w(f'term.school_days (raw): {term.school_days!r}')
        w(f'effective school_days_set: {sorted(term.school_days_set)}  (1=Mon .. 7=Sun)')

        valid_days = get_valid_school_days(term.start_date, term.end_date, term=term)
        w(f'\nget_valid_school_days(term.start_date, term.end_date) -> {len(valid_days)} days')
        if valid_days:
            w(f'  first 5: {valid_days[:5]}')
            w(f'  last 5:  {valid_days[-5:]}')

        all_days = [
            term.start_date + datetime.timedelta(days=i)
            for i in range((term.end_date - term.start_date).days + 1)
        ]
        holidays_in_range = [
            h for h in SchoolHoliday.objects.all()
            if term.start_date <= h.date <= term.end_date
            or (h.recurring_annually and any(
                d.month == h.date.month and d.day == h.date.day for d in all_days
            ))
        ]
        w(f'\nSchoolHoliday entries falling inside the term range: {len(holidays_in_range)}')
        for h in holidays_in_range:
            w(f'  {h.date}  {h.name}  recurring={h.recurring_annually}')

        total_calendar_days = len(all_days)
        weekday_matches = sum(1 for d in all_days if d.isoweekday() in term.school_days_set)
        w(f'\nCalendar days in term: {total_calendar_days}')
        w(f'Days matching school_days_set (before holiday subtraction): {weekday_matches}')
        w(
            f'  -> {weekday_matches} minus {len(holidays_in_range)} holiday(s) should roughly '
            f'equal the {len(valid_days)} from get_valid_school_days above (small differences '
            f'are fine if a holiday landed on a non-school-day already).'
        )

        w('\n' + '-' * 70)
        w('Per-class actual recorded attendance vs. the valid_days window above')
        w('-' * 70)

        classes = Class.objects.filter(is_active=True)
        if options.get('class_name'):
            classes = classes.filter(name=options['class_name'])
            if not classes.exists():
                self.stderr.write(f"  Class \"{options['class_name']}\" not found.")

        valid_set = set(valid_days)

        for klass in classes.order_by('name'):
            recorded_dates = set(
                AttendanceSession.objects.filter(
                    class_assigned=klass,
                    date__gte=term.start_date,
                    date__lte=term.end_date,
                    records__isnull=False,
                ).values_list('date', flat=True).distinct()
            )
            if not recorded_dates:
                continue
            outside_valid = sorted(d for d in recorded_dates if d not in valid_set)
            w(f'\n{klass.name} (attendance_type={klass.attendance_type}):')
            w(f'  distinct dates with real attendance recorded: {len(recorded_dates)}')
            w(f'  of those, INSIDE the valid_days window:  {len(recorded_dates & valid_set)}')
            w(f'  of those, OUTSIDE the valid_days window: {len(outside_valid)}')
            if outside_valid:
                w('    -> these real attendance dates are NOT being counted on report cards:')
                for d in outside_valid[:15]:
                    weekday_ok = d.isoweekday() in term.school_days_set
                    holiday_name = SchoolHoliday.get_holiday_name(d)
                    reason = (
                        'holiday: ' + holiday_name if holiday_name
                        else 'weekday not in school_days_set' if not weekday_ok
                        else 'outside term start/end range'
                    )
                    w(f'       {d} ({d.strftime("%A")})  reason: {reason}')
                if len(outside_valid) > 15:
                    w(f'       ... and {len(outside_valid) - 15} more')

        w('\nDone.')
