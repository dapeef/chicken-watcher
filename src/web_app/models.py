from datetime import date, datetime, timedelta

from django.db import models
from django.db.models import Exists, OuterRef
from django.utils import timezone


# ---------------------------------------------------------------------------
# Custom QuerySets / Managers
#
# Keeping these alongside the models rather than in a separate ``managers.py``
# because each queryset is tightly coupled to the fields on its model.
# ---------------------------------------------------------------------------


class ChickenQuerySet(models.QuerySet):
    """Common filters on :class:`Chicken`."""

    def alive(self) -> "ChickenQuerySet":
        """Chickens without a date of death."""
        return self.filter(date_of_death__isnull=True)

    def deceased(self) -> "ChickenQuerySet":
        """Chickens with a recorded date of death."""
        return self.filter(date_of_death__isnull=False)


class EggQuerySet(models.QuerySet):
    """Common filters on :class:`Egg`."""

    def saleable(self) -> "EggQuerySet":
        return self.filter(quality=Egg.Quality.SALEABLE)

    def edible(self) -> "EggQuerySet":
        return self.filter(quality=Egg.Quality.EDIBLE)

    def messy(self) -> "EggQuerySet":
        return self.filter(quality=Egg.Quality.MESSY)

    def laid_on(self, local_date: date) -> "EggQuerySet":
        """Eggs laid on a specific **local** date.

        Uses ``laid_at__date`` which Django evaluates in the current
        timezone (``TIME_ZONE=Europe/London``), not UTC. For "today",
        call with ``timezone.localdate()``.
        """
        return self.filter(laid_at__date=local_date)

    def laid_between(self, start: date, end: date) -> "EggQuerySet":
        """Eggs laid on local dates in the inclusive range ``[start, end]``."""
        return self.filter(laid_at__date__range=(start, end))


class NestingBoxPresencePeriodQuerySet(models.QuerySet):
    """Common filters on :class:`NestingBoxPresencePeriod`."""

    def ended_since(self, moment: datetime) -> "NestingBoxPresencePeriodQuerySet":
        """Periods whose ``ended_at`` is at or after ``moment``.

        Useful for "today's activity" queries where ``moment`` is the
        local start-of-day converted to UTC.
        """
        return self.filter(ended_at__gte=moment)

    def for_box(self, box) -> "NestingBoxPresencePeriodQuerySet":
        return self.filter(nesting_box=box)

    def overlapping(
        self, start: datetime, end: datetime
    ) -> "NestingBoxPresencePeriodQuerySet":
        """Periods that overlap the interval ``[start, end]``.

        Two intervals [a, b] and [c, d] overlap iff a <= d AND c <= b.
        """
        return self.filter(started_at__lte=end, ended_at__gte=start)


class HardwareSensorQuerySet(models.QuerySet):
    """Common filters on :class:`HardwareSensor`."""

    def online(self) -> "HardwareSensorQuerySet":
        return self.filter(is_connected=True)

    def offline(self) -> "HardwareSensorQuerySet":
        return self.filter(is_connected=False)


class NestingBoxImageQuerySet(models.QuerySet):
    """Common filters on :class:`NestingBoxImage`."""

    def far_from_events(self, window: timedelta) -> "NestingBoxImageQuerySet":
        """Images that are NOT within ``window`` of any
        NestingBoxPresencePeriod or Egg.

        Used by the prune job to delete "boring" frames (no chicken was
        there and no egg was laid nearby in time). Encapsulated here so
        the complex Exists() subquery is reusable and testable without
        reaching into the management command.
        """
        nearby_presence = NestingBoxPresencePeriod.objects.filter(
            started_at__lte=OuterRef("created_at") + window,
            ended_at__gte=OuterRef("created_at") - window,
        )
        nearby_egg = Egg.objects.filter(
            laid_at__gte=OuterRef("created_at") - window,
            laid_at__lte=OuterRef("created_at") + window,
        )
        return self.filter(~Exists(nearby_presence) & ~Exists(nearby_egg))


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class Tag(models.Model):
    rfid_string = models.CharField(max_length=200, unique=True)
    number = models.PositiveIntegerField(unique=True)

    class Meta:
        ordering = ["number"]

    def __str__(self):
        return f"Tag {self.number} ({self.rfid_string})"


