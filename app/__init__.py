from flask import Flask
from os import environ, mkdir
from os.path import exists,join
from shutil import rmtree
import os.path
#import whoosh
#import whoosh.fields, whoosh.index
from pymongo import MongoClient
import sys

#whoosh_dir = join(environ["OPENSHIFT_DATA_DIR"],'index')
#
#if True or not exists(whoosh_dir):
#    rmtree(whoosh_dir)
#    mkdir(whoosh_dir)
#
#    schema = whoosh.fields.Schema(
#        title = whoosh.fields.TEXT(),
#        authors = whoosh.fields.TEXT(),
#        description = whoosh.fields.TEXT()
#    )
#    ix = whoosh.index.create_in(whoosh_dir, schema)
#else:
#    ix = whoosh.index.open_ix(whoosh_dir)

app = Flask(__name__)

@app.oute('/')
def index():
    exctype, value = None, None
    try:
        mongoclient = pymongo.MongoClient(environ["OPENSHIFT_MONGODB_DB_URL"])

        db = mongoclient.database
    except:
        exctype, value = sys.exc_info()[:2]
    return " ".join(exctype,value)

#
#@app.route('/eimer/add/<thing>')
#def add_to_collection(thing):
#    db.eimer.insert({"thing" : thing})
#    return "%s added" % thing
#
#@app.route('/eimer/view')
#def view_collection():
#    return " ".join([doc["thing"] for doc in db.eimer.find()])


if __name__ == '__main__':
    app.run()
