bdist_nsi
=========

The bdist_nsi module extends Python's distutils module with a bdist_nsi 
setup command to create binary Windows installers for Python modules, 
based on NSIS. Thereby, bdist_nsi brings all the features of NSIS to 
Windows installers for Python modules, such as silent install, modern 
user interface, and internationalization. 

In action
---------

Take a look at the `screenshots <http://sourceforge.net/project/screenshots.php?group_id=139858>`_.

What you need
-------------

Besides Python and the bdist_nsi module, you will need `NSIS <http://nsis.sourceforge.net/>`_. It can be run under windows and linux (see NSIS forum for instructions).

Installation
------------

The latest version can always be downloaded from https://sourceforge.net/projects/bdist-nsi/files.

To install from source, simply run::

    python setup.py install

Usage
-----

Add ``bdist_nsi`` option to your setup.py file.

In your projects setup.py::

    from bdist_nsi import bdist_nsi

    nsis_options = {} # your nsis options
    setup(
        name='your application name', 
        version='0.0.x',
        author='your name',
        author_email='your email',
        url='http://yourdomain.com/',
        license='your license',) # your setup options

You can create installer ``python setup.py bdist_nsi`` command.

If the makensis executable is not installed in one of the usual
locations (``/usr/bin``, ``C:\Program Files\NSIS``, or
``C:\Program Files (x86)\NSIS``), then you can specify the
NSIS folder with the *--nsis-dir* option, or just add *-k* to have a look
at the temporary generated files.

Development
-----------

Development happens at github, http://github.com/amorilia/bdist_nsi/. Fork at will!
