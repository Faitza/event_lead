from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Review(models.Model):
    name = models.CharField("nom", max_length=100)
    stars = models.PositiveIntegerField("note", validators=[MinValueValidator(1), MaxValueValidator(5)])
    text = models.TextField("avis")
    is_published = models.BooleanField("publié", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "avis"
        verbose_name_plural = "avis"

    def __str__(self):
        return f"{self.name} ({self.stars}/5)"


class ContactMessage(models.Model):
    name = models.CharField("nom", max_length=100)
    email = models.EmailField("email")
    phone = models.CharField("téléphone", max_length=30, blank=True)
    message = models.TextField("message")
    is_read = models.BooleanField("lu", default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "message de contact"
        verbose_name_plural = "messages de contact"

    def __str__(self):
        return f"{self.name} - {self.email}"
