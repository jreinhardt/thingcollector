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
from whoosh.writing import AsyncWriter
import sys
import requests
from jsonschema import Draft3Validator
import json
from datetime import datetime, timedelta
import bleach
import apscheduler
from apscheduler.scheduler import Scheduler
import logging
from logging.handlers import RotatingFileHandler

INDEX_VERSION = 2

whoosh_dir = join(environ["OPENSHIFT_DATA_DIR"],'index')

class NowTrigger:
    def __init__(self):
        self.triggered = False
    def get_next_fire_time(self,start):
        if not self.triggered:
            self.triggered = True
            return start
        else:
            return None

scheduler = Scheduler()
scheduler.start()

ttn_schema = json.loads(open(join(environ["OPENSHIFT_REPO_DIR"],"app","spec","schema.json")).read())
validator = Draft3Validator(ttn_schema)

app = Flask(__name__)
app.config.from_pyfile(join(environ['OPENSHIFT_DATA_DIR'],'collector.cfg'))

log_handler = RotatingFileHandler(join(environ['OPENSHIFT_LOG_DIR'],'collector.log'),maxBytes=2**20,backupCount=3)
log_handler.setLevel(logging.INFO)
log_handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s '
    '[in %(pathname)s:%(lineno)d]'
))

app.logger.addHandler(log_handler)
logging.getLogger().addHandler(log_handler)


def initialize_index():
    mkdir(whoosh_dir)

    index_schema = whoosh.fields.Schema(
        version = whoosh.fields.NUMERIC(stored = True)
    )
    index_idx = whoosh.index.create_in(whoosh_dir, index_schema, indexname = "index")
    with AsyncWriter(index_idx) as writer:
        writer.add_document(version = INDEX_VERSION)

    tracker_schema = whoosh.fields.Schema(
        url = whoosh.fields.ID(stored = True, unique = True),
        description = whoosh.fields.TEXT(stored = True),
        updated = whoosh.fields.DATETIME(),
        accessed = whoosh.fields.DATETIME()
    )
    tracker_idx = whoosh.index.create_in(whoosh_dir, tracker_schema, indexname = "trackers")

    thing_schema = whoosh.fields.Schema(
        id = whoosh.fields.ID(unique = True,stored = True),
        url = whoosh.fields.TEXT(stored = True),
        title = whoosh.fields.TEXT(stored = True),
        description = whoosh.fields.TEXT(stored = True),
        authors = whoosh.fields.TEXT(stored = True),
        licenses = whoosh.fields.TEXT(stored = True),
        tags = whoosh.fields.TEXT(stored = True)
    )
    thing_idx = whoosh.index.create_in(whoosh_dir, thing_schema, indexname = "things")
    return (index_idx,tracker_idx,thing_idx)

def index_tracker(tracker):
    """
    write the tracker information of this tracker to the tracker index
    """
    with AsyncWriter(tracker_idx) as writer:
        for opt in ["description"]:
            if not opt in tracker:
                tracker[opt] = u""

        if not "updated" in tracker:
            tracker["updated"] = datetime.now()
        else:
            tracker["updated"] = datetime.strptime(tracker["updated"][:-6],"%Y-%m-%dT%H:%M:%S")

        tracker["accessed"] = datetime.now()

        writer.update_document(
            url = tracker["url"],
            description = tracker["description"],
            accessed = tracker["accessed"],
            updated = tracker["updated"]
        )

def index_things(tracker):
    """
    write the things of this tracker to the thing index
    """
    if "things" in tracker:
        with AsyncWriter(thing_idx) as writer:
            for thing in tracker["things"]:
                if "refUrl" in thing:
                    r_thing = requests.get(thing["refUrl"])
                    if not r_thing.status_code == requests.codes.ok:
                        messages.append("Skipping unreachable thing %s" % thing["refUrl"])
                    thing.update(r_thing.json())

                #fill in default values if necessary
                for opt in ['url','description']:
                    if not opt in thing:
                        thing[opt] = u''
                for opt in ['authors','licenses','tags']:
                    if not opt in thing:
                        thing[opt] = []

                writer.update_document(
                    id = thing["id"],
                    url = bleach.clean(thing["url"]),
                    title = bleach.clean(thing["title"]),
                    description = bleach.linkify(bleach.clean(thing["description"])),
                    authors = bleach.clean(u" ".join([a["name"] for a in thing["authors"]])),
                    licenses = bleach.clean(u" ".join([l for l in thing["licenses"]])),
                    tags = bleach.clean(u", ".join([t for t in thing["tags"]]))
                )

