# -*- coding: utf-8 -*-
from __future__ import absolute_import
from __future__ import print_function
from __future__ import unicode_literals

import signal
import pytz
import sys

# from six.moves import urllib
from lxml import etree
import requests
from requests.exceptions import ReadTimeout
from datetime import datetime, timedelta
from copy import deepcopy

from django.conf import settings
from django.utils.translation import get_language
from rest_framework.throttling import UserRateThrottle  # , AnonRateThrottle
from .wp_connection import MediaWiki
from time import sleep
from requests_oauthlib import OAuth1

def get_wp_api_url(language=None):
    return settings.WP_API_URL.format(language or get_language())


def create_wp_session(language=None):
    # create session
    session = requests.session()
    # session.auth = (settings.WP_USER, settings.WP_PASSWORD)
    oauth_values = (
        getattr(settings, 'WP_CONSUMER_TOKEN', ''),
        getattr(settings, 'WP_CONSUMER_SECRET', ''),
        getattr(settings, 'WP_ACCESS_TOKEN', ''),
        getattr(settings, 'WP_ACCESS_SECRET', ''),
    )
    if all(oauth_values):
        session.auth = OAuth1(settings.WP_CONSUMER_TOKEN,
                  client_secret=settings.WP_CONSUMER_SECRET,
                  resource_owner_key=settings.WP_ACCESS_TOKEN,
                  resource_owner_secret=settings.WP_ACCESS_SECRET)
    session.headers.update(settings.WP_HEADERS)
    # get token to log in
    #wp_api_url = get_wp_api_url(language)
    #r1 = session.post(wp_api_url, data={'action': 'query', 'meta': 'tokens',
    #                                    'type': 'login', 'format': 'json'})
    #token = r1.json()["query"]["tokens"]["logintoken"]
    # token = urllib.parse.quote(token)
    # log in
    #r2 = session.post(wp_api_url, data={'action': 'login', 'format': 'json', 'lgname': settings.WP_USER,
    #                                    'lgpassword': settings.WP_PASSWORD, 'lgtoken': token})
    return session

def create_wp_session2(language=None):
    # create session
    session = requests.session()
    #session.auth = (settings.WP_USER, settings.WP_PASSWORD)
    session.headers.update(settings.WP_HEADERS)
    return session

def create_wiki_session(language, logger):
    wiki = MediaWiki(get_wp_api_url(language), headers=settings.WP_HEADERS)
    return wiki
    #if wiki.login(settings.WP_USER, settings.WP_PASSWORD):
    #    return wiki
    #else:
    #    logger.error("Login into wikipedia failed")
    #    raise Exception("Login into wikipedia failed")


def insistent_request(wiki_session, params, logger, attempts=20):

    for attempt in range(1, attempts + 1):
        try:
            # return wiki_session.get(wiki_session, params=params).json()
            return wiki_session.call(params)
        except Exception as exc:
            if attempt == attempts:
                logger.exception(str(exc))
                raise exc
            else:
                logger.error(f"Request ({wiki_session._api_url}: {str(params)}) failed "
                             f"(attempt {attempt} of {attempts})")
                sleep(10)


def query(wiki_session, params, _all, logger, request_number=3, lastContinue={}):

    params['action'] = 'query'
    params['format'] = 'json'
    counter = 0

    # if (settings.DEBUG or settings.TESTING):
    #    lastContinue = {'gapcontinue': 'z', 'continue': 'gapcontinue||'}

    while _all | (counter < request_number):

        # Clone original params
        req = params.copy()

        # Modify it with the values returned in the 'continue' section of the
        # last result.
        req.update(lastContinue)

        # Call API
        result = insistent_request(wiki_session, req, logger)

        if 'error' in result:
            logger.error("ERROR in result: " + str(result['error']) + "\n"
                         "Full result of the request: " + str(result))
            raise Exception(result['error'])
        if 'warnings' in result:
            logger.error(result['warnings'])
        if 'query' in result:
            counter += 1
            yield req, result['query']
        if 'continue' not in result:
            break

        lastContinue = result['continue']


