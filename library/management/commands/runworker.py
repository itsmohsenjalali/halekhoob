from django.core.management.base import BaseCommand, CommandError

from library.worker import work


class Command(BaseCommand):
    help = "Run the persistent single-video downloader."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")

    def handle(self, *args, **options):
        try:
            work(once=options["once"])
        except RuntimeError as exc:
            raise CommandError(str(exc)) from exc
