#!/usr/bin/env python

"""Setup script for bdist_nsi."""

classifiers = """Development Status :: 5 - Production/Stable
Intended Audience :: Developers
License :: OSI Approved :: BSD License
Natural Language :: English
Operating System :: OS Independent
Programming Language :: Python
Topic :: System :: Software Distribution
Topic :: Software Development :: Code Generators"""

from distutils.core import setup
import os

long_description = open("README.rst").read()

setup(
    name = 'bdist_nsi',
    packages = ['bdist_nsi'],
    package_data = {'': ['*.ico', '*.bmp']}, # include ico and bmp files
    version = '0.1.3',
    description = 'Create NSIS windows installers for Python modules.',
    # note: author of the original http://bdist-nsi.sourceforge.net/ package
    #       (which formed the original basis of bdist_nsi) is j-cg
    author = 'Amorilia',
    author_email = 'amorilia@users.sourceforge.net',
    url = 'http://bdist-nsi.sourceforge.net/',
    license = 'BSD',
    platforms = ["any"],
    classifiers = [_f for _f in classifiers.split("\n") if _f],
    long_description = long_description
)
