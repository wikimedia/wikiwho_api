# -*- coding: utf-8 -*-
"""Tests for utils_pickles subdirectory structure and gzip compression.

Related: T414087 (subdirectory structure)
         T414075 (gzip compression)
"""
import gzip
import os
import pickle
import tempfile
import unittest
from unittest.mock import patch


class TestGetPicklePath(unittest.TestCase):
    """Test get_pickle_path subdirectory calculation."""

    def _call(self, page_id, folder='/cache/en'):
        from api.utils_pickles import get_pickle_path
        with patch('api.utils_pickles.get_pickle_folder', return_value=folder):
            return get_pickle_path(page_id)

    def test_basic_path(self):
        path = self._call(100000)
        self.assertEqual(path, '/cache/en/100000/100000.p')

    def test_same_subdirectory_for_range(self):
        # 100000-100999 all map to subdirectory 100000
        self.assertEqual(self._call(100000), '/cache/en/100000/100000.p')
        self.assertEqual(self._call(100002), '/cache/en/100000/100002.p')
        self.assertEqual(self._call(100999), '/cache/en/100000/100999.p')

    def test_different_subdirectory(self):
        self.assertEqual(self._call(200005), '/cache/en/200000/200005.p')

    def test_edge_case_zero(self):
        self.assertEqual(self._call(0), '/cache/en/0/0.p')

    def test_edge_case_999(self):
        self.assertEqual(self._call(999), '/cache/en/0/999.p')

    def test_edge_case_1000(self):
        self.assertEqual(self._call(1000), '/cache/en/1000/1000.p')

    def test_filename_is_page_id_dot_p(self):
        path = self._call(123456)
        self.assertTrue(path.endswith('/123456.p'))


class TestPickleDumpLoad(unittest.TestCase):
    """Test pickle_dump writes compressed files and pickle_load reads them."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _dump(self, obj, path):
        from api.utils_pickles import pickle_dump
        with patch('api.utils_pickles.settings') as mock_settings:
            mock_settings.PICKLE_OPEN_TIMEOUT = 5
            pickle_dump(obj, path)

    def _load(self, path):
        from api.utils_pickles import pickle_load
        with patch('api.utils_pickles.settings') as mock_settings:
            mock_settings.PICKLE_OPEN_TIMEOUT = 5
            return pickle_load(path)

    def test_dump_creates_gzip_file(self):
        path = os.path.join(self.tmpdir, 'test.p')
        self._dump({'key': 'value'}, path)
        # Verify it's a valid gzip file
        with open(path, 'rb') as f:
            self.assertEqual(f.read(2), b'\x1f\x8b')  # gzip magic bytes

    def test_dump_creates_parent_directory(self):
        subdir_path = os.path.join(self.tmpdir, '100000', '100000.p')
        self._dump({'page': 100000}, subdir_path)
        self.assertTrue(os.path.exists(subdir_path))

    def test_roundtrip_compressed(self):
        path = os.path.join(self.tmpdir, 'roundtrip.p')
        obj = {'title': 'Test Article', 'revisions': [1, 2, 3], 'nested': {'a': 1}}
        self._dump(obj, path)
        result = self._load(path)
        self.assertEqual(result, obj)

    def test_load_legacy_uncompressed_file(self):
        """pickle_load should transparently read old uncompressed pickle files."""
        path = os.path.join(self.tmpdir, 'legacy.p')
        obj = {'legacy': True, 'data': [1, 2, 3]}
        # Write an old-style uncompressed pickle directly
        with open(path, 'wb') as f:
            pickle.dump(obj, f, protocol=-1)
        # Should load without error
        result = self._load(path)
        self.assertEqual(result, obj)

    def test_compression_reduces_size(self):
        path_compressed = os.path.join(self.tmpdir, 'compressed.p')
        path_plain = os.path.join(self.tmpdir, 'plain.p')
        # Use repetitive data that compresses well
        obj = {'data': list(range(10000))}
        self._dump(obj, path_compressed)
        with open(path_plain, 'wb') as f:
            pickle.dump(obj, f, protocol=-1)
        self.assertLess(
            os.path.getsize(path_compressed),
            os.path.getsize(path_plain),
        )


class TestPickleDeleteAndSize(unittest.TestCase):
    """Test pickle_delete and get_pickle_size with new and legacy paths."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_settings(self, mock_settings):
        mock_settings.PICKLE_OPEN_TIMEOUT = 5

    def test_delete_new_path(self):
        from api.utils_pickles import pickle_delete, get_pickle_path
        with patch('api.utils_pickles.get_pickle_folder', return_value=self.tmpdir):
            path = get_pickle_path(100000)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            open(path, 'wb').close()
            self.assertTrue(os.path.exists(path))
            result = pickle_delete(100000, None)
            self.assertTrue(result)
            self.assertFalse(os.path.exists(path))

    def test_delete_falls_back_to_legacy(self):
        from api.utils_pickles import pickle_delete
        with patch('api.utils_pickles.get_pickle_folder', return_value=self.tmpdir):
            legacy_path = os.path.join(self.tmpdir, '100000.p')
            open(legacy_path, 'wb').close()
            result = pickle_delete(100000, None)
            self.assertTrue(result)
            self.assertFalse(os.path.exists(legacy_path))

    def test_delete_returns_false_when_not_found(self):
        from api.utils_pickles import pickle_delete
        with patch('api.utils_pickles.get_pickle_folder', return_value=self.tmpdir):
            result = pickle_delete(999999, None)
            self.assertFalse(result)

    def test_get_pickle_size_new_path(self):
        from api.utils_pickles import get_pickle_size, get_pickle_path
        with patch('api.utils_pickles.get_pickle_folder', return_value=self.tmpdir):
            path = get_pickle_path(100000)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'wb') as f:
                f.write(b'x' * 100)
            size = get_pickle_size(100000)
            self.assertEqual(size, 100)

    def test_get_pickle_size_returns_zero_when_missing(self):
        from api.utils_pickles import get_pickle_size
        with patch('api.utils_pickles.get_pickle_folder', return_value=self.tmpdir):
            size = get_pickle_size(999999)
            self.assertEqual(size, 0)


if __name__ == '__main__':
    unittest.main()
