"""Internal archive accounts; identity is always provided by verified Clerk tokens."""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Account, Mood

DEFAULT_MOODS = [
    ("امید", "◒"),
    ("شادی", "☼"),
    ("آرامش", "≈"),
    ("انگیزه", "↗"),
    ("اعتمادبه‌نفس", "◇"),
    ("انرژی", "✳"),
]


def ensure_account(user):
    account, created = Account.objects.get_or_create(
        user=user,
        defaults={
            "storage_limit": settings.DEFAULT_USER_STORAGE_BYTES,
        },
    )
    if created:
        Mood.objects.bulk_create(
            [
                Mood(owner=user, name=name, symbol=symbol, order=index)
                for index, (name, symbol) in enumerate(DEFAULT_MOODS)
            ],
            ignore_conflicts=True,
        )
    return account


@receiver(post_save, sender=get_user_model())
def initialize_account(sender, instance, created, raw=False, **kwargs):
    if created and not raw:
        ensure_account(instance)


def provision_identity(subject, identity):
    User = get_user_model()
    with transaction.atomic():
        # A subject is stable. Never associate two existing users merely by email.
        account = Account.objects.select_related("user").filter(clerk_id=subject).first()
        if account:
            return account.user
        email = identity["email"].lower()
        if settings.CLERK_LEGACY_OWNER_EMAIL and email == settings.CLERK_LEGACY_OWNER_EMAIL:
            legacy = User.objects.select_for_update().filter(username="owner").first()
            if legacy:
                account = ensure_account(legacy)
                account = Account.objects.select_for_update().get(pk=account.pk)
                if account.clerk_id and account.clerk_id != subject:
                    raise ValueError("Legacy account already linked")
                account.clerk_id = subject
                account.save(update_fields=["clerk_id"])
                legacy.email = email
                legacy.first_name = identity.get("first_name", "")[:150]
                legacy.set_unusable_password()
                legacy.save(update_fields=["email", "first_name", "password"])
                return legacy
        # The deterministic username plus unique Clerk ID makes concurrent first requests safe.
        user, created = User.objects.get_or_create(
            username=subject,
            defaults={
                "email": email,
                "first_name": identity.get("first_name", "")[:150],
            },
        )
        account = ensure_account(user)
        account = Account.objects.select_for_update().get(pk=account.pk)
        if account.clerk_id not in (None, subject):
            raise ValueError("Conflicting identity")
        if not created and account.clerk_id is None:
            raise ValueError("Unlinked existing username")
        account.clerk_id = subject
        account.save(update_fields=["clerk_id"])
        if created:
            user.set_unusable_password()
            user.save(update_fields=["password"])
        return user
