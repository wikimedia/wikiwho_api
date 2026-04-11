# -*- coding: utf-8 -*-
"""
Example usage:
python manage.py generate_articles_from_wp_xmls -p '/home/kenan/PycharmProjects/wikiwho_api/wikiwho/tests/test_jsons/test' -t 1 -m 2 -d 'R' --check_exists
python manage.py generate_articles_from_wp_xmls -p '/home/kenan/PycharmProjects/wikiwho_api/wikiwho/tests/test_jsons/' -t 30 -m 24
python manage.py generate_articles_from_wp_xmls -p '/home/kenan/PycharmProjects/wikiwho_api/wikiwho/tests/test_jsons/' -j '' -m 24 --check_exists
"""
from os import mkdir, listdir
from os.path import basename, exists
import logging
import re
from time import strftime, sleep
import operator

from concurrent.futures import ProcessPoolExecutor, as_completed  # , ThreadPoolExecutor, TimeoutError, CancelledError
from mwxml import Dump
from mwtypes.files import reader

from django.core.management.base import BaseCommand, CommandError
from django.db.utils import OperationalError, DatabaseError
from django.conf import settings

from api.handler import WPHandler
from base.utils import is_db_running
from wikiwho.utils_db import wikiwho_to_csv


def generate_articles(xml_file_path, page_ids, log_folder, format_, save_tables, language,
                      check_exists=False, timeout=None, is_write_into_csv=False):
    xml_file_name = basename(xml_file_path)
    logger = logging.getLogger(xml_file_name[:-3].split('-')[-1])
    file_handler = logging.FileHandler('{}/{}_at_{}.log'.format(log_folder,
                                                                xml_file_name,
                                                                strftime("%Y-%m-%d-%H:%M:%S")))
    file_handler.setLevel(logging.ERROR)
    formatter = logging.Formatter(format_)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    parsing_pattern = settings.LOG_PARSING_PATTERN

    print('Start: {} at {}'.format(xml_file_name, strftime("%H:%M:%S %d-%m-%Y")))
    try:
        dump = Dump.from_file(reader(xml_file_path))
        # dump = iteration.Iterator.from_file(open('decompressed file path'))
        # import itertools
        # dump = itertools.islice(dump, 2)
    except Exception as e:
        logger.exception('{}--------{}'.format(xml_file_name, parsing_pattern))
    else:
        c = 0
        for page in dump:
            try:
                if page.namespace == 0 and not page.redirect and (not page_ids or int(page.id) in page_ids):
                    with WPHandler(page.title, page_id=page.id, save_tables=save_tables,
                                   check_exists=check_exists, is_xml=True, language=language) as wp:
                        # in some wiki dumps such as eu or de, revisions are not ordered by timestamp
                        page_ = sorted(list(page), key=operator.attrgetter('timestamp'))
                        wp.handle_from_xml_dump(page_, timeout)
                        if is_write_into_csv:
                            wikiwho_to_csv(wp.wikiwho, log_folder + '/csv')
                        if page_ids:
                            c += 1
                            if c == len(page_ids):
                                break
            except (OperationalError, DatabaseError):
                while not is_db_running():
                    sleep(60*5)
                logger.exception('{}-({})--------{}-DBError'.format(page.title, page.id, parsing_pattern))
            except Exception as e:
                logger.exception('{}-({})--------{}'.format(page.title, page.id, parsing_pattern))
    print('Done: {} at {}'.format(xml_file_name, strftime("%H:%M:%S %d-%m-%Y")))
    return True


