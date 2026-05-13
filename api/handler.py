# -*- coding: utf-8 -*-
from __future__ import absolute_import
from __future__ import unicode_literals

import os
import sys
import time
import logging
from datetime import datetime
from email.utils import parsedate_to_datetime
from requests.exceptions import ConnectionError, RequestException

# from time import time
from django.conf import settings
from django.core.cache import cache
from django.utils.translation import get_language, get_language_info

import elasticsearch
from elasticsearch import Elasticsearch
from elasticsearch_dsl import Search
from elasticsearch import helpers

from wikiwho.wikiwho_simple import Wikiwho
from wikiwho_chobj import ChobjerPickle
from wikiwho_chobj.utils import Timer

from deployment.gunicorn_config import timeout as gunicorn_timeout
from deployment.celery_config import user_task_soft_time_limit

from .utils import create_wp_session, Timeout, generate_rvcontinue, get_wp_api_url
from .utils_pickles import pickle_dump, pickle_load, get_pickle_path, _legacy_pickle_path, get_pickle_folder, UnpicklingError
from .models import RecursionErrorArticle, LongFailedArticle
from .messages import MESSAGES


logger = logging.getLogger(__name__)
sys.setrecursionlimit(5000)  # default is 1000
# http://neopythonic.blogspot.de/2009/04/tail-recursion-elimination.html
# session = create_wp_session()


def debug_timing_enabled():
    return getattr(settings, 'WP_DEBUG_TIMING', False)


class WPHandlerException(Exception):

    def __init__(self, message, code):
        self.message = message
        self.code = code

    def __str__(self):
        return repr(self.message)


