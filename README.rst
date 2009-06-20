The bdist_nsi module extends Python's distutils module with a bdist_nsi 
setup command to create binary Windows installers for Python modules, 
based on NSIS. Thereby, bdist_nsi brings all the features of NSIS to 
Windows installers for Python modules, such as silent install, modern 
user interface, and internationalization. 

Installation
============

Simply run::

    python setup.py install

Usage
=====

Create your installer with::

    python setup.py --command-packages bdist_nsi bdist_nsi --nsis-dir="C:\Program Files (x86)\NSIS"

Acknowledgements
================

This project effectively builds further on j-cg's bdist-nsi project,
http://bdist-nsi.sourceforge.net/
