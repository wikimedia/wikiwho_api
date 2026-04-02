# -*- coding: utf-8 -*-
from __future__ import absolute_import
from __future__ import unicode_literals

import os
import sys
from requests.exceptions import ConnectionError

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

from .utils import get_latest_revision_data, create_wp_session, Timeout, generate_rvcontinue, get_wp_api_url
from .utils_pickles import pickle_dump, pickle_load, get_pickle_folder, UnpicklingError
from .models import RecursionErrorArticle, LongFailedArticle
from .messages import MESSAGES


sys.setrecursionlimit(5000)  # default is 1000
# http://neopythonic.blogspot.de/2009/04/tail-recursion-elimination.html
# session = create_wp_session()


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

    def __enter__(self):
        # time1 = time()
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
            d = get_latest_revision_data(
                self.language, self.page_id, self.article_title, self.revision_id)
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

        pickle_folder = self.pickle_folder or get_pickle_folder(self.language)
        self.pickle_path = "{}/{}.p".format(pickle_folder, self.page_id)
        self.already_exists = os.path.exists(self.pickle_path)
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
                    self.wikiwho = pickle_load(self.pickle_path)
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

        # time2 = time()
        # print("Execution time enter: {}".format(time2-time1))
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
        # time1 = time()
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
        while True:
            # continue downloading as long as we reach to the given rev_id
            # limit
            print(params)
            if rvcontinue != '0' and rvcontinue != '1':
                params['rvcontinue'] = rvcontinue
            try:
                result = session.get(url=get_wp_api_url(self.language), headers=settings.WP_HEADERS,
                                     params=params, timeout=settings.WP_REQUEST_TIMEOUT).json()
            except ConnectionError as e:
                try:
                    sub_error = e.args[0].args[1]
                except Exception:
                    sub_error = None
                if isinstance(sub_error, TimeoutError):
                    raise TimeoutError
                if is_api_call:
                    raise WPHandlerException(*MESSAGES['wp_http_error'])
                else:
                    # if not api query, raise the original exception
                    raise e
            except Exception as e:
                if is_api_call:
                    raise WPHandlerException(*MESSAGES['wp_http_error'])
                else:
                    # if not api query, raise the original exception
                    raise e

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
                    for i in range(len(revisions)):
                        # A revision may have texthidden, in which case the main slot looks like {'main': {'texthidden': ''}}
                        # So we skip those if we get a KeyError.
                        try:
                          revisions[i]['*'] = revisions[i]['slots']['main']['*']
                        except KeyError:
                          pass

                    self.wikiwho.analyse_article(revisions)

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
                self._set_wikiwho_rvcontinue()
                break
            rvcontinue = result['continue']['rvcontinue']
            # used at end to decide if there is new revisions to be saved
            self.wikiwho.rvcontinue = rvcontinue


        # self.load_chobs(chobstart_revid)
        # time2 = time()
        # print("Execution time handle: {}".format(time2-time1))

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
        # time1 = time()
        # print(exc_type, exc_val, exc_tb)
        if not exc_type and not exc_val and not exc_tb and\
           self.wikiwho and self.wikiwho.rvcontinue != self.saved_rvcontinue:
            # if here is no error/exception
            # and there is a new revision or first revision of the article
            self.wikiwho.clean_attributes()
            pickle_dump(self.wikiwho, self.pickle_path)
            # if self.save_tables:
            #     wikiwho_to_db_task.delay(self.wikiwho, self.language, self.save_tables)
        if self.cache_set:
            cache.delete(self.cache_key)
        # return True
        # time2 = time()
        # print("Execution time exit: {}".format(time2-time1))