def get_latest_revision_timestamps(language, _all, logger):

    wiki_session = create_wiki_session(language, logger)
    #wiki_session = create_wp_session(language)

    params = {'action': 'query',
              'prop': 'revisions',
              'generator': 'allpages',
              'gaplimit': 'max',
              'rvprop': 'timestamp',
              'gapnamespace': '0',
              'format': 'json',
              'formatversion': '2',
              #'gapfilterredir': 'nonredirects'
              }

    for req, result in query(wiki_session, params, _all, logger):
        yield req, result


def get_page_data_from_wp_api(params, language='en'):
    """
    Example params:
    params = {'pageids': page_id, 'action': 'query', 'prop': 'revisions',
              'rvprop': 'content|ids|timestamp|sha1|comment|flags|user|userid',
              'rvlimit': 'max', 'format': 'json', 'continue': '', 'rvdir': 'newer',
              'rvendid': Revision ID to stop listing a}
    More info: https://www.mediawiki.org/wiki/API:Revisions

    :param params: Dictionary of parameters.
    :return: Revision data.
    """
    params = deepcopy(params)
    pageids = params.get('pageids')
    titles = params.get('titles')
    if pageids:
        pageids = str(pageids).split('|')
        if len(pageids) > 1:
            raise Exception('Please provide only 1 page id in params.')
        page_id = pageids[0]
    elif titles:
        titles = str(titles).split('|')
        if len(titles) > 1:
            raise Exception('Please provide only 1 page title in params.')
        page_title = titles[0]
    else:
        raise Exception(
            'Please provide "pageids" or "titles" parameter in params.')
    rvcontinue = params.get('rvcontinue', '0')

    session = create_wp_session()

    while True:
        # continue downloading as long as we reach to the given rev_id limit
        if rvcontinue != '0' and rvcontinue != '1':
            params['rvcontinue'] = rvcontinue

        # IIRC the params flag means the params you see tacked onto the end of
        # your url, while data is the POST data.
        result = session.get(url=get_wp_api_url(language), headers=settings.WP_HEADERS,
                             params=params, timeout=settings.WP_REQUEST_TIMEOUT)
        result = result.json()

        if 'error' in result:
            raise Exception(
                'Wikipedia API returned the following error:' + str(result['error']))

        # if 'query' in result:
        pages = result['query']['pages']
        if "-1" in pages:
            raise Exception('The article ({}) you are trying to request does not exist!'.
                            format(page_title or page_id))
        _, page = result['query']['pages'].popitem()
        for rev_data in page.get('revisions', []):
            yield rev_data

        if 'continue' not in result:
            break
        rvcontinue = result['continue']['rvcontinue']


def get_latest_revision_data(language, page_id=None, article_title=None, revision_id=None):
    if page_id:
        params = {'pageids': page_id}
    elif article_title:
        params = {'titles': article_title}
    elif revision_id:
        params = {'revids': revision_id}
    else:
        return ''
    # set up request for Wikipedia API.
    params.update({'action': "query", 'prop': 'info', 'format': 'json'})
    # params = {'action': "query", 'titles': article_title, 'format': 'json'}
    # make get request
    resp_ = requests.get(get_wp_api_url(language),
                         params=params, headers=settings.WP_HEADERS)
    response = resp_.json()  # convert response into dict
    pages = response["query"].get('pages')
    is_pages = False
    if pages:
        is_pages = True
        _, page = pages.popitem()
    if not is_pages or 'missing' in page or _ == '-1':
        # article title does not exist or contains invalid character
        return {'page_id': page_id,  # only return page id. because maybe article is deleted on wp but we still have it.
                'article_db_title': None,
                'latest_revision_id': None,
                'namespace': None}
    # NOTE: page['touched']: Page touched timestamp. Note that this can differ from the timestamp of the last revision.
    # https://www.mediawiki.org/wiki/API:Info
    return {'page_id': page['pageid'],
            'article_db_title': page['title'].replace(' ', '_'),
            'latest_revision_id': page["lastrevid"],
            'namespace': page["ns"]}


