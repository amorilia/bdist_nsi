#!/bin/sh

# a script for making an nsis installer for the bdist_nsi package

git clean -x -f -d
python setup.py build
su -c 'python setup.py install'
python setup.py --command-packages bdist_nsi bdist_nsi