def crawl_trackers(tracker_url):
    """
    Index this tracker and all of its subtrackers
    """
    r_tracker = requests.get(tracker_url)

    #skip unreachable trackers
    if not r_tracker.status_code == requests.codes.ok:
        app.logger.info("Skipping unreachable tracker %s" % tracker_url)
        return

    tracker = r_tracker.json()

    if not validator.is_valid(tracker):
        app.logger.info("Skipping invalid tracker %s" % tracker["url"])
        for error in validator.iter_errors(tracker):
            app.logger.info("%s not conforming to spec: %s" % (tracker_url,error.message))
        return

    with tracker_idx.searcher() as searcher:
        if len(searcher.search(Term("url",tracker_url))) == 1:
            app.logger.info("Skipping known tracker %s" % tracker_url)
            return

    index_tracker(tracker)
    index_things(tracker)


    if "trackers" in tracker:
        for subtracker in tracker["trackers"]:
            crawl_tracker(subtracker["url"])
    return

@scheduler.interval_schedule(hours=2)
def update_trackers():
    app.logger.warning("Start update")
    searcher = tracker_idx.searcher()
    for tracker in searcher.all_stored_fields():
        crawl_trackers(tracker['url'])

if not exists(whoosh_dir):
    app.logger.info("Index directory does not exist. Recreating index")
    index_idx,tracker_idx,thing_idx = initialize_index()
else:
    tracker_idx = whoosh.index.open_dir(whoosh_dir, indexname = "trackers")
    thing_idx = whoosh.index.open_dir(whoosh_dir, indexname = "things")
    index_idx = whoosh.index.open_dir(whoosh_dir, indexname = "index")

    with index_idx.searcher() as searcher:
        version = list(searcher.all_stored_fields())[0]["version"]

    if version != INDEX_VERSION:
        app.logger.info("Version mismatch %d vs. %d. Recreating index" % (version, INDEX_VERSION))
        with tracker_idx.searcher() as searcher:
            tracker_urls = [tracker["url"] for tracker in searcher.all_stored_fields()]
            rmtree(whoosh_dir)
            index_idx,tracker_idx,thing_idx = initialize_index()
            for url in tracker_urls:
                crawl_trackers(url)

thing_parser = MultifieldParser(['title','description','tags','licenses'],schema = thing_idx.schema)
tracker_parser = MultifieldParser(['description'],schema = tracker_idx.schema)
id_parser = QueryParser('id',schema = thing_idx.schema)

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

@app.route('/show/thing/<thing_id>')
def show_thing(thing_id):
    with thing_idx.searcher() as searcher:
        hits = searcher.search(id_parser.parse(thing_id))
        if len(hits) == 0:
            return render_template('thing.html',thing = None,config=config)
        else:
            return render_template('thing.html',thing = hits[0],config=config)

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
    error = False
    form = SubmissionForm()
    if form.validate_on_submit():
        tracker_url = form.url.data
        r_tracker = requests.get(tracker_url)

        #skip unreachable trackers
        if not r_tracker.status_code == requests.codes.ok:
            messages.append("Tracker unreachable %s" % tracker_url)
            return messages, True

        if not error:
            tracker = r_tracker.json()

            if tracker_url != tracker["url"]:
                messages.append("Tracker url inconsistent: %s vs. %s" % (tracker_url, tracker["url"]))

            if not validator.is_valid(tracker):
                messages.append("Tracker invalid %s" % tracker["url"])
                error = True
                for msg in validator.iter_errors(tracker):
                    messages.append("Tracker %s not conforming to spec: %s" % (tracker_url,msg.message))

        if not error:
            with tracker_idx.searcher() as searcher:
                if len(searcher.search(Term("url",tracker_url))) == 1:
                    messages.append("Skipping known tracker %s" % tracker_url)

        scheduler.add_job(NowTrigger(),index_tracker,[tracker],{})
        scheduler.add_job(NowTrigger(),index_things,[tracker],{})

        if "trackers" in tracker:
            for subtracker in tracker["trackers"]:
                scheduler.add_job(NowTrigger(),crawl_trackers,[subtracker["url"]],{})
        if len(messages) == 0:
            return redirect(url_for("submit"))
    return render_template('submit.html', form=form, messages = messages,config=config, error = error)

@app.route('/tracker')
def tracker():
    searcher = tracker_idx.searcher()
    trackers = [tracker for tracker in searcher.all_stored_fields()]
    return render_template('tracker.json',config = config, trackers = trackers)


if __name__ == '__main__':
    app.run()
