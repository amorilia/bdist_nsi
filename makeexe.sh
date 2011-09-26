#!/bin/sh

# a script for making an nsis installer for the bdist_nsi package

git clean -x -f -d
python setup.py build
su -c 'python setup.py install'
python setup.py --command-packages bdist_nsi bdist_nsi --target-versions=2.5,2.6,2.7,3.0,3.1,3.2
python setup.py sdist --formats zip,bztar

