#!/usr/bin/env python

"""Setup script for bdist-nsi."""

classifiers = """Development Status :: 2 - Pre-Alpha
Intended Audience :: Developers
License :: OSI Approved :: BSD License
Natural Language :: English
Operating System :: OS Independent
Programming Language :: Python
Topic :: Software Distribution
Topic :: Code Generators"""

from distutils.core import setup
import os

long_description = open("README.rst").read()

setup(
    name = 'bdist-nsi',
    version = '0.1.0',
    description = 'Create an NSIS windows installer.',
    author = 'j-cg, amorilia',
    author_email = 'amorilia@users.sourceforge.net',
    url = 'http://github.com/amorilia/bdist-nsi',
    license = 'BSD',
    platforms = ["any"],
    classifiers = filter(None, classifiers.split("\n")),
    long_description = long_description,
    data_files = [['distutils/command',['bdist_nsi.py']]]
)
