**************
Thingcollector
**************

The thingcollector is a web application that provides a full text search for
the [thingtracker network](https://thingtracker.net). It is written in
[python](http://python.org), using [flask](http://flask.pocoo.org/) and
[whoosh](https://pythonhosted.org/Whoosh/index.html) with easy deployment on
[OpenShift](https://www.openshift.com/) in mind. The frontend is based on
[bootstrap](http://getbootstrap.com/).


Register for OpenShift
======================

Go to the [OpenShift website](https://www.openshift.com/) and create a new
account if you don't have one already. The free plan allows you to use up to 3
"gears". For a thingcollector instance we only need one.

Spin up a a OpenShift gear
==========================

This can be done via the web interface as well, but this is how to do it on the
command line. First install the [RHC client
tools](https://www.openshift.com/developers/rhc-client-tools-install) if you
have not already done so.

Create a new application:
=========================

    rhc app create thingcollector python-2.7

`thingcollector` is the name of the application, and can be replaced by
something else if necessary.

Pull the thingcollector code into your application repo
=======================================================

    cd thingcollector
    git remote add upstream -m master git://github.com/jreinhardt/thingcollector.git
    git pull -s recursive -X theirs upstream master

Push your application repo to the gear
======================================

    git push


Configuration
=============

The configuration options for the thingcollector reside outside the code repo,
as they contain a secret key that should not be made public.

Create a textfile with name `collector.cfg` secret_key in the
$OPENSHIFT_DATA_DIR on your gear and add a secret key and a uuid for the
tracker that is published by this collector, as well as name and contact
information for the maintainer of this collector:

    SECRET_KEY = "replace this by a proper secret key"
    TRACKER_UUID = "replace this by a unique UUID, e.g. generated by uuidgen"
    TRACKER_URL = "replace this by the url of the tracker, i.e. http://thingcollector-domain.rhcloud.com/tracker"
    MAINTAINER_NAME = "your name"
    MAINTAINER_EMAIL = "your.name@domain.com"

If you have a [Piwik](http://piwik.org/) instance running (e.g. on
[OpenShift](https://github.com/openshift/piwik-openshift-quickstart)) you can
get analytics enabled on the thingcollector by specifying

    PIWIK_URL = "the url of your piwik instance without leading http(s)://"
    PIWIK_ID = "the site id of the thingcollector assigned in your piwik"

Test the app
============

Now you should be able to access your thingcollector instance at
`http://thingcollector-yourdomain.rhcloud.com`. If you created your application
with a different name, its not `thingcollector`, but whatever you used, when
you created the application.


Make the collector known to the network
=======================================

Submit the tracker of your collector to one or two other collectors, and their
trackers to your collector. This way your collector learns about all the
trackers known to them and they learn about all the trackers that get submitted
to your collector.

An instance of the thingcollector is running
[here](http://thingcollector-bolts.rhcloud.com).



Updating the collector code
===========================

You should check regularly if the thingcollector code has been improved. You
can update your collector by pulling the changes from the upstream repo and
pushing them to your gear.

    git pull -s recursive -X theirs upstream master
    git push

The data that the tracker collected is left untouched, unless there was a
database schema change, in which case instructions will be provided.
