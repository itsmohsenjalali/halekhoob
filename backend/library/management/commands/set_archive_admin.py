from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Explicitly grant staff access to an existing, linked Clerk account."

    def add_arguments(self, parser):
        parser.add_argument("email")

    def handle(self, *args, **options):
        users = get_user_model().objects.filter(
            email__iexact=options["email"], is_active=True, archive_account__clerk_id__isnull=False
        )
        if users.count() != 1:
            raise CommandError("Expected exactly one active, linked account.")
        users.update(is_staff=True)
        self.stdout.write("Admin access granted to the selected account.")
