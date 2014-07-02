from flask import Flask
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

whoosh_dir = join(environ["OPENSHIFT_DATA_DIR"],'index')

if True or not exists(whoosh_dir):
    rmtree(whoosh_dir)
    mkdir(whoosh_dir)

    schema = whoosh.fields.Schema(
        thing = whoosh.fields.TEXT(),
        subthing = whoosh.fields.TEXT()
    )
    ix = whoosh.index.create_in(whoosh_dir, schema)
else:
    ix = whoosh.index.open_ix(whoosh_dir)

app = Flask(__name__)

mongoclient = pymongo.MongoClient(environ["OPENSHIFT_MONGODB_DB_URL"])
db = mongoclient.database
db.eimer.drop()

@app.route('/eimer/add/<thing>/<subthing>')
def add_to_collection(thing,subthing):
    db.eimer.insert({"thing" : thing, "subthing" : subthing})

    #TODO: handle non-thread safety
    writer = ix.writer()
    writer.add_document(thing=thing, subthing=subthing)
    writer.commit()
    return "%s added" % thing

@app.route('/eimer/view')
def view_collection():
    return " ".join([doc["thing"] for doc in db.eimer.find()])

@app.route('/eimer/search/<term>')
def search_collection(term):
    with ix.searcher() as searcher:
        query = Or([Term("thing",term), Term("subthing",term)])
        results = searcher.search(query)
        if len(results) == 0:
            return "No results found"
        else:
            " ".join(res["thing"] for res in results)


if __name__ == '__main__':
    app.run()
