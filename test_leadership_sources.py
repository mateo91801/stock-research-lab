"""Regression tests for conservative SEC management-source extraction."""
import unittest
from leadership_sources import (
    extract_ceo_signature, extract_ceo_certification, _certification_documents
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


if __name__ == "__main__":
    unittest.main()
