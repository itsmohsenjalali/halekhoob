"""Short DB transactions and a renewable fenced lease, compatible with transaction pooling."""

import threading
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import close_old_connections, transaction
from django.utils import timezone

from .models import WorkerLease


class LeaseLost(RuntimeError):
    pass


class LeaseBusy(RuntimeError):
    pass


class Lease:
    def __init__(self):
        self.token = uuid.uuid4()
        self.finished = threading.Event()
        self.lost = threading.Event()

    def acquire(self):
        with transaction.atomic():
            WorkerLease.objects.get_or_create(name="worker")
            lease = WorkerLease.objects.select_for_update().get(name="worker")
            if lease.token and lease.expires_at > timezone.now():
                raise LeaseBusy("The worker or an archive maintenance command is running.")
            lease.token = self.token
            lease.expires_at = timezone.now() + timedelta(seconds=settings.WORKER_LEASE_SECONDS)
            lease.save()
        return self

    def check(self, locked=False):
        query = WorkerLease.objects.select_for_update() if locked else WorkerLease.objects
        if (
            self.lost.is_set()
            or not query.filter(
                name="worker", token=self.token, expires_at__gt=timezone.now()
            ).exists()
        ):
            raise LeaseLost("Worker lease expired; this attempt may no longer publish.")

    def renew(self):
        if not WorkerLease.objects.filter(
            name="worker", token=self.token, expires_at__gt=timezone.now()
        ).update(expires_at=timezone.now() + timedelta(seconds=settings.WORKER_LEASE_SECONDS)):
            self.lost.set()
            raise LeaseLost("Lease renewal failed.")

    def heartbeat(self):
        close_old_connections()
        try:
            while not self.finished.wait(settings.WORKER_LEASE_SECONDS / 4):
                try:
                    self.renew()
                except Exception:
                    self.lost.set()
                    return
        finally:
            close_old_connections()

    def __enter__(self):
        self.acquire()
        self.thread = threading.Thread(target=self.heartbeat, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.finished.set()
        self.thread.join(timeout=15)
        WorkerLease.objects.filter(name="worker", token=self.token).update(
            token=None, expires_at=timezone.now()
        )