def get_revision_timestamp(revision_ids, language):
    # set up request for Wikipedia API.
    params = {'action': "query", 'prop': 'revisions', 'format': 'json',
              'rvprop': 'timestamp|ids', 'revids': '|'.join(revision_ids)}
    # make get request
    try:
        resp_ = requests.get(get_wp_api_url(language), params, headers=settings.WP_HEADERS,
                             timeout=settings.WP_REQUEST_TIMEOUT)
    except ReadTimeout:
        return {'error': 'Bad revision ids.'}
    response = resp_.json()  # convert response into dict
    pages = response["query"].get('pages', [])
    if len(pages) != 1 or 'badrevids' in response['query']:
        # given rev ids must belong to 1 article
        return {'error': 'Bad revision ids.'}
    _, page = pages.popitem()
    timestamps = {str(rev['revid']): rev['timestamp']
                  for rev in page['revisions']}
    return [timestamps[rev_id] for rev_id in revision_ids]


def get_page_id_from_deletion_log_id(page_title, language, log_id):
    params = {
        'action': 'query',
        'list': 'logevents',
        'leprop': 'ids',
        'letype': 'delete',
        'letitle': page_title,
        'format': 'json',
    }
    resp_ = requests.get(get_wp_api_url(language),
                         params=params, headers=settings.WP_HEADERS)
    response = resp_.json()
    events = response['query'].get('logevents')
    for event in events:
        if event['logid'] == log_id:
            return event['logpage']
    return None


class Timeout:

    def __init__(self, seconds=1, error_message='Timeout'):
        self.seconds = seconds
        self.error_message = error_message

    def handle_timeout(self, signum, frame):
        raise TimeoutError(self.error_message)

    def __enter__(self):
        signal.signal(signal.SIGALRM, self.handle_timeout)
        signal.alarm(self.seconds)

    def __exit__(self, type, value, traceback):
        signal.alarm(0)


def generate_rvcontinue(language, rev_id, rev_ts=None):
    """
    :param rev_id: Revision id, must be integer.
    :param rev_ts: revision timestamp, must be string representation.
    :return: rvcontinue
    """
    return_ts = False
    if rev_ts is None:
        return_ts = True
        try:
            rev_ts_list = get_revision_timestamp([str(rev_id)], language)
        except Exception:
            return '0', '0'
        if 'error' in rev_ts_list:
            return '0', '0'
        rev_ts = rev_ts_list[0]
    timestamp = datetime.strptime(
        rev_ts, '%Y-%m-%dT%H:%M:%SZ') + timedelta(seconds=1)
    rvcontinue = timestamp.strftime('%Y%m%d%H%M%S') + "|" + str(rev_id + 1)
    if return_ts:
        return rvcontinue, rev_ts
    else:
        return rvcontinue


def revert_rvcontinue(rvcontinue):
    timestamp = datetime.strptime(rvcontinue.split(
        '|')[0], '%Y%m%d%H%M%S') - timedelta(seconds=1)
    timestamp = timestamp.strftime('%Y-%m-%dT%H:%M:%SZ')
    return timestamp


def get_throttle_data(request):
    throttle_dict = {}
    if request.user.is_authenticated:
        user_rate = UserRateThrottle()
        cache_key = user_rate.get_cache_key(request, None)
        history = user_rate.cache.get(cache_key)
        if history:
            throttle_dict[user_rate.scope] = {
                'allowed': user_rate.rate,
                'used': len(history),
                'remaining_duration': user_rate.duration - (user_rate.timer() - history[-1])}
        else:
            throttle_dict[user_rate.scope] = {
                'allowed': user_rate.rate,
                'used': None,
                'remaining_duration': user_rate.duration}
        user_rate.scope = 'burst'
        throttle_dict[user_rate.scope] = {'allowed': user_rate.get_rate()}
    else:
        pass
        # anon_rate = AnonRateThrottle()
        # cache_key = anon_rate.get_cache_key(request, None)
        # history = anon_rate.cache.get(cache_key)
        # throttle_dict[anon_rate.scope] = {'allowed': anon_rate.rate, 'used': len(history) if history else None}
        # anon_rate.scope = 'burst'
        # throttle_dict[anon_rate.scope] = {'allowed': anon_rate.get_rate()}
    return throttle_dict


