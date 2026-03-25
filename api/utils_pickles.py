# -*- coding: utf-8 -*-
import gzip
import time
# import os
import io
import fcntl
import errno
from os import makedirs, remove
from os.path import getsize, dirname

from six.moves import cPickle as pickle
from six.moves.cPickle import UnpicklingError

from django.conf import settings
from django.utils.translation import get_language


class OpenFileLock:
    """
    Modified from:
    https://github.com/derpston/python-simpleflock
    """
    def __init__(self, path, mode, timeout=None):
        self._path = path
        self._mode = mode
        self._timeout = timeout
        self._fd = None

    def __enter__(self):
        self._fd = io.open(self._path, self._mode)
        if self._timeout:
            start_lock_search = time.time()
        while True:
            try:
                fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                # Lock acquired!
                return self._fd
            except (OSError, IOError) as ex:
                # BlockingIOError is raised
                if ex.errno != errno.EAGAIN:  # Resource temporarily unavailable
                    raise
                elif self._timeout is not None and time.time() > (start_lock_search + self._timeout):
                    # Exceeded the user-specified timeout.
                    raise
            # without a delay is also undesirable.
            time.sleep(0.1)

    def __exit__(self, *args):
        fcntl.flock(self._fd, fcntl.LOCK_UN)
        # os.close(self._fd)
        self._fd.close()


def get_pickle_folder(language=None):
    # return '{}_{}'.format(settings.PICKLE_FOLDER, get_language())
    return getattr(settings, 'PICKLE_FOLDER_{}'.format(language or get_language()).upper())


