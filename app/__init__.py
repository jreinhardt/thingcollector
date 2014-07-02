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
from whoosh.query import *
import pymongo
from pymongo import MongoClient
import sys
import requests
from jsonschema import Draft3Validator
import json

whoosh_dir = join(environ["OPENSHIFT_DATA_DIR"],'index')


#TODO: somethings phishy with pythons json load, as the results depends on the case of the boolean values
ttn_schema = json.loads(open(join(environ["OPENSHIFT_REPO_DIR"],"app","spec","schema_true.json")).read())
validator = Draft3Validator(ttn_schema)

if False or not exists(whoosh_dir):
    if exists(whoosh_dir):
        rmtree(whoosh_dir)
    mkdir(whoosh_dir)

    schema = whoosh.fields.Schema(
        thing = whoosh.fields.TEXT(stored = True),
        subthing = whoosh.fields.TEXT()
    )
    ix = whoosh.index.create_in(whoosh_dir, schema)
else:
    ix = whoosh.index.open_dir(whoosh_dir)

app = Flask(__name__)
app.secret_key = open(join(environ["OPENSHIFT_DATA_DIR"],"secret_key")).read()

class SubmissionForm(Form):
    url = TextField("url",validators=[DataRequired(),URL(require_tld=True)])

@app.route('/submit', methods=('GET', 'POST'))
def submit():
    form = SubmissionForm()
    if form.validate_on_submit():
        r = requests.get(form.url.data)
        if not validator.is_valid(r.json()):
            for error in validator.iter_errors(r.json()):
                flash("%s not conforming to spec: %s" % (form.url.data,error.message))
        else:
            flash("%s successfully submitted" % form.url.data)
        return redirect("/submit")
    return render_template('submit.html', form=form)

@app.route('/')
def index():
    return redirect('/submit')

#mongoclient = pymongo.MongoClient(environ["OPENSHIFT_MONGODB_DB_URL"])
#db = mongoclient.database

#@app.route('/eimer/clear')
#def clear_collection():
#    db.eimer.drop()

#@app.route('/eimer/add/<thing>/<subthing>')
#def add_to_collection(thing,subthing):
##    db.eimer.insert({"thing" : thing, "subthing" : subthing})
#
#    #TODO: handle non-thread safety
#    writer = ix.writer()
#    writer.add_document(thing=thing, subthing=subthing)
#    writer.commit()
#    return "%s added" % thing

#@app.route('/eimer/view')
#def view_collection():
#    return " ".join([doc["thing"] for doc in db.eimer.find()])

#@app.route('/eimer/search/<term>')
#def search_collection(term):
#    with ix.searcher() as searcher:
#        query = Or([Term("thing",term), Term("subthing",term)])
#        results = searcher.search(query)
#        n = min(20,len(results))
#        print n
#        print results[0]["thing"]
#        if n == 0:
#            return "No results found"
#        else:
#            return " ".join([str(results[i]) for i in range(n)])


if __name__ == '__main__':
    app.run()
