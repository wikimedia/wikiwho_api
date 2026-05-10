"""
API user messages and codes
"""
MESSAGES = {
    'article_not_in_wp': ('The article ({}) you are trying to request does not exist in {} Wikipedia.', '00'),
    'invalid_page_id': ('Please enter a valid page id ({}).', '01'),
    'invalid_namespace': ('Only articles! Namespace {} is not accepted.', '02'),
    'revision_under_process': ('Revision {} of the article ({}) is under process now. '
                               'Content of the requested revision will be available soon. '
                               'Try to request again in couple of minutes. (Max {} seconds).',
                               '03'),
    'revision_not_in_wp': ('The revision ({}) you are trying to request does not exist!', '04'),
    'wp_http_error': ('HTTP Response error from Wikipedia! Please try again later.', '10'),
    'wp_error': ('Wikipedia API returned the following error:', '11'),
    'wp_warning': ('Wikipedia API returned the following warning:', '12'),
    'wp_rate_limited': ('Wikipedia API rate limit reached. Waited {} seconds; next Retry-After was {} seconds. '
                        'Please try again later.', '13'),
    'already_exists': ('Article ({}) already exists.', '20'),
    'only_read_allowed': ('Only read is allowed for now.', '21'),
    'never_finished_article': ('Article cannot be processed.', '30'),
    'ignore_article_in_staging': ('Non-pickled article ({}) is ignored during staging.', '40'),
}
