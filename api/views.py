from simplejson import JSONDecodeError
import time

from rest_framework.decorators import detail_route, api_view, renderer_classes
from rest_framework.renderers import StaticHTMLRenderer, JSONRenderer
from rest_framework import permissions, status, authentication, throttling
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet
from rest_framework.schemas import SchemaGenerator  # , as_query_fields
from rest_framework_swagger.renderers import OpenAPIRenderer as OpenAPIRendererBase, \
    SwaggerUIRenderer as SwaggerUIRendererBase
# from rest_framework_extensions.cache.decorators import cache_response, CacheResponse
# from rest_framework.compat import coreapi, urlparse

# from django.utils.translation import get_language
from django.conf import settings
from django.views.generic.base import RedirectView
from django.urls import reverse
from django.utils.translation import get_language
# from django.core.signals import request_started, request_finished
# from django.http import HttpResponse

from rest_framework_tracking.mixins import LoggingMixin
from deployment.gunicorn_config import timeout as gunicorn_timeout
from deployment.celery_config import user_task_soft_time_limit
from .handler import WPHandler, WPHandlerException, debug_timing_enabled
from .swagger_data import custom_data, allowed_params, query_params, version_url
from .utils import get_revision_timestamp, Timeout
from .tasks import process_article_user
from .messages import MESSAGES


class OpenAPIRenderer(OpenAPIRendererBase):
    """
    Custom OpenAPIRenderer to update field types and descriptions.
    """
    def get_customizations(self):
        """
        Adds settings, overrides, etc. to the specification.
        """
        data = super(OpenAPIRenderer, self).get_customizations()
        # print(type(data), data)
        data['paths'] = custom_data['paths']
        data['info'] = custom_data['info']
        data['basePath'] = '/{}{}'.format(get_language(), custom_data['basePath'])
        # data['externalDocs'] = custom_data['externalDocs']
        # import pprint
        # pp = pprint.PrettyPrinter(indent=4)
        # print(type(data))
        # pp.pprint(data)
        return data


class SwaggerUIRenderer(SwaggerUIRendererBase):
    def set_context(self, renderer_context):
        super(SwaggerUIRenderer, self).set_context(renderer_context)
        renderer_context['is_ww_api'] = True


@api_view()
@renderer_classes([OpenAPIRenderer, SwaggerUIRenderer])
def schema_view(request, version):
    generator = SchemaGenerator(title='WikiWho API', urlconf='api.urls')
    schema = generator.get_schema(request=request)
    # print(type(schema), schema)
    return Response(schema)


class BurstRateThrottle(throttling.UserRateThrottle):
    """
    Limit authenticated users when they burst the api. Check DEFAULT_THROTTLE_RATES settings: 100/min
    """
    scope = 'burst'

    def allow_request(self, request, view):
        """
        Implement the check to see if the request should be throttled.

        On success calls `throttle_success`.
        On failure calls `throttle_failure`.
        """
        if self.rate is None:
            return True

        self.key = self.get_cache_key(request, view)
        if self.key is None:
            return True

        self.history = self.cache.get(self.key, [])
        self.now = self.timer()

        # Adjust if user has special privileges. 
        override_rate = settings.REST_FRAMEWORK['OVERRIDE_THROTTLE_RATES'].get(
            request.user.username.split('_')[0],
            None,
        )
        if override_rate is not None:
            self.num_requests, self.duration = self.parse_rate(override_rate)

        # Drop any requests from the history which have now passed the
        # throttle duration
        while self.history and self.history[-1] <= self.now - self.duration:
            self.history.pop()
        if len(self.history) >= self.num_requests:
            return self.throttle_failure()
        return self.throttle_success()



