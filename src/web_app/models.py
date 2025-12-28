from django.db import models
from django.utils import timezone


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


class NestingBoxPresence(models.Model):
    chicken = models.ForeignKey(Chicken, on_delete=models.CASCADE)
    nesting_box = models.ForeignKey(NestingBox, on_delete=models.CASCADE)
    present_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return (
            f"{self.chicken.name}, in {self.nesting_box.name} box at {self.present_at}"
        )
