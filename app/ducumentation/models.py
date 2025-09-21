from django.db import models
from django.utils import timezone
from django.conf import settings
import sys

class Documentogenerados(models.Model):
    observacion = models.TextField(blank=True, null=True)
    fecha = models.DateTimeField(blank=True, null=True)
    usuario = models.IntegerField(blank=True, null=True)
    ip = models.CharField(max_length=20, blank=True, null=True)
    pc = models.CharField(max_length=50, blank=True, null=True)
    tipogeneracion = models.CharField(max_length=30, blank=True, null=True)
    kardex = models.CharField(max_length=15, blank=True, null=True)
    cliente = models.CharField(max_length=255, blank=True, null=True)
    tipo_docu = models.IntegerField(blank=True, null=True)
    num_docu = models.CharField(max_length=15, blank=True, null=True)
    fecha_partest = models.CharField(max_length=15, blank=True, null=True)
    flag = models.CharField(max_length=5, blank=True, null=True)
    hora = models.CharField(max_length=20, blank=True, null=True)
    estado = models.IntegerField(blank=True, null=True)
    extension = models.CharField(max_length=10, blank=True, null=True)
    otrotipo = models.CharField(db_column='otroTipo', max_length=150, blank=True, null=True)  # Field name made lowercase.

    class Meta:
        managed = False
        db_table = 'documentogenerados'


class APIToken(models.Model):
    """Model for managing API tokens with expiration"""
    name = models.CharField(max_length=100, help_text="Token name/description")
    token_hash = models.CharField(max_length=64, unique=True, help_text="SHA256 hash of the token")
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(help_text="Token expiration date")
    is_active = models.BooleanField(default=True, help_text="Whether token is active")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, help_text="User who created the token")
    
    class Meta:
        db_table = 'api_tokens'
        verbose_name = 'API Token'
        verbose_name_plural = 'API Tokens'
        managed = False
    
    def __str__(self):
        return f"{self.name} (expires: {self.expires_at.strftime('%Y-%m-%d')})"
    
    @property
    def is_expired(self):
        """Check if token is expired"""
        return timezone.now() > self.expires_at
    
    @property
    def days_until_expiry(self):
        """Days until token expires"""
        delta = self.expires_at - timezone.now()
        return max(0, delta.days)
    
    def deactivate(self):
        """Deactivate the token"""
        self.is_active = False
        self.save()
    
    @classmethod
    def get_valid_tokens(cls):
        """Get all valid, non-expired tokens"""
        return cls.objects.filter(
            is_active=True,
            expires_at__gt=timezone.now()
        )
