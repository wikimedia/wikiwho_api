"""
This module is to compare mwpersistence package with WikiWho in detail.
"""
from os import listdir
from os.path import join
from json import load, dumps
from difflib import SequenceMatcher, Differ
import argparse


def mw_pesistence_compare(ww_jsons, mw_jsons):
    articles = []
    for i in listdir(mw_jsons):
        if not i.endswith('_rev_ids.json'):
            articles.append(i[:-5])

    # articles = ["Amstrad CPC", "Antarctica", "Apollo 11", "Armenian Genocide", "Barack_Obama",
    #             "Bioglass", "Bothrops_jararaca", "Chlorine", "Circumcision", "Communist Party of China",
    #             "Democritus", "Diana,_Princess_of_Wales", "Encryption", "Eritrean Defence Forces",
    #             "European Free Trade Association", "Evolution", "Geography of El Salvador",
    #             "Germany", "Home and Away", "Homeopathy", "Iraq War", "Islamophobia", "Jack the Ripper", "Jesus",
    #             "KLM destinations", "Lemur", "Macedonians (ethnic group)", "Muhammad", "Newberg, Oregon",
    #             "Race_and_intelligence", "Rhapsody_on_a_Theme_of_Paganini", "Robert Hues", "Saturn's_moons_in_fiction",
    #             "Sergei Korolev", "South_Western_Main_Line", "Special Air Service", "The_Holocaust",
    #             "Toshitsugu_Takamatsu", "Vladimir_Putin", "Wernher_von_Braun"]
    # articles = ['Bioglass', 'Amstrad_CPC', 'Lemur', 'Antarctica', 'Jesus']
    # articles = ['Bioglass', 'Amstrad_CPC']
    # articles = ['Bioglass']
    output = {}
    for article_title in articles:
        article_title = article_title.replace(' ', '_')
        # calculate mw persistence for each token
        print('mw_article_tokens')
        mw_article_tokens = []  # [{'str': , 'o_rev_id': , 'in': , 'out': }]
        mw_token_values = []
        with open(join(mw_jsons, '{}_rev_ids.json'.format(article_title))) as f:
            d = load(f)
            article_rev_ids = d['revision_ids']
            article_rev_ids_dict = {rev_id: i for i, rev_id in enumerate(article_rev_ids)}

        with open(join(mw_jsons, '{}.json'.format(article_title))) as f:
            d = load(f)
            for rev_id, tokens in d['revisions'][0].items():
                for t in tokens['tokens']:
                    if not t['str'].replace('\\n', '').replace('\r\n', '\n').replace('\r', '\n').strip():
                        continue
                    o_rev_id = t['revisions'][0]
                    ins = []
                    outs = []
                    mw_article_tokens.append({'str': t['str'], 'o_rev_id': o_rev_id, 'in': ins, 'out': outs})
                    mw_token_values.append(t['str'])
                    # calculate in and outs
                    token_rev_indexes = [article_rev_ids_dict[r] for r in t['revisions']]
                    prev_rev_index = None
                    for rev_index in token_rev_indexes:
                        if prev_rev_index is not None and rev_index - prev_rev_index > 1:
                            # first rev id is o_rev_id, so skip it
                            # if there are more than 1 revs between, it means token is deleted and re-inserted.
                            outs.append(article_rev_ids[prev_rev_index+1])
                            ins.append(article_rev_ids[rev_index])
                        prev_rev_index = rev_index

        # calculate wikiwho survival for each token
        print('ww_article_tokens')
        ww_article_tokens = []  # [{'str': , 'o_rev_id': , 'in': , 'out': }]
        ww_token_values = []
        with open(join(ww_jsons, '{}_ri_ai.json'.format(article_title))) as f:
            d = load(f)
            for rev_id, tokens in d['revisions'][0].items():
                for t in tokens['tokens']:
                    ww_article_tokens.append({'str': t['str'], 'o_rev_id': t['o_rev_id']})
                    ww_token_values.append(t['str'])
        with open(join(ww_jsons, '{}_io.json'.format(article_title))) as f:
            d = load(f)
            for rev_id, tokens in d['revisions'][0].items():
                for i, t in enumerate(tokens['tokens']):
                    ww_article_tokens[i].update({'in': t['in'], 'out': t['out']})

        print('comparing...')
        # compare results
        d = Differ()
        mw_vs_ww_tokens = []  # [{'str': {'same_o': , 'same_in': , 'same_out': }}]
        ww_article_tokens_iter = iter(ww_article_tokens)
        mw_article_tokens_iter = iter(mw_article_tokens)
        ww_found = 0
        ww_found_same_o = 0
        ww_not_found = 0
        for token in d.compare(ww_token_values, mw_token_values):
            op = token[0]
            token = token[2:]
            if op == '-':
                ww_not_found += 1
                ww_token = next(ww_article_tokens_iter)
                mw_vs_ww_tokens.append({ww_token['str']: {'not_found': True}})
                assert token == ww_token['str']
            elif op == ' ':
                ww_found += 1
                ww_token = next(ww_article_tokens_iter)
                assert token == ww_token['str']
                for mw_token in mw_article_tokens_iter:
                    if mw_token['str'] == token:
                        break
                same_o = ww_token['o_rev_id'] == mw_token['o_rev_id']
                ww_found_same_o += 1 if same_o else 0
                # similarity_in = SequenceMatcher(None, ww_token['in'], mw_token['in']).ratio()
                # similarity_out = SequenceMatcher(None, ww_token['out'], mw_token['out']).ratio()
                mw_vs_ww_tokens.append({
                    ww_token['str']: {
                        'same_o': same_o,
                        # 'similartiy_in': similarity_in,
                        # 'similarity_out': similarity_out,
                        'same_in': ww_token['in'] == mw_token['in'],
                        'same_out': ww_token['out'] == mw_token['out']
                    }
                })
        assert len(list(ww_article_tokens_iter)) == 0, len(list(ww_article_tokens_iter))

        output[article_title] = {'total': len(ww_article_tokens),
                                 'found': ww_found,
                                 'ww_found_same_origin': ww_found_same_o,
                                 'ww_found_same_origin%': float(ww_found_same_o * 100) / ww_found,
                                 'not_found': ww_not_found}
        with open('{}_comparison_with_ww.json'.format(join(mw_jsons, article_title)), 'w', encoding='utf-8') as f:
            f.write(dumps(mw_vs_ww_tokens, indent=4, separators=(',', ': '), sort_keys=True, ensure_ascii=False))
        print('{}: {}'.format(article_title, output[article_title]))
    with open(join(mw_jsons, 'ww_vs_mw_comparison_output.json'), 'w', encoding='utf-8') as f:
        f.write(dumps(output, indent=4, separators=(',', ': '), sort_keys=True, ensure_ascii=False))


def get_args():
    """
python mw_persistence_compare.py -w='/home/kenan/PycharmProjects/wikiwho_api/tests_ignore/jsons/after_token_density_increase' -m='/home/kenan/PycharmProjects/wikiwho_api/tests_ignore/mwpersistence'
    """
    parser = argparse.ArgumentParser(description='Compare computed content persistence and token authorship by '
                                                 'mwpersistence package in detail. This module is created to compare '
                                                 'results of mwpersistence with WikiWho.')

    parser.add_argument('-w', '--wikiwho_jsons', help='Path of the folder where all token persistence and '
                                                      'token authorship json files are.')
    parser.add_argument('-m', '--mediawiki_jsons', help='Path of the folder where all token persistence and '
                                                        'token authorship json files are.')
    args = parser.parse_args()
    return args


def main():
    args = get_args()
    wikiwho_jsons = args.wikiwho_jsons
    mediawiki_jsons = args.mediawiki_jsons
    mw_pesistence_compare(wikiwho_jsons, mediawiki_jsons)

if __name__ == '__main__':
    main()
