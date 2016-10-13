# -*- coding: utf-8 -*-
"""
Copyright 2015-2016 Ricordisamoa

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import json
from collections import Counter
from urllib.parse import urlencode
from urllib.request import urlopen

import mwparserfromhell

MARKER = '\ue0ff'
WIKIPEDIA_API = 'https://{}.wikipedia.org/w/api.php'
DBPEDIA_API = 'http://mappings.dbpedia.org/api.php'


def translate_templates(wikitext, lang_from, lang_to, shood_has_marker=True):
    can_has_marker = (shood_has_marker and MARKER not in wikitext)
    wikitext = mwparserfromhell.parse(wikitext)
    templates = []
    for template in wikitext.ifilter_templates():
        templates.append(template.name.strip())

    prefixed_titles = ['Template:{}'.format(title) for title in templates]

    old_langlinks = get_langlinks(prefixed_titles, lang_from, lang_to)
    langlinks = {}
    for title_from, title_to in old_langlinks.items():
        if ':' in title_from[1:] and ':' in title_to[1:]:
            langlinks[title_from.split(':', 1)[1]] = title_to.split(':', 1)[1]

    mappings_from, mappings_to = get_mappings_from_templates(lang_from, lang_to, langlinks)
    mappings = intersect(mappings_from, mappings_to, langlinks)
    ignored_templates = {}
    ignored_parameters = {}

    for template in wikitext.ifilter_templates():
        tname = template.name.strip()
        mapped = mappings.get(tname)
        if mapped:
            change_prop_with_spaces(template, 'name', langlinks[tname])
            for param in template.params:
                pname = param.name.strip()
                pm = mapped.get(pname)
                if pm:
                    change_prop_with_spaces(param, 'name', pm)
                else:
                    set_marker(can_has_marker, param, 'name')
                    # it might have been excluded for being duplicate
                    ignored_parameters.setdefault(tname, {})[pname] = 'mapping not found'
        else:
            set_marker(can_has_marker, template, 'name')
            if tname not in mappings_from:
                ignored_templates[tname] = 'mapping not found'
            elif tname not in langlinks:
                ignored_templates[tname] = 'langlink not found'
    result = {
        'wikitext': str(wikitext),
        'ignoredTemplates': ignored_templates,
        'ignoredParameters': ignored_parameters
    }
    return result, can_has_marker, MARKER


def set_marker(can_has_marker, obj, prop):
    if can_has_marker:
        change_prop_with_spaces(obj, prop, marker=MARKER)


def change_prop_with_spaces(obj, prop, value=None, marker=''):
    obj_prop = getattr(obj, prop)
    lstrip = obj_prop.lstrip()
    lspaces = obj_prop[:len(obj_prop) - len(lstrip)]
    rstrip = lstrip.rstrip()
    rspaces = lstrip[len(rstrip):]
    if value is None:
        value = rstrip
    setattr(obj, prop, lspaces + marker + value + marker + rspaces)


def flip_dict(dic):
    flipped = {}
    counter = Counter(dic.values())
    for key, value in dic.items():
        if counter[value] == 1:
            flipped[value] = key
    return flipped


def intersect(mappings_from, mappings_to, langlinks):
    mappings = {}
    for tmp_from, mapped_from in mappings_from.items():
        tmp_translated = langlinks.get(tmp_from)
        if tmp_translated:
            mapped_to = mappings_to.get(tmp_translated)
            if mapped_to:
                mappings[tmp_from] = {}
                flipped = flip_dict(mapped_to)
                for param, field in mapped_from.items():
                    if field in flipped:
                        mappings[tmp_from][param] = flipped[field]
    return mappings


def get_json(url, data):
    with urlopen(url, urlencode(data).encode('utf-8')) as response:
        raw = response.read()
    return json.loads(raw.decode('utf-8'))


def is_tmp(template, name):
    tname = template.name.strip()
    tname = tname[0].upper() + tname[1:]
    return tname == name


def get_langlinks(titles, lang_from, lang_to):
    data = {
        'action': 'query',
        'titles': '|'.join(titles),
        'prop': 'langlinks',
        'redirects': '1',
        'lllang': lang_to,
        'format': 'json'
    }
    result = get_json(WIKIPEDIA_API.format(lang_from), data)
    if 'query' in result and 'pages' in result['query']:
        pages = {}
        for pageid, page in result['query']['pages'].items():
            langlinks = [ll for ll in page.get('langlinks', [])
                         if ll['lang'] == lang_to]
            if len(langlinks) == 1:
                pages[page['title']] = langlinks[0]['*']
        # protect against title normalization
        for norm in result['query'].get('normalized', []):
            if norm['to'] in pages:
                pages[norm['from']] = pages[norm['to']]
        return pages
    return {}


def parse_mapping(mapping):
    if (mapping.has('templateProperty') and
            mapping.has('ontologyProperty') and
            len(mapping.params) == 2):
        return (mapping.get('templateProperty').value.strip(),
                mapping.get('ontologyProperty').value.strip())


def get_mappings_from_wikitext(wikitext):
    wikitext = mwparserfromhell.parse(wikitext)
    found_mapping = False
    mappings = {}
    for template in wikitext.ifilter_templates():
        if is_tmp(template, 'TemplateMapping'):
            if found_mapping:
                return {}
            found_mapping = True
            if template.has('mappings'):
                for mapping in template.get('mappings').value.ifilter_templates():
                    if is_tmp(mapping, 'PropertyMapping'):
                        mpp = parse_mapping(mapping)
                        if mpp:
                            mappings[mpp[0]] = mpp[1]
    return mappings


def get_mappings_from_templates(lang_from, lang_to, langlinks):
    cnf = {
        lang_from: langlinks.keys(),
        lang_to: langlinks.values()
    }
    titles = {}
    for lang, templates in cnf.items():
        for template in templates:
            titles['Mapping {lang}:{title}'.format(lang=lang, title=template)] = (lang, template)
    pages = get_page_contents(DBPEDIA_API, titles.keys())
    templates = {
        lang_from: {},
        lang_to: {}
    }
    for title, content in pages.items():
        lang, template = titles[title]
        templates[lang][template] = get_mappings_from_wikitext(content)
    return templates[lang_from], templates[lang_to]


def get_page_contents(api_url, titles):
    data = {
        'action': 'query',
        'titles': '|'.join(titles),
        'prop': 'revisions',
        'rvprop': 'content',
        'format': 'json'
    }
    result = get_json(api_url, data)
    if 'query' in result and 'pages' in result['query']:
        pages = {}
        for pageid, page in result['query']['pages'].items():
            if 'revisions' in page and len(page['revisions']) == 1 and '*' in page['revisions'][0]:
                pages[page['title']] = page['revisions'][0]['*']
        # protect against title normalization
        for norm in result['query'].get('normalized', []):
            if norm['to'] in pages:
                pages[norm['from']] = pages[norm['to']]
        return pages
    return {}
