from __future__ import absolute_import, unicode_literals
from simplejson import JSONDecodeError
from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from requests import ReadTimeout

from django.core.cache import cache

from deployment.celery_config import default_task_soft_time_limit, user_task_soft_time_limit, long_task_soft_time_limit
from .handler import WPHandler, WPHandlerException
from .models import LongFailedArticle
from .utils import get_page_id_from_deletion_log_id
from .utils_pickles import pickle_delete

import logging
from django.conf import settings
from base.utils_log import get_base_logger

logger = get_base_logger('events_streamer', settings.EVENTS_STREAM_LOG, level=logging.WARNING)


def process_article_task(language, page_title, page_id=None, revision_id=None,
                         cache_key_timeout=0, raise_soft_time_limit=False, is_user_request=False):
    # if cache.get('page_{}'.format(page_id)) == '1':
    #     return False
    cache_key = None
    try:
        with WPHandler(page_title, page_id=page_id, revision_id=revision_id, language=language, is_user_request=is_user_request) as wp:
            cache_key = wp.cache_key
            wp.handle(revision_ids=[], is_api_call=False, timeout=cache_key_timeout)

        if wp.chobj_error != '':
            raise Exception(wp.chobj_error)

    except WPHandlerException as e:
        if cache_key:
            cache.delete(cache_key)
        if e.code == '03':
            # 03: if article is already under process, simply skip it. TODO wait and start a new task?
            return False
        if e.code == '00':
            # 00: 'article doesnt exist' error
            pickle_delete(page_id, language)
            return False
        raise e
    except SoftTimeLimitExceeded as e:
        cache.delete(cache_key)
        if raise_soft_time_limit:
            save_long_failed_article(wp, language)
            raise e
        else:
            process_article_long.delay(language, wp.saved_article_title or '', wp.page_id, revision_id)
    #         process_article_long.apply_async([page_title], queue='long_lasting')
    return True


def save_long_failed_article(wp, language):
    failed_rev_id = int(wp.wikiwho.revision_curr.id)
    failed_article, created = LongFailedArticle.objects.get_or_create(page_id=wp.page_id,
                                                                      language=language,
                                                                      defaults={'count': 1,
                                                                                'title': wp.saved_article_title or '',
                                                                                'revisions': [failed_rev_id]})
    if not created:
        failed_article.count += 1
        if failed_rev_id not in failed_article.revisions:
            failed_article.revisions.append(failed_rev_id)
            failed_article.save(update_fields=['count', 'modified', 'revisions'])
        else:
            failed_article.save(update_fields=['count', 'modified'])


# retry max 6 times (default value of max_retries is 3) and
# wait 360 seconds (default value of default_retry_delay is 180) between each retry.
@shared_task(ignore_result=True, bind=True, soft_time_limit=default_task_soft_time_limit, max_retries=6, default_retry_delay=6 * 60)
def process_article(self, language, page_title):
    try:
        process_article_task(language, page_title, cache_key_timeout=default_task_soft_time_limit)
    except WPHandlerException as e:
        if e.code =='40':
            # 40: Non-pickled articles are ignored during staging
            self.update_state(state="IGNORED")
            return e.message
        elif e.code in ['10', '11', '13']:
            # if wp errors
            # NOTE: actually 10 should not occur because we set is_api_call=False in the process_article_task!
            raise self.retry(exc=e)
        else:
            raise e
    except (ValueError, ConnectionError, ReadTimeout, JSONDecodeError) as e:
        # ReadTimeout -> requests timeout
        # JSONDecodeError -> WP api error from get_latest_revision_data or create_wp_session
        # FIXME are ConnectionResetError and ProtocolError during requests.get occurs due to SoftTimeLimitExceeded?
        raise self.retry(exc=e)


# retry max 6 times (default value of max_retries is 3) and
# wait 360 seconds (default value of default_retry_delay is 180) between each retry.
@shared_task(ignore_result=True, bind=True, soft_time_limit=user_task_soft_time_limit, max_retries=6, default_retry_delay=6 * 60)
def process_article_user(self, language, page_title, page_id=None, revision_id=None):
    try:
        process_article_task(language, page_title, page_id, revision_id, cache_key_timeout=user_task_soft_time_limit, is_user_request=True)
    except WPHandlerException as e:
        if e.code =='40':
            # 40: Non-pickled articles are ignored during staging
            self.update_state(state="IGNORED")
            return e.message
        elif e.code in ['10', '11', '13']:
            # if wp errors
            # NOTE: actually 10 should not occur because we set is_api_call=False in the process_article_task!
            raise self.retry(exc=e)
        else:
            raise e
    except (ValueError, ConnectionError, ReadTimeout, JSONDecodeError) as e:
        raise self.retry(exc=e)


# retry max 6 times (default value of max_retries is 3) and
# wait 360 seconds (default value of default_retry_delay is 180) between each retry.
@shared_task(ignore_result=True, bind=True, soft_time_limit=long_task_soft_time_limit, max_retries=6, default_retry_delay=6 * 60)
def process_article_long(self, language, page_title, page_id=None, revision_id=None):
    try:
        process_article_task(language, page_title, page_id, revision_id,
                             cache_key_timeout=long_task_soft_time_limit,
                             raise_soft_time_limit=True)
    except WPHandlerException as e:
        if e.code =='40':
            # 40: Non-pickled articles are ignored during staging
            self.update_state(state="IGNORED")
            return e.message
        elif e.code in ['10', '11', '13']:
            # if wp errors
            # NOTE: actually 10 should not occur because we set is_api_call=False in the process_article_task!
            raise self.retry(exc=e)
        else:
            raise e
    except (ValueError, ConnectionError, ReadTimeout, JSONDecodeError) as e:
        raise self.retry(exc=e)


def process_article_deletion(language, page_id):
    pickle_delete(page_id, language)
    logger.info(f"DELETED: {page_id} ({language})")


# This is a celery task because it gets called immediately when a page is deleted, and sometimes
# on the first run the logevents API doesn't give results because it reads from the replica database.
# Retry max 3 times, wait 10 seconds between each retry.
@shared_task(ignore_result=True, bind=True, soft_time_limit=default_task_soft_time_limit, max_retries=3, default_retry_delay=10)
def process_article_deletion_from_log_id(self, language, page_title, log_id):
    try:
        page_id = get_page_id_from_deletion_log_id(page_title, language, log_id)
        if page_id is None:
            logger.error(f"Failed to retrieve page ID for '{page_title}' ({language}).")
            e = BaseException('process_article_deletion retry')
            raise self.retry(exc=e)
        else:
            process_article_deletion(language, page_id)
    except WPHandlerException as e:
        if e.code =='40':
            # 40: Non-pickled articles are ignored during staging
            self.update_state(state="IGNORED")
            return e.message
        elif e.code in ['10', '11', '13']:
            # if wp errors
            # NOTE: actually 10 should not occur because we set is_api_call=False in the process_article_task!
            raise self.retry(exc=e)
        else:
            raise e
    except (ValueError, ConnectionError, ReadTimeout, JSONDecodeError) as e:
        raise self.retry(exc=e)


# # retry max 3 times (default value of max_retries) and
# # wait 180 seconds (default value of default_retry_delay) between each retry.
# @shared_task(ignore_result=True, bind=True, soft_time_limit=db_time_limit)
# def wikiwho_to_db_task(self, wikiwho, language, save_tables=('article', 'revision', 'token',)):
#     try:
#         wikiwho_to_db(wikiwho, language, save_tables)
#     except Exception as e:
#         raise self.retry(exc=e)
