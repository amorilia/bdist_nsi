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
                    ]

    boolean_options = ['keep-temp', 'no-target-compile', 'no-target-optimize',
                       'skip-build', 'run2to3', 'msvc2005', 'msvc2005sp1',
                       'msvc2008', 'msvc2008sp1']

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
                                             "python-install-150x57.bmp")
        else:
            self.headerbitmap = os.path.abspath(self.headerbitmap)
        if not self.bitmap:
            self.bitmap = os.path.join(os.path.dirname(__file__),
                                       "python-install-164x314.bmp")
        else:
            self.bitmap = os.path.abspath(self.bitmap)

        if self.nshextra:
            self.nshextra = os.path.abspath(self.nshextra)

        self.set_undefined_options('bdist',
                                   ('dist_dir', 'dist_dir'),
                                   ('plat_name', 'plat_name'),
                                   ('nsis_dir', 'nsis_dir'),
                                  )

    # finalize_options()


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
                                            os.path.abspath(licensefile))
                break
        else:
            nsiscript=nsiscript.replace('@haslicensefile@', ";")

        # dist dir relative to the build dir
        distdir=os.path.join('..','..','..',self.dist_dir)
            
        if self.target_version:
            installer_path = os.path.join(distdir, "%s.win32-py%s.exe" % (self.distribution.get_fullname(), self.target_version))
        else:
            installer_path = os.path.join(distdir, "%s.win32.exe" % self.distribution.get_fullname())
                
        nsiscript=nsiscript.replace('@installer_path@',installer_path)
        
        haspythonversion=";"
        if self.target_version.upper() not in ["","ANY"]:
            nsiscript=nsiscript.replace('@pythonversion@',self.target_version)
            haspythonversion=""
            
        nsiscript=nsiscript.replace('@haspythonversion@',haspythonversion)
        
        files=[]
        
        os.path.walk(self.bdist_dir+os.sep+'_python',self.visit,files)
        
        _f=[]
        _d=[]
        _fd=[]
        _fc=[]
        _froots=[]
        lastdir=""
        for each in files:
            # skip egg info files
            if each[1].endswith(".egg-info"):
                continue
            if lastdir != each[0]:
                _f.append('  SetOutPath "$0\%s"\n' % each[0])
                lastdir=each[0]
                if each[0] not in ['Lib\\site-packages','Scripts','Include','']:
                    #_d.insert(0,'    RMDir "$0\\'+each[0]+'\"\n')
                    # find root directories of modules
                    if each[0].startswith("Lib\\site-packages\\"):
                        root = "\\".join(each[0].split("\\")[:3])
                        if root not in _froots:
                            _froots.append(root)
                            _d.append('    RMDir /r "$0\\%s"\n' % root)
            _f.append('  File "_python\\'+each[1]+'\"\n')
            
            if (each[1][len(each[1])-3:].lower() == ".py"):
                _fc.append('"'+each[1]+'",\n')
                if each[0].lower() == "scripts":
                    _fd.append('    Delete "$0\\'+each[1]+'o'+'\"\n')
                    _fd.append('    Delete "$0\\'+each[1]+'c'+'\"\n')
            if each[0].lower() == "scripts":
                _fd.append('    Delete "$0\\'+each[1]+'\"\n')
        _fd.append('    Delete "$0\\Remove${PRODUCT_NAME}.*"\n')
        _fd.append('    Delete "$0\\${PRODUCT_NAME}-wininst.log"\n')
        _fd.append('    Delete "$0\\${PRODUCT_NAME}*.egg-info"\n')
        # 2to3
        _f.append('  !ifdef MISC_2TO3\n')
        _f.append('  Push $9\n')
        _f.append('  StrCpy $9 "$2" 1\n')
        _f.append('  StrCmp $9 "3" 0 end2to3\n')
        _f.append('  SetOutPath "$0"\n')
        for root in _froots:
            _f.append("""  nsExec::ExecToLog "$0\\$1 $\\"$0\\Tools\\Scripts\\2to3.py$\\" -w -n $\\"$0\\%s$\\""\n""" % root)
        _f.append('end2to3:\n')
        _f.append('  Pop $9\n')
        _f.append('  !endif\n')
        # compile modules
        _f.append('  !ifdef MISC_COMPILE\n')
        _f.append('  SetOutPath "$0"\n')
        _f.append("""  nsExec::ExecToLog "$0\$1 -c $\\"import compileall; compileall.compile_dir('Scripts')$\\""\n""")
        for root in _froots:
            _f.append("""  nsExec::ExecToLog "$0\$1 -c $\\"import compileall; compileall.compile_dir('%s')$\\""\n""" % root.replace("\\", "\\\\"))
        _f.append('  !endif\n')
        _f.append('  !ifdef MISC_OPTIMIZE\n')
        _f.append('  SetOutPath "$0"\n')
        _f.append("""  nsExec::ExecToLog "$0\$1 -OO -c $\\"import compileall; compileall.compile_dir('Scripts')$\\""\n""")
        for root in _froots:
            _f.append("""  nsExec::ExecToLog "$0\$1 -OO -c $\\"import compileall; compileall.compile_dir('%s')$\\""\n""" % root.replace("\\", "\\\\"))
        _f.append('  !endif\n')
        nsiscript=nsiscript.replace('@_files@',''.join(_f))
        nsiscript=nsiscript.replace('@_deletefiles@',''.join(_fd))
        nsiscript=nsiscript.replace('@_deletedirs@',''.join(_d))

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

        nsiscript = nsiscript.replace("@srcdir@", os.getcwd())

        # icon files
        # XXX todo: make icons configurable
        nsiscript = nsiscript.replace(
            "@ico_install@",
            os.path.join(os.path.dirname(__file__), "python-install.ico"))
        nsiscript = nsiscript.replace(
            "@ico_uninstall@",
            os.path.join(os.path.dirname(__file__), "python-uninstall.ico"))
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
    if "2.5" in pythonversions:
        # maya versions that come with Python 2.5
        mayaversions = [
            ("2008", "2008"),
            ("2008_x64", "2008-x64"),
            ("2009", "2009"),
            ("2009_x64", "2009-x64"),
            ]
    else:
        mayaversions = []
    
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
@hasurl@BrandingText "@url@"
@hasnshextra@!define MISC_NSHEXTRA "1"



