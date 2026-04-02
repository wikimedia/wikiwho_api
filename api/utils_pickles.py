# -*- coding: utf-8 -*-
import time
# import os
import io
import fcntl
import errno
from os.path import getsize
from os import remove

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
                # if self._mode == 'rb':
                #     # do not prevent other reads, just check if file is locked.
                #     # but then it is possible that during reading, file is over written by some other process
                #     # and read data is not correct
                #     # if read mode, check only if file is locked
                #     fcntl.flock(self._fd, fcntl.LOCK_UN)
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


def pickle_dump(obj, pickle_path):
    # try to lock file:
    # 1) if not already locked, then lock, write and then unlock
    # 2) if already locked, wait until unlocked (in timeout) and then lock, write and unlock
    with OpenFileLock(pickle_path, 'wb', timeout=settings.PICKLE_OPEN_TIMEOUT) as f:
        pickle.dump(obj, f, protocol=-1)  # -1 to select HIGHEST_PROTOCOL available
    # print('?', f.closed)


def pickle_load(pickle_path):
    # try to lock file:
    # 1) if not already locked, then lock, read and then unlock
    # 2) if already locked, wait until unlocked (in timeout) and then lock, read and unlock
    retries = 6
    while retries:
        retries -= 1
        try:
            with OpenFileLock(pickle_path, 'rb', timeout=settings.PICKLE_OPEN_TIMEOUT) as f:
                obj = pickle.load(f)
            return obj
        except (EOFError,  UnpicklingError, FileNotFoundError) as e:  # TODO should we also catch BlockingIOError and retry?
            # if EOFError, retry
            # EOFError Ran out of input
            # EOFError usually happens when pickle file is empty (size 0)
            time.sleep(0.1)
            if not retries:
                raise e


def pickle_delete(page_id, language):
    pickle_path = "{}/{}.p".format(get_pickle_folder(language), page_id)
    try:
        remove(pickle_path)
    except Exception as e:
        # TODO: add a logging channel for utils_pickles
        # Simply silently ignore for now.
        return False
    return True


def pickle_load_only_id(page_id, language=None):
    pickle_path = "{}/{}.p".format(get_pickle_folder(language), page_id)
    return pickle_load(pickle_path)


def get_pickle_size(page_id, language=None):
    pickle_path = "{}/{}.p".format(get_pickle_folder(language), page_id)
    try:
        size = getsize(pickle_path)  # [byte]
    except FileNotFoundError:
        size = 0
    return size


def find_pickles_randomly(pickle_folder_path=None, n=2, output_folder=None):
    # output_folder = '/home/wikiwho/wikiwho_api/tests_ignore/mwpersistence/random_1000/wikiwho'
    from os.path import getsize, join
    from os import listdir
    from random import sample
    import json
    pickle_folder_path = pickle_folder_path or get_pickle_folder()
    random_files = sample(listdir(pickle_folder_path), n)
    csv_data = [['article_title', 'last_rev_id', 'len_revs', 'pickle_size', 'page_id']]
    for file in random_files:
        path = join(pickle_folder_path, file)
        ww = pickle_load(path)
        if not ww.ordered_revisions:
            continue
        page_id = ww.page_id
        article_title = ww.title
        if '/' in article_title:
            continue
        # print(page_id, article_title)
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
