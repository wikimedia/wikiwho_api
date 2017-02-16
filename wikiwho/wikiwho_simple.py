# -*- coding: utf-8 -*-
"""
Created on Feb 20, 2013

@author: Maribel Acosta
@author: Fabian Floeck
@author: Andriy Rodchenko
"""
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

from difflib import Differ

from .structures import Word, Sentence, Paragraph, Revision
from .utils import calculate_hash, split_into_paragraphs, split_into_sentences, split_into_tokens, \
    compute_avg_word_freq, iter_rev_tokens


# Spam detection variables.
CHANGE_PERCENTAGE = -0.40
PREVIOUS_LENGTH = 1000
CURR_LENGTH = 1000
FLAG = "move"
UNMATCHED_PARAGRAPH = 0.0
WORD_DENSITY = 10
WORD_LEN = 100


class Wikiwho:
    def __init__(self, article_title):
        # Hash tables.
        self.paragraphs_ht = {}
        self.sentences_ht = {}

        self.spam_ids = []
        self.spam_hashes = []
        self.tokens = []  # [word_obj, ..] ordered, unique list of tokens of this article
        self.revisions = {}  # {rev_id : rev_obj, ...}
        self.ordered_revisions = []  # [rev_id, ...]
        self.rvcontinue = '0'
        self.title = article_title
        self.page_id = None  # article id
        self.token_id = 0  # sequential id for tokens in article. unique per token per article.
        # Revisions to compare.
        self.revision_curr = Revision()
        self.revision_prev = Revision()

        self.text_curr = ''
        self.temp = []

    def clean_attributes(self):
        """
        Empty attributes that are usually not needed after analyzing an article.

        Making them empty reduces pickle size too.
        """
        self.revision_prev = None
        self.text_curr = ''
        self.temp = []

    def analyse_article_xml(self, page):
        # Iterate over revisions of the article.
        for revision in page:
            text = revision.text or ''
            if not text and (revision.deleted.text or revision.deleted.restricted):
                # equivalent of "'texthidden' in revision or 'textmissing' in revision" in analyse_article
                continue

            vandalism = False
            # Update the information about the previous revision.
            self.revision_prev = self.revision_curr

            rev_id = revision.id
            rev_hash = revision.sha1 or calculate_hash(text)
            if rev_id in self.spam_ids:
                vandalism = True

            # TODO: spam detection: DELETION
            text_len = len(text)
            if not vandalism and not(revision.comment and revision.minor):
                # if content is not moved (flag) to different article in good faith, check for vandalism
                # if revisions have reached a certain size
                if self.revision_prev.length > PREVIOUS_LENGTH and \
                   text_len < CURR_LENGTH and \
                   ((text_len-self.revision_prev.length) / self.revision_prev.length) <= CHANGE_PERCENTAGE:
                    # VANDALISM: CHANGE PERCENTAGE - DELETION
                    vandalism = True

            if vandalism:
                # print("---------------------------- FLAG 1")
                self.revision_curr = self.revision_prev
                self.spam_ids.append(rev_id)
                self.spam_hashes.append(rev_hash)
            else:
                # Information about the current revision.
                self.revision_curr = Revision()
                self.revision_curr.id = rev_id
                self.revision_curr.length = text_len
                self.revision_curr.timestamp = revision.timestamp.long_format()

                # Get editor information
                if revision.user:
                    contributor_name = revision.user.text or ''  # Not Available
                    if revision.user.id is None and contributor_name or revision.user.id == 0:
                        contributor_id = 0
                    else:
                        contributor_id = revision.user.id or ''
                else:
                    # Some revisions don't have contributor.
                    contributor_name = ''
                    contributor_id = ''
                editor = contributor_id
                editor = str(editor) if editor != 0 else '0|{}'.format(contributor_name)
                self.revision_curr.editor = editor

                # Content within the revision.
                self.text_curr = text.lower()

                # Perform comparison.
                vandalism = self.determine_authorship()

                if vandalism:
                    # print "---------------------------- FLAG 2"
                    self.revision_curr = self.revision_prev  # skip revision with vandalism in history
                    self.spam_ids.append(rev_id)
                    self.spam_hashes.append(rev_hash)
                else:
                    # Add the current revision with all the information.
                    self.revisions.update({self.revision_curr.id: self.revision_curr})
                    self.ordered_revisions.append(self.revision_curr.id)
            self.temp = []

    def analyse_article(self, revisions):
        # Iterate over revisions of the article.
        for revision in revisions:
            if 'texthidden' in revision or 'textmissing' in revision:
                continue

            vandalism = False
            # Update the information about the previous revision.
            self.revision_prev = self.revision_curr

            text = revision.get('*', '')
            rev_id = int(revision['revid'])
            rev_hash = revision.get('sha1', calculate_hash(text))
            if rev_id in self.spam_ids:
                vandalism = True

            # TODO: spam detection: DELETION
            text_len = len(text)
            if not vandalism and not(revision.get('comment') and 'minor' in revision):
                # if content is not moved (flag) to different article in good faith, check for vandalism
                # if revisions have reached a certain size
                if self.revision_prev.length > PREVIOUS_LENGTH and \
                   text_len < CURR_LENGTH and \
                   ((text_len-self.revision_prev.length) / self.revision_prev.length) <= CHANGE_PERCENTAGE:
                    # VANDALISM: CHANGE PERCENTAGE - DELETION
                    vandalism = True

            if vandalism:
                # print("---------------------------- FLAG 1")
                self.revision_curr = self.revision_prev
                self.spam_ids.append(rev_id)
                self.spam_hashes.append(rev_hash)
            else:
                # Information about the current revision.
                self.revision_curr = Revision()
                self.revision_curr.id = rev_id
                self.revision_curr.length = text_len
                self.revision_curr.timestamp = revision['timestamp']

                # Get editor information.
                # Some revisions don't have editor.
                contributor_id = revision.get('userid', '')
                contributor_name = revision.get('user', '')
                editor = contributor_id
                editor = str(editor) if editor != 0 else '0|{}'.format(contributor_name)
                self.revision_curr.editor = editor

                # Content within the revision.
                self.text_curr = text.lower()

                # Perform comparison.
                vandalism = self.determine_authorship()

                if vandalism:
                    # print "---------------------------- FLAG 2"
                    self.revision_curr = self.revision_prev  # skip revision with vandalism in history
                    self.spam_ids.append(rev_id)
                    self.spam_hashes.append(rev_hash)
                else:
                    # Add the current revision with all the information.
                    self.revisions.update({self.revision_curr.id: self.revision_curr})
                    self.ordered_revisions.append(self.revision_curr.id)
            self.temp = []

    def determine_authorship(self):
        # Containers for unmatched paragraphs and sentences in both revisions.
        unmatched_sentences_curr = []
        unmatched_sentences_prev = []
        matched_sentences_prev = []
        matched_words_prev = []
        possible_vandalism = False
        vandalism = False

        # Analysis of the paragraphs in the current revision.
        unmatched_paragraphs_curr, unmatched_paragraphs_prev, matched_paragraphs_prev = \
            self.analyse_paragraphs_in_revision()

        # Analysis of the sentences in the unmatched paragraphs of the current revision.
        if unmatched_paragraphs_curr:
            unmatched_sentences_curr, unmatched_sentences_prev, matched_sentences_prev, total_sentences = \
                self.analyse_sentences_in_paragraphs(unmatched_paragraphs_curr, unmatched_paragraphs_prev)

            # TODO: spam detection
            if len(unmatched_paragraphs_curr) / len(self.revision_curr.ordered_paragraphs) > UNMATCHED_PARAGRAPH:
                # will be used to detect copy-paste vandalism - token density
                possible_vandalism = True

            # Analysis of words in unmatched sentences (diff of both texts).
            if unmatched_sentences_curr:
                matched_words_prev, vandalism = self.analyse_words_in_sentences(unmatched_sentences_curr,
                                                                                unmatched_sentences_prev,
                                                                                possible_vandalism)

        if not vandalism:
            # Add the information of 'deletion' to words
            for unmatched_sentence in unmatched_sentences_prev:
                for word_prev in unmatched_sentence.words:
                    if not word_prev.matched:
                        word_prev.outbound.append(self.revision_curr.id)
            if not unmatched_sentences_prev:
                # if all current paragraphs are matched
                for unmatched_paragraph in unmatched_paragraphs_prev:
                    for sentence_hash in unmatched_paragraph.sentences:
                        for sentence in unmatched_paragraph.sentences[sentence_hash]:
                            for word_prev in sentence.words:
                                if not word_prev.matched:
                                    word_prev.outbound.append(self.revision_curr.id)

        # Reset matched structures from old revisions.
        for matched_paragraph in matched_paragraphs_prev:
            matched_paragraph.matched = False
            for sentence_hash in matched_paragraph.sentences:
                for sentence in matched_paragraph.sentences[sentence_hash]:
                    sentence.matched = False
                    for word_prev in sentence.words:
                        # first update inbound and last used info of matched words of all previous revisions
                        if not vandalism and word_prev.matched and \
                                (not word_prev.outbound or word_prev.outbound[-1] != self.revision_curr.id):
                            if word_prev.last_rev_id != self.revision_prev.id:
                                word_prev.inbound.append(self.revision_curr.id)
                            word_prev.last_rev_id = self.revision_curr.id
                        # reset
                        word_prev.matched = False

        for matched_sentence in matched_sentences_prev:
            matched_sentence.matched = False
            for word_prev in matched_sentence.words:
                # first update inbound and last used info of matched words of all previous revisions
                if not vandalism and word_prev.matched and \
                        (not word_prev.outbound or word_prev.outbound[-1] != self.revision_curr.id):
                    if word_prev.last_rev_id != self.revision_prev.id:
                        word_prev.inbound.append(self.revision_curr.id)
                    word_prev.last_rev_id = self.revision_curr.id
                # reset
                word_prev.matched = False

        for matched_word in matched_words_prev:
            # first update last used info of matched prev words
            # there is no inbound chance because we only diff with words of previous revision
            if not vandalism and word_prev.matched:
                if not word_prev.outbound or word_prev.outbound[-1] != self.revision_curr.id:
                    word_prev.last_rev_id = self.revision_curr.id
            # reset
            matched_word.matched = False

        if not vandalism:
            # Add the new paragraphs to hash table of paragraphs.
            for unmatched_paragraph in unmatched_paragraphs_curr:
                if unmatched_paragraph.hash_value in self.paragraphs_ht:
                    self.paragraphs_ht[unmatched_paragraph.hash_value].append(unmatched_paragraph)
                else:
                    self.paragraphs_ht.update({unmatched_paragraph.hash_value: [unmatched_paragraph]})
                unmatched_paragraph.value = ''  # hash value is not used for next rev analysis

            # Add the new sentences to hash table of sentences.
            for unmatched_sentence in unmatched_sentences_curr:
                if unmatched_sentence.hash_value in self.sentences_ht:
                    self.sentences_ht[unmatched_sentence.hash_value].append(unmatched_sentence)
                else:
                    self.sentences_ht.update({unmatched_sentence.hash_value: [unmatched_sentence]})
                unmatched_sentence.value = ''  # hash value is not used for next rev analysis
                unmatched_sentence.splitted = None  # splitted word values are not used for next rev analysis

        return vandalism

    def analyse_paragraphs_in_revision(self):
        # Containers for unmatched and matched paragraphs.
        unmatched_paragraphs_curr = []
        unmatched_paragraphs_prev = []
        matched_paragraphs_prev = []

        # Split the text of the current into paragraphs.
        paragraphs = split_into_paragraphs(self.text_curr)

        # Iterate over the paragraphs of the current version.
        for paragraph in paragraphs:
            # Build Paragraph structure and calculate hash value.
            paragraph = paragraph.strip()
            if not paragraph:
                # dont track empty lines
                continue
            hash_curr = calculate_hash(paragraph)
            matched_curr = False

            # If the paragraph is in the previous revision,
            # update the authorship information and mark both paragraphs as matched (also in HT).
            for paragraph_prev in self.revision_prev.paragraphs.get(hash_curr, []):
                if not paragraph_prev.matched:
                    matched_one = False
                    matched_all = True
                    for h in paragraph_prev.sentences:
                        for s_prev in paragraph_prev.sentences[h]:
                            for w_prev in s_prev.words:
                                if w_prev.matched:
                                    matched_one = True
                                else:
                                    matched_all = False

                    if not matched_one:
                        # if there is not any already matched prev word, so set them all as matched
                        matched_curr = True
                        paragraph_prev.matched = True
                        matched_paragraphs_prev.append(paragraph_prev)

                        # Set all sentences and words of this paragraph as matched
                        for hash_sentence_prev in paragraph_prev.sentences:
                            for sentence_prev in paragraph_prev.sentences[hash_sentence_prev]:
                                sentence_prev.matched = True
                                for word_prev in sentence_prev.words:
                                    word_prev.matched = True

                        # Add paragraph to current revision.
                        if hash_curr in self.revision_curr.paragraphs:
                            self.revision_curr.paragraphs[hash_curr].append(paragraph_prev)
                        else:
                            self.revision_curr.paragraphs.update({paragraph_prev.hash_value: [paragraph_prev]})
                        self.revision_curr.ordered_paragraphs.append(paragraph_prev.hash_value)
                        break
                    elif matched_all:
                        # if all prev words in this paragraph are already matched
                        paragraph_prev.matched = True
                        # for hash_sentence_prev in paragraph_prev.sentences:
                        #     for sentence_prev in paragraph_prev.sentences[hash_sentence_prev]:
                        #         sentence_prev.matched = True
                        matched_paragraphs_prev.append(paragraph_prev)

            # If the paragraph is not in the previous revision, but it is in an older revision
            # update the authorship information and mark both paragraphs as matched.
            if not matched_curr:
                for paragraph_prev in self.paragraphs_ht.get(hash_curr, []):
                    if not paragraph_prev.matched:
                        matched_one = False
                        matched_all = True
                        for h in paragraph_prev.sentences:
                            for s_prev in paragraph_prev.sentences[h]:
                                for w_prev in s_prev.words:
                                    if w_prev.matched:
                                        matched_one = True
                                    else:
                                        matched_all = False

                        if not matched_one:
                            # if there is not any already matched prev word, so set them all as matched
                            matched_curr = True
                            paragraph_prev.matched = True
                            matched_paragraphs_prev.append(paragraph_prev)

                            # Set all sentences and words of this paragraph as matched
                            for hash_sentence_prev in paragraph_prev.sentences:
                                for sentence_prev in paragraph_prev.sentences[hash_sentence_prev]:
                                    sentence_prev.matched = True
                                    for word_prev in sentence_prev.words:
                                        word_prev.matched = True

                            # Add paragraph to current revision.
                            if hash_curr in self.revision_curr.paragraphs:
                                self.revision_curr.paragraphs[hash_curr].append(paragraph_prev)
                            else:
                                self.revision_curr.paragraphs.update({paragraph_prev.hash_value: [paragraph_prev]})
                            self.revision_curr.ordered_paragraphs.append(paragraph_prev.hash_value)
                            break
                        elif matched_all:
                            # if all prev words in this paragraph are already matched
                            paragraph_prev.matched = True
                            # for hash_sentence_prev in paragraph_prev.sentences:
                            #     for sentence_prev in paragraph_prev.sentences[hash_sentence_prev]:
                            #         sentence_prev.matched = True
                            matched_paragraphs_prev.append(paragraph_prev)

            # If the paragraph did not match with previous revisions,
            # add to container of unmatched paragraphs for further analysis.
            if not matched_curr:
                paragraph_curr = Paragraph()
                paragraph_curr.hash_value = hash_curr
                paragraph_curr.value = paragraph

                if hash_curr in self.revision_curr.paragraphs:
                    self.revision_curr.paragraphs[hash_curr].append(paragraph_curr)
                else:
                    self.revision_curr.paragraphs.update({paragraph_curr.hash_value: [paragraph_curr]})
                self.revision_curr.ordered_paragraphs.append(paragraph_curr.hash_value)
                unmatched_paragraphs_curr.append(paragraph_curr)

        # Identify unmatched paragraphs in previous revision for further analysis.
        for paragraph_prev_hash in self.revision_prev.ordered_paragraphs:
            if len(self.revision_prev.paragraphs[paragraph_prev_hash]) > 1:
                s = 'p-{}-{}'.format(self.revision_prev, paragraph_prev_hash)
                self.temp.append(s)
                count = self.temp.count(s)
                paragraph_prev = self.revision_prev.paragraphs[paragraph_prev_hash][count - 1]
            else:
                paragraph_prev = self.revision_prev.paragraphs[paragraph_prev_hash][0]
            if not paragraph_prev.matched:
                unmatched_paragraphs_prev.append(paragraph_prev)

        return unmatched_paragraphs_curr, unmatched_paragraphs_prev, matched_paragraphs_prev

    def analyse_sentences_in_paragraphs(self, unmatched_paragraphs_curr, unmatched_paragraphs_prev):
        # Containers for unmatched and matched sentences.
        unmatched_sentences_curr = []
        unmatched_sentences_prev = []
        matched_sentences_prev = []
        total_sentences = 0

        # Iterate over the unmatched paragraphs of the current revision.
        for paragraph_curr in unmatched_paragraphs_curr:
            # Split the current paragraph into sentences.
            sentences = split_into_sentences(paragraph_curr.value)
            # Iterate over the sentences of the current paragraph
            for sentence in sentences:
                # Create the Sentence structure.
                sentence = sentence.strip()
                if not sentence:
                    # dont track empty lines
                    continue
                sentence = ' '.join(split_into_tokens(sentence))
                hash_curr = calculate_hash(sentence)
                matched_curr = False
                total_sentences += 1

                # Iterate over the unmatched paragraphs from the previous revision.
                for paragraph_prev in unmatched_paragraphs_prev:
                    for sentence_prev in paragraph_prev.sentences.get(hash_curr, []):
                        if not sentence_prev.matched:
                            matched_one = False
                            matched_all = True
                            for word_prev in sentence_prev.words:
                                if word_prev.matched:
                                    matched_one = True
                                else:
                                    matched_all = False

                            if not matched_one:
                                # if there is not any already matched prev word, so set them all as matched
                                sentence_prev.matched = True
                                matched_curr = True
                                matched_sentences_prev.append(sentence_prev)

                                for word_prev in sentence_prev.words:
                                    word_prev.matched = True

                                # Add the sentence information to the paragraph.
                                if hash_curr in paragraph_curr.sentences:
                                    paragraph_curr.sentences[hash_curr].append(sentence_prev)
                                else:
                                    paragraph_curr.sentences.update({sentence_prev.hash_value: [sentence_prev]})
                                paragraph_curr.ordered_sentences.append(sentence_prev.hash_value)
                                break
                            elif matched_all:
                                # if all prev words in this sentence are already matched
                                sentence_prev.matched = True
                                matched_sentences_prev.append(sentence_prev)
                    if matched_curr:
                        break

                # Iterate over the hash table of sentences from old revisions.
                if not matched_curr:
                    for sentence_prev in self.sentences_ht.get(hash_curr, []):
                        if not sentence_prev.matched:
                            matched_one = False
                            matched_all = True
                            for word_prev in sentence_prev.words:
                                if word_prev.matched:
                                    matched_one = True
                                else:
                                    matched_all = False

                            if not matched_one:
                                # if there is not any already matched prev word, so set them all as matched
                                sentence_prev.matched = True
                                matched_curr = True
                                matched_sentences_prev.append(sentence_prev)

                                for word_prev in sentence_prev.words:
                                    word_prev.matched = True

                                # Add the sentence information to the paragraph.
                                if hash_curr in paragraph_curr.sentences:
                                    paragraph_curr.sentences[hash_curr].append(sentence_prev)
                                else:
                                    paragraph_curr.sentences.update({sentence_prev.hash_value: [sentence_prev]})
                                paragraph_curr.ordered_sentences.append(sentence_prev.hash_value)
                                break
                            elif matched_all:
                                # if all prev words in this sentence are already matched
                                sentence_prev.matched = True
                                matched_sentences_prev.append(sentence_prev)

                # If the sentence did not match,
                # then include in the container of unmatched sentences for further analysis.
                if not matched_curr:
                    sentence_curr = Sentence()
                    sentence_curr.value = sentence
                    sentence_curr.hash_value = hash_curr

                    if hash_curr in paragraph_curr.sentences:
                        paragraph_curr.sentences[hash_curr].append(sentence_curr)
                    else:
                        paragraph_curr.sentences.update({sentence_curr.hash_value: [sentence_curr]})
                    paragraph_curr.ordered_sentences.append(sentence_curr.hash_value)
                    unmatched_sentences_curr.append(sentence_curr)

        # Identify the unmatched sentences in the previous paragraph revision.
        for paragraph_prev in unmatched_paragraphs_prev:
            for sentence_prev_hash in paragraph_prev.ordered_sentences:
                if len(paragraph_prev.sentences[sentence_prev_hash]) > 1:
                    s = 's-{}-{}'.format(paragraph_prev, sentence_prev_hash)
                    self.temp.append(s)
                    count = self.temp.count(s)
                    sentence_prev = paragraph_prev.sentences[sentence_prev_hash][count - 1]
                else:
                    sentence_prev = paragraph_prev.sentences[sentence_prev_hash][0]
                if not sentence_prev.matched:
                    unmatched_sentences_prev.append(sentence_prev)
                    # to reset 'matched words in analyse_words_in_sentences' of unmatched paragraphs and sentences
                    sentence_prev.matched = True
                    matched_sentences_prev.append(sentence_prev)

        return unmatched_sentences_curr, unmatched_sentences_prev, matched_sentences_prev, total_sentences

    def analyse_words_in_sentences(self, unmatched_sentences_curr, unmatched_sentences_prev, possible_vandalism):
        matched_words_prev = []
        unmatched_words_prev = []

        # Split sentences into words.
        text_prev = []
        for sentence_prev in unmatched_sentences_prev:
            for word_prev in sentence_prev.words:
                if not word_prev.matched:
                    text_prev.append(word_prev.value)
                    unmatched_words_prev.append(word_prev)

        text_curr = []
        for sentence_curr in unmatched_sentences_curr:
            words = split_into_tokens(sentence_curr.value)
            text_curr.extend(words)
            sentence_curr.splitted.extend(words)

        # Edit consists of removing sentences, not adding new content.
        if not text_curr:
            return matched_words_prev, False

        # spam detection.
        if possible_vandalism:
            token_density = compute_avg_word_freq(text_curr)
            if token_density > WORD_DENSITY:
                return matched_words_prev, possible_vandalism
            else:
                possible_vandalism = False

        # Edit consists of adding new content, not changing/removing content
        if not text_prev:
            for sentence_curr in unmatched_sentences_curr:
                for word in sentence_curr.splitted:
                    word_curr = Word()
                    word_curr.value = word
                    word_curr.token_id = self.token_id
                    word_curr.origin_rev_id = self.revision_curr.id
                    word_curr.last_rev_id = self.revision_curr.id

                    sentence_curr.words.append(word_curr)
                    self.token_id += 1
                    self.revision_curr.original_adds += 1
                    self.tokens.append(word_curr)
            return matched_words_prev, possible_vandalism

        d = Differ()
        diff = list(d.compare(text_prev, text_curr))
        for sentence_curr in unmatched_sentences_curr:
            for word in sentence_curr.splitted:
                curr_matched = False
                pos = 0
                while pos < len(diff):
                    word_diff = diff[pos]
                    if word == word_diff[2:]:
                        if word_diff[0] == ' ':
                            # match
                            for word_prev in unmatched_words_prev:
                                if not word_prev.matched and word_prev.value == word:

                                    word_prev.matched = True
                                    curr_matched = True
                                    sentence_curr.words.append(word_prev)
                                    matched_words_prev.append(word_prev)
                                    diff[pos] = ''
                                    pos = len(diff) + 1
                                    break
                        elif word_diff[0] == '-':
                            # deleted
                            for word_prev in unmatched_words_prev:
                                if not word_prev.matched and word_prev.value == word:
                                    word_prev.matched = True
                                    word_prev.outbound.append(self.revision_curr.id)
                                    matched_words_prev.append(word_prev)
                                    diff[pos] = ''
                                    break
                        elif word_diff[0] == '+':
                            # a new added word
                            curr_matched = True
                            word_curr = Word()
                            word_curr.value = word
                            word_curr.token_id = self.token_id
                            word_curr.origin_rev_id = self.revision_curr.id
                            word_curr.last_rev_id = self.revision_curr.id

                            sentence_curr.words.append(word_curr)
                            self.token_id += 1
                            self.revision_curr.original_adds += 1
                            self.tokens.append(word_curr)
                            diff[pos] = ''
                            pos = len(diff) + 1
                    pos += 1

                if not curr_matched:
                    # if diff returns a word as '? ...'
                    word_curr = Word()
                    word_curr.value = word
                    word_curr.token_id = self.token_id
                    word_curr.origin_rev_id = self.revision_curr.id
                    word_curr.last_rev_id = self.revision_curr.id
                    sentence_curr.words.append(word_curr)

                    self.token_id += 1
                    self.revision_curr.original_adds += 1
                    self.tokens.append(word_curr)

        return matched_words_prev, possible_vandalism

    def get_revision_json(self, revision_ids, parameters):
        """
        :param revision_ids: List of revision ids. 2 revision ids mean a range.
        :param parameters: List of parameters ('rev_id', 'editor', 'token_id', 'inbound', 'outbound') to decide
        content of revision(s).
        :return: Content of revision in json format.
        """
        json_data = dict()
        json_data["article"] = self.title
        json_data["success"] = True
        json_data["message"] = None

        # Check if given rev ids exits
        for rev_id in revision_ids:
            if rev_id not in self.revisions:
                return {'Error': 'Revision ID ({}) does not exist or is spam or deleted!'.format(rev_id)}

        if len(revision_ids) == 2:
            # Get range of revisions
            start_index = self.ordered_revisions.index(revision_ids[0])
            end_index = self.ordered_revisions.index(revision_ids[1])
            revision_ids = self.ordered_revisions[start_index:end_index]

        json_data['revisions'] = []
        for rev_id in revision_ids:
            # Prepare output revision content according to parameters
            revision = self.revisions[rev_id]
            tokens = []
            json_data['revisions'].append({rev_id: {"editor": revision.editor,
                                                    "time": revision.timestamp,
                                                    "tokens": tokens}})
            for word in iter_rev_tokens(revision):
                token = dict()
                token['str'] = word.value
                if 'rev_id' in parameters:
                    token['rev_id'] = word.origin_rev_id
                if 'editor' in parameters:
                    token['editor'] = self.revisions[word.origin_rev_id].editor
                if 'token_id' in parameters:
                    token['token_id'] = word.token_id
                if 'inbound' in parameters:
                    token['inbound'] = word.inbound
                if 'outbound' in parameters:
                    token['outbound'] = word.outbound
                tokens.append(token)

        # import json
        # with open('tmp_pickles/{}.json'.format(self.page_id), 'w') as f:
        #     f.write(json.dumps(json_data, indent=4, separators=(',', ': '), sort_keys=True, ensure_ascii=False))
        return json_data

    def get_revision_min_json(self, revision_ids):
        """
        Calculates the revision content in minimum form (list of values).

        It behaves as all parameters are given.
        :param revision_ids: List of revision ids. 2 revision ids mean a range.
        :return: Content of revision in json format in min form.
        """
        json_data = dict()
        json_data["article"] = self.title
        json_data["success"] = True
        json_data["message"] = None

        # Check if given rev ids exits
        for rev_id in revision_ids:
            if rev_id not in self.revisions:
                return {'Error': 'Revision ID ({}) does not exist or is spam or deleted!'.format(rev_id)}

        if len(revision_ids) == 2:
            # Get range of revisions
            start_index = self.ordered_revisions.index(revision_ids[0])
            end_index = self.ordered_revisions.index(revision_ids[1])
            revision_ids = self.ordered_revisions[start_index:end_index]

        json_data['revisions'] = []
        for rev_id in revision_ids:
            # Prepare output revision content
            revision = self.revisions[rev_id]
            values = []
            rev_ids = []
            editors = []
            token_ids = []
            outs = []
            ins = []
            json_data['revisions'].append({rev_id: {"editor": revision.editor,
                                                    "time": revision.timestamp,
                                                    "str": values,
                                                    "rev_ids": rev_ids,
                                                    "editors": editors,
                                                    "token_ids": token_ids,
                                                    "outs": outs,
                                                    "ins": ins,
                                                    }})
            for word in iter_rev_tokens(revision):
                values.append(word.value)
                rev_ids.append(word.origin_rev_id)
                editors.append(self.revisions[word.origin_rev_id].editor)
                token_ids.append(word.token_id)
                outs.append(word.outbound)
                ins.append(word.inbound)

        # import json
        # with open('tmp_pickles/{}.json'.format(self.page_id), 'w') as f:
        #     f.write(json.dumps(json_data, indent=4, separators=(',', ': '), sort_keys=True, ensure_ascii=False))
        return json_data

    def get_deleted_tokens(self, parameters):
        """
        Calculates and returns deleted content of this article.

        Deleted content is all tokens that are not present
        in last revision.
        :param parameters: List of parameters ('rev_id', 'editor', 'token_id', 'inbound', 'outbound') to decide
        content of revision(s).
        :return: Deleted content of revision in json format.
        """
        json_data = dict()
        json_data["article"] = self.title
        json_data["success"] = True
        json_data["message"] = None

        threshold = parameters[-1]
        json_data["threshold"] = threshold
        last_rev_id = self.ordered_revisions[-1]
        json_data["revision_id"] = last_rev_id

        deleted_tokens = []
        json_data["deleted_tokens"] = deleted_tokens
        for word in self.tokens:
            if len(word.outbound) > threshold and word.last_rev_id != last_rev_id:
                token = dict()
                token['str'] = word.value
                if 'rev_id' in parameters:
                    token['rev_id'] = word.origin_rev_id
                if 'editor' in parameters:
                    token['editor'] = self.revisions[word.origin_rev_id].editor
                if 'token_id' in parameters:
                    token['token_id'] = word.token_id
                if 'inbound' in parameters:
                    token['inbound'] = word.inbound
                if 'outbound' in parameters:
                    token['outbound'] = word.outbound
                deleted_tokens.append(token)
        # import json
        # with open('tmp_pickles/{}_deleted_tokens.json'.format(self.title), 'w') as f:
        #     f.write(json.dumps(response, indent=4, separators=(',', ': '), sort_keys=True, ensure_ascii=False))
        return json_data

    def get_revision_ids(self, parameters):
        """
        :return: List of revision ids of this article in json format.
        """
        json_data = dict()
        json_data["article"] = self.title
        json_data["success"] = True
        json_data["message"] = None

        revisions = []
        json_data["revisions"] = revisions
        for rev_id in self.ordered_revisions:
            rev = {'id': rev_id}
            revision = self.revisions[rev_id]
            if 'editor' in parameters:
                rev['editor'] = revision.editor
            if 'timestamp' in parameters:
                rev['timestamp'] = revision.timestamp
            revisions.append(rev)
        return json_data

    def get_revision_text(self, revision_id):
        """
        :param revision_id:
        :return: List of token values and list of origin of rev id respectively.
        """
        revision = self.revisions[revision_id]
        text = []
        origin_rev_ids = []
        for word in iter_rev_tokens(revision):
            text.append(word.value)
            origin_rev_ids.append(word.origin_rev_id)
        return text, origin_rev_ids
