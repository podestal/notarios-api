import logging

from django.db.models.signals import post_delete, post_save, pre_delete, pre_save

from audit.services import enqueue_instance_change, snapshot_instance, snapshot_row

logger = logging.getLogger(__name__)

_CONNECTED = False


def audited_models():
    from notaria.models import (
        Cliente,
        Cliente2,
        Contratantes,
        DetalleActosKardex,
        Detallebienes,
        Detallemediopago,
        Detallevehicular,
        Formulario,
        Kardex,
        Patrimonial,
        Predios,
        Renta,
        Representantes,
    )

    return (
        Kardex,
        DetalleActosKardex,
        Contratantes,
        Cliente2,
        Cliente,
        Representantes,
        Patrimonial,
        Detallebienes,
        Detallemediopago,
        Detallevehicular,
        Predios,
        Renta,
        Formulario,
    )


def _field_names(sender) -> list:
    return [field.attname for field in sender._meta.concrete_fields]


def _cache_old(instance, sender) -> None:
    try:
        pk = instance.pk
        if not pk:
            instance._kardex_audit_old = None
            return
        pk_name = sender._meta.pk.attname
        row = sender.objects.filter(pk=pk).values(*_field_names(sender)).first()
        instance._kardex_audit_old = snapshot_row(row, pk_name)
    except Exception:
        instance._kardex_audit_old = None


def kardex_audit_pre_save(sender, instance, raw=False, **kwargs):
    if raw:
        return
    _cache_old(instance, sender)


def kardex_audit_post_save(sender, instance, created, raw=False, update_fields=None, **kwargs):
    if raw:
        return
    old = getattr(instance, "_kardex_audit_old", None)
    new = snapshot_instance(instance)
    action = "create" if created or old is None else "update"
    enqueue_instance_change(
        instance,
        action=action,
        old=old,
        new=new,
        update_fields=update_fields,
    )


def kardex_audit_pre_delete(sender, instance, **kwargs):
    try:
        instance._kardex_audit_old = snapshot_instance(instance)
    except Exception:
        instance._kardex_audit_old = None


def kardex_audit_post_delete(sender, instance, **kwargs):
    old = getattr(instance, "_kardex_audit_old", None) or snapshot_instance(instance)
    enqueue_instance_change(instance, action="delete", old=old, new=None)


def connect_signals() -> None:
    global _CONNECTED
    if _CONNECTED:
        return
    for model in audited_models():
        table = model._meta.db_table
        pre_save.connect(
            kardex_audit_pre_save,
            sender=model,
            dispatch_uid=f"audit.pre_save.{table}",
        )
        post_save.connect(
            kardex_audit_post_save,
            sender=model,
            dispatch_uid=f"audit.post_save.{table}",
        )
        pre_delete.connect(
            kardex_audit_pre_delete,
            sender=model,
            dispatch_uid=f"audit.pre_delete.{table}",
        )
        post_delete.connect(
            kardex_audit_post_delete,
            sender=model,
            dispatch_uid=f"audit.post_delete.{table}",
        )
    _CONNECTED = True
