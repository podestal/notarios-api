from django.test import SimpleTestCase

from compliance.services.sisgen_sent_filter import (
    is_kardex_sent_to_sisgen,
    partition_kardex_by_sisgen_sent,
    sisgen_estado_code,
)


class SisgenSentFilterTests(SimpleTestCase):
    def test_sent_estados(self):
        self.assertTrue(is_kardex_sent_to_sisgen(1))
        self.assertTrue(is_kardex_sent_to_sisgen(2))
        self.assertTrue(is_kardex_sent_to_sisgen("1"))
        self.assertFalse(is_kardex_sent_to_sisgen(0))
        self.assertFalse(is_kardex_sent_to_sisgen(3))
        self.assertFalse(is_kardex_sent_to_sisgen(None))

    def test_partition(self):
        class Row:
            def __init__(self, estado):
                self.estado_sisgen = estado

        eligible, sent = partition_kardex_by_sisgen_sent(
            [Row(0), Row(1), Row(2), Row(3)]
        )
        self.assertEqual(len(eligible), 2)
        self.assertEqual(len(sent), 2)
        self.assertEqual(sisgen_estado_code(None), 0)
