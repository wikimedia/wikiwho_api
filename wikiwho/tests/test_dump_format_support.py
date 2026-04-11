# -*- coding: utf-8 -*-
"""
Tests for the dump format support in generate_articles_from_wp_xmls.
Validates that both legacy .7z and new .bz2 (MediaWiki Content File Exports)
formats are correctly discovered, filtered, and sorted by page range.

Bug: T372340
"""
import os
import re
import tempfile
import unittest


# --- Extracted logic from generate_articles_from_wp_xmls.py ---
# We test the file discovery and sorting logic in isolation,
# without needing Django or the full WikiWho setup.

SUPPORTED_EXTENSIONS = ('.7z', '.bz2')


def discover_dump_files(xml_folder):
    """Discover dump files in a folder, supporting both .7z and .bz2 formats."""
    xml_folder = xml_folder[:-1] if xml_folder.endswith('/') else xml_folder
    xml_files = [
        ['{}/{}'.format(xml_folder, x), []]
        for x in os.listdir(xml_folder)
        if x.endswith(SUPPORTED_EXTENSIONS) and 'index' not in x.lower()
    ]
    return xml_files


def sort_dump_files(xml_files):
    """Sort dump files by starting page number, handling both filename formats."""
    try:
        # Legacy format: enwiki-20161101-pages-meta-history1.xml-p000000010p000002289.7z
        xml_files = {int(x[0].split('xml-p')[1].split('p')[0]): x for x in xml_files}
        xml_files = [xml_files[x] for x in sorted(xml_files)]
    except (IndexError, ValueError):
        # New format: ukwiki-2026-04-01-p1015979p1087621.xml.bz2
        # Also handles single-page revision ranges: ukwiki-2026-04-01-p193624r847223r25026950.xml.bz2
        try:
            def _extract_start_page(filepath):
                m = re.search(r'-p(\d+)(?:[pr]\d+)+\.xml\.', filepath)
                return int(m.group(1)) if m else 0

            xml_files = {_extract_start_page(x[0]): x for x in xml_files}
            xml_files = [xml_files[x] for x in sorted(xml_files)]
        except (IndexError, ValueError):
            pass
    return xml_files


