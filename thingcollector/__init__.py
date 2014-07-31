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
import sys
import logging
from logging.handlers import RotatingFileHandler

from scheduler import scheduler, NowTrigger
import index

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

config = {}
if 'PIWIK_URL' in app.config and 'PIWIK_ID' in app.config:
    for conf in ['PIWIK_URL', 'PIWIK_ID','TRACKER_UUID','TRACKER_URL','MAINTAINER_NAME','MAINTAINER_EMAIL']:
        config[conf] = app.config[conf]

class SubmissionForm(Form):
    url = TextField("url",validators=[DataRequired(),URL(require_tld=True)])

class SearchForm(Form):
    query = TextField("query",validators=[DataRequired()])


@app.route('/')
def home():
    return redirect(url_for("search"))

@app.route('/about')
def about():
    return render_template('about.html',config=config)

@app.route('/list/trackers')
def list_trackers():
    trackers = index.get_trackers()
    return render_template('trackers.html',trackers=trackers,config=config)

@app.route('/list/things')
def list_things():
    things = index.get_things()
    return render_template('things.html',things=things,config=config)

@app.route('/show/thing/<thing_id>')
def show_thing(thing_id):
    thing = index.get_thing(thing_id)
    return render_template('thing.html',thing = None,config=config)

@app.route('/search', methods=('GET', 'POST'))
def search():
    results = None
    query = request.args.get('q','')
    form = SearchForm()

    if query == '':
        if form.validate_on_submit():
            return redirect(url_for('search',q=form.query.data))
    else:
        results = index.search_thing(query)
    return render_template('search.html', form=form,query=query,results=results,config=config)

@app.route('/submit', methods=('GET', 'POST'))
def submit():
    messages = []
    error = False
    form = SubmissionForm()
    if form.validate_on_submit():
        tracker_url = form.url.data
        error,messages = index.check_and_submit_tracker(tracker_url)
        if len(messages) == 0:
            return redirect(url_for("submit"))
    return render_template('submit.html', form=form, messages = messages,config=config, error = error)

@app.route('/tracker')
def tracker():
    trackers = index.get_trackers()
    return render_template('tracker.json',config = config, trackers = trackers)


if __name__ == '__main__':
    app.run()