class WikiwhoView(object):

    def __init__(self, article=None, page_id=None):
        self.article = article
        self.page_id = page_id

    @staticmethod
    def _set_default_type_parameters(query_type, parameters):
        if query_type == 'rev_content' or query_type == 'all_content' or query_type == 'deleted_content':
            parameters.append('str')
        if query_type == 'rev_ids':
            parameters.append('rev_id')

    def get_parameters(self, query_type):
        """
        :return: Full parameters with default values.
        """
        parameters = []
        self._set_default_type_parameters(query_type, parameters)
        allowed_parameters = allowed_params[query_type]
        for parameter in query_params:
            if parameter['name'] in allowed_parameters:
                parameters.append(parameter['name'])
        if 'timestamp' in allowed_parameters:
            parameters.append('timestamp')
        if 'threshold' in allowed_parameters:
            if query_type == 'all_content':
                parameters.append(settings.ALL_CONTENT_THRESHOLD_LIMIT)
            else:
                parameters.append(settings.DELETED_CONTENT_THRESHOLD_LIMIT)
        return parameters

    def get_revision_content(self, wp, parameters, only_last_valid_revision=False, minimal=False,
                             from_db=False, with_token_ids=True):
        if not from_db:
            if minimal:
                return wp.wikiwho.get_revision_min_content(wp.revision_ids)
            else:
                return wp.wikiwho.get_revision_content(wp.revision_ids, parameters)

    def get_all_content(self, wp, parameters, minimal=False, from_db=False):
        if not from_db:
            return wp.wikiwho.get_all_content(parameters)
            if minimal:
                # TODO
                return wp.wikiwho.get_all_min_content()
            else:
                return wp.wikiwho.get_all_content(parameters)

    def get_deleted_content(self, wp, parameters, minimal=False, last_rev_id=None, from_db=False):
        # TODO get deleted content for a specific revision
        if not from_db:
            return wp.wikiwho.get_deleted_content(parameters)

    def get_revision_ids(self, wp, parameters=None, from_db=False):
        if not from_db:
            return wp.wikiwho.get_revision_ids(parameters)


