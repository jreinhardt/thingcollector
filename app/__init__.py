# Copyright 2014 Johannes Reinhardt <jreinhardt@ist-dein-freund.de>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from flask import Flask, render_template, request, flash, redirect, url_for, g
from flask_wtf import Form
from wtforms import TextField
from wtforms.validators import DataRequired, URL
from os import environ, mkdir
from os.path import exists,join
from shutil import rmtree
import os.path
import whoosh
import whoosh.fields, whoosh.index
from whoosh.analysis import CharsetFilter, StemmingAnalyzer
from whoosh.support.charset import accent_map
from whoosh.query import *
from whoosh.qparser import QueryParser, MultifieldParser
import sys
import requests
from jsonschema import Draft3Validator
import json
from datetime import datetime

INDEX_VERSION = 1

whoosh_dir = join(environ["OPENSHIFT_DATA_DIR"],'index')

ttn_schema = json.loads(open(join(environ["OPENSHIFT_REPO_DIR"],"app","spec","schema.json")).read())
validator = Draft3Validator(ttn_schema)

def initialize_index():
    mkdir(whoosh_dir)

    index_schema = whoosh.fields.Schema(
        version = whoosh.fields.NUMERIC(stored = True)
    )
    index_idx = whoosh.index.create_in(whoosh_dir, index_schema, indexname = "index")
    with index_idx.writer() as writer:
        writer.add_document(version = INDEX_VERSION)

    tracker_schema = whoosh.fields.Schema(
        url = whoosh.fields.ID(stored = True, unique = True),
        description = whoosh.fields.TEXT(stored = True),
        updated = whoosh.fields.DATETIME(),
        accessed = whoosh.fields.DATETIME()
    )
    tracker_idx = whoosh.index.create_in(whoosh_dir, tracker_schema, indexname = "trackers")

    thing_schema = whoosh.fields.Schema(
        id = whoosh.fields.ID(unique = True),
        url = whoosh.fields.TEXT(stored = True),
        title = whoosh.fields.TEXT(stored = True),
        description = whoosh.fields.TEXT(),
        authors = whoosh.fields.TEXT(),
        licenses = whoosh.fields.TEXT(),
        tags = whoosh.fields.TEXT()
    )
    thing_idx = whoosh.index.create_in(whoosh_dir, thing_schema, indexname = "things")
    return (index_idx,tracker_idx,thing_idx)

def scan_tracker(url):
    messages = []
    r = requests.get(url)

    #skip unreachable trackers
    if not r.status_code == requests.codes.ok:
        messages.append("Skipping unreachable tracker %s" % url)
        return messages

    tracker = r.json()

    if not validator.is_valid(tracker):
        messages.append("Skipping invalid tracker %s" % tracker["url"])
        for error in validator.iter_errors(tracker):
            messages.append("%s not conforming to spec: %s" % (url,error.message))
        return messages

    with tracker_idx.searcher() as searcher:
        if len(searcher.search(Term("url",url))) == 1:
            messages.append("Skipping known tracker %s" % url)
            return messages

    with tracker_idx.writer() as writer:
        for opt in ["description"]:
            if not opt in tracker:
                tracker[opt] = u""

        if not "updated" in tracker:
            tracker["updated"] = datetime.now()
        else:
            tracker["updated"] = datetime.strptime(tracker["updated"][:-6],"%Y-%m-%dT%H:%M:%S")

        tracker["accessed"] = datetime.now()

        writer.add_document(
            url = tracker["url"],
            description = tracker["description"],
            accessed = tracker["accessed"],
            updated = tracker["updated"]
        )
    if "things" in tracker:
        with thing_idx.writer() as writer:
            for thing in tracker["things"]:
                for opt in ['url','description']:
                    if not opt in thing:
                        thing[opt] = u''
                for opt in ['authors','licenses','tags']:
                    if not opt in thing:
                        thing[opt] = []

                writer.update_document(
                    id = thing["id"],
                    url = thing["url"],
                    title = thing["title"],
                    description = thing["description"],
                    authors = u" ".join([a["name"] for a in thing["authors"]]),
                    licenses = u" ".join([l for l in thing["licenses"]]),
                    tags = u", ".join([t for t in thing["tags"]])
                )

    if "trackers" in tracker:
        for subtracker in tracker["trackers"]:
            messages += scan_tracker(subtracker["url"])
    return messages


if not exists(whoosh_dir):
    print "Creating index"
    index_idx,tracker_idx,thing_idx = initialize_index()
else:
    tracker_idx = whoosh.index.open_dir(whoosh_dir, indexname = "trackers")
    thing_idx = whoosh.index.open_dir(whoosh_dir, indexname = "things")
    index_idx = whoosh.index.open_dir(whoosh_dir, indexname = "index")

    with index_idx.searcher() as searcher:
        version = list(searcher.all_stored_fields())[0]["version"]

    if version != INDEX_VERSION:
        print "Recreating index"
        with tracker_idx.searcher() as searcher:
            tracker_urls = [tracker["url"] for tracker in searcher.all_stored_fields()]
            rmtree(whoosh_dir)
            index_idx,tracker_idx,thing_idx = initialize_index()
            for url in tracker_urls:
                scan_tracker(url)

thing_parser = MultifieldParser(['title','description','tags','licenses'],schema = thing_idx.schema)
tracker_parser = MultifieldParser(['description'],schema = tracker_idx.schema)

app = Flask(__name__)
app.config.from_pyfile(join(environ['OPENSHIFT_DATA_DIR'],'collector.cfg'))

config = {}
if 'PIWIK_URL' in app.config and 'PIWIK_ID' in app.config:
    for conf in ['PIWIK_URL', 'PIWIK_ID','TRACKER_UUID','TRACKER_URL','MAINTAINER_NAME','MAINTAINER_EMAIL']:
        config[conf] = app.config[conf]

class SubmissionForm(Form):
    url = TextField("url",validators=[DataRequired(),URL(require_tld=True)])

class SearchForm(Form):
    query = TextField("query",validators=[DataRequired()])


@app.route('/')
def index():
    return redirect(url_for("search"))

@app.route('/about')
def about():
    return render_template('about.html',config=config)

@app.route('/list/trackers')
def list_trackers():
    searcher = tracker_idx.searcher()
    trackers = [tracker for tracker in searcher.all_stored_fields()]
    return render_template('trackers.html',trackers=trackers,config=config)

@app.route('/list/things')
def list_things():
    searcher = thing_idx.searcher()
    things = [thing for thing in searcher.all_stored_fields()]
    return render_template('things.html',things=things,config=config)

@app.route('/search', methods=('GET', 'POST'))
def search():
    results = None
    query = request.args.get('q','')
    form = SearchForm()

    if query == '':
        if form.validate_on_submit():
            return redirect(url_for('search',q=form.query.data))
    else:
        with thing_idx.searcher() as searcher:
            results = []
            hits = searcher.search(thing_parser.parse(query))
            for i in range(hits.scored_length()):
                results.append(hits[i].fields())
    return render_template('search.html', form=form,query=query,results=results,config=config)

@app.route('/submit', methods=('GET', 'POST'))
def submit():
    messages = []
    form = SubmissionForm()
    if form.validate_on_submit():
        messages = scan_tracker(form.url.data)
        print messages
        if len(messages) == 0:
            return redirect(url_for("submit"))
    return render_template('submit.html', form=form, messages = messages,config=config)

@app.route('/tracker')
def tracker():
    searcher = tracker_idx.searcher()
    trackers = [tracker for tracker in searcher.all_stored_fields()]
    return render_template('tracker.json',config = config, trackers = trackers)


if __name__ == '__main__':
    app.run()
