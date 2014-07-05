from setuptools import setup

setup(name='Thing Tracker Network Collector',
      version='1.0',
      description='A web app to collect thing trackers',
      author='Johannes Reinhardt',
      author_email='jreinhardt@ist-dein-freund.de',
      url='http://www.python.org/sigs/distutils-sig/',
      install_requires=['Flask','Whoosh','Flask-WTF','requests','jsonschema'],
     )