def get_pickle_path(page_id, language=None):
    """Return the pickle file path for a given page_id and language.

    Uses a subdirectory structure based on floor(page_id / 1000) * 1000
    to avoid filesystem performance issues caused by storing millions of
    files in a single flat directory.

    Directory structure:
        <PICKLE_FOLDER>/<subdirectory>/<page_id>.p

    Where subdirectory = floor(page_id / 1000) * 1000

    Examples:
        page_id 100000 -> en/100000/100000.p
        page_id 100002 -> en/100000/100002.p
        page_id 200005 -> en/200000/200005.p

    This reduces files per directory from ~7M to ~7K for enwiki.

    Related: T414087
    """
    folder = get_pickle_folder(language)
    subdirectory = (page_id // 1000) * 1000
    return "{}/{}/{}.p".format(folder, subdirectory, page_id)


def _legacy_pickle_path(page_id, language=None):
    """Return the old flat-directory pickle path for backward compatibility."""
    return "{}/{}.p".format(get_pickle_folder(language), page_id)


def pickle_dump(obj, pickle_path):
    """Write a pickle file with gzip-6 compression.

    Creates the parent subdirectory if it does not already exist.
    Compression reduces disk usage by ~84% (6x ratio) with negligible
    decompression overhead (~23ms).

    Related: T414075, T414087
    """
    makedirs(dirname(pickle_path), exist_ok=True)
    with OpenFileLock(pickle_path, 'wb', timeout=settings.PICKLE_OPEN_TIMEOUT) as f:
        with gzip.GzipFile(fileobj=f, mode='wb', compresslevel=6) as gz:
            pickle.dump(obj, gz, protocol=-1)  # -1 to select HIGHEST_PROTOCOL available


def pickle_load(pickle_path):
    """Load a pickle file, transparently handling both compressed and legacy files.

    Tries gzip decompression first. If the file is an older uncompressed
    pickle (written before this change), falls back to reading it directly
    so existing data remains accessible without a migration step.

    Related: T414075
    """
    retries = 6
    while retries:
        retries -= 1
        try:
            with OpenFileLock(pickle_path, 'rb', timeout=settings.PICKLE_OPEN_TIMEOUT) as f:
                try:
                    with gzip.GzipFile(fileobj=f, mode='rb') as gz:
                        obj = pickle.load(gz)
                except OSError:
                    # File is not gzip-compressed — legacy uncompressed pickle.
                    # Seek back to the start and read it as plain pickle.
                    f.seek(0)
                    obj = pickle.load(f)
            return obj
        except (EOFError, UnpicklingError, FileNotFoundError) as e:
            time.sleep(0.1)
            if not retries:
                raise e


def pickle_delete(page_id, language):
    pickle_path = get_pickle_path(page_id, language)
    try:
        remove(pickle_path)
    except FileNotFoundError:
        # Fall back to legacy flat path in case file predates subdirectory change
        legacy_path = _legacy_pickle_path(page_id, language)
        try:
            remove(legacy_path)
        except Exception:
            return False
    except Exception:
        # TODO: add a logging channel for utils_pickles
        return False
    return True


def pickle_load_only_id(page_id, language=None):
    pickle_path = get_pickle_path(page_id, language)
    if not _path_exists(pickle_path):
        # Fall back to legacy flat path for files written before subdirectory change
        legacy_path = _legacy_pickle_path(page_id, language)
        if _path_exists(legacy_path):
            return pickle_load(legacy_path)
    return pickle_load(pickle_path)


def get_pickle_size(page_id, language=None):
    pickle_path = get_pickle_path(page_id, language)
    try:
        size = getsize(pickle_path)  # [byte]
    except FileNotFoundError:
        # Fall back to legacy flat path
        legacy_path = _legacy_pickle_path(page_id, language)
        try:
            size = getsize(legacy_path)
        except FileNotFoundError:
            size = 0
    return size


def _path_exists(path):
    """Return True if path exists on the filesystem."""
    from os.path import exists
    return exists(path)


def find_pickles_randomly(pickle_folder_path=None, n=2, output_folder=None):
    # output_folder = '/home/wikiwho/wikiwho_api/tests_ignore/mwpersistence/random_1000/wikiwho'
    from os.path import getsize, join
    from os import listdir, walk
    from random import sample
    import json
    pickle_folder_path = pickle_folder_path or get_pickle_folder()

    # Collect pickle files from subdirectories and flat layout alike
    all_files = []
    for root, dirs, files in walk(pickle_folder_path):
        for fname in files:
            if fname.endswith('.p'):
                all_files.append(join(root, fname))

    random_files = sample(all_files, min(n, len(all_files)))

    csv_data = [['article_title', 'last_rev_id', 'len_revs', 'pickle_size', 'page_id']]
    for path in random_files:
        ww = pickle_load(path)
        if not ww.ordered_revisions:
            continue
        page_id = ww.page_id
        article_title = ww.title
        if '/' in article_title:
            continue
        last_rev_id = ww.ordered_revisions[-1]
        len_revs = len(ww.ordered_revisions)
        pickle_size = getsize(path)
        csv_data.append([article_title, last_rev_id, len_revs, pickle_size, page_id])
        ri_ai_json = ww.get_revision_content([last_rev_id], {'str', 'o_rev_id', 'editor'})
        json_file_path = '{}/{}_ri_ai.json'.format(output_folder, article_title)
        with open(json_file_path, 'w', encoding='utf-8') as f:
            f.write(json.dumps(ri_ai_json, indent=4, separators=(',', ': '), sort_keys=True, ensure_ascii=False))

        io_json = ww.get_revision_content([last_rev_id], {'str', 'in', 'out'})
        json_file_path = '{}/{}_io.json'.format(output_folder, article_title)
        with open(json_file_path, 'w', encoding='utf-8') as f:
            f.write(json.dumps(io_json, indent=4, separators=(',', ': '), sort_keys=True, ensure_ascii=False))

        rev_ids_json = ww.get_revision_ids({'rev_id', 'editor', 'timestamp'})
        json_file_path = '{}/{}_rev_ids.json'.format(output_folder, article_title)
        with open(json_file_path, 'w', encoding='utf-8') as f:
            f.write(json.dumps(rev_ids_json, indent=4, separators=(',', ': '), sort_keys=True, ensure_ascii=False))

    import csv
    with open(join(output_folder, '1000_random_articles.csv'), 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerows(csv_data)
