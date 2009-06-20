#!/usr/bin/env python

from distutils.core import setup
import os
setup(	name = 'bdist_nsi',
	version = '0.0.2a',
	description = 'create a windows installer exe-program',
	author = 'j-cg',
	author_email = 'j-cg@users.sourceforge.net',
	url = 'http://bdist-nsi.sourceforge.net/',
	license = 'Python Software Foundation License',
	platforms = ["any"],
	classifiers =	['Development Status :: 2 - Pre-Alpha',	\
			 'Intended Audience :: Developers',	\
			 'License :: OSI Approved :: PSF License',\
			 'Natural Language :: English',			\
			 'Operating System :: OS Independent',		\
			 'Programming Language :: Python',		\
			 'Topic :: Software Distribution',\
			 'Topic :: Code Generators'],
	long_description = "\ncreate a windows installer exe-program with nsis",
	data_files = [['distutils/command',['bdist_nsi.py']]],
        )