; Extra header
; ============

!ifdef MISC_NSHEXTRA
!include "@nshextra@"
!endif



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



; Core
; ====

Section "Core" Core
    SectionIn RO
SectionEnd



; Macros
; ======

; $0 = install path (typically, C:\PythonXX)
; $1 = python executable (typically, python.exe)
; $2 = python version (e.g. "2.6")
Function InstallFiles

  ; first remove any stray files leftover from a previous installation
  Call UninstallFiles

  ; now install all files
@_files@

  !ifdef MISC_NSHEXTRA
  !insertmacro InstallFilesExtra
  !endif
FunctionEnd

; $0 = install path (typically, C:\PythonXX)
; $1 = python executable (typically, python.exe)
; $2 = python version (e.g. "2.6")
Function UninstallFiles
@_deletefiles@
@_deletedirs@

  !ifdef MISC_NSHEXTRA
  !insertmacro UninstallFilesExtra
  !endif
FunctionEnd

; (identical to UninstallFiles, but for uninstaller)
Function un.UninstallFiles
@_deletefiles@
@_deletedirs@

  !ifdef MISC_NSHEXTRA
  !insertmacro UninstallFilesExtra
  !endif
FunctionEnd

!macro PythonSection PYTHONVERSION

!define HAVE_SECTION_PYTHON${PYTHONVERSION}

; Set up variable for install path of this python version
Var PYTHONPATH${PYTHONVERSION}

; Function to detect the python path
Function GetPythonPath${PYTHONVERSION}
    ClearErrors

    ReadRegStr $PYTHONPATH${PYTHONVERSION} HKLM "SOFTWARE\Python\PythonCore\${PYTHONVERSION}\InstallPath" ""
    IfErrors 0 python_registry_found

    ReadRegStr $PYTHONPATH${PYTHONVERSION} HKCU "SOFTWARE\Python\PythonCore\${PYTHONVERSION}\InstallPath" ""
    IfErrors python_not_found python_registry_found

