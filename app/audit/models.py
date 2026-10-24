from django.db import models


class KardexChangeLog(models.Model):
    ACTION_CREATE = "create"
    ACTION_UPDATE = "update"
    ACTION_DELETE = "delete"
    ACTION_CHOICES = (
        (ACTION_CREATE, "Created"),
        (ACTION_UPDATE, "Updated"),
        (ACTION_DELETE, "Deleted"),
    )

    kardex = models.CharField(max_length=30, db_index=True, blank=True, default="")
    idkardex = models.IntegerField(blank=True, null=True, db_index=True)
    table_name = models.CharField(max_length=64, db_index=True)
    record_pk = models.CharField(max_length=64, blank=True, default="")
    action = models.CharField(max_length=16, choices=ACTION_CHOICES)
    changes = models.JSONField(default=dict, blank=True)
    user_id = models.IntegerField(blank=True, null=True, db_index=True)
    username = models.CharField(max_length=150, blank=True, default="")
    source = models.CharField(max_length=200, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = True
        db_table = "kardex_change_logs"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["kardex", "-created_at"]),
            models.Index(fields=["table_name", "-created_at"]),
            models.Index(fields=["user_id", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.kardex} {self.table_name} {self.action} {self.record_pk}"
