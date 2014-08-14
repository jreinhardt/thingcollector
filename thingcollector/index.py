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

from os.path import exists,join, dirname
from os import environ, mkdir
from shutil import rmtree

import whoosh
import whoosh.fields, whoosh.index
from whoosh.analysis import CharsetFilter, StemmingAnalyzer
from whoosh.support.charset import accent_map
from whoosh.query import *
from whoosh.qparser import QueryParser, MultifieldParser
from whoosh.writing import AsyncWriter
import requests
import json
import bleach

from scheduler import scheduler, NowTrigger

from jsonschema import Draft3Validator

from datetime import datetime, timedelta

ttn_schema = json.loads(open(join(dirname(__file__),"spec","schema.json")).read())
validator = Draft3Validator(ttn_schema)

INDEX_VERSION = 3

whoosh_dir = join(environ["OPENSHIFT_DATA_DIR"],'index')

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
        tags = whoosh.fields.TEXT(stored = True),
        tracker = whoosh.fields.ID(stored = True)
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
                    tags = bleach.clean(u", ".join([t for t in thing["tags"]])),
                    tracker = tracker["url"]
                )

def crawl_trackers(tracker_url):
    """
    Index this tracker and all of its subtrackers
    """
    r_tracker = requests.get(tracker_url)

    #skip unreachable trackers
    if not r_tracker.status_code == requests.codes.ok:
        return

    tracker = r_tracker.json()

    if not validator.is_valid(tracker):
        return

    with tracker_idx.searcher() as searcher:
        if len(searcher.search(Term("url",tracker_url))) == 1:
            return

    index_tracker(tracker)
    index_things(tracker)


    if "trackers" in tracker:
        for subtracker in tracker["trackers"]:
            crawl_tracker(subtracker["url"])
    return

def check_and_submit_tracker(tracker_url):
    messages = []
    error = False

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

    return error,messages

def search_thing(query):
    results = []
    with thing_idx.searcher() as searcher:
        hits = searcher.search(thing_parser.parse(query))
        for i in range(hits.scored_length()):
            results.append(hits[i].fields())
    return results

def get_thing(thing_id):
    with thing_idx.searcher() as searcher:
        hits = searcher.search(id_parser.parse(thing_id))
        if len(hits) == 0:
            return None
        else:
            return hits[0].fields()

def get_tracker_for_url(thing_url):
    with thing_idx.searcher() as searcher:
        hits = searcher.search(thing_url_parser.parse(thing_url))
        if len(hits) == 0:
            return None
        else:
            return hits[0].fields()["tracker"]

def get_things():
    with thing_idx.searcher() as searcher:
        things = [thing for thing in searcher.all_stored_fields()]
    return things

def get_trackers():
    with tracker_idx.searcher() as searcher:
        trackers = [tracker for tracker in searcher.all_stored_fields()]
    return trackers

@scheduler.interval_schedule(hours=2)
def update_trackers():
    searcher = tracker_idx.searcher()
    for tracker in searcher.all_stored_fields():
        crawl_trackers(tracker['url'])


if not exists(whoosh_dir):
    index_idx,tracker_idx,thing_idx = initialize_index()
else:
    tracker_idx = whoosh.index.open_dir(whoosh_dir, indexname = "trackers")
    thing_idx = whoosh.index.open_dir(whoosh_dir, indexname = "things")
    index_idx = whoosh.index.open_dir(whoosh_dir, indexname = "index")

    with index_idx.searcher() as searcher:
        version = list(searcher.all_stored_fields())[0]["version"]

    if version != INDEX_VERSION:
        with tracker_idx.searcher() as searcher:
            tracker_urls = [tracker["url"] for tracker in searcher.all_stored_fields()]
            rmtree(whoosh_dir)
            index_idx,tracker_idx,thing_idx = initialize_index()
            for url in tracker_urls:
                crawl_trackers(url)

thing_parser = MultifieldParser(['title','description','tags','licenses'],schema = thing_idx.schema)
thing_url_parser = QueryParser('url',schema = thing_idx.schema)
tracker_parser = MultifieldParser(['description'],schema = tracker_idx.schema)
id_parser = QueryParser('id',schema = thing_idx.schema)

