"""Regression tests for conservative SEC management-source extraction."""
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
import requests
from leadership_sources import (
    extract_ceo_signature, extract_ceo_certification, _certification_documents,
    sec_ceo_from_recent_filing_diagnostic
)


class LeadershipTests(unittest.TestCase):
    def test_signed_filing_ceo(self):
        filing = """<html><body><p>/s/ Jane A. Doe</p>
        <p>Jane A. Doe</p><p>Chief Executive Officer</p></body></html>"""
        self.assertEqual(extract_ceo_signature(filing)["name"], "Jane A. Doe")

    def test_certification_ceo(self):
        exhibit = """<html><body><p>EXHIBIT 31.1</p>
        <p>I, Jane A. Doe, certify that:</p>
        <p>1. I have reviewed this quarterly report.</p>
        <p>/s/ Jane A. Doe</p><p>Jane A. Doe</p>
        <p>Chief Executive Officer</p></body></html>"""
        self.assertEqual(extract_ceo_certification(exhibit)["name"], "Jane A. Doe")

    def test_certification_requires_signature(self):
        exhibit = """<p>I, Jane A. Doe, certify that this report is accurate.</p>
        <p>Chief Executive Officer</p><p>/s/ Mark Other</p>"""
        self.assertEqual(extract_ceo_certification(exhibit), {})

    def test_certification_requires_ceo_title(self):
        exhibit = """<p>I, John Smith, certify that:</p>
        <p>/s/ John Smith</p><p>Chief Financial Officer</p>"""
        self.assertEqual(extract_ceo_certification(exhibit), {})

    def test_conflicting_certifiers_are_not_guessed(self):
        exhibit = """<p>I, Jane A. Doe, certify that:</p>
        <p>/s/ Jane A. Doe</p><p>Chief Executive Officer</p>
        <p>I, John Smith, certify that:</p><p>/s/ John Smith</p>"""
        self.assertEqual(extract_ceo_certification(exhibit), {})

    def test_exhibit_filename_filter(self):
        directory = {"directory": {"item": [
            {"name": "abc-ex31_1.htm"}, {"name": "financials.htm"},
            {"name": "../not-allowed.htm"}, {"name": "ex31_2.htm"}]}}
        self.assertEqual(_certification_documents(directory),
                         ["abc-ex31_1.htm", "ex31_2.htm"])



class LookupDiagnosticTests(unittest.TestCase):
    def _submissions(self):
        return {'filings': {'recent': {
            'form': ['10-Q'],
            'accessionNumber': ['0000000001-26-000001'],
            'primaryDocument': ['sample.htm'],
            'filingDate': [datetime.now(timezone.utc).strftime('%Y-%m-%d')]
        }}}

    def test_missing_sec_contact_has_explanation(self):
        record, status = sec_ceo_from_recent_filing_diagnostic('MSFT', '')
        self.assertEqual(record, {})
        self.assertIn('SEC_USER_AGENT', status)

    @patch('sec_fundamentals.sec_cik', return_value=123)
    @patch('leadership_sources._sec_get')
    def test_signed_ceo_returns_source_and_date(self, get, _cik):
        get.side_effect = [self._submissions(),
                           '<p>/s/ Jane A. Doe</p><p>Jane A. Doe</p><p>Chief Executive Officer</p>']
        record, status = sec_ceo_from_recent_filing_diagnostic(
            'MSFT', 'TestApp test@example.com')
        self.assertEqual(record['name'], 'Jane A. Doe')
        self.assertEqual(record['source'], 'SEC 10-Q signed filing')
        self.assertIn('CEO verified', status)

    @patch('sec_fundamentals.sec_cik', return_value=123)
    @patch('leadership_sources._sec_get')
    def test_unavailable_sec_submissions_reports_network_failure(self, get, _cik):
        get.side_effect = requests.Timeout('timeout')
        record, status = sec_ceo_from_recent_filing_diagnostic(
            'MSFT', 'TestApp test@example.com')
        self.assertEqual(record, {})
        self.assertIn('timed out', status)
        self.assertNotIn('test@example.com', status)

    @patch('sec_fundamentals.sec_cik', return_value=123)
    @patch('leadership_sources._sec_get')
    def test_missing_certified_signatures_are_not_guessed(self, get, _cik):
        get.side_effect = [self._submissions(),
                           '<p>/s/ John Smith</p><p>Chief Financial Officer</p>',
                           {'directory': {'item': []}}]
        record, status = sec_ceo_from_recent_filing_diagnostic(
            'MSFT', 'TestApp test@example.com')
        self.assertEqual(record, {})
        self.assertIn('no unambiguous CEO signature', status)

if __name__ == "__main__":
    unittest.main()
