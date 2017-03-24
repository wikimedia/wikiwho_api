# -*- coding: utf-8 -*-
from __future__ import absolute_import
from __future__ import print_function
from __future__ import unicode_literals

import signal

# from six.moves import urllib
from lxml import etree
import requests
from requests.exceptions import ReadTimeout

from django.conf import settings
from rest_framework.throttling import UserRateThrottle  # , AnonRateThrottle


def get_latest_revision_data(page_id=None, article_title=None, revision_id=None):
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
    headers = {'User-Agent': settings.WP_HEADERS_USER_AGENT,
               'From': settings.WP_HEADERS_FROM,
               "Accept": "*/*", "Host": settings.WP_SERVER}
    # make get request
    resp_ = requests.get(settings.WP_API_URL, params, headers=headers)
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
    return {'page_id': page['pageid'],
            'article_db_title': page['title'].replace(' ', '_'),
            'latest_revision_id': page["lastrevid"],
            'namespace': page["ns"]}


def get_revision_timestamp(revision_ids):
    # set up request for Wikipedia API.
    params = {'action': "query", 'prop': 'revisions', 'format': 'json',
              'rvprop': 'timestamp|ids', 'revids': '|'.join(revision_ids)}
    headers = {'User-Agent': settings.WP_HEADERS_USER_AGENT,
               'From': settings.WP_HEADERS_FROM,
               "Accept": "*/*", "Host": settings.WP_SERVER}
    # make get request
    try:
        resp_ = requests.get(settings.WP_API_URL, params, headers=headers, timeout=3)
    except ReadTimeout:
        return {'error': 'Bad revision ids.'}
    response = resp_.json()  # convert response into dict
    pages = response["query"].get('pages', [])
    if len(pages) != 1 or 'badrevids' in response['query']:
        # given rev ids must belong to 1 article
        return {'error': 'Bad revision ids.'}
    _, page = pages.popitem()
    timestamps = {str(rev['revid']): rev['timestamp'] for rev in page['revisions']}
    return [timestamps[rev_id] for rev_id in revision_ids]


def create_wp_session():
    # create session
    session = requests.session()
    session.auth = (settings.WP_USER, settings.WP_PASSWORD)
    headers = {'User-Agent': settings.WP_HEADERS_USER_AGENT,
               'From': settings.WP_HEADERS_FROM}
    session.headers.update(headers)
    # get token to log in
    r1 = session.post(settings.WP_API_URL, data={'action': 'query', 'meta': 'tokens',
                                                 'type': 'login', 'format': 'json'})
    token = r1.json()["query"]["tokens"]["logintoken"]
    # token = urllib.parse.quote(token)
    # log in
    r2 = session.post(settings.WP_API_URL, data={'action': 'login', 'format': 'json', 'lgname': settings.WP_USER,
                                                 'lgpassword': settings.WP_PASSWORD, 'lgtoken': token})
    return session


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
            result = session.get(url=settings.WP_API_URL, headers=headers, params=params)
        except:
            print("HTTP Response error! Try again later!")
        p = etree.XMLParser(huge_tree=True, encoding='utf-8')
        try:
            root = etree.fromstringlist(list(result.content), parser=p)
        except TypeError:
            root = etree.fromstring(result.content, parser=p)
        if root.find('error') is not None:
            print("Wikipedia API returned the following error: " + str(root.find('error').get('info')))
        query = root.find('query')
        if query is not None:
            pages = query.find('pages')
            if pages is not None:
                page = pages.find('page')
                if page is not None:
                    if page.get('_idx') == '-1':
                        print("The article ({}) you are trying to request does not exist!".format(article_name))
                    else:
                        if mediawiki_page.find('title') is None:
                            title = etree.SubElement(mediawiki_page, "title")
                            title.text = page.get('title', '')
                            ns = etree.SubElement(mediawiki_page, "ns")
                            ns.text = page.get('ns', '')
                            id = etree.SubElement(mediawiki_page, "id")
                            id.text = page.get('pageid', '')
                        for rev in root.find('query').find('pages').find('page').find('revisions').findall('rev'):
                            revision = etree.SubElement(mediawiki_page, "revision")
                            id = etree.SubElement(revision, "id")
                            id.text = rev.get('revid')
                            timestamp = etree.SubElement(revision, "timestamp")
                            timestamp.text = rev.get('timestamp', '')
                            contributor = etree.SubElement(revision, "contributor")
                            username = etree.SubElement(contributor, "username")
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
    # document.write(xml_file, pretty_print=True, xml_declaration=True, encoding)
