"""bdist_nsi.bdist_nsi

Implements the Distutils 'bdist_nsi' command: create a Windows NSIS installer.
"""

# Created 2005/05/24, j-cg , inspired by the bdist_wininst of the python
# distribution

# June/July 2009: further developed by Amorilia

import sys, os, string
import subprocess
from distutils.core import Command
from distutils.util import get_platform
from distutils.dir_util import create_tree, remove_tree
from distutils.errors import *
from distutils.sysconfig import get_python_version
from distutils import log
from distutils.spawn import spawn
from distutils.command.install import WINDOWS_SCHEME

class bdist_nsi(Command):

    description = "create an executable installer for MS Windows, using NSIS"

    user_options = [('bdist-dir=', None,
                    "temporary directory for creating the distribution"),
                    ('plat-name=', 'p',
                     "platform name to embed in generated filenames "
                     "(default: %s)" % get_platform()),
                    ('keep-temp', 'k',
                     "keep the pseudo-installation tree around after " +
                     "creating the distribution archive"),
                    ('target-version=', None,
                     "require a specific python version" +
                     " on the target system"),
                    ('no-target-compile', 'c',
                     "do not compile .py to .pyc on the target system"),
                    ('no-target-optimize', 'o',
                     "do not compile .py to .pyo (optimized)"
                     "on the target system"),
                    ('dist-dir=', 'd',
                     "directory to put final built distributions in"),
                    ('nsis-dir=', 'n',
                     "directory of nsis compiler"),
                    ('bitmap=', 'b',
                     "bitmap (size 164x314) to use for the " +
                     "installer instead of python-powered logo"),
                    ('headerbitmap=', None,
                     "header bitmap (size 150x57) to use for the " +
                     "installer instead of python-powered logo"),
                    ('title=', 't',
                     "title to display on the installer background instead of default"),
                    ('skip-build', None,
                     "skip rebuilding everything (for testing/debugging)"),
                    ('run2to3', None,
                     "run 2to3 on 3.x installs"),
                    ('msvc2005', None,
                     "check if msvc 2005 redistributable package is installed"),
                    ('msvc2005sp1', None,
                     "check if msvc 2005 sp1 redistributable package is installed"),
                    ('msvc2008', None,
                     "check if msvc 2008 redistributable package is installed"),
                    ('msvc2008sp1', None,
                     "check if msvc 2008 sp1 redistributable package is installed"),
                    ('nshextra=', None,
                     "additional nsis header file to include at the start of the file, and which must define the following macros (they can be empty if not used): InstallFilesExtra, UninstallFilesExtra, PostExtra, and UnPostExtra"),
                    ('target-versions=', None,
                     "comma separated list of python versions (only for pure packages)"),
                    ('maya', None,
                     "include (compatible) Maya targets in installer"),
                    ('blender', None,
                     "include (compatible) Blender targets in installer"),
                    ('debug', None,
                     "debug mode (only use if you know what you are doing)"),
                    ]

    boolean_options = ['keep-temp', 'no-target-compile', 'no-target-optimize',
                       'skip-build', 'run2to3', 'msvc2005', 'msvc2005sp1',
                       'msvc2008', 'msvc2008sp1', 'maya', 'blender', 'debug']

    def initialize_options (self):
        self.bdist_dir = None
        self.plat_name = None
        self.keep_temp = 0
        self.no_target_compile = 0
        self.no_target_optimize = 0
        self.target_version = None
        self.dist_dir = None
        self.nsis_dir = None
        self.bitmap = None
        self.headerbitmap = None
        self.title = None
        self.skip_build = 0
        self.run2to3 = 0
        self.msvc2005 = 0
        self.msvc2005sp1 = 0
        self.msvc2008 = 0
        self.msvc2008sp1 = 0
        self.nshextra = None
        self.target_versions = None
        self.maya = 0
        self.blender = 0
        self.debug = 0

    # initialize_options()


    def finalize_options (self):
        if self.bdist_dir is None:
            if self.skip_build and self.plat_name:
                # If build is skipped and plat_name is overridden, bdist will
                # not see the correct 'plat_name' - so set that up manually.
                bdist = self.distribution.get_command_obj('bdist')
                bdist.plat_name = self.plat_name
                # next the command will be initialized using that name
            bdist_base = self.get_finalized_command('bdist').bdist_base
            self.bdist_dir = os.path.join(bdist_base, 'nsi')
        if not self.target_version:
            self.target_version = ""
        if not self.skip_build and self.distribution.has_ext_modules():
            short_version = get_python_version()
            if self.target_version and self.target_version != short_version:
                raise DistutilsOptionError, \
                      "target version can only be %s, or the '--skip_build'" \
                      " option must be specified" % (short_version,)
            self.target_version = short_version

        # find makensis executable
        if self.nsis_dir is None:
            pathlist = os.environ.get('PATH', os.defpath).split(os.pathsep)
            # common locations
            pathlist.extend([
                ".",
                "C:\\Program Files\\NSIS",
                "C:\\Program Files (x86)\\NSIS"])
        else:
            pathlist = [self.nsis_dir]
        for path in pathlist:
            # windows executable?
            makensis = os.path.join(path, "makensis.exe")
            if os.access(makensis, os.X_OK):
                self.nsis_dir = makensis
                break
            # linux executable? (for instance on Fedora 11)
            makensis = os.path.join(path, "makensis")
            if os.access(makensis, os.X_OK):
                self.nsis_dir = makensis
                break
        else:
            print(
                "Error: makensis executable not found, "
                "add NSIS directory to the path or specify it "
                "with --nsis-dir")
            self.nsis_dir = None

        if not self.headerbitmap:
            self.headerbitmap = os.path.join(os.path.dirname(__file__),
                                             "python-install-150x57.bmp").replace("/", "\\")
        else:
            self.headerbitmap = self.abspath(self.headerbitmap)
        if not self.bitmap:
            self.bitmap = os.path.join(os.path.dirname(__file__),
                                       "python-install-164x314.bmp").replace("/", "\\")
        else:
            self.bitmap = self.abspath(self.bitmap)

        if self.nshextra:
            self.nshextra = self.abspath(self.nshextra)

        self.set_undefined_options('bdist',
                                   ('dist_dir', 'dist_dir'),
                                   ('plat_name', 'plat_name'),
                                   ('nsis_dir', 'nsis_dir'),
                                  )

    # finalize_options()

    def abspath(self, filename):
        # absolute path with windows separator
        return os.path.abspath(filename).replace('/', '\\')

    def run (self):
        if (sys.platform != "win32" and
            (self.distribution.has_ext_modules() or
             self.distribution.has_c_libraries())):
            raise DistutilsPlatformError \
                  ("distribution contains extensions and/or C libraries; "
                   "must be compiled on a Windows 32 platform")

        if not self.skip_build:
            self.run_command('build')

        install = self.reinitialize_command('install', reinit_subcommands=1)
        install.root = self.bdist_dir
        install.skip_build = self.skip_build
        install.warn_dir = 0
        install.plat_name = self.plat_name

        install_lib = self.reinitialize_command('install_lib')
        # we do not want to include pyc or pyo files
        install_lib.compile = 0
        install_lib.optimize = 0

        if self.distribution.has_ext_modules():
            # If we are building an installer for a Python version other
            # than the one we are currently running, then we need to ensure
            # our build_lib reflects the other Python version rather than ours.
            # Note that for target_version!=sys.version, we must have skipped the
            # build step, so there is no issue with enforcing the build of this
            # version.
            target_version = self.target_version
            if not target_version:
                assert self.skip_build, "Should have already checked this"
                target_version = sys.version[0:3]
            plat_specifier = ".%s-%s" % (self.plat_name, target_version)
            build = self.get_finalized_command('build')
            build.build_lib = os.path.join(build.build_base,
                                           'lib' + plat_specifier)
        # use windows installation scheme
        for key in WINDOWS_SCHEME.keys():
            value = WINDOWS_SCHEME[key].replace("$base", "_python")
            setattr(install,
                    'install_' + key,
                    value)

        log.info("installing to %s", self.bdist_dir)
        install.ensure_finalized()
        install.run()

        self.build_nsi()
        
        if not self.keep_temp:
            remove_tree(self.bdist_dir, dry_run=self.dry_run)

    # run()

    
    def build_nsi(self):
        if self.target_version.upper() not in ["","ANY"]:
            nsiscript = get_nsi(pythonversions=[self.target_version])
        elif self.target_versions:
            nsiscript = get_nsi(pythonversions=self.target_versions.split(","))
        else:
            pythonversions = ["2.3", "2.4", "2.5", "2.6", "2.7", "2.8", "2.9"]
            if self.run2to3:
                pythonversions.extend(["3.0", "3.1", "3.2", "3.3", "3.4"])
            nsiscript = get_nsi(pythonversions=pythonversions)
        metadata = self.distribution.metadata

        def get_full_author(key):
            # full author and maintainer info?
            author = key
            author_email = "%s_email" % author
            if (getattr(metadata, author, "")
                and getattr(metadata, author_email, "")):
                return '@%s@ <@%s@>' % (author, author_email)
            elif getattr(metadata, author, ""):
                return '@%s@' % author
            elif getattr(metadata, author_email, ""):
                return '@%s@' % author_email
            else:
                return ''

        annotated_author = get_full_author("author")
        if annotated_author:
            nsiscript = nsiscript.replace(
                "@annotated_author@",
                "Author: %s$\\r$\\n" % annotated_author)
        annotated_maintainer = get_full_author("maintainer")
        if annotated_maintainer:
            nsiscript = nsiscript.replace(
                "@annotated_maintainer@",
                "Maintainer: %s$\\r$\\n" % annotated_maintainer)

        for name in ["author", "author_email", "maintainer",
                     "maintainer_email", "description", "name", "url",
                     "version", "license"]:
            data = getattr(metadata, name, "")
            if data:
                nsiscript = nsiscript.replace('@has'+name+'@', "")
                nsiscript = nsiscript.replace('@'+name+'@',data)
                nsiscript = nsiscript.replace(
                    '@annotated_'+name+'@',
                    "%s: %s$\\r$\\n"
                    % (name.replace("_", " ").capitalize(), data))
            else:
                nsiscript = nsiscript.replace(
                    '@annotated_'+name+'@', '')
                nsiscript = nsiscript.replace('@has'+name+'@', ";")
        # XXX todo: use the moduleinfo file in the installer?

        for licensefile in ['license', 'license.txt', 'license.rst',
                            'LICENSE', 'LICENSE.txt', 'LICENSE.rst',
                            'LICENSE.TXT', 'LICENSE.RST']:
            if os.path.exists(licensefile):
                nsiscript=nsiscript.replace('@haslicensefile@', "")
                nsiscript=nsiscript.replace('@licensefile@',
                                            self.abspath(licensefile))
                break
        else:
            nsiscript=nsiscript.replace('@haslicensefile@', ";")

        if self.target_version:
            installer_path = os.path.join(self.dist_dir, "%s.win32-py%s.exe" % (self.distribution.get_fullname(), self.target_version))
        else:
            installer_path = os.path.join(self.dist_dir, "%s.win32.exe" % self.distribution.get_fullname())
        installer_path = self.abspath(installer_path)
                
        nsiscript=nsiscript.replace('@installer_path@',installer_path)
        
        haspythonversion=";"
        if self.target_version.upper() not in ["","ANY"]:
            nsiscript=nsiscript.replace('@pythonversion@',self.target_version)
            haspythonversion=""
            
        nsiscript=nsiscript.replace('@haspythonversion@',haspythonversion)
        
        files=[]
        
        os.path.walk(self.bdist_dir+os.sep+'_python',self.visit,files)

        # install folders and files (as nsis commands)
        _f_packages=[]
        _f_scripts=[]
        _f_include=[]
        # delete files (as nsis commands)
        _d_packages=[]
        _d_scripts=[]
        _d_include=[]
        # folders for recursive delete (as strings, for compiling and cleaning)
        _r_packages=[]
        _r_scripts=[]
        _r_include=[]
        lastdir=""
        for each in files:
            # skip egg info files
            if each[1].endswith(".egg-info"):
                continue
            if each[1].lower().startswith("lib\\site-packages\\"):
                outpath = "$3\\%s" % each[0][18:]
                outfile = "$3\\%s" % each[1][18:]
                _f = _f_packages
                _d = _d_packages
                _r = _r_packages
            elif each[1].lower().startswith("scripts\\"):
                outpath = "$4\\%s" % each[0][8:]
                outfile = "$4\\%s" % each[1][8:]
                _f = _f_scripts
                _d = _d_scripts
                _r = _r_scripts
            elif each[1].lower().startswith("include\\"):
                outpath = "$5\\%s" % each[0][8:]
                outfile = "$5\\%s" % each[1][8:]
                _f = _f_include
                _d = _d_include
                _r = _r_include
            else:
                log.warn("warning: ignoring %s" % each[1])
                continue

            # find root directories and root files
            components = outfile.split("\\")
            # components[1] can be empty in case of e.g. "$4\\"
            if len(components) >= 2 and components[1]:
                root = "\\".join(components[:2])
                if len(components) >= 3:
                    root = root + "\\" # folder!
                if root not in _r:
                    _r.append(root)

            if lastdir != each[0]:
                lastdir=each[0]
                _f.append('  SetOutPath "%s"\n' % outpath)
            _f.append('  File "_python\\'+each[1]+'\"\n')
            _d.append('  Delete "%s"\n' % outfile)
            if outfile.lower().endswith(".py"):
                _d.append('  Delete "%so"\n' % outfile)
                _d.append('  Delete "%sc"\n' % outfile)

        # remove folders
        for _d, _r, tag in zip([_d_packages, _d_scripts, _d_include],
                               [_r_packages, _r_scripts, _r_include],
                               ['packages', 'scripts', 'include']):
            _d.append('  ; cleaning folders\n')
            for root in _r:
                if root.endswith("\\"):
                    _d.append('  RmDir /r "%s"\n' % root)

        # 2to3, compile, optimize
        for _f, _r, tag in zip([_f_packages, _f_scripts],
                               [_r_packages, _r_scripts],
                               ['packages', 'scripts']):
            if not _r:
                continue
            # 2to3
            _f.append('  !ifdef MISC_2TO3\n')
            _f.append('  Push $9\n')
            _f.append('  StrCmp $0 "" end_2to3_%s 0 ; only run if we have a full python install\n' % tag)
            _f.append('  StrCmp $1 "" end_2to3_%s 0 ; only run if we have an executable\n' % tag)
            _f.append('  StrCpy $9 "$2" 1\n')
            _f.append('  StrCmp $9 "3" 0 end_2to3_%s\n' % tag)
            _f.append('  SetOutPath "$0"\n')
            for root in _r:
                _f.append("""  nsExec::ExecToLog "$1 $\\"$0\\Tools\\Scripts\\2to3.py$\\" -w -n $\\"%s$\\""\n""" % root.rstrip("\\"))
            _f.append('end_2to3_%s:\n' % tag)
            _f.append('  Pop $9\n')
            _f.append('  !endif\n')
            # compile modules
            _f.append('  !ifdef MISC_COMPILE\n')
            _f.append('  StrCmp $0 "" end_compile_%s 0 ; only run if we have a full python install\n' % tag)
            _f.append('  StrCmp $1 "" end_compile_%s 0 ; only run if we have an executable\n' % tag)
            _f.append('  SetOutPath "$0"\n')
            for root in _r:
                if root.endswith("\\"):
                    _f.append("""  nsExec::ExecToLog "$1 -c $\\"import compileall; compileall.compile_dir('%s')$\\""\n""" % root.replace("\\", "\\\\"))
                else:
                    _f.append("""  nsExec::ExecToLog "$1 -c $\\"import py_compile; py_compile.compile('%s')$\\""\n""" % root.replace("\\", "\\\\"))
            _f.append('end_compile_%s:\n' % tag)
            _f.append('  !endif\n')
            _f.append('  !ifdef MISC_OPTIMIZE\n')
            _f.append('  StrCmp $0 "" end_optimize_%s 0 ; only run if we have a full python install\n' % tag)
            _f.append('  StrCmp $1 "" end_optimize_%s 0 ; only run if we have an executable\n' % tag)
            _f.append('  SetOutPath "$0"\n')
            for root in _r:
                if root.endswith("\\"):
                    _f.append("""  nsExec::ExecToLog "$1 -OO -c $\\"import compileall; compileall.compile_dir('%s')$\\""\n""" % root.replace("\\", "\\\\"))
                else:
                    _f.append("""  nsExec::ExecToLog "$1 -OO -c $\\"import py_compile; py_compile.compile('%s')$\\""\n""" % root.replace("\\", "\\\\"))
            _f.append('end_optimize_%s:\n' % tag)
            _f.append('  !endif\n')

        _f = []

        _f.append('  ; packages\n')
        _f.append('  StrCmp $3 "" end_packages 0\n')
        _f += _f_packages
        _f.append('end_packages:\n\n')
        _f.append('  ; scripts\n')
        _f.append('  StrCmp $4 "" end_scripts 0\n')
        _f += _f_scripts
        _f.append('end_scripts:\n\n')
        _f.append('  ; headers\n')
        _f.append('  StrCmp $5 "" end_include 0\n')
        _f += _f_include
        _f.append('end_include:\n\n')

        _d = []

        _d.append('  ; packages\n')
        _d.append('  StrCmp $3 "" end_clean_packages 0\n')
        _d += _d_packages
        _d.append('  Delete "$3\\${PRODUCT_NAME}*.egg-info"\n')
        _d.append('end_clean_packages:\n\n')
        _d.append('  ; scripts\n')
        _d.append('  StrCmp $4 "" end_clean_scripts 0\n')
        _d += _d_scripts
        _d.append('end_clean_scripts:\n\n')
        _d.append('  ; headers\n')
        _d.append('  StrCmp $5 "" end_clean_include 0\n')
        _d += _d_include
        _d.append('end_clean_include:\n\n')

        _d.append('  ; remove clutter\n')
        _d.append('  StrCmp $0 "" end_clean_clutter 0\n')
        _d.append('  Delete "$0\\Remove${PRODUCT_NAME}.*"\n')
        _d.append('  Delete "$0\\${PRODUCT_NAME}-wininst.log"\n')
        _d.append('end_clean_clutter:\n\n')

        nsiscript=nsiscript.replace('@_files@',''.join(_f))
        nsiscript=nsiscript.replace('@_deletefiles@',''.join(_d))

        abs_py_dir = os.path.abspath(self.bdist_dir+os.sep+'_python')
        if not self.no_target_compile:
            nsiscript=nsiscript.replace('@compile@','')
            print(sys.executable +
                  ' -c "import compileall; compileall.compile_dir(\'%s\')"'
                  % (abs_py_dir.replace('\\', '\\\\')))
            # compile folder - for size calculation below
            subprocess.call([sys.executable,
                             '-c', 'import compileall; compileall.compile_dir(\'%s\')'
                             % (abs_py_dir.replace('\\', '\\\\'))])
        else:
            nsiscript=nsiscript.replace('@compile@',';')        
            
        if not self.no_target_optimize:
            nsiscript=nsiscript.replace('@optimize@','')
            # compile folder - for size calculation below
            subprocess.call([sys.executable,
                             '-OO', '-c', 'import compileall; compileall.compile_dir(\'%s\')'
                             % (abs_py_dir.replace('\\', '\\\\'))])
        else:
            nsiscript=nsiscript.replace('@optimize@',';')

        # get total size
        def round4k(x):
            """Round number up to closest 4k boundary (disk space is allocated
            in chunks of 4k so this 'fixes' the file size).
            """
            return (1 + (x // 4096)) * 4096
        pysize = sum(
            sum(round4k(os.path.getsize(os.path.join(dirpath, filename)))
                for filename in filenames)
            for dirpath, dirnames, filenames
            in os.walk(self.bdist_dir+os.sep+'_python'))
        nsiscript=nsiscript.replace('@pysizekb@', str(1 + (pysize // 1000)))
        
        if self.run2to3:
            nsiscript=nsiscript.replace('@2to3@','')
        else:
            nsiscript=nsiscript.replace('@2to3@',';')   

        if self.msvc2005:
            nsiscript=nsiscript.replace('@msvc2005@','')
        else:
            nsiscript=nsiscript.replace('@msvc2005@',';')   

        if self.msvc2005sp1:
            nsiscript=nsiscript.replace('@msvc2005sp1@','')
        else:
            nsiscript=nsiscript.replace('@msvc2005sp1@',';')   

        if self.msvc2008:
            nsiscript=nsiscript.replace('@msvc2008@','')
        else:
            nsiscript=nsiscript.replace('@msvc2008@',';')   

        if self.msvc2008sp1:
            nsiscript=nsiscript.replace('@msvc2008sp1@','')
        else:
            nsiscript=nsiscript.replace('@msvc2008sp1@',';')   

        if self.nshextra:
            nsiscript=nsiscript.replace('@hasnshextra@','')
            nsiscript=nsiscript.replace('@nshextra@', self.nshextra)
        else:
            nsiscript=nsiscript.replace('@hasnshextra@',';')   

        if self.maya:
            nsiscript=nsiscript.replace('@maya@','')
        else:
            nsiscript=nsiscript.replace('@maya@',';')   

        if self.blender:
            nsiscript=nsiscript.replace('@blender@','')
        else:
            nsiscript=nsiscript.replace('@blender@',';')   

        if self.debug:
            nsiscript=nsiscript.replace('@debug@','')
        else:
            nsiscript=nsiscript.replace('@debug@',';')   

        nsiscript = nsiscript.replace("@srcdir@", self.abspath(os.getcwd()))

        # icon files
        # XXX todo: make icons configurable
        nsiscript = nsiscript.replace(
            "@ico_install@",
            self.abspath(os.path.join(os.path.dirname(__file__), "python-install.ico")))
        nsiscript = nsiscript.replace(
            "@ico_uninstall@",
            self.abspath(os.path.join(os.path.dirname(__file__), "python-uninstall.ico")))
        nsiscript = nsiscript.replace("@header_bitmap@", self.headerbitmap)
        nsiscript = nsiscript.replace("@welcome_bitmap@", self.bitmap)
        nsifile=open(os.path.join(self.bdist_dir,'setup.nsi'),'wt')
        nsifile.write(nsiscript)
        nsifile.close()
        self.compile()
        

    def visit(self,arg,dir,fil):
        for each in fil:
            if not os.path.isdir(dir+os.sep+each):
                f=str(dir+os.sep+each)[len(self.bdist_dir+os.sep+'_python'+os.sep):]
                # replace / by \\ so it works on linux too
                arg.append([os.path.dirname(f).replace("/", "\\"),
                            f.replace("/", "\\")])
                
    def compile(self):
        if self.nsis_dir is not None:
            # create destination directory
            # (nsis complains if it does not yet exist)
            self.mkpath(self.dist_dir)
            try:
                spawn([os.path.join(self.nsis_dir),
                       os.path.join(self.bdist_dir, 'setup.nsi')])
            except:
                print("Warning: possible error during NSIS compilation.")

            
# class bdist_nsi

def get_nsi(pythonversions=None):
    # list all maya versions
    mayaversions = [
        ("2.5", "2008", "2008"),
        ("2.5", "2008_x64", "2008-x64"),
        ("2.5", "2009", "2009"),
        ("2.5", "2009_x64", "2009-x64"),
        ("2.6", "2010", "2010"),
        ("2.6", "2010_x64", "2010-x64"),
        ]

    # filter maya versions    
    mayaversions = [
        (pythonversion, mayaversion, mayaregistry)
        for pythonversion, mayaversion, mayaregistry in mayaversions
        if pythonversion in pythonversions
        ]

    NSI_HEADER = """\
; @name@ self-installer for Windows
; (@name@ - @url@)
; (NSIS - http://nsis.sourceforge.net)



; Define Application Specific Constants
; =====================================

!define PRODUCT_NAME "@name@"
!define PRODUCT_VERSION "@version@"
!define PRODUCT_PUBLISHER "@author@ <@author_email@>"
!define PRODUCT_WEB_SITE "@url@"
!define PRODUCT_UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}"
!define PRODUCT_UNINST_ROOT_KEY "HKLM"
!define MISC_SRCDIR "@srcdir@"
!define MISC_PYSIZEKB "@pysizekb@"
@compile@!define MISC_COMPILE "1"
@optimize@!define MISC_OPTIMIZE "1"
@2to3@!define MISC_2TO3 "1"
@msvc2005@!define MISC_MSVC2005 "1"
@msvc2005sp1@!define MISC_MSVC2005SP1 "1"
@msvc2008@!define MISC_MSVC2008 "1"
@msvc2008sp1@!define MISC_MSVC2008SP1 "1"
@maya@!define MISC_MAYA "1"
@blender@!define MISC_BLENDER "1"
@hasurl@BrandingText "@url@"
@hasnshextra@!define MISC_NSHEXTRA "1"

@debug@!define MISC_DEBUG "1"


; Various Settings
; ================

; solid lzma gives best compression in virtually all cases
SetCompressor /SOLID lzma

Name "${PRODUCT_NAME} ${PRODUCT_VERSION}"
OutFile "@installer_path@"
InstallDir "$PROGRAMFILES\\${PRODUCT_NAME}"
ShowInstDetails show
ShowUnInstDetails show



; Includes
; ========

!include "MUI2.nsh"
!include "LogicLib.nsh"



; MUI Settings
; ============

!define MUI_ABORTWARNING
!define MUI_FINISHPAGE_NOAUTOCLOSE
!define MUI_UNFINISHPAGE_NOAUTOCLOSE

!define MUI_ICON "@ico_install@"
!define MUI_UNICON "@ico_uninstall@"

!define MUI_HEADERIMAGE
!define MUI_HEADERIMAGE_BITMAP "@header_bitmap@"
!define MUI_HEADERIMAGE_UNBITMAP "@header_bitmap@"

!define MUI_WELCOMEFINISHPAGE_BITMAP "@welcome_bitmap@"
!define MUI_UNWELCOMEFINISHPAGE_BITMAP "@welcome_bitmap@"

!insertmacro MUI_PAGE_WELCOME
@haslicensefile@!insertmacro MUI_PAGE_LICENSE "@licensefile@"
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_WELCOME
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_UNPAGE_FINISH

!define MUI_COMPONENTSPAGE_NODESC



; Languages
; =========

!insertmacro MUI_LANGUAGE "English" ;first language is the default language
!insertmacro MUI_LANGUAGE "French"
!insertmacro MUI_LANGUAGE "German"
!insertmacro MUI_LANGUAGE "Spanish"
!insertmacro MUI_LANGUAGE "SpanishInternational"
!insertmacro MUI_LANGUAGE "SimpChinese"
!insertmacro MUI_LANGUAGE "TradChinese"
!insertmacro MUI_LANGUAGE "Japanese"
!insertmacro MUI_LANGUAGE "Korean"
!insertmacro MUI_LANGUAGE "Italian"
!insertmacro MUI_LANGUAGE "Dutch"
!insertmacro MUI_LANGUAGE "Danish"
!insertmacro MUI_LANGUAGE "Swedish"
!insertmacro MUI_LANGUAGE "Norwegian"
!insertmacro MUI_LANGUAGE "NorwegianNynorsk"
!insertmacro MUI_LANGUAGE "Finnish"
!insertmacro MUI_LANGUAGE "Greek"
!insertmacro MUI_LANGUAGE "Russian"
!insertmacro MUI_LANGUAGE "Portuguese"
!insertmacro MUI_LANGUAGE "PortugueseBR"
!insertmacro MUI_LANGUAGE "Polish"
!insertmacro MUI_LANGUAGE "Ukrainian"
!insertmacro MUI_LANGUAGE "Czech"
!insertmacro MUI_LANGUAGE "Slovak"
!insertmacro MUI_LANGUAGE "Croatian"
!insertmacro MUI_LANGUAGE "Bulgarian"
!insertmacro MUI_LANGUAGE "Hungarian"
!insertmacro MUI_LANGUAGE "Thai"
!insertmacro MUI_LANGUAGE "Romanian"
!insertmacro MUI_LANGUAGE "Latvian"
!insertmacro MUI_LANGUAGE "Macedonian"
!insertmacro MUI_LANGUAGE "Estonian"
!insertmacro MUI_LANGUAGE "Turkish"
!insertmacro MUI_LANGUAGE "Lithuanian"
!insertmacro MUI_LANGUAGE "Slovenian"
!insertmacro MUI_LANGUAGE "Serbian"
!insertmacro MUI_LANGUAGE "SerbianLatin"
!insertmacro MUI_LANGUAGE "Arabic"
!insertmacro MUI_LANGUAGE "Farsi"
!insertmacro MUI_LANGUAGE "Hebrew"
!insertmacro MUI_LANGUAGE "Indonesian"
!insertmacro MUI_LANGUAGE "Mongolian"
!insertmacro MUI_LANGUAGE "Luxembourgish"
!insertmacro MUI_LANGUAGE "Albanian"
!insertmacro MUI_LANGUAGE "Breton"
!insertmacro MUI_LANGUAGE "Belarusian"
!insertmacro MUI_LANGUAGE "Icelandic"
!insertmacro MUI_LANGUAGE "Malay"
!insertmacro MUI_LANGUAGE "Bosnian"
!insertmacro MUI_LANGUAGE "Kurdish"
!insertmacro MUI_LANGUAGE "Irish"
!insertmacro MUI_LANGUAGE "Uzbek"
!insertmacro MUI_LANGUAGE "Galician"
!insertmacro MUI_LANGUAGE "Afrikaans"
!insertmacro MUI_LANGUAGE "Catalan"
!insertmacro MUI_LANGUAGE "Esperanto"

; If you are using solid compression, files that are required before
; the actual installation should be stored first in the data block,
; because this will make your installer start faster.
  
!insertmacro MUI_RESERVEFILE_LANGDLL



; Extra header
; ============

!ifdef MISC_NSHEXTRA
!include "@nshextra@"
!endif



; Install and uninstall functions
; ===============================

; $0 = full path to python directory (typically, C:\PythonXX)
; $1 = full path to python executable (typically, C:\PythonXX\python.exe; if empty then compile/optimize/2to3 will be disabled)
; $2 = python version (e.g. "2.6")
; $3 = full path to python package directory (typically, C:\PythonXX\Lib\site-packages)
; $4 = full path to python scripts directory (if empty, not installed)
; $5 = full path to python include directory (if empty, not installed)
Function InstallFiles

  ; first remove any stray files leftover from a previous installation
@_deletefiles@

  !ifdef MISC_NSHEXTRA
  !insertmacro UninstallFilesExtra
  !endif

  ; now install all files
@_files@

  !ifdef MISC_NSHEXTRA
  !insertmacro InstallFilesExtra
  !endif
FunctionEnd

Function un.InstallFiles
@_deletefiles@

  !ifdef MISC_NSHEXTRA
  !insertmacro UninstallFilesExtra
  !endif
FunctionEnd



; Macros
; ======

!macro GetPythonPath PYTHONVERSION un
; Function to detect the python path
Function ${un}GetPythonPath${PYTHONVERSION}
    ClearErrors

    ReadRegStr $PYTHONPATH${PYTHONVERSION} HKLM "SOFTWARE\Python\PythonCore\${PYTHONVERSION}\InstallPath" ""
    IfErrors 0 python_registry_found

    ReadRegStr $PYTHONPATH${PYTHONVERSION} HKCU "SOFTWARE\Python\PythonCore\${PYTHONVERSION}\InstallPath" ""
    IfErrors 0 python_registry_found

    ; clean string just in case
    StrCpy $PYTHONPATH${PYTHONVERSION} ""

!ifdef MISC_DEBUG
    MessageBox MB_OK "Python ${PYTHONVERSION} not found in registry."
!endif

    Goto python_path_done

python_registry_found:

    ; remove trailing backslash using the $EXEDIR trick
    Push $PYTHONPATH${PYTHONVERSION}
    Exch $EXEDIR
    Exch $EXEDIR
    Pop $PYTHONPATH${PYTHONVERSION}

!ifdef MISC_DEBUG
    MessageBox MB_OK "Found Python ${PYTHONVERSION} path in registry: $PYTHONPATH${PYTHONVERSION}"
!endif

    IfFileExists $PYTHONPATH${PYTHONVERSION}\python.exe 0 python_exe_not_found

!ifdef MISC_DEBUG
    MessageBox MB_OK "Found Python executable at $PYTHONPATH${PYTHONVERSION}\python.exe."
!endif

    GoTo python_path_done

python_exe_not_found:

!ifdef MISC_DEBUG
    MessageBox MB_OK "Python ${PYTHONVERSION} executable not found."
!endif

    StrCpy $PYTHONPATH${PYTHONVERSION} ""

python_path_done:

FunctionEnd
!macroend

!macro PythonSectionDef PYTHONVERSION un
; Install the library for Python ${PYTHONVERSION}
Section ${un}${PYTHONVERSION} ${un}Python${PYTHONVERSION}
    SetShellVarContext all

    StrCmp $PYTHONPATH${PYTHONVERSION} "" python_install_end

    StrCpy $0 "$PYTHONPATH${PYTHONVERSION}"
    StrCpy $1 "$PYTHONPATH${PYTHONVERSION}\\python.exe"
    StrCpy $2 "${PYTHONVERSION}"
    StrCpy $3 "$PYTHONPATH${PYTHONVERSION}\\Lib\\site-packages"
    StrCpy $4 "$PYTHONPATH${PYTHONVERSION}\\Scripts"
    StrCpy $5 "$PYTHONPATH${PYTHONVERSION}\\Include"
    Call ${un}InstallFiles

python_install_end:

SectionEnd
!macroend

!macro PythonSection PYTHONVERSION
!define HAVE_SECTION_PYTHON${PYTHONVERSION}
; Set up variable for install path of this python version
Var PYTHONPATH${PYTHONVERSION}
!insertmacro GetPythonPath ${PYTHONVERSION} ""
!insertmacro GetPythonPath ${PYTHONVERSION} "un."
!insertmacro PythonSectionDef ${PYTHONVERSION} ""
!macroend

!macro un.PythonSection PYTHONVERSION
!insertmacro PythonSectionDef ${PYTHONVERSION} "un."
!macroend



!ifdef MISC_MAYA

!macro GetMayaPath PYTHONVERSION MAYAVERSION MAYAREGISTRY un
; Function to detect the maya path
Function ${un}GetMayaPath${MAYAVERSION}
    ClearErrors

    ReadRegStr $MAYAPATH${MAYAVERSION} HKLM "SOFTWARE\Autodesk\Maya\${MAYAREGISTRY}\Setup\InstallPath" "MAYA_INSTALL_LOCATION"
    IfErrors 0 maya_registry_found

    ReadRegStr $MAYAPATH${MAYAVERSION} HKCU "SOFTWARE\Autodesk\Maya\${MAYAREGISTRY}\Setup\InstallPath" "MAYA_INSTALL_LOCATION"
    IfErrors 0 maya_registry_found

    ; clean string just in case
    StrCpy $MAYAPATH${MAYAVERSION} ""

!ifdef MISC_DEBUG
    MessageBox MB_OK "Maya ${MAYAVERSION} not found in registry."
!endif

    Goto maya_path_done

maya_registry_found:

    ; remove trailing backslash using the $EXEDIR trick
    Push $MAYAPATH${MAYAVERSION}
    Exch $EXEDIR
    Exch $EXEDIR
    Pop $MAYAPATH${MAYAVERSION}

!ifdef MISC_DEBUG
    MessageBox MB_OK "Found Maya ${MAYAVERSION} path in registry: $MAYAPATH${MAYAVERSION}"
!endif

    IfFileExists $MAYAPATH${MAYAVERSION}\\bin\mayapy.exe 0 mayapy_exe_not_found

!ifdef MISC_DEBUG
    MessageBox MB_OK "Found Python executable for Maya ${MAYAVERSION} at $MAYAPATH${MAYAVERSION}\\bin\mayapy.exe."
!endif

    GoTo maya_path_done

mayapy_exe_not_found:

!ifdef MISC_DEBUG
    MessageBox MB_OK "Python executable for Maya ${MAYAVERSION} not found."
!endif

    StrCpy $MAYAPATH${MAYAVERSION} ""

maya_path_done:

FunctionEnd
!macroend ;GetMayaPath

!macro MayaSectionDef PYTHONVERSION MAYAVERSION MAYAREGISTRY un
; Install the library for Maya ${MAYAVERSION}
Section ${un}"${MAYAVERSION}" ${un}Maya${MAYAVERSION}
    SetShellVarContext all

    StrCmp $MAYAPATH${MAYAVERSION} "" maya_install_end

    StrCpy $0 "$MAYAPATH${MAYAVERSION}\\Python"
    StrCpy $1 "$MAYAPATH${MAYAVERSION}\\bin\\mayapy.exe"
    StrCpy $2 "${PYTHONVERSION}"
    StrCpy $3 "$MAYAPATH${MAYAVERSION}\\Python\\Lib\\site-packages"
    StrCpy $4 "" ; no scripts
    StrCpy $5 "" ; no headers

    Call ${un}InstallFiles

maya_install_end:

SectionEnd
!macroend ;MayaSectionDef

!macro MayaSection PYTHONVERSION MAYAVERSION MAYAREGISTRY
Var MAYAPATH${MAYAVERSION}
!insertmacro GetMayaPath ${PYTHONVERSION} ${MAYAVERSION} ${MAYAREGISTRY} ""
!insertmacro GetMayaPath ${PYTHONVERSION} ${MAYAVERSION} ${MAYAREGISTRY} "un."
!insertmacro MayaSectionDef ${PYTHONVERSION} ${MAYAVERSION} ${MAYAREGISTRY} ""
!macroend

!macro un.MayaSection PYTHONVERSION MAYAVERSION MAYAREGISTRY
!insertmacro MayaSectionDef ${PYTHONVERSION} ${MAYAVERSION} ${MAYAREGISTRY} "un."
!macroend

!endif ;MISC_MAYA



!ifdef MISC_BLENDER

; Function to detect the blender path
!macro GetBlenderPath un
Function ${un}GetBlenderPath
  ; clear variables
  StrCpy $BLENDERHOME ""
  StrCpy $BLENDERSCRIPTS ""
  StrCpy $BLENDERINST ""

  ClearErrors

  ReadRegStr $BLENDERHOME HKLM SOFTWARE\BlenderFoundation "Install_Dir"
  IfErrors 0 blender_registry_check_end
  ReadRegStr $BLENDERHOME HKCU SOFTWARE\BlenderFoundation "Install_Dir"
  IfErrors 0 blender_registry_check_end

     ; no key, that means that Blender is not installed
     Goto blender_scripts_not_found

blender_registry_check_end:
  StrCpy $BLENDERINST $BLENDERHOME

  ; get Blender scripts dir

  ; first try Blender's global install dir
  StrCpy $BLENDERSCRIPTS "$BLENDERHOME\.blender\scripts"
  IfFileExists "$BLENDERSCRIPTS\*.*" blender_scripts_found 0

; XXX check disabled for now - function should be non-interactive
;  ; check if we are running vista, if so, complain to user because scripts are not in the "safe" location
;  Call GetWindowsVersion
;  Pop $0
;  StrCmp $0 "Vista" 0 blender_scripts_notininstallfolder
;  
;    MessageBox MB_YESNO|MB_ICONQUESTION "You are running Windows Vista, but Blender's user data files (such as scripts) do not reside in Blender's installation directory. On Vista, Blender will sometimes only find its scripts if Blender's user data files reside in Blender's installation directory. Do you wish to abort installation, and first reinstall Blender, selecting 'Use the installation directory' when the Blender installer asks you to specify where to install Blender's user data files?" IDNO blender_scripts_notininstallfolder
;    MessageBox MB_OK "Pressing OK will take you to the Blender download page. Please download and run the Blender windows installer. Select 'Use the installation directory' when the Blender installer asks you to specify where to install Blender's user data files. When you are done, rerun the ColladaCGF installer."
;    StrCpy $0 "http://www.blender.org/download/get-blender/"
;    Call openLinkNewWindow
;    Abort ; causes installer to quit
;
;blender_scripts_notininstallfolder:

  ; now try Blender's application data directory (current user)
  SetShellVarContext current
  StrCpy $BLENDERHOME "$APPDATA\Blender Foundation\Blender"
  StrCpy $BLENDERSCRIPTS "$BLENDERHOME\.blender\scripts"
  IfFileExists "$BLENDERSCRIPTS\*.*" blender_scripts_found 0
  
  ; now try Blender's application data directory (everyone)
  SetShellVarContext all
  StrCpy $BLENDERHOME "$APPDATA\Blender Foundation\Blender"
  StrCpy $BLENDERSCRIPTS "$BLENDERHOME\.blender\scripts"
  IfFileExists "$BLENDERSCRIPTS\*.*" blender_scripts_found 0

  ; finally, try the %HOME% variable
  ReadEnvStr $BLENDERHOME "HOME"
  StrCpy $BLENDERSCRIPTS "$BLENDERHOME\.blender\scripts"
  IfFileExists "$BLENDERSCRIPTS\*.*" blender_scripts_found 0
  
    ; all failed!
    GoTo blender_scripts_not_found

blender_scripts_found:

    ; remove trailing backslash using the $EXEDIR trick
    Push $BLENDERHOME
    Exch $EXEDIR
    Exch $EXEDIR
    Pop $BLENDERHOME
    Push $BLENDERSCRIPTS
    Exch $EXEDIR
    Exch $EXEDIR
    Pop $BLENDERSCRIPTS
    Push $BLENDERINST
    Exch $EXEDIR
    Exch $EXEDIR
    Pop $BLENDERINST

    ; debug
    ;MessageBox MB_OK "Found Blender scripts in $BLENDERSCRIPTS"

    IfFileExists $BLENDERINST\\blender.exe blender_scripts_done blender_scripts_not_found

blender_scripts_not_found:

  StrCpy $BLENDERHOME ""
  StrCpy $BLENDERSCRIPTS ""
  StrCpy $BLENDERINST ""

blender_scripts_done:

FunctionEnd
!macroend

!macro BlenderSectionDef un
; Install the library for Blender 
Section ${un}Blender ${un}Blender
    SetShellVarContext all

    StrCmp $BLENDERSCRIPTS "" blender_install_end

    StrCpy $0 "" ; XXX todo: set python path
    StrCpy $1 "" ; XXX todo: set python executable
    StrCpy $2 "" ; XXX todo: set python version
    StrCpy $3 "$BLENDERSCRIPTS\\bpymodules"
    StrCpy $4 "" ; no scripts
    StrCpy $5 "" ; no headers
    Call ${un}InstallFiles

blender_install_end:

SectionEnd
!macroend ;BlenderSectionDef

!macro BlenderSection
Var BLENDERHOME    ; blender settings location
Var BLENDERSCRIPTS ; blender scripts location ($BLENDERHOME/.blender/scripts)
Var BLENDERINST    ; blender.exe location
!insertmacro GetBlenderPath ""
!insertmacro BlenderSectionDef ""
!macroend ;BlenderSection

!macro un.BlenderSection
!insertmacro GetBlenderPath "un."
!insertmacro BlenderSectionDef "un."
!macroend ;un.BlenderSection

!endif ;MISC_BLENDER



!include "FileFunc.nsh"
!include "WordFunc.nsh"

!insertmacro Locate
!insertmacro VersionCompare

!macro SearchDLL DLLLABEL DLLDESC DLLFILE DLLVERSION DLLLINK

Var DLLFound${DLLLABEL}

!define REQUIREOPENLINKNEWWINDOW "1"
Function Download${DLLLABEL}
  Push ${DLLLINK}
  MessageBox MB_OK "You will need to download ${DLLDESC}. Pressing OK will take you to the download page, please follow the instructions on the page that appears."
  StrCpy $0 ${DLLLINK}
  Call openLinkNewWindow
FunctionEnd

Function LocateCallback${DLLLABEL}
  MoreInfo::GetProductVersion "$R9"
  Pop $0

  ${VersionCompare} "$0" "${DLLVERSION}" $R1

  ; $R1 contains the result of the comparison
  ; 0 = versions are equal
  ; 1 = first version is newer than second version
  ; 2 = first version is older than second version
  StrCmp $R1 2 0 found

  ; version $0 is older than ${DLLVERSION}
  ;DEBUG;MessageBox MB_OK "${DLLFILE} ($0) is too old."
  Push "$0"
  GoTo notfound

found:
  ; version $0 is equal or newer than ${DLLVERSION}
  ;DEBUG;MessageBox MB_OK "${DLLFILE} ($0) located!"
  StrCpy "$0" StopLocate
  StrCpy $DLLFound${DLLLABEL} "true"
  Push "$0"
notfound:
FunctionEnd

Function Find${DLLLABEL}
  Push $0
  Push $1

  DetailPrint "Locating ${DLLDESC}: ${DLLFILE} (${DLLVERSION})."

  StrCpy $1 $WINDIR
  StrCpy $DLLFound${DLLLABEL} "false"
  ${Locate} "$1" "/L=F /M=${DLLFILE} /S=0B" "LocateCallback${DLLLABEL}"
  StrCmp $DLLFound${DLLLABEL} "false" 0 +2
    Call Download${DLLLABEL}

  Pop $1
  Pop $0
FunctionEnd
!macroend


!ifdef MISC_MSVC2005
!insertmacro SearchDLL "MSVC2005" "Microsoft Visual C++ 2005 Redistributable Package" "MSVCR80.DLL" "8.0.50727.42" "http://www.microsoft.com/downloads/details.aspx?familyid=32bc1bee-a3f9-4c13-9c99-220b62a191ee&displaylang=en"
!endif

!ifdef MISC_MSVC2005SP1
!insertmacro SearchDLL "MSVC2005SP1" "Microsoft Visual C++ 2005 SP1 Redistributable Package" "MSVCR80.DLL" "8.0.50727.762" "http://www.microsoft.com/downloads/details.aspx?familyid=200b2fd9-ae1a-4a14-984d-389c36f85647&displaylang=en"
!endif

!ifdef MISC_MSVC2008
!insertmacro SearchDLL "MSVC2008" "Microsoft Visual C++ 2008 Redistributable Package" "MSVCR90.DLL" "9.0.21022.8" "http://www.microsoft.com/downloads/details.aspx?FamilyID=9b2da534-3e03-4391-8a4d-074b9f2bc1bf&DisplayLang=en"
!endif

!ifdef MISC_MSVC2008SP1
!insertmacro SearchDLL "MSVC2008SP1" "Microsoft Visual C++ 2008 SP1 Redistributable Package" "MSVCR90.DLL" "9.0.30729.1" "http://www.microsoft.com/downloads/details.aspx?familyid=A5C84275-3B97-4AB7-A40D-3802B2AF5FC2&displaylang=en"
!endif
"""

    NSI_FOOTER = """
; Functions
; =========

!ifdef REQUIREOPENLINKNEWWINDOW
; taken from http://nsis.sourceforge.net/Open_link_in_new_browser_window
# uses $0
Function openLinkNewWindow
  Push $3 
  Push $2
  Push $1
  Push $0
  ReadRegStr $0 HKCR "http\shell\open\command" ""
# Get browser path
    DetailPrint $0
  StrCpy $2 '"'
  StrCpy $1 $0 1
  StrCmp $1 $2 +2 # if path is not enclosed in " look for space as final char
    StrCpy $2 ' '
  StrCpy $3 1
  loop:
    StrCpy $1 $0 1 $3
    DetailPrint $1
    StrCmp $1 $2 found
    StrCmp $1 "" found
    IntOp $3 $3 + 1
    Goto loop
 
  found:
    StrCpy $1 $0 $3
    StrCmp $2 " " +2
      StrCpy $1 '$1"'
 
  Pop $0
  Exec '$1 $0'
  Pop $1
  Pop $2
  Pop $3
FunctionEnd
!endif

Function .onInit
  ; Check if user is admin.
  ; Call userInfo plugin to get user info.
  ; The plugin puts the result in the stack.
  userInfo::getAccountType

  ; pop the result from the stack into $0
  pop $0

  ; Compare the result with the string "Admin" to see if the user is admin.
  ; If match, jump 3 lines down.
  strCmp $0 "Admin" +3
  
    ; if there is not a match, print message and return
    messageBox MB_OK|MB_ICONEXCLAMATION "You require administrator privileges to install ${PRODUCT_NAME} successfully."
    Abort ; quit installer

  ; Language selection.
  !insertmacro MUI_LANGDLL_DISPLAY

  ; check python versions
""" + "\n".join("""\
  SectionSetSize ${Python${PYTHONVERSION}} ${MISC_PYSIZEKB}
  Call GetPythonPath${PYTHONVERSION}
  StrCmp $PYTHONPATH${PYTHONVERSION} "" 0 +2
  ; python version not found, so disable that section
  SectionSetFlags ${Python${PYTHONVERSION}} ${SF_RO}
""".replace("${PYTHONVERSION}", pythonversion)
                for pythonversion in pythonversions) + """

  ; check maya versions

  !ifdef MISC_MAYA

""" + "\n".join("""\
  SectionSetSize ${Maya${MAYAVERSION}} ${MISC_PYSIZEKB}
  Call GetMayaPath${MAYAVERSION}
  StrCmp $MAYAPATH${MAYAVERSION} "" 0 +2
  ; maya version not found, so disable that section
  SectionSetFlags ${Maya${MAYAVERSION}} ${SF_RO}
""".replace("${MAYAVERSION}", mayaversion)
                for pythonversion, mayaversion, mayaregistry in mayaversions) + """
  !endif ;MISC_MAYA

  !ifdef MISC_BLENDER

  SectionSetSize ${Blender} ${MISC_PYSIZEKB}
  Call GetBlenderPath
  StrCmp $BLENDERSCRIPTS "" 0 +2
  ; blender version not found, so disable that section
  SectionSetFlags ${Blender} ${SF_RO}

  !endif ;MISC_BLENDER

FunctionEnd

Function un.onInit
""" + "\n".join("  Call un.GetPythonPath%s" % pythonversion
                 for pythonversion in pythonversions) + """


  !ifdef MISC_MAYA

""" + "\n".join("  Call un.GetMayaPath%s" % mayaversion
                 for pythonversion, mayaversion, mayaregistry in mayaversions) + """
""" + """
  !endif ;MISC_MAYA



  !ifdef MISC_BLENDER

  Call un.GetBlenderPath

  !endif ;MISC_BLENDER

FunctionEnd

Section -Post
  SetOutPath "$INSTDIR"
  WriteUninstaller "$INSTDIR\\${PRODUCT_NAME}_uninstall.exe"
  WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "DisplayName" "$(^Name)"
  WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "UninstallString" "$INSTDIR\${PRODUCT_NAME}_uninstall.exe"
  WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "DisplayVersion" "${PRODUCT_VERSION}"
  WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "URLInfoAbout" "${PRODUCT_WEB_SITE}"
  WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "Publisher" "${PRODUCT_PUBLISHER}"

  !ifdef MISC_NSHEXTRA
  !insertmacro UnPostExtra
  !insertmacro PostExtra
  !endif

  !ifdef MISC_MSVC2005
  Call FindMSVC2005
  !endif

  !ifdef MISC_MSVC2005SP1
  Call FindMSVC2005SP1
  !endif

  !ifdef MISC_MSVC2008
  Call FindMSVC2008
  !endif

  !ifdef MISC_MSVC2008SP1
  Call FindMSVC2008SP1
  !endif
SectionEnd

Section un.Post
  !ifdef MISC_NSHEXTRA
  !insertmacro UnPostExtra
  !endif

  Delete "$INSTDIR\\${PRODUCT_NAME}_uninstall.exe"
  RmDir "$INSTDIR"
  DeleteRegKey ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}"
SectionEnd
"""

    return (NSI_HEADER
            + "\nSectionGroup /e Python\n"
            + "\n".join(
                "!insertmacro PythonSection %s" % pythonversion
                for pythonversion in pythonversions)
            + "\nSectionGroupEnd\n\n"
            + "\nSectionGroup /e un.Python\n"
            + "\n".join(
                "!insertmacro un.PythonSection %s" % pythonversion
                for pythonversion in pythonversions)
            + "\nSectionGroupEnd\n\n\n"
            + "!ifdef MISC_MAYA\n"
            + "\nSectionGroup /e Maya\n"
            + "\n".join(
                "!insertmacro MayaSection %s %s %s"
                % (pythonversion, mayaversion, mayaregistry)
                for pythonversion, mayaversion, mayaregistry in mayaversions)
            + "\nSectionGroupEnd\n\n"
            + "\nSectionGroup /e un.Maya\n"
            + "\n".join(
                "!insertmacro un.MayaSection %s %s %s"
                % (pythonversion, mayaversion, mayaregistry)
                for pythonversion, mayaversion, mayaregistry in mayaversions)
            + "\nSectionGroupEnd\n\n"
            + "!endif ;MISC_MAYA\n\n\n"
            + "!ifdef MISC_BLENDER\n"
            + "!insertmacro BlenderSection\n"
            + "!insertmacro un.BlenderSection\n"
            + "!endif ;MISC_BLENDER\n\n\n"
            + NSI_FOOTER)