class WPHandler(object):

    def __init__(self, article_title, page_id=None, pickle_folder='', save_tables=(),
                 check_exists=True, is_xml=False, revision_id=None, log_error_into_db=True,
                 language=None, is_user_request=False, wikiwho=None, *args, **kwargs):
        self.article_title = article_title
        self.saved_article_title = ''
        self.revision_ids = []
        self.wikiwho = wikiwho
        self.pickle_folder = pickle_folder
        self.pickle_path = ''
        self.saved_rvcontinue = ''
        self.latest_revision_id = None
        self.page_id = page_id
        self.revision_id = revision_id
        self.save_tables = save_tables
        self.check_exists = check_exists
        self.already_exists = False
        self.is_xml = is_xml
        self.namespace = 0
        self.cache_key = None
        self.cache_set = False
        self.log_error_into_db = log_error_into_db
        self.language = language or get_language()
        self.is_user_request = is_user_request
        self.chobj_error = ''
        self.wp_rate_limit_slept_seconds = 0
        self._timing_start = time.perf_counter()
        self._timing_last = self._timing_start

    def _timing(self, event, **data):
        if not debug_timing_enabled():
            return
        now = time.perf_counter()
        parts = [
            '[wikiwho-api-timing]',
            '+{:.3f}s'.format(now - self._timing_start),
            'delta={:.3f}s'.format(now - self._timing_last),
            event,
        ]
        for key in sorted(data):
            parts.append('{}={}'.format(key, data[key]))
        print(' '.join(parts), flush=True)
        self._timing_last = now

    @staticmethod
    def _retry_after_seconds(value):
        if value is None:
            return None
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            pass

        try:
            retry_at = parsedate_to_datetime(value)
        except (TypeError, ValueError, IndexError):
            return None

        if retry_at.tzinfo is None:
            return max(0, int((retry_at - datetime.utcnow()).total_seconds()))
        return max(0, int((retry_at - datetime.now(retry_at.tzinfo)).total_seconds()))

    def _request_wp_json(self, session, params, is_api_call):
        fallback_sleep = getattr(settings, 'WP_RATE_LIMIT_MAX_SLEEP', 60)
        retry_budget = getattr(settings, 'WP_RATE_LIMIT_RETRY_BUDGET', 300)
        attempts = 0

        while True:
            request_start = time.perf_counter()
            try:
                response = session.get(url=get_wp_api_url(self.language), headers=settings.WP_HEADERS,
                                       params=params, timeout=settings.WP_REQUEST_TIMEOUT)
            except ConnectionError as e:
                try:
                    sub_error = e.args[0].args[1]
                except Exception:
                    sub_error = None
                if isinstance(sub_error, TimeoutError):
                    raise TimeoutError
                if is_api_call:
                    raise WPHandlerException(*MESSAGES['wp_http_error'])
                raise e
            except RequestException as e:
                if is_api_call:
                    raise WPHandlerException(*MESSAGES['wp_http_error'])
                raise e
            request_seconds = time.perf_counter() - request_start
            self._timing(
                'wp_request',
                action=params.get('action'),
                prop=params.get('prop'),
                rvcontinue=params.get('rvcontinue', '0'),
                status=response.status_code,
                seconds='{:.3f}'.format(request_seconds),
                bytes=len(response.content),
                retry_after=response.headers.get('Retry-After', ''),
            )

            if response.status_code == 429:
                retry_after = self._retry_after_seconds(response.headers.get('Retry-After'))
                if retry_after is None:
                    retry_after = min(2 ** attempts, fallback_sleep)

                total_slept = self.wp_rate_limit_slept_seconds
                remaining_budget = retry_budget - total_slept
                if remaining_budget <= 0:
                    logger.warning(
                        'Wikipedia API rate limit budget exhausted for page_id=%s title=%s after %s attempts and %s seconds; '
                        'next Retry-After was %s seconds',
                        self.page_id,
                        self.saved_article_title or self.article_title,
                        attempts,
                        total_slept,
                        retry_after,
                    )
                    raise WPHandlerException(
                        MESSAGES['wp_rate_limited'][0].format(total_slept, retry_after),
                        MESSAGES['wp_rate_limited'][1],
                    )

                sleep_seconds = min(retry_after, remaining_budget)
                attempts += 1
                self.wp_rate_limit_slept_seconds += sleep_seconds
                logger.warning(
                    'Wikipedia API returned 429 for page_id=%s title=%s; sleeping %s seconds '
                    '(attempt %s; total rate-limit sleep: %s/%s seconds; Retry-After: %s seconds)',
                    self.page_id,
                    self.saved_article_title or self.article_title,
                    sleep_seconds,
                    attempts,
                    self.wp_rate_limit_slept_seconds,
                    retry_budget,
                    retry_after,
                )
                time.sleep(sleep_seconds)

                if sleep_seconds < retry_after:
                    logger.warning(
                        'Wikipedia API Retry-After exceeded local retry budget for page_id=%s title=%s; '
                        'waited %s seconds total and did not retry early',
                        self.page_id,
                        self.saved_article_title or self.article_title,
                        self.wp_rate_limit_slept_seconds,
                    )
                    raise WPHandlerException(
                        MESSAGES['wp_rate_limited'][0].format(self.wp_rate_limit_slept_seconds, retry_after),
                        MESSAGES['wp_rate_limited'][1],
                    )
                continue

            try:
                response.raise_for_status()
            except RequestException as e:
                if is_api_call:
                    raise WPHandlerException(*MESSAGES['wp_http_error'])
                raise e

            try:
                return response.json()
            except ValueError as e:
                if is_api_call:
                    raise WPHandlerException(*MESSAGES['wp_http_error'])
                raise e

    def _get_latest_revision_data(self):
        self._timing('latest_revision_lookup_start', title=self.article_title, page_id=self.page_id,
                     revision_id=self.revision_id)
        if self.page_id:
            params = {'pageids': self.page_id}
        elif self.article_title:
            params = {'titles': self.article_title}
        elif self.revision_id:
            params = {'revids': self.revision_id}
        else:
            return ''

        params.update({'action': 'query', 'prop': 'info', 'format': 'json'})
        session = create_wp_session(self.language)
        response = self._request_wp_json(session, params, is_api_call=True)
        pages = response["query"].get('pages')
        is_pages = False
        if pages:
            is_pages = True
            _, page = pages.popitem()
        if not is_pages or 'missing' in page or _ == '-1':
            return {'page_id': self.page_id,
                    'article_db_title': None,
                    'latest_revision_id': None,
                    'namespace': None}
        data = {'page_id': page['pageid'],
                'article_db_title': page['title'].replace(' ', '_'),
                'latest_revision_id': page["lastrevid"],
                'namespace': page["ns"]}
        self._timing('latest_revision_lookup_done', **data)
        return data

    def __enter__(self):
        self._timing('enter_start', title=self.article_title, page_id=self.page_id)
        # check if given page_id valid
        if self.page_id:
            self.page_id = int(self.page_id)
            if not 0 < self.page_id < 2147483647:
                raise WPHandlerException(MESSAGES['invalid_page_id'][0].format(self.page_id),
                                         MESSAGES['invalid_page_id'][1])
            if (LongFailedArticle.objects.filter(page_id=self.page_id, language=self.language).exists() or
                    RecursionErrorArticle.objects.filter(page_id=self.page_id, language=self.language).exists()):
                raise WPHandlerException(MESSAGES['never_finished_article'][0] + f' Page Id: {self.page_id}',
                                         MESSAGES['never_finished_article'][1])

        if self.is_xml:
            self.saved_article_title = self.article_title.replace(' ', '_')
            # self.page_id = self.page_id
        else:
            # get db title from wp api
            d = self._get_latest_revision_data()
            self.latest_revision_id = d['latest_revision_id']
            self.page_id = d['page_id']
            if not settings.TESTING and (
                (LongFailedArticle.objects.filter(page_id=self.page_id, language=self.language).exists() or
                 RecursionErrorArticle.objects.filter(page_id=self.page_id, language=self.language).exists())):
                raise WPHandlerException(MESSAGES['never_finished_article'][0] + f' Page Id: {self.page_id}',
                                         MESSAGES['never_finished_article'][1])
            self.saved_article_title = d['article_db_title']
            self.namespace = d['namespace']
            if not settings.TESTING:
                self.cache_key = 'page_{}_{}'.format(
                    self.language, self.page_id)

        if self.pickle_folder:
            # Custom folder override (e.g. tests): apply subdirectory structure within it
            subdirectory = (self.page_id // 1000) * 1000
            self.pickle_path = "{}/{}/{}.p".format(self.pickle_folder, subdirectory, self.page_id)
        else:
            self.pickle_path = get_pickle_path(self.page_id, self.language)
        self.already_exists = os.path.exists(self.pickle_path)
        # Check legacy flat path for articles written before the subdirectory change
        self._load_path = self.pickle_path
        if not self.already_exists:
            legacy_path = (
                "{}/{}.p".format(self.pickle_folder, self.page_id)
                if self.pickle_folder
                else _legacy_pickle_path(self.page_id, self.language)
            )
            if os.path.exists(legacy_path):
                self.already_exists = True
                self._load_path = legacy_path  # load from legacy; next save will write to new path

        if not self.already_exists:
            if not settings.TESTING and (
                    not (self.is_user_request or settings.SERVER_LEVEL == settings.LEVEL_PRODUCTION)):
                raise WPHandlerException(MESSAGES['ignore_article_in_staging'][0].format(self.saved_article_title),
                                         MESSAGES['ignore_article_in_staging'][1])

            # a new pickle will be created
            self.wikiwho = Wikiwho(self.saved_article_title)
            self.wikiwho.page_id = self.page_id

        else:
            try:
                if self.wikiwho is None:
                    self.wikiwho = pickle_load(self._load_path)
                else:
                    self.wikiwho.page_id = self.page_id
            except (EOFError,  UnpicklingError) as e:
                # create a new pickle, this one will overwrite the problematic
                # one
                self.wikiwho = Wikiwho(self.saved_article_title)
                self.wikiwho.page_id = self.page_id
            else:
                self.wikiwho.title = self.saved_article_title
        self.saved_rvcontinue = self.wikiwho.rvcontinue

        self._timing('enter_done', page_id=self.page_id, latest_revision_id=self.latest_revision_id,
                     pickle_path=self.pickle_path, already_exists=self.already_exists,
                     saved_rvcontinue=self.saved_rvcontinue)
        return self

    def _set_wikiwho_rvcontinue(self):
        # hackish: create a rvcontinue with last revision of this article
        rev = self.wikiwho.revision_curr
        if rev.timestamp == 0 or (self.wikiwho.spam_ids and self.wikiwho.spam_ids[-1] > rev.id):
            # if all revisions were detected as spam,
            # wikiwho object holds no information (it is in initial status, rvcontinue=0)
            # or if last processed revision is a spam
            self.wikiwho.rvcontinue, last_spam_ts = generate_rvcontinue(
                self.language, self.wikiwho.spam_ids[-1])
            if rev.timestamp != 0 and (rev.timestamp > last_spam_ts or last_spam_ts == '0'):
                # rev id comparison was wrong
                self.wikiwho.rvcontinue = generate_rvcontinue(
                    self.language, rev.id, rev.timestamp)
        else:
            self.wikiwho.rvcontinue = generate_rvcontinue(
                self.language, rev.id, rev.timestamp)

    def handle_from_xml_dump(self, page, timeout=None):
        # this handle is used only to fill the db so if already exists, skip this article
        # here we don't have rvcontinue check to analyse article as we have in
        # handle method
        if self.check_exists and self.already_exists:
            # no continue logic for xml processing
            # return
            raise WPHandlerException(MESSAGES['already_exists'][0].format(self.page_id),
                                     MESSAGES['already_exists'][1])

        if timeout:
            with Timeout(seconds=timeout,
                         error_message='Timeout in analyse_article_from_xml_dump ({} seconds)'.format(timeout)):
                self.wikiwho.analyse_article_from_xml_dump(page)
        else:
            self.wikiwho.analyse_article_from_xml_dump(page)
        self._set_wikiwho_rvcontinue()


    def get_resuming_chob_revid(self):
        """ return the last revision id of which chobs were processed
        """
        try:
            return Search(using=Elasticsearch(),
                index="chobs_" + self.language).source('to_rev').filter(
                "term", page_id=self.page_id)[0].sort('-to_timestamp')[0].execute(
                ).hits[0].to_rev
        except IndexError as exc1:
            # No results for that page
            return -1
        except elasticsearch.exceptions.NotFoundError as exc2:
            # The elasticsearc index for that language is new
            return -1
        except Exception as exc3:
            self.chobj_error += f'Error querying previous chobs (page_id={self.page_id})\b'
            return -2

    def load_chobs(self, starting_revid):
        """Calculate and save the chobs in the elasticsearch database"""

        if self.language in settings.CHOBS_LANGUAGES:
            try:
                pages = ({
                    "_index": "chobs_" + self.language,
                    "_type": "chob",
                    "_source": chob
                } for chob in ChobjerPickle(
                    ww_pickle=self.wikiwho, context=settings.CHOBS_CONTEXT,
                    starting_revid=starting_revid).iter_chobjs())
            except Exception as e:
                self.chobj_error += str(e) + f'\nError calculating chobs (page_id={self.page_id})\n'

            try:
                helpers.bulk(Elasticsearch(), pages)
            except Exception as e:
                self.chobj_error += str(e) + f'\nError storing chobs (page_id={self.page_id})\n'


    def handle(self, revision_ids, is_api_call=True, timeout=None):
        """

        :param revision_ids:
        :param is_api_call:
        :param timeout: cache_key_timeout
        :return:
        """
        handle_start = time.perf_counter()
        self._timing('handle_start', revision_ids=revision_ids or 'latest',
                     latest_revision_id=self.latest_revision_id, saved_rvcontinue=self.saved_rvcontinue)
        # check if article exists

        if self.latest_revision_id is None:
            raise WPHandlerException(MESSAGES['article_not_in_wp'][0].format(self.article_title or self.page_id,
                                                                             get_language_info(self.language)['name'].lower()),
                                     MESSAGES['article_not_in_wp'][1])
        elif self.namespace != 0:
            raise WPHandlerException(MESSAGES['invalid_namespace'][0].format(self.namespace),
                                     MESSAGES['invalid_namespace'][1])
        elif settings.ONLY_READ_ALLOWED:
            if self.already_exists:
                return
            else:
                raise WPHandlerException(*MESSAGES['only_read_allowed'])

        # the pickle is up to date
        self.revision_ids = revision_ids or [self.latest_revision_id]
        # chobstart_revid = self.get_resuming_chob_revid()

        # if self.revision_ids[-1] in self.wikiwho.revisions:
        #     if chobstart_revid == -1:
        #         self.load_chobs(chobstart_revid)
        #     return


        # set cache key to prevent processing an article simultaneously
        if not settings.TESTING:
            if cache.get(self.cache_key, '0') != '1':
                cache.set(self.cache_key, '1', timeout or gunicorn_timeout)
                self.cache_set = True
            else:
                raise WPHandlerException(MESSAGES['revision_under_process'][0].format(self.revision_ids[-1],
                                                                                      self.article_title or self.page_id,
                                                                                      user_task_soft_time_limit),
                                         MESSAGES['revision_under_process'][1])


        # process new revisions of the article
        # holds the last revision id which is saved. 0 for new article
        rvcontinue = self.saved_rvcontinue
        session = create_wp_session(self.language)
        params = {'pageids': self.page_id, 'action': 'query', 'prop': 'revisions',
                  'rvprop': 'content|ids|timestamp|sha1|comment|flags|user|userid',
                  'rvlimit': 'max', 'format': 'json', 'continue': '', 'rvdir': 'newer',
                  'rvendid': self.revision_ids[-1], 'rvslots': 'main'}
        batch_count = 0
        fetched_revision_count = 0
        while True:
            batch_count += 1
            # continue downloading as long as we reach to the given rev_id
            if rvcontinue != '0' and rvcontinue != '1':
                params['rvcontinue'] = rvcontinue
            batch_start = time.perf_counter()
            self._timing('batch_fetch_start', batch=batch_count, rvcontinue=params.get('rvcontinue', '0'))
            result = self._request_wp_json(session, params, is_api_call)
            self._timing('batch_fetch_done', batch=batch_count,
                         seconds='{:.3f}'.format(time.perf_counter() - batch_start))

            if 'error' in result:
                raise WPHandlerException(MESSAGES['wp_error'][0] + str(result['error']),
                                         MESSAGES['wp_error'][1])
            # if 'warnings' in result:
            #     raise WPHandlerException(messages['wp_warning'][0] + str(result['warnings']), messages['wp_warning'][1])
            if 'query' in result:
                pages = result['query']['pages']
                if "-1" in pages:
                    raise WPHandlerException(MESSAGES['article_not_in_wp'][0].format(self.article_title or self.page_id,
                                                                                     get_language_info(self.language)['name'].lower()),
                                             MESSAGES['article_not_in_wp'][1])
                # pass first item in pages dict
                _, page = result['query']['pages'].popitem()
                if 'missing' in page:
                    raise WPHandlerException('The article ({}) you are trying to request does not exist!'.
                                             format(self.article_title or self.page_id), '00')
                try:
                    # Here we work around the rvslots format, which differs from the older default
                    # format that wikiwho.analyse_article was written for. In the old API format,
                    # each revision object includes the text as property '*' and the comment as 'comment':
                    # {'revid': 1083758908, 'parentid': 0, 'user': 'Sichoon', 'userid': 33041991, 'timestamp': '2022-04-20T14:42:55Z',
                    # 'sha1': 'fe56f6f3045d118355c235071be9b63431172ec1', '*': '<long string of article text>', 'comment': 'This is a description of an organocatalyst.' }
                    # In the rvslots format that we request now, it looks instead like:
                    # {'revid': 1083758908, 'parentid': 0, 'user': 'Sichoon', 'userid': 33041991, 'timestamp': '2022-04-20T14:42:55Z',
                    # 'sha1': 'fe56f6f3045d118355c235071be9b63431172ec1', 'slots': {'main': {'contentmodel': 'wikitext', 'contentformat': 'text/x-wiki',
                    # '*': '<long string of article text>'}}, 'comment': 'This is a description of an organocatalyst.'}
                    revisions = page.get('revisions', [])
                    fetched_revision_count += len(revisions)
                    first_revid = revisions[0].get('revid') if revisions else ''
                    last_revid = revisions[-1].get('revid') if revisions else ''
                    text_bytes = 0
                    normalize_start = time.perf_counter()
                    for i in range(len(revisions)):
                        # A revision may have texthidden, in which case the main slot looks like {'main': {'texthidden': ''}}
                        # So we skip those if we get a KeyError.
                        try:
                          revisions[i]['*'] = revisions[i]['slots']['main']['*']
                          text_bytes += len(revisions[i]['*'])
                        except KeyError:
                          pass
                    self._timing('batch_normalized', batch=batch_count, revisions=len(revisions),
                                 fetched_total=fetched_revision_count, first_revid=first_revid,
                                 last_revid=last_revid, text_bytes=text_bytes,
                                 seconds='{:.3f}'.format(time.perf_counter() - normalize_start))

                    analyse_start = time.perf_counter()
                    self.wikiwho.analyse_article(revisions)
                    self._timing('batch_analyse_done', batch=batch_count, revisions=len(revisions),
                                 seconds='{:.3f}'.format(time.perf_counter() - analyse_start),
                                 ordered_revisions=len(self.wikiwho.ordered_revisions),
                                 spam_ids=len(self.wikiwho.spam_ids),
                                 tokens_total=len(self.wikiwho.tokens),
                                 latest_processed=self.wikiwho.ordered_revisions[-1] if self.wikiwho.ordered_revisions else '')

                except RecursionError as e:
                    if self.log_error_into_db:
                        failed_rev_id = int(self.wikiwho.revision_curr.id)
                        failed_article, created = RecursionErrorArticle.objects.get_or_create(
                            page_id=self.page_id,
                            language=self.language,
                            defaults={'count': 1,
                                      'title': self.saved_article_title or '',
                                      'revisions': [failed_rev_id]})
                        if not created:
                            failed_article.count += 1
                            if failed_rev_id not in failed_article.revisions:
                                failed_article.revisions.append(failed_rev_id)
                                failed_article.save(
                                    update_fields=['count', 'modified', 'revisions'])
                            else:
                                failed_article.save(
                                    update_fields=['count', 'modified'])
                    raise e
            if 'continue' not in result:
                rvcontinue_start = time.perf_counter()
                self._set_wikiwho_rvcontinue()
                self._timing('rvcontinue_done', seconds='{:.3f}'.format(time.perf_counter() - rvcontinue_start),
                             rvcontinue=self.wikiwho.rvcontinue)
                break
            rvcontinue = result['continue']['rvcontinue']
            # used at end to decide if there is new revisions to be saved
            self.wikiwho.rvcontinue = rvcontinue


        # self.load_chobs(chobstart_revid)
        self._timing('handle_done', batches=batch_count, fetched_revisions=fetched_revision_count,
                     seconds='{:.3f}'.format(time.perf_counter() - handle_start),
                     ordered_revisions=len(self.wikiwho.ordered_revisions),
                     spam_ids=len(self.wikiwho.spam_ids),
                     tokens_total=len(self.wikiwho.tokens))

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        If the context was exited without an exception, all three arguments will be None.
        If an exception is supplied, and the method wishes to suppress the exception (i.e., prevent it from being
        propagated), it should return a true value. Otherwise, the exception will be processed normally upon exit
        from this method.
        Note that __exit__() methods should not reraise the passed-in exception; this is the caller’s responsibility.
        :param exc_type:
        :param exc_val:
        :param exc_tb:
        :return:
        """
        exit_start = time.perf_counter()
        self._timing('exit_start', exc_type=exc_type.__name__ if exc_type else '',
                     rvcontinue=getattr(self.wikiwho, 'rvcontinue', ''),
                     saved_rvcontinue=self.saved_rvcontinue)
        if not exc_type and not exc_val and not exc_tb and\
           self.wikiwho and self.wikiwho.rvcontinue != self.saved_rvcontinue:
            # if here is no error/exception
            # and there is a new revision or first revision of the article
            clean_start = time.perf_counter()
            self.wikiwho.clean_attributes()
            self._timing('clean_attributes_done', seconds='{:.3f}'.format(time.perf_counter() - clean_start))
            pickle_start = time.perf_counter()
            pickle_dump(self.wikiwho, self.pickle_path)
            self._timing('pickle_dump_done', seconds='{:.3f}'.format(time.perf_counter() - pickle_start),
                         pickle_path=self.pickle_path)
            # if self.save_tables:
            #     wikiwho_to_db_task.delay(self.wikiwho, self.language, self.save_tables)
        if self.cache_set:
            cache.delete(self.cache_key)
        # return True
        self._timing('exit_done', seconds='{:.3f}'.format(time.perf_counter() - exit_start))