class Chicken(models.Model):
    name = models.CharField(max_length=200)
    date_of_birth = models.DateField()
    date_of_death = models.DateField(null=True, blank=True)
    # A chicken may have at most one RFID tag, but tags can be reused
    # after a chicken dies. ForeignKey(+ partial unique constraint below)
    # models this better than OneToOneField, which would force tag
    # assignments to be permanent.
    tag = models.ForeignKey(
        Tag, on_delete=models.SET_NULL, null=True, blank=True, related_name="chickens"
    )

    objects = ChickenQuerySet.as_manager()

    class Meta:
        ordering = ["name"]
        constraints = [
            # Only one *live* chicken may hold a given tag.
            models.UniqueConstraint(
                fields=["tag"],
                condition=models.Q(date_of_death__isnull=True)
                & models.Q(tag__isnull=False),
                name="unique_tag_per_live_chicken",
            ),
        ]

    @property
    def age(self) -> int:
        """Age in days (till death date or today, in the project's local timezone)."""
        end = self.date_of_death or timezone.localdate()
        return (end - self.date_of_birth).days

    @property
    def is_alive(self) -> bool:
        return self.date_of_death is None

    def __str__(self):
        return self.name


class NestingBox(models.Model):
    name = models.CharField(max_length=200)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "nesting boxes"

    def __str__(self):
        return self.name.title()


class Egg(models.Model):
    class Quality(models.TextChoices):
        SALEABLE = "saleable", "Saleable"
        EDIBLE = "edible", "Edible"
        MESSY = "messy", "Messy"

    chicken = models.ForeignKey(
        Chicken, on_delete=models.SET_NULL, null=True, blank=True
    )
    nesting_box = models.ForeignKey(
        NestingBox, on_delete=models.SET_NULL, null=True, blank=True
    )
    laid_at = models.DateTimeField(default=timezone.now, db_index=True)
    quality = models.CharField(
        max_length=10,
        choices=Quality.choices,
        default=Quality.SALEABLE,
        db_index=True,
    )

    objects = EggQuerySet.as_manager()

    class Meta:
        ordering = ["-laid_at"]

    @property
    def is_saleable(self) -> bool:
        return self.quality == self.Quality.SALEABLE

    @property
    def is_edible(self) -> bool:
        return self.quality == self.Quality.EDIBLE

    @property
    def is_messy(self) -> bool:
        return self.quality == self.Quality.MESSY

    def __str__(self):
        chicken = self.chicken.name if self.chicken else "Unknown chicken"
        box = self.nesting_box.name if self.nesting_box else "unknown"
        return f"{chicken} in {box} box at {self.laid_at:%Y-%m-%d %H:%M}"


class NestingBoxPresencePeriod(models.Model):
    chicken = models.ForeignKey(Chicken, on_delete=models.CASCADE)
    nesting_box = models.ForeignKey(NestingBox, on_delete=models.CASCADE)
    started_at = models.DateTimeField(default=timezone.now, db_index=True)
    ended_at = models.DateTimeField(default=timezone.now, db_index=True)

    objects = NestingBoxPresencePeriodQuerySet.as_manager()

    class Meta:
        ordering = ["-started_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(ended_at__gte=models.F("started_at")),
                name="presence_period_started_before_ended",
            ),
        ]

    @property
    def duration(self):
        return self.ended_at - self.started_at

    def __str__(self):
        return f"{self.chicken.name} in {self.nesting_box.name} ({self.started_at} - {self.ended_at})"


class NestingBoxPresence(models.Model):
    chicken = models.ForeignKey(Chicken, on_delete=models.CASCADE)
    nesting_box = models.ForeignKey(NestingBox, on_delete=models.CASCADE)
    present_at = models.DateTimeField(default=timezone.now)
    presence_period = models.ForeignKey(
        NestingBoxPresencePeriod,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="presences",
    )
    # The sensor that triggered this individual ping (e.g. "left_a", "left_b").
    # Null for legacy records or when the sensor is not known.
    sensor_id = models.CharField(max_length=200, blank=True, default="")

    class Meta:
        ordering = ["-present_at"]

    def __str__(self):
        return (
            f"{self.chicken.name}, in {self.nesting_box.name} box at {self.present_at}"
        )


class NestingBoxImage(models.Model):
    # The current deployment uses a single overhead camera that covers
    # both nesting boxes (and some of the surrounding area), so images
    # aren't associated with a specific box. The originating camera is
    # recorded in the stored filename (`{cam_name}_{timestamp}.jpg`).
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    image = models.ImageField(upload_to="nesting_box_images")

    objects = NestingBoxImageQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Image taken at {self.created_at}"


class HardwareSensor(models.Model):
    name = models.CharField(
        max_length=100, unique=True
    )  # e.g., "left_rfid", "main_camera"
    is_connected = models.BooleanField(default=False)
    last_event_at = models.DateTimeField(
        null=True, blank=True
    )  # Last time a tag/beam was detected
    last_seen_at = models.DateTimeField(auto_now=True)  # Last heartbeat from the agent
    status_message = models.TextField(
        blank=True
    )  # Error messages (e.g., "Permission Denied")

    objects = HardwareSensorQuerySet.as_manager()

    class Meta:
        ordering = ["name"]

    def __str__(self):
        status = "Online" if self.is_connected else "Offline"
        return f"{self.name} ({status})"
