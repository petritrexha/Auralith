from django.core.management.base import BaseCommand, CommandError

from core.services.accounts import create_member


class Command(BaseCommand):
    help = "Create a LearnLoop account (admin-only signup). Prints the temp password and plugin token once."

    def add_arguments(self, parser):
        parser.add_argument("email")
        parser.add_argument("--name", default="")
        parser.add_argument("--admin", action="store_true")
        parser.add_argument("--password", default=None, help="Default: auto-generated temp password")
        parser.add_argument("--skill", choices=["beginner", "intermediate"], default="beginner")
        parser.add_argument("--no-force-change", action="store_true", help="Don't force a password change at first login")

    def handle(self, *args, **opts):
        try:
            user, password, token = create_member(
                email=opts["email"], full_name=opts["name"], is_admin=opts["admin"], password=opts["password"],
                skill_level=opts["skill"], must_change_password=not opts["no_force_change"],
            )
        except ValueError as exc:
            raise CommandError(str(exc))
        self.stdout.write(self.style.SUCCESS(f"Created {'admin' if user.is_staff else 'member'} {user.email}"))
        self.stdout.write(f"  password: {password}")
        self.stdout.write(f"  token:    {token}")
