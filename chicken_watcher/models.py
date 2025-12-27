from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db.models import Q, F, CheckConstraint


class Chicken(models.Model):
    name = models.CharField(max_length=200)
    date_of_birth = models.DateField()
    date_of_death = models.DateField(null=True, blank=True)
    tag_string = models.CharField(max_length=200)

    def __str__(self):
        return self.name


class NestingBox(models.Model):
    name = models.CharField(max_length=200)

    def __str__(self):
        return self.name


class Egg(models.Model):
    chicken = models.ForeignKey(Chicken, on_delete=models.CASCADE)
    nesting_box = models.ForeignKey(NestingBox, on_delete=models.CASCADE)
    laid_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.chicken.name}, at {self.laid_at}"


class NestingBoxVisit(models.Model):
    chicken = models.ForeignKey(Chicken, on_delete=models.CASCADE)
    nesting_box = models.ForeignKey(NestingBox, on_delete=models.CASCADE)
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField(default=timezone.now)

    def clean(self):
        super().clean()  # keep built-in checks
        if self.started_at and self.ended_at and self.started_at > self.ended_at:
            raise ValidationError(
                {"ended_at": "ended_at must be later than started_at."}
            )

    class Meta:
        constraints = [
            CheckConstraint(
                condition=Q(started_at__lte=F("ended_at")),
                name="started_before_ended",
            )
        ]

    def __str__(self):
        return f"{self.chicken.name}, at {self.started_at}"
