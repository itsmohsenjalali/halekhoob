from django.conf import settings
from django.db import models
from django.utils import timezone


class Mood(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="moods")
    name = models.CharField("نام حس", max_length=40, )
    symbol = models.CharField(max_length=8, default="✧")
    order = models.PositiveIntegerField(default=10)

    class Meta:
        ordering = ["order", "id"]
        constraints = [models.UniqueConstraint(fields=["owner", "name"], name="mood_owner_name_unique")]

    def __str__(self):
        return self.name


class Video(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "در صف"
        DOWNLOADING = "downloading", "در حال دانلود"
        READY = "ready", "آماده"
        FAILED = "failed", "ناموفق"

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    source_key = models.CharField(max_length=160)
    source_url = models.URLField(max_length=1000)
    platform = models.CharField(max_length=20)
    title = models.CharField("عنوان", max_length=300, blank=True)
    note = models.TextField("یادداشت", max_length=3000, blank=True)
    moods = models.ManyToManyField(Mood, verbose_name="حس‌ها")
    favorite = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED)
    progress = models.PositiveSmallIntegerField(default=0)
    attempts = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField(default=timezone.now)
    error = models.CharField(max_length=500, blank=True)
    error_code = models.CharField(max_length=40, blank=True)
    file_name = models.CharField(max_length=250, blank=True)
    thumbnail_name = models.CharField(max_length=250, blank=True)
    audio_name = models.CharField(max_length=250, blank=True)
    audio_checked = models.BooleanField(default=False)
    storage_backend = models.CharField(max_length=10, default="local")
    job_token = models.UUIDField(null=True, blank=True)
    reserved_bytes = models.PositiveBigIntegerField(default=0)
    size_bytes = models.PositiveBigIntegerField(default=0)
    duration = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-favorite", "-created_at"]
        constraints = [models.UniqueConstraint(fields=["owner", "source_key"], name="video_owner_source_unique")]
        indexes = [models.Index(fields=["status", "next_attempt_at"])]

    @property
    def display_title(self):
        return self.title or "ویدیوی تازه"

    @property
    def duration_label(self):
        return f"{self.duration // 60}:{self.duration % 60:02}"

    @property
    def platform_label(self):
        return "یوتیوب" if self.platform == "youtube" else "اینستاگرام"


class LoginThrottle(models.Model):
    key = models.CharField(max_length=64, unique=True)
    failures = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField(default=timezone.now)


class WorkerLease(models.Model):
    """A fenced, renewable lease across machines; no disk lock in cloud mode."""

    name = models.CharField(max_length=30, primary_key=True)
    token = models.UUIDField(null=True)
    expires_at = models.DateTimeField(default=timezone.now)


class CloudObject(models.Model):
    """An upload journal and durable, delayed deletion queue. Keys are immutable."""

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="cloud_objects")
    key = models.CharField(max_length=250, unique=True)
    video = models.ForeignKey(Video, null=True, on_delete=models.SET_NULL)
    size_bytes = models.PositiveBigIntegerField()
    sha256 = models.CharField(max_length=64)
    state = models.CharField(max_length=12, default="pending")
    delete_after = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    attempts = models.PositiveIntegerField(default=0)
    error = models.CharField(max_length=100, blank=True)


class Account(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="archive_account")
    clerk_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    storage_limit = models.PositiveBigIntegerField(default=1_000_000_000)
    last_served_at = models.DateTimeField(null=True, blank=True)


class DailyUsage(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    day = models.DateField()
    downloads = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["owner", "day"], name="usage_owner_day_unique")]


class QuotaChange(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="quota_changes_made")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="quota_changes")
    old_limit = models.PositiveBigIntegerField()
    new_limit = models.PositiveBigIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
