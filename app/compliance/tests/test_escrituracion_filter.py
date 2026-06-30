from django.test import SimpleTestCase

from compliance.services.escrituracion_filter import (
    has_escrituracion_info,
    partition_kardex_by_escrituracion,
)


class EscrituracionFilterTests(SimpleTestCase):
    def test_has_escrituracion_info(self):
        class Row:
            def __init__(self, numescritura):
                self.numescritura = numescritura

        self.assertTrue(has_escrituracion_info(Row("1234")))
        self.assertTrue(has_escrituracion_info(Row("  99  ")))
        self.assertFalse(has_escrituracion_info(Row("")))
        self.assertFalse(has_escrituracion_info(Row("   ")))
        self.assertFalse(has_escrituracion_info(Row(None)))

    def test_partition(self):
        class Row:
            def __init__(self, numescritura):
                self.numescritura = numescritura

        ready, pending = partition_kardex_by_escrituracion(
            [Row("10"), Row(""), Row(None), Row("11")]
        )
        self.assertEqual(len(ready), 2)
        self.assertEqual(len(pending), 2)
