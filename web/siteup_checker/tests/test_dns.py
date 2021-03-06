import logging
logger = logging.getLogger("debugging")

from django.test import TestCase

from siteup_checker import monitoring


class TestDns(TestCase):

    def test_wrong_record_type(self):
        res = monitoring.check_dns('bad', 'BAD', '1.1.1.1')
        self.assertFalse(res['valid'])

    def test_wrong_host(self):
        res = monitoring.check_dns('josetomasitotocinote.com', 'A', '1.1.1.1')
        self.assertFalse(res['valid'])

    def test_wrong_resolved_address(self):
        res = monitoring.check_dns('josetomastocino.com', 'A', '1.1.1.1')
        self.assertTrue(res['valid'])
        self.assertFalse(res['status_ok'])

    def test_valid(self):
        res = monitoring.check_dns('josetomastocino.com', 'A', '78.47.140.228')
        self.assertTrue(res['valid'])
        self.assertTrue(res['status_ok'])

    def test_no_register(self):
        res = monitoring.check_dns('josetomastocino.com', 'AAAA', '78.47.140.228')
        self.assertFalse(res['valid'])
