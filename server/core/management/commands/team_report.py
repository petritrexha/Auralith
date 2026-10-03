from django.core.management.base import BaseCommand

from core.agent.reporter import generate_report


class Command(BaseCommand):
    help = "Run the manager agent and save a team comprehension briefing (schedule weekly with cron / Task Scheduler)."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=7)

    def handle(self, *args, **opts):
        report = generate_report(days=opts["days"])
        self.stdout.write(self.style.SUCCESS(f"[{report.mode}] {report.title}"))
        self.stdout.write(report.body_markdown)