def get_article_xml(article_name):
    """
    Imports full revision history of an wikipedia article as a xml file. The format is changed to be able to
    used by wikimedia utilities in original (paper) code.
    """
    article_name = article_name.replace(" ", "_")

    session = create_wp_session()

    # revisions: Returns revisions for a given page
    params = {'titles': article_name, 'action': 'query', 'prop': 'revisions',
              'rvprop': 'content|ids|timestamp|sha1|comment|flags|user|userid',
              'rvlimit': 'max', 'format': 'xml', 'continue': '', 'rvdir': 'newer'}
    headers = {'User-Agent': settings.WP_HEADERS_USER_AGENT,
               'From': settings.WP_HEADERS_FROM}

    rvcontinue = True
    # document = None
    # xml_file = '/home/kenan/PycharmProjects/wikiwho_api/local/original_code_xml_tests/{}.xml'.format(article_name)
    xml_file = '{}.xml'.format(article_name)
    mediawiki = etree.Element("mediawiki")
    etree.SubElement(mediawiki, "siteinfo")
    mediawiki_page = etree.SubElement(mediawiki, "page")
    while rvcontinue:
        if rvcontinue is not True and rvcontinue != '0':
            params['rvcontinue'] = rvcontinue
            print(rvcontinue)
        try:
            result = session.get(url=get_wp_api_url(),
                                 headers=headers, params=params)
        except:
            print("HTTP Response error! Try again later!")
        p = etree.XMLParser(huge_tree=True, encoding='utf-8')
        try:
            root = etree.fromstringlist(list(result.content), parser=p)
        except TypeError:
            root = etree.fromstring(result.content, parser=p)
        if root.find('error') is not None:
            print("Wikipedia API returned the following error: " +
                  str(root.find('error').get('info')))
        query = root.find('query')
        if query is not None:
            pages = query.find('pages')
            if pages is not None:
                page = pages.find('page')
                if page is not None:
                    if page.get('_idx') == '-1':
                        print("The article ({}) you are trying to request does not exist!".format(
                            article_name))
                    else:
                        if mediawiki_page.find('title') is None:
                            title = etree.SubElement(mediawiki_page, "title")
                            title.text = page.get('title', '')
                            ns = etree.SubElement(mediawiki_page, "ns")
                            ns.text = page.get('ns', '')
                            id = etree.SubElement(mediawiki_page, "id")
                            id.text = page.get('pageid', '')
                        for rev in root.find('query').find('pages').find('page').find('revisions').findall('rev'):
                            revision = etree.SubElement(
                                mediawiki_page, "revision")
                            id = etree.SubElement(revision, "id")
                            id.text = rev.get('revid')
                            timestamp = etree.SubElement(revision, "timestamp")
                            timestamp.text = rev.get('timestamp', '')
                            contributor = etree.SubElement(
                                revision, "contributor")
                            username = etree.SubElement(
                                contributor, "username")
                            username.text = rev.get('user', '')
                            id = etree.SubElement(contributor, "id")
                            id.text = rev.get('userid', '0')
                            text = etree.SubElement(revision, "text")
                            text.text = rev.text
                            sha1 = etree.SubElement(revision, "sha1")
                            sha1.text = rev.get('sha1', '')
                            model = etree.SubElement(revision, "model")
                            model.text = rev.get('contentmodel', '')
                            format = etree.SubElement(revision, "format")
                            format.text = rev.get('contentformat', '')
        continue_ = root.find('continue')
        if continue_ is not None:
            rvcontinue = continue_.get('rvcontinue')
        else:
            rvcontinue = False
    document = etree.ElementTree(mediawiki)
    document.write(xml_file)
    # document.write(xml_file, pretty_print=True, xml_declaration=True,
    # encoding)
