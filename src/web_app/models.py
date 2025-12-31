from datetime import date, timedelta

from django.db import models
from django.db.models import Count, ExpressionWrapper, FloatField, Value, Q
from django.utils import timezone


class ChickenQuerySet(models.QuerySet):
    """
    Extra query helpers; returned via Chicken.objects.
    """

    def with_egg_metrics(self, days: int = 30):
        """
        Adds:
          • eggs_window      – eggs laid in the last <days>
          • eggs_per_day     – avg eggs / day over that window
        """
        window_start = timezone.localtime() - timedelta(days=days)

        return self.annotate(
            eggs_window=Count("egg", filter=Q(egg__laid_at__gte=window_start)),
            eggs_per_day=ExpressionWrapper(
                Count("egg", filter=Q(egg__laid_at__gte=window_start))
                / Value(float(days)),
                output_field=FloatField(),
            ),
        )


class Chicken(models.Model):
    name = models.CharField(max_length=200)
    date_of_birth = models.DateField()
    date_of_death = models.DateField(null=True, blank=True)
    tag_string = models.CharField(max_length=200)

    objects = ChickenQuerySet.as_manager()

    @property
    def age(self) -> int:
        """Age in days (till death date or today)."""
        end = self.date_of_death or date.today()
        return (end - self.date_of_birth).days

    def __str__(self):
        return self.name


class NestingBox(models.Model):
    name = models.CharField(max_length=200)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "nesting boxes"


class Egg(models.Model):
    chicken = models.ForeignKey(Chicken, on_delete=models.CASCADE)
    nesting_box = models.ForeignKey(NestingBox, on_delete=models.CASCADE)
    laid_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.chicken.name}, at {self.laid_at}"


class NestingBoxPresence(models.Model):
    chicken = models.ForeignKey(Chicken, on_delete=models.CASCADE)
    nesting_box = models.ForeignKey(NestingBox, on_delete=models.CASCADE)
    present_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return (
            f"{self.chicken.name}, in {self.nesting_box.name} box at {self.present_at}"
        )


class NestingBoxImage(models.Model):
    created_at = models.DateTimeField(default=timezone.now)
    image = models.ImageField(upload_to="nesting_box_images")

    def __str__(self):
        return f"Image taken at {self.created_at}"