class WikiwhoApiView(LoggingMixin, WikiwhoView, ViewSet):
    """
    import requests
    session = requests.session()

    from requests.auth import HTTPBasicAuth
    r1 = session.get(url, auth=HTTPBasicAuth('username', 'password'))
    OR
    session.auth = ('username', 'pass')

    r2 = session.get('http://127.0.0.1:8000/api/v1.0.0-beta/rev_content/thomas_Bellut/?origin_rev_id=true&editor=true&token_id=true&inbound=true&outbound=true')
    r2.json()
    """
    permission_classes = (permissions.IsAuthenticatedOrReadOnly, )  # TODO attention here!
    authentication_classes = (authentication.SessionAuthentication, authentication.BasicAuthentication)
    # authentication_classes = (authentication.TokenAuthentication, )
    throttle_classes = (throttling.AnonRateThrottle, BurstRateThrottle)
    renderer_classes = [JSONRenderer]  # to disable browsable api

    def get_parameters(self, query_type):
        all_parameters = super(WikiwhoApiView, self).get_parameters(query_type)
        parameters = []
        self._set_default_type_parameters(query_type, parameters)
        for parameter in all_parameters:
            if type(parameter) == int:
                if query_type == 'all_content':
                    threshold = int(self.request.GET.get('threshold', settings.ALL_CONTENT_THRESHOLD_LIMIT))
                else:
                    threshold = int(self.request.GET.get('threshold', settings.DELETED_CONTENT_THRESHOLD_LIMIT))
                parameters.append(0 if threshold < 0 else threshold)
            elif self.request.GET.get(parameter) == 'true':
                parameters.append(parameter)
        return parameters

    def get_response(self, parameters, article_title=None, page_id=None, revision_ids=list(),
                     all_content=False, deleted=False, rev_ids=False):
        # if not parameters:
        #     return Response({'Error': 'At least one query parameter should be selected.'},
        #                     status=status.HTTP_400_BAD_REQUEST)

        response_start = time.perf_counter()
        if debug_timing_enabled():
            print('[wikiwho-api-timing] view_get_response_start article_title={} page_id={} revision_ids={} parameters={}'.
                  format(article_title, page_id, revision_ids, parameters), flush=True)
        timeout = gunicorn_timeout - 60  # 5 mins
        timeout_message = 'Process took more than {} seconds. ' \
                          'Requested data will be available soon (Max {} seconds). ' \
                          'Please try again later.'.format(timeout, user_task_soft_time_limit)
        language = get_language()
        try:
            revision_id = revision_ids[0] if revision_ids else None
            if settings.DEBUG:
                # to run locally with Timeout: runserver --noreload --nothreading
                if debug_timing_enabled():
                    print('[wikiwho-api-timing] handler_context_start seconds={:.3f}'.
                          format(time.perf_counter() - response_start), flush=True)
                with WPHandler(article_title, page_id=page_id, revision_id=revision_id, language=language, is_user_request=True) as wp:
                    self.page_id = wp.page_id
                    wp.handle(revision_ids, is_api_call=True)
                if debug_timing_enabled():
                    print('[wikiwho-api-timing] handler_context_done seconds={:.3f}'.
                          format(time.perf_counter() - response_start), flush=True)
            else:
                with Timeout(seconds=timeout, error_message=timeout_message):
                    if debug_timing_enabled():
                        print('[wikiwho-api-timing] handler_context_start seconds={:.3f}'.
                              format(time.perf_counter() - response_start), flush=True)
                    with WPHandler(article_title, page_id=page_id, revision_id=revision_id, language=language, is_user_request=True) as wp:
                        self.page_id = wp.page_id
                        wp.handle(revision_ids, is_api_call=True, timeout=timeout)
                    if debug_timing_enabled():
                        print('[wikiwho-api-timing] handler_context_done seconds={:.3f}'.
                              format(time.perf_counter() - response_start), flush=True)
        except TimeoutError as e:
            # TODO ? process_article_user.delay(wp.saved_article_title, wp.page_id, )
            process_article_user.delay(language, article_title, page_id, revision_id)
            response = {'Info': timeout_message}
            status_ = status.HTTP_408_REQUEST_TIMEOUT
        except WPHandlerException as e:
            if e.code == '03':
                response = {'Info': e.message}
                status_ = status.HTTP_200_OK
            elif e.code == '30':
                response = {'Info': e.message}
                status_ = status.HTTP_408_REQUEST_TIMEOUT
            else:
                response = {'Error': e.message}
                if e.code in ['10', '11', '13']:
                    # WP errors
                    status_ = status.HTTP_503_SERVICE_UNAVAILABLE
                else:
                    status_ = status.HTTP_400_BAD_REQUEST
        except JSONDecodeError as e:
            response = {'Error': MESSAGES['wp_http_error'][0]}
            status_ = status.HTTP_503_SERVICE_UNAVAILABLE
        else:
            if all_content:
                build_start = time.perf_counter()
                response = self.get_all_content(wp, parameters)
                if debug_timing_enabled():
                    print('[wikiwho-api-timing] response_build_done type=all_content seconds={:.3f}'.
                          format(time.perf_counter() - build_start), flush=True)
                status_ = status.HTTP_200_OK
            elif deleted:
                build_start = time.perf_counter()
                response = self.get_deleted_content(wp, parameters)
                if debug_timing_enabled():
                    print('[wikiwho-api-timing] response_build_done type=deleted seconds={:.3f}'.
                          format(time.perf_counter() - build_start), flush=True)
                status_ = status.HTTP_200_OK
            elif rev_ids:
                build_start = time.perf_counter()
                response = self.get_revision_ids(wp, parameters)
                if debug_timing_enabled():
                    print('[wikiwho-api-timing] response_build_done type=rev_ids seconds={:.3f}'.
                          format(time.perf_counter() - build_start), flush=True)
                status_ = status.HTTP_200_OK
            else:
                build_start = time.perf_counter()
                response = self.get_revision_content(wp, parameters, from_db=False)
                if debug_timing_enabled():
                    token_count = 0
                    try:
                        for rev_data in response.get('revisions', []):
                            for _, payload in rev_data.items():
                                token_count += len(payload.get('tokens', []))
                    except AttributeError:
                        pass
                    print('[wikiwho-api-timing] response_build_done type=rev_content seconds={:.3f} tokens={}'.
                          format(time.perf_counter() - build_start, token_count), flush=True)
                if 'Error' in response:
                    status_ = status.HTTP_400_BAD_REQUEST
                else:
                    status_ = status.HTTP_200_OK
        # handler_time = time.time() - handler_start
        # return HttpResponse(json.dumps(response), content_type='application/json; charset=utf-8')
        # import json
        # with open('tmp_pickles/{}_ri.json'.format(article_title), 'w') as f:
        #     f.write(json.dumps(response, indent=4, separators=(',', ': '), sort_keys=True, ensure_ascii=False))
        if debug_timing_enabled():
            print('[wikiwho-api-timing] view_get_response_done status={} total_seconds={:.3f}'.
                  format(status_, time.perf_counter() - response_start), flush=True)
        return Response(response, status=status_)

    def get_rev_content_by_rev_id(self, request, version, rev_id):
        parameters = self.get_parameters('rev_content')
        return self.get_response(parameters, revision_ids=[int(rev_id)])

    # @detail_route(renderer_classes=(StaticHTMLRenderer,))
    def get_range_rev_content(self, request, version, article_title, start_rev_id, end_rev_id):
        timestamps = get_revision_timestamp([start_rev_id, end_rev_id], get_language())
        if 'error' in timestamps:
            return Response({'Error': timestamps['error']},
                            status=status.HTTP_400_BAD_REQUEST)
        elif timestamps[0] > timestamps[1]:
            return Response({'Error': 'End revision id has to be older than start revision id!'},
                            status=status.HTTP_400_BAD_REQUEST)
        parameters = self.get_parameters('rev_content')
        return self.get_response(parameters, article_title, revision_ids=[int(start_rev_id), int(end_rev_id)])

    # @detail_route(renderer_classes=(StaticHTMLRenderer,))
    def get_article_rev_content(self, request, version, article_title, rev_id):
        parameters = self.get_parameters('rev_content')
        return self.get_response(parameters, article_title, revision_ids=[int(rev_id)])

    # @detail_route(renderer_classes=(StaticHTMLRenderer,))
    def get_rev_content_by_title(self, request, version, article_title):
        parameters = self.get_parameters('rev_content')
        return self.get_response(parameters, article_title)

    def get_rev_content_by_page_id(self, request, version, page_id):
        parameters = self.get_parameters('rev_content')
        return self.get_response(parameters, page_id=page_id)

    # @detail_route(renderer_classes=(StaticHTMLRenderer,))
    def get_deleted_content_by_title(self, request, version, article_title):
        parameters = self.get_parameters('deleted_content')
        return self.get_response(parameters, article_title, deleted=True)

    def get_deleted_content_by_page_id(self, request, version, page_id):
        parameters = self.get_parameters('deleted_content')
        return self.get_response(parameters, page_id=page_id, deleted=True)

    def get_all_content_by_title(self, request, version, article_title):
        parameters = self.get_parameters('all_content')
        return self.get_response(parameters, article_title, all_content=True)

    def get_all_content_by_page_id(self, request, version, page_id):
        parameters = self.get_parameters('all_content')
        return self.get_response(parameters, page_id=page_id, all_content=True)

    # @detail_route(renderer_classes=(StaticHTMLRenderer,))
    def get_rev_ids_by_title(self, request, version, article_title):
        parameters = self.get_parameters('rev_ids')
        return self.get_response(parameters, article_title, rev_ids=True)

    def get_rev_ids_by_page_id(self, request, version, page_id):
        parameters = self.get_parameters('rev_ids')
        return self.get_response(parameters, page_id=page_id, rev_ids=True)

    # def dispatch(self, request, *args, **kwargs):
    #     global dispatch_time
    #     global render_time
    #
    #     dispatch_start = time.time()
    #     ret = super(WikiwhoApiView, self).dispatch(request, *args, **kwargs)
    #
    #     render_start = time.time()
    #     # ret.render()
    #     render_time = time.time() - render_start
    #
    #     dispatch_time = time.time() - dispatch_start
    #     return ret
    #
    # def started(sender, **kwargs):
    #     global started
    #     started = time.time()
    #
    # def finished(sender, **kwargs):
    #     total = time.time() - started
    #     api_view_time = dispatch_time - (render_time + handler_time)
    #     request_response_time = total - dispatch_time
    #
    #     # print ("Database lookup               | %.4fs" % db_time)
    #     # print ("Serialization                 | %.4fs" % serializer_time)
    #     print ("Django request/response       | %.4fs" % request_response_time)
    #     print ("API view                      | %.4fs" % api_view_time)
    #     print ("Response rendering            | %.4fs" % render_time)
    #     print ("handler_time                  | %.4fs" % handler_time)
    #     print ("total                         | %.4fs" % total)
    #
    # request_started.connect(started)
    # request_finished.connect(finished)


class ApiRedirectView(RedirectView):
    permanent = False  # 302
    # pattern_name = 'api:swagger'

    def get_redirect_url(self, *args, **kwargs):
        return reverse('api:swagger', kwargs={'version': version_url})