python_registry_found:

    ; remove trailing backslash using the $EXEDIR trick
    Push $PYTHONPATH${PYTHONVERSION}
    Exch $EXEDIR
    Exch $EXEDIR
    Pop $PYTHONPATH${PYTHONVERSION}

    ; debug
    ;MessageBox MB_OK "Found Python ${PYTHONVERSION} in $PYTHONPATH${PYTHONVERSION}"

    IfFileExists $PYTHONPATH${PYTHONVERSION}\python.exe python_path_done python_not_found

python_not_found:

    StrCpy $PYTHONPATH${PYTHONVERSION} ""

python_path_done:

FunctionEnd

; Function to detect the python path on uninstall
Function un.GetPythonPath${PYTHONVERSION}
    ClearErrors

    ReadRegStr $PYTHONPATH${PYTHONVERSION} HKLM "SOFTWARE\Python\PythonCore\${PYTHONVERSION}\InstallPath" ""
    IfErrors 0 python_registry_found

    ReadRegStr $PYTHONPATH${PYTHONVERSION} HKCU "SOFTWARE\Python\PythonCore\${PYTHONVERSION}\InstallPath" ""
    IfErrors python_not_found python_registry_found

python_registry_found:

    ; remove trailing backslash using the $EXEDIR trick
    Push $PYTHONPATH${PYTHONVERSION}
    Exch $EXEDIR
    Exch $EXEDIR
    Pop $PYTHONPATH${PYTHONVERSION}

    Goto python_path_done

python_not_found:

    StrCpy $PYTHONPATH${PYTHONVERSION} ""

python_path_done:

FunctionEnd

; Install the library for Python ${PYTHONVERSION}
Section "${PYTHONVERSION}" Python${PYTHONVERSION}
    SetShellVarContext all
    AddSize ${MISC_PYSIZEKB}

    StrCmp $PYTHONPATH${PYTHONVERSION} "" python_install_end

    StrCpy $0 $PYTHONPATH${PYTHONVERSION}
    StrCpy $1 "python.exe"
    StrCpy $2 "${PYTHONVERSION}"
    Call InstallFiles

python_install_end:

SectionEnd

!macroend

!macro un.PythonSection PYTHONVERSION

Section un.Python${PYTHONVERSION}
    SetShellVarContext all

    StrCmp $PYTHONPATH${PYTHONVERSION} "" python_uninstall_end

    StrCpy $0 $PYTHONPATH${PYTHONVERSION}
    StrCpy $1 "python.exe"
    StrCpy $2 "${PYTHONVERSION}"
    Call un.UninstallFiles

python_uninstall_end:

SectionEnd

!macroend



!macro MayaSection MAYAVERSION MAYAREGISTRY

; Set up variable for install path of this maya version
Var MAYAPATH${MAYAVERSION}

; Function to detect the maya path
Function GetMayaPath${MAYAVERSION}
    ClearErrors

    ReadRegStr $MAYAPATH${MAYAVERSION} HKLM "SOFTWARE\Autodesk\Maya\${MAYAREGISTRY}\Setup\InstallPath" "MAYA_INSTALL_LOCATION"
    IfErrors 0 maya_registry_found

    ReadRegStr $MAYAPATH${MAYAVERSION} HKCU "SOFTWARE\Autodesk\Maya\${MAYAREGISTRY}\Setup\InstallPath" "MAYA_INSTALL_LOCATION"
    IfErrors 0 maya_registry_found

    Goto maya_not_found

maya_registry_found:

    ; remove trailing backslash using the $EXEDIR trick
    Push $MAYAPATH${MAYAVERSION}
    Exch $EXEDIR
    Exch $EXEDIR
    Pop $MAYAPATH${MAYAVERSION}

    ; debug
    ;MessageBox MB_OK "Found Maya ${MAYAVERSION} in $MAYAPATH${MAYAVERSION}"

    IfFileExists $MAYAPATH${MAYAVERSION}\\bin\mayapy.exe maya_path_done maya_not_found

maya_not_found:

    StrCpy $MAYAPATH${MAYAVERSION} ""

maya_path_done:

FunctionEnd

; Function to detect the maya path on uninstall
Function un.GetMayaPath${MAYAVERSION}
    ClearErrors

    ReadRegStr $MAYAPATH${MAYAVERSION} HKLM "SOFTWARE\Autodesk\Maya\${MAYAREGISTRY}\Setup\InstallPath" "MAYA_INSTALL_LOCATION"
    IfErrors 0 maya_registry_found

    ReadRegStr $MAYAPATH${MAYAVERSION} HKCU "SOFTWARE\Autodesk\Maya\${MAYAREGISTRY}\Setup\InstallPath" "MAYA_INSTALL_LOCATION"
    IfErrors 0 maya_registry_found

    Goto maya_not_found

maya_registry_found:

    ; remove trailing backslash using the $EXEDIR trick
    Push $MAYAPATH${MAYAVERSION}
    Exch $EXEDIR
    Exch $EXEDIR
    Pop $MAYAPATH${MAYAVERSION}

    Goto maya_path_done

maya_not_found:

    StrCpy $MAYAPATH${MAYAVERSION} ""

maya_path_done:

FunctionEnd

; Install the library for Maya ${MAYAVERSION}
Section "${MAYAVERSION}" Maya${MAYAVERSION}
    SetShellVarContext all
    AddSize ${MISC_PYSIZEKB}

    StrCmp $MAYAPATH${MAYAVERSION} "" maya_install_end

    StrCpy $0 "$MAYAPATH${MAYAVERSION}\Python"
    StrCpy $1 "..\\bin\mayapy.exe"
    StrCpy $2 "2.5" ; XXX include in macro
    Call InstallFiles

maya_install_end:

SectionEnd

!macroend

!macro un.MayaSection MAYAVERSION MAYAREGISTRY

Section un.Maya${MAYAVERSION}
    SetShellVarContext all

    StrCmp $MAYAPATH${MAYAVERSION} "" maya_uninstall_end

    StrCpy $0 "$MAYAPATH${MAYAVERSION}\Python"
    StrCpy $1 "..\\bin\mayapy.exe"
    StrCpy $2 "2.5" ; XXX include in macro
    Call un.UninstallFiles

maya_uninstall_end:

SectionEnd

!macroend



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
  MessageBox MB_YESNO|MB_ICONEXCLAMATION "Installer is experimental and is likely to fail. Continue?" IDYES +2

    Abort ; quit installer

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
    Call GetPythonPath${PYTHONVERSION}
    StrCmp $PYTHONPATH${PYTHONVERSION} "" 0 +2
    ; python version not found, so disable that section
    SectionSetFlags ${Python${PYTHONVERSION}} ${SF_RO}
""".replace("${PYTHONVERSION}", pythonversion)
                for pythonversion in pythonversions) + """

  ; check maya versions
""" + "\n".join("""\
    Call GetMayaPath${MAYAVERSION}
    StrCmp $MAYAPATH${MAYAVERSION} "" 0 +2
    ; python version not found, so disable that section
    SectionSetFlags ${Maya${MAYAVERSION}} ${SF_RO}
""".replace("${MAYAVERSION}", mayaversion)
                for mayaversion, mayaregistry in mayaversions) + """

FunctionEnd

Function un.onInit
""" + "\n".join("  Call un.GetPythonPath%s" % pythonversion
                 for pythonversion in pythonversions) + """
""" + "\n".join("  Call un.GetMayaPath%s" % mayaversion
                 for mayaversion, mayaregistry in mayaversions) + """
""" + """
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
            + "\nSectionGroupEnd\n\n"
            + "\nSectionGroup /e Maya\n"
            + "\n".join(
                "!insertmacro MayaSection %s %s" % (mayaversion, mayaregistry)
                for mayaversion, mayaregistry in mayaversions)
            + "\nSectionGroupEnd\n\n"
            + "\nSectionGroup /e un.Maya\n"
            + "\n".join(
                "!insertmacro un.MayaSection %s %s" % (mayaversion, mayaregistry)
                for mayaversion, mayaregistry in mayaversions)
            + "\nSectionGroupEnd\n\n"
            + NSI_FOOTER)
