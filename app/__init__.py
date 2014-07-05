from flask import Flask, render_template, request, flash, redirect
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

whoosh_dir = join(environ["OPENSHIFT_DATA_DIR"],'index')

ttn_schema = json.loads(open(join(environ["OPENSHIFT_REPO_DIR"],"app","spec","schema.json")).read())
validator = Draft3Validator(ttn_schema)

if False or not exists(whoosh_dir):
    if exists(whoosh_dir):
        rmtree(whoosh_dir)
    mkdir(whoosh_dir)

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


else:
    tracker_idx = whoosh.index.open_dir(whoosh_dir, indexname = "trackers")
    thing_idx = whoosh.index.open_dir(whoosh_dir, indexname = "things")

thing_parser = MultifieldParser(['title','description','tags','licenses'],schema = thing_idx.schema)
tracker_parser = MultifieldParser(['description'],schema = tracker_idx.schema)

app = Flask(__name__)
app.config.from_pyfile(join(environ['OPENSHIFT_DATA_DIR'],'collector.cfg'))


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

class SubmissionForm(Form):
    url = TextField("url",validators=[DataRequired(),URL(require_tld=True)])

class SearchForm(Form):
    query = TextField("query",validators=[DataRequired()])


@app.route('/submit', methods=('GET', 'POST'))
def submit():
    messages = []
    form = SubmissionForm()
    if form.validate_on_submit():
        messages = scan_tracker(form.url.data)
        print messages
        if len(messages) == 0:
            return redirect("/submit")
    return render_template('submit.html', form=form, messages = messages)

@app.route('/')
def index():
    return redirect('/search')

@app.route('/list/trackers')
def list_trackers():
    searcher = tracker_idx.searcher()
    trackers = [tracker for tracker in searcher.all_stored_fields()]
    return render_template('list.html',trackers=trackers)

@app.route('/list/things')
def list_things():
    searcher = thing_idx.searcher()
    things = [thing for thing in searcher.all_stored_fields()]
    return render_template('things.html',things=things)

@app.route('/search', methods=('GET', 'POST'))
def search():
    results = []
    form = SearchForm()
    if form.validate_on_submit():
        with thing_idx.searcher() as searcher:
            hits = searcher.search(thing_parser.parse(form.query.data))
            for i in range(hits.scored_length()):
                results.append(hits[i].fields())
    return render_template('search.html', form=form, results=results)

if __name__ == '__main__':
    app.run()