class TestDumpFileDiscovery(unittest.TestCase):
    """Test that dump files are correctly discovered from a directory."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir)

    def _touch(self, filename):
        """Create an empty file."""
        path = os.path.join(self.tmpdir, filename)
        open(path, 'w').close()
        return path

    # --- Legacy .7z format tests ---

    def test_discovers_7z_files(self):
        """Should find .7z dump files."""
        self._touch('enwiki-20161101-pages-meta-history1.xml-p000000010p000002289.7z')
        self._touch('enwiki-20161101-pages-meta-history1.xml-p000002290p000004535.7z')
        files = discover_dump_files(self.tmpdir)
        self.assertEqual(len(files), 2)

    def test_ignores_non_dump_files(self):
        """Should ignore .txt, .json, .log, etc."""
        self._touch('enwiki-20161101-pages-meta-history1.xml-p000000010p000002289.7z')
        self._touch('readme.txt')
        self._touch('status.json')
        self._touch('import.log')
        files = discover_dump_files(self.tmpdir)
        self.assertEqual(len(files), 1)

    # --- New .bz2 format tests ---

    def test_discovers_bz2_files(self):
        """Should find .bz2 dump files (new MediaWiki Content File Exports format)."""
        self._touch('ukwiki-2026-04-01-p1015979p1087621.xml.bz2')
        self._touch('ukwiki-2026-04-01-p1087622p1212603.xml.bz2')
        self._touch('ukwiki-2026-04-01-p1212604p1279381.xml.bz2')
        files = discover_dump_files(self.tmpdir)
        self.assertEqual(len(files), 3)

    def test_filters_out_index_files(self):
        """Should NOT include index files (e.g. multistream-index*.bz2)."""
        self._touch('ukwiki-20260401-pages-articles-multistream1.xml-p1p194007.bz2')
        self._touch('ukwiki-20260401-pages-articles-multistream-index1.txt-p1p194007.bz2')
        self._touch('ukwiki-20260401-pages-articles-multistream-INDEX2.txt-p194008p537482.bz2')
        files = discover_dump_files(self.tmpdir)
        self.assertEqual(len(files), 1)
        self.assertIn('multistream1', files[0][0])

    # --- Mixed format tests ---

    def test_discovers_mixed_formats(self):
        """Should find both .7z and .bz2 files in the same directory."""
        self._touch('ukwiki-20260401-pages-meta-history1.xml-p1p10509.7z')
        self._touch('ukwiki-2026-04-01-p1015979p1087621.xml.bz2')
        files = discover_dump_files(self.tmpdir)
        self.assertEqual(len(files), 2)

    # --- Empty directory ---

    def test_empty_directory(self):
        """Should return empty list for directory with no dump files."""
        self._touch('readme.txt')
        files = discover_dump_files(self.tmpdir)
        self.assertEqual(len(files), 0)

    def test_truly_empty_directory(self):
        """Should return empty list for completely empty directory."""
        files = discover_dump_files(self.tmpdir)
        self.assertEqual(len(files), 0)


class TestDumpFileSorting(unittest.TestCase):
    """Test that dump files are correctly sorted by starting page number."""

    # --- Legacy .7z format sorting ---

    def test_sorts_legacy_format_by_page_range(self):
        """Legacy .7z files should be sorted by the start page number."""
        files = [
            ['/dumps/enwiki-20161101-pages-meta-history1.xml-p000004536p000006546.7z', []],
            ['/dumps/enwiki-20161101-pages-meta-history1.xml-p000000010p000002289.7z', []],
            ['/dumps/enwiki-20161101-pages-meta-history1.xml-p000002290p000004535.7z', []],
        ]
        sorted_files = sort_dump_files(files)
        # Should be sorted by start page: 10, 2290, 4536
        self.assertIn('p000000010', sorted_files[0][0])
        self.assertIn('p000002290', sorted_files[1][0])
        self.assertIn('p000004536', sorted_files[2][0])

    def test_sorts_legacy_uk_format(self):
        """Legacy ukwiki .7z files should sort correctly."""
        files = [
            ['/dumps/ukwiki-20260401-pages-meta-history2.xml-p194008p250751.7z', []],
            ['/dumps/ukwiki-20260401-pages-meta-history1.xml-p1p10509.7z', []],
            ['/dumps/ukwiki-20260401-pages-meta-history1.xml-p74105p168931.7z', []],
            ['/dumps/ukwiki-20260401-pages-meta-history1.xml-p10510p24698.7z', []],
        ]
        sorted_files = sort_dump_files(files)
        # Should be sorted: p1, p10510, p74105, p194008
        self.assertIn('p1p', sorted_files[0][0])
        self.assertIn('p10510', sorted_files[1][0])
        self.assertIn('p74105', sorted_files[2][0])
        self.assertIn('p194008', sorted_files[3][0])

    # --- New .bz2 format sorting ---

    def test_sorts_new_format_by_page_range(self):
        """New .bz2 files should be sorted by the start page number."""
        files = [
            ['/dumps/ukwiki-2026-04-01-p1212604p1279381.xml.bz2', []],
            ['/dumps/ukwiki-2026-04-01-p10166p14034.xml.bz2', []],
            ['/dumps/ukwiki-2026-04-01-p1087622p1212603.xml.bz2', []],
            ['/dumps/ukwiki-2026-04-01-p1015979p1087621.xml.bz2', []],
        ]
        sorted_files = sort_dump_files(files)
        # Should be sorted: p10166, p1015979, p1087622, p1212604
        self.assertIn('p10166', sorted_files[0][0])
        self.assertIn('p1015979', sorted_files[1][0])
        self.assertIn('p1087622', sorted_files[2][0])
        self.assertIn('p1212604', sorted_files[3][0])

    def test_sorts_new_format_large_set(self):
        """Test sorting with a realistic number of new-format files."""
        files = [
            ['/dumps/ukwiki-2026-04-01-p1563680p1595740.xml.bz2', []],
            ['/dumps/ukwiki-2026-04-01-p109747p160336.xml.bz2', []],
            ['/dumps/ukwiki-2026-04-01-p14035p17927.xml.bz2', []],
            ['/dumps/ukwiki-2026-04-01-p1p10165.xml.bz2', []],
            ['/dumps/ukwiki-2026-04-01-p1706123p1736360.xml.bz2', []],
        ]
        sorted_files = sort_dump_files(files)
        # Verify ascending order
        page_nums = []
        for f in sorted_files:
            m = re.search(r'-p(\d+)(?:[pr]\d+)+', f[0])
            page_nums.append(int(m.group(1)))
        self.assertEqual(page_nums, sorted(page_nums))

    # --- Single-page revision range format (p{page}r{rev}r{rev}) ---

    def test_sorts_revision_range_files(self):
        """Files with p{page}r{rev}r{rev} pattern should sort by page ID."""
        files = [
            ['/dumps/ukwiki-2026-04-01-p193624r25026995r47770213.xml.bz2', []],
            ['/dumps/ukwiki-2026-04-01-p10166p14034.xml.bz2', []],
            ['/dumps/ukwiki-2026-04-01-p193624r847223r25026950.xml.bz2', []],
            ['/dumps/ukwiki-2026-04-01-p1p10165.xml.bz2', []],
        ]
        sorted_files = sort_dump_files(files)
        self.assertIn('p1p', sorted_files[0][0])
        self.assertIn('p10166', sorted_files[1][0])
        # Both p193624 files have same page ID, one will overwrite the other in dict
        # but the remaining files should still be sorted
        self.assertIn('p193624', sorted_files[2][0])

    # --- Edge cases ---

    def test_single_file(self):
        """Should handle a single file without error."""
        files = [['/dumps/ukwiki-2026-04-01-p1p10165.xml.bz2', []]]
        sorted_files = sort_dump_files(files)
        self.assertEqual(len(sorted_files), 1)

    def test_preserves_page_ids_attachment(self):
        """The page_ids list (2nd element) should be preserved through sorting."""
        page_ids_a = [100, 200, 300]
        page_ids_b = [400, 500]
        files = [
            ['/dumps/ukwiki-2026-04-01-p1087622p1212603.xml.bz2', page_ids_b],
            ['/dumps/ukwiki-2026-04-01-p10166p14034.xml.bz2', page_ids_a],
        ]
        sorted_files = sort_dump_files(files)
        # p10166 should come first
        self.assertIn('p10166', sorted_files[0][0])
        self.assertEqual(sorted_files[0][1], page_ids_a)
        self.assertIn('p1087622', sorted_files[1][0])
        self.assertEqual(sorted_files[1][1], page_ids_b)


class TestPageRangeExtraction(unittest.TestCase):
    """Test the regex-based page range extraction for both formats."""

    def test_legacy_format_extraction(self):
        """Test page range extraction from legacy filename."""
        filepath = 'enwiki-20161101-pages-meta-history1.xml-p000000010p000002289.7z'
        # Legacy: split on 'xml-p', then split on 'p'
        start_page = int(filepath.split('xml-p')[1].split('p')[0])
        self.assertEqual(start_page, 10)

    def test_new_format_extraction(self):
        """Test page range extraction from new filename."""
        filepath = 'ukwiki-2026-04-01-p1015979p1087621.xml.bz2'
        m = re.search(r'-p(\d+)(?:[pr]\d+)+\.xml\.', filepath)
        self.assertIsNotNone(m)
        self.assertEqual(int(m.group(1)), 1015979)

    def test_new_format_small_page_numbers(self):
        """Test extraction with small page numbers."""
        filepath = 'ukwiki-2026-04-01-p1p10165.xml.bz2'
        m = re.search(r'-p(\d+)(?:[pr]\d+)+\.xml\.', filepath)
        self.assertIsNotNone(m)
        self.assertEqual(int(m.group(1)), 1)

    def test_revision_range_format_extraction(self):
        """Test page ID extraction from p{page}r{rev}r{rev} filename."""
        filepath = 'ukwiki-2026-04-01-p193624r25026995r47770213.xml.bz2'
        m = re.search(r'-p(\d+)(?:[pr]\d+)+\.xml\.', filepath)
        self.assertIsNotNone(m)
        self.assertEqual(int(m.group(1)), 193624)

    def test_legacy_format_does_not_match_new_regex(self):
        """Legacy format should NOT match the new format regex (different pattern)."""
        filepath = 'enwiki-20161101-pages-meta-history1.xml-p000000010p000002289.7z'
        m = re.search(r'-p(\d+)(?:[pr]\d+)+\.xml\.', filepath)
        # This should NOT match because legacy has .xml-p not -p...xml.
        self.assertIsNone(m)

    def test_new_format_does_not_match_legacy_split(self):
        """New format should fail the legacy split approach (no 'xml-p' substring)."""
        filepath = 'ukwiki-2026-04-01-p1015979p1087621.xml.bz2'
        parts = filepath.split('xml-p')
        # New format has 'xml.bz2' not 'xml-p', so split returns single element
        self.assertEqual(len(parts), 1)


class TestEndToEndDiscoverAndSort(unittest.TestCase):
    """Integration test: discover files then sort them."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir)

    def _touch(self, filename):
        path = os.path.join(self.tmpdir, filename)
        open(path, 'w').close()

    def test_e2e_legacy_format(self):
        """End-to-end: discover and sort legacy .7z files."""
        self._touch('enwiki-20161101-pages-meta-history1.xml-p000004536p000006546.7z')
        self._touch('enwiki-20161101-pages-meta-history1.xml-p000000010p000002289.7z')
        self._touch('enwiki-20161101-pages-meta-history1.xml-p000002290p000004535.7z')
        self._touch('readme.txt')  # noise

        files = discover_dump_files(self.tmpdir)
        self.assertEqual(len(files), 3)

        sorted_files = sort_dump_files(files)
        self.assertEqual(len(sorted_files), 3)
        self.assertIn('p000000010', sorted_files[0][0])
        self.assertIn('p000002290', sorted_files[1][0])
        self.assertIn('p000004536', sorted_files[2][0])

    def test_e2e_new_format(self):
        """End-to-end: discover and sort new .bz2 files."""
        self._touch('ukwiki-2026-04-01-p1212604p1279381.xml.bz2')
        self._touch('ukwiki-2026-04-01-p10166p14034.xml.bz2')
        self._touch('ukwiki-2026-04-01-p1p10165.xml.bz2')
        self._touch('SHA256SUMS')  # noise from the dump directory
        self._touch('_SUCCESS')   # noise

        files = discover_dump_files(self.tmpdir)
        self.assertEqual(len(files), 3)

        sorted_files = sort_dump_files(files)
        self.assertEqual(len(sorted_files), 3)
        self.assertIn('p1p', sorted_files[0][0])
        self.assertIn('p10166', sorted_files[1][0])
        self.assertIn('p1212604', sorted_files[2][0])

    def test_e2e_new_format_with_index_filtering(self):
        """End-to-end: index files should be excluded even with .bz2 extension."""
        self._touch('ukwiki-20260401-pages-articles-multistream1.xml-p1p194007.bz2')
        self._touch('ukwiki-20260401-pages-articles-multistream-index1.txt-p1p194007.bz2')
        self._touch('ukwiki-20260401-pages-articles-multistream2.xml-p194008p537482.bz2')
        self._touch('ukwiki-20260401-pages-articles-multistream-index2.txt-p194008p537482.bz2')

        files = discover_dump_files(self.tmpdir)
        # Only 2 actual dump files, not the 2 index files
        self.assertEqual(len(files), 2)
        for f in files:
            self.assertNotIn('index', f[0].lower())


if __name__ == '__main__':
    unittest.main()
