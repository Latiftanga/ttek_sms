import time
from django.core.management.base import BaseCommand
from django.db import connections
from django.db.utils import OperationalError
from psycopg2 import OperationalError as Psycopg2OpError


class Command(BaseCommand):
    help = 'Wait for database to be available'

    def add_arguments(self, parser):
        parser.add_argument(
            '--timeout',
            type=int,
            default=60,
            help='Maximum time to wait in seconds (default: 60)'
        )
        parser.add_argument(
            '--interval',
            type=int,
            default=1,
            help='Seconds between retry attempts (default: 1)'
        )

    def handle(self, *args, **options):
        timeout = options['timeout']
        interval = options['interval']
        
        self.stdout.write('⏳ Waiting for database to be available...')
        
        db_conn = None
        start_time = time.time()
        attempts = 0
        
        while not db_conn:
            try:
                attempts += 1
                elapsed = int(time.time() - start_time)
                
                # Try to get database connection
                db_conn = connections['default']
                
                # Actually execute a query to ensure database is ready
                with db_conn.cursor() as cursor:
                    cursor.execute('SELECT 1')
                
                # If we get here, database is ready!
                self.stdout.write(
                    self.style.SUCCESS(
                        f'✅ Database available! (took {elapsed}s, {attempts} attempts)'
                    )
                )
                return
                
            except (OperationalError, Psycopg2OpError) as e:
                # Check if we've exceeded timeout
                if elapsed >= timeout:
                    self.stdout.write(
                        self.style.ERROR(
                            f'❌ Database connection timeout after {timeout}s ({attempts} attempts)'
                        )
                    )
                    self.stdout.write(
                        self.style.ERROR(f'Last error: {str(e)}')
                    )
                    raise
                
                # Show progress with dots
                dots = '.' * (attempts % 4)
                self.stdout.write(
                    f'   Database unavailable{dots:<3} '
                    f'(attempt {attempts}, {elapsed}s/{timeout}s)',
                    ending='\r'
                )
                self.stdout.flush()
                
                # Wait before retrying
                time.sleep(interval)
                
                # Close the connection to try fresh next time
                try:
                    connections['default'].close()
                except Exception:
                    pass