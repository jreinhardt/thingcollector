#!/usr/bin/python

if __name__ == '__main__':
    #when executed as a module, run in debug mode
    from thingcollector import app
    app.run(debug=True)
else:
    #else set up virtualenv for openshift
    import os

    virtenv = os.environ['OPENSHIFT_PYTHON_DIR'] + '/virtenv/'
    virtualenv = os.path.join(virtenv, 'bin/activate_this.py')
    try:
        execfile(virtualenv, dict(__file__=virtualenv))
    except IOError:
        pass

    from thingcollector import app as application
