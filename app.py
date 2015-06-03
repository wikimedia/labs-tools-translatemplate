# -*- coding: utf-8 -*-
"""Licensed under the Apache License, Version 2.0"""

from flask import Flask, request, jsonify, render_template

from mappings import translate_templates

app = Flask(__name__)
all_params = set(('wikitext', 'from', 'to'))


@app.route('/')
def index():
    """Render the index page."""
    return render_template('index.html')


@app.route('/', methods=['POST'])
def results():
    """Render the results page."""
    params = request.form
    if all_params.issubset(params):
        final = {key: params[key] for key in all_params.intersection(params)}
        try:
            result, can_has_marker, MARKER = translate_templates(
                params['wikitext'], params['from'], params['to'])
        except Exception as e:
            final['error'] = e.__class__.__name__
        else:
            wt = result['wikitext']
            final['result'] = wt.split(MARKER) if can_has_marker else [wt]
        return render_template('index.html', **final)
    return render_template('index.html')


@app.route('/api', methods=['GET', 'POST'])
def api():
    """Translate a wikitext and return the results, or render the API page."""
    params = (request.args if request.method == 'GET' else request.form)
    if all_params.issubset(params):
        try:
            result = translate_templates(
                params['wikitext'], params['from'], params['to'], False)[0]
        except Exception as e:
            result = {
                'error': e.__class__.__name__
            }
        return jsonify(result)
    else:
        return render_template('api.html')


if __name__ == '__main__':
    app.run()