class Command(BaseCommand):
    help = 'Generates articles from xml dumps in given path. Skips redirect articles and ' \
           'pages which does not have namespace as 0. This command processes files concurrently.'

    def add_arguments(self, parser):
        parser.add_argument('-p', '--path', help='Path of xml folder where compressed dumps take place.',
                            required=True)
        parser.add_argument('-j', '--json', help='Path of json folder.', required=False)
        parser.add_argument('-l', '--log_folder', help='Folder where to write logs. Default is folder of xml folder',
                            required=False)
        parser.add_argument('-m', '--max_workers', type=int, help='Number of processors/threads to run parallel. '
                                                                  'Default is # compressed files in given folder path.',
                            required=False)
        parser.add_argument('-lang', '--language', help="Wikipedia language. Default is 'en'.",
                            required=False)
        parser.add_argument('-t', '--timeout', type=float, required=False,
                            help='Timeout value for each processor for analyzing articles [minutes]')
        parser.add_argument('-c', '--check_exists', action='store_true',
                            help='Check if an article exists before creating it.'
                                 ' If yes, go to the next article. If not, process article. ',
                            default=False, required=False)
        parser.add_argument('-w', '--write_into_csv', action='store_true',
                            help='Write content, current content and deleted content into csv. '
                                 'This must be called with check_exists flag. Default is False.',
                            default=False, required=False)
        parser.add_argument('-db', '--db_mode', help='Empty: dont save into db, A: Save only articles , '
                                                     'R: save only revisions, ART: Save all. Default is empty.',
                            required=False)
        parser.add_argument('-tpe', '--thread_pool_executor', action='store_true',
                            help='Use ThreadPoolExecutor, default is ProcessPoolExecutor (Not implemented)',
                            default=False, required=False)

    def handle(self, *args, **options):
        # get path of xml dumps
        xml_folder = options['path']
        xml_folder = xml_folder[:-1] if xml_folder.endswith('/') else xml_folder

        check_exists = options['check_exists']
        json_folder = options['json']
        xml_files = []
        if json_folder and check_exists:
            # get page ids for each xml file from parse_logs json outputs
            import json
            json_folder = json_folder[:-1] if json_folder.endswith('/') else json_folder
            json_files = ['{}/{}'.format(json_folder, j) for j in listdir(json_folder) if j.endswith('.json')]
            for json_file in json_files:
                with open(json_file, 'r') as f:
                    json_data = json.loads(f.read())
                    for xml_file in json_data:
                        title_ids = json_data[xml_file].get('timeouts', [])
                        if check_exists:
                            title_ids += json_data[xml_file].get('operationals', [])
                        title_ids += json_data[xml_file].get('missing', [])
                        # print(title_ids)
                        page_ids = set(int(ti[1]) for ti in title_ids)
                        if page_ids:
                            xml_files.append(['{}/{}'.format(xml_folder, xml_file), page_ids])
        elif not json_folder:
            # if there is no json inputs, process all pages in each xml dump
            # Support both legacy .7z and new .bz2 (MediaWiki Content File Exports) formats
            xml_files = [['{}/{}'.format(xml_folder, x), []] for x in listdir(xml_folder)
                         if x.endswith(('.7z', '.bz2')) and 'index' not in x.lower()]
        try:
            xml_files = {int(x[0].split('xml-p')[1].split('p')[0]): x for x in xml_files}
            xml_files = [xml_files[x] for x in sorted(xml_files)]
        except (IndexError, ValueError):
            # Try new dump format: e.g. ukwiki-2026-04-01-p1015979p1087621.xml.bz2
            # Also handles single-page revision ranges: ukwiki-2026-04-01-p193624r847223r25026950.xml.bz2
            try:
                def _extract_start_page(filepath):
                    m = re.search(r'-p(\d+)(?:[pr]\d+)+\.xml\.', filepath)
                    return int(m.group(1)) if m else 0
                xml_files = {_extract_start_page(x[0]): x for x in xml_files}
                xml_files = [xml_files[x] for x in sorted(xml_files)]
            except (IndexError, ValueError):
                pass

        if not xml_files:
            raise CommandError('In given folder ({}), there are no dump files (.7z or .bz2).'.format(xml_folder))

        # decide concurrency type
        is_ppe = not options['thread_pool_executor']
        if is_ppe:
            Executor = ProcessPoolExecutor
            format_ = '%(asctime)s %(processName)-10s %(name)s %(levelname)-8s %(message)s'
        else:
            raise NotImplemented  # Not used/tested
            # Executor = ThreadPoolExecutor
            # format_ = '%(asctime)s %(threadName)-10s %(name)s %(levelname)-8s %(message)s'

        # set logging
        log_folder = options['log_folder']
        log_folder = log_folder[:-1] if log_folder and log_folder.endswith('/') else log_folder
        log_folder = '{}/{}'.format(log_folder or xml_folder, 'logs')
        if not exists(log_folder):
            mkdir(log_folder)
        logger = logging.getLogger('future_log')
        file_handler = logging.FileHandler('{}/{}_at_{}.log'.format(log_folder,
                                                                    xml_folder.split('/')[-1],
                                                                    strftime("%Y-%m-%d-%H:%M:%S")))
        file_handler.setLevel(logging.ERROR)
        formatter = logging.Formatter(format_)
        file_handler.setFormatter(formatter)
        logger.handlers = [file_handler]

        # if outputs will be written into csv
        is_write_into_csv = options['write_into_csv']
        if is_write_into_csv:
            import csv
            import sys
            csv.field_size_limit(sys.maxsize)
            csv_folder = log_folder + '/csv'
            if not exists(csv_folder):
                mkdir(csv_folder)

        # get max number of concurrent workers and timeout value for process of each article
        max_workers = options['max_workers'] or len(xml_files)
        timeout = int(options['timeout'] * 60) if options['timeout'] else None  # convert into seconds

        # decide which tables in db will be filled
        db_mode = options['db_mode'] or ''
        save_tables = []
        for m in db_mode:
            if m.upper() == 'A':
                save_tables.append('article')
            elif m.upper() == 'R':
                save_tables.append('revision')
            elif m.upper() == 'T':
                save_tables.append('token')

        language = options['language'] or 'en'

        # Sequential process of xml dumps - test purposes
        # for xml_file_path, page_ids in xml_files:
        #     generate_articles(xml_file_path, page_ids, log_folder, format_,
        #                       save_tables, language, check_exists, timeout, is_write_into_csv)

        # Concurrent process of xml dumps
        print(max_workers, save_tables, language)
        # print(xml_files)
        with Executor(max_workers=max_workers) as executor:
            jobs = {}
            files_left = len(xml_files)
            files_iter = iter(xml_files)

            while files_left:
                for xml_file_path, page_ids in files_iter:
                    job = executor.submit(generate_articles, xml_file_path, page_ids, log_folder,
                                          format_, save_tables, language, check_exists, timeout, is_write_into_csv)
                    jobs[job] = basename(xml_file_path)
                    if len(jobs) == max_workers:  # limit # jobs with max_workers
                        break

                for job in as_completed(jobs):
                    files_left -= 1
                    xml_file_name = jobs[job]
                    try:
                        data = job.result()
                    except Exception as exc:
                        logger.exception(xml_file_name)

                    del jobs[job]
                    break  # to add a new job, if there is any
        print('Done: {} at {}'.format(xml_folder, strftime("%H:%M:%S %d-%m-%Y")))
