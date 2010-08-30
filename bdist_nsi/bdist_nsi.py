"""bdist_nsi.bdist_nsi

Implements the Distutils 'bdist_nsi' command: create a Windows NSIS installer.
"""

# Created 2005/05/24, j-cg , inspired by the bdist_wininst of the python
# distribution

# June/July 2009 (Amorilia):
#   - further developed, 2to3, blender, maya

# December 2009/January 2010 (Amorilia):
#   - added AppInfo classes for better implementation
#   - added proper 64 bit support

# April 2010 (Amorilia):
#   - added support for native Python 3 packages (without 2to3)

# August 2010 (Surgo)
#   - added distutils commandoption

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

from distutils import command
command.__all__.append('bdist_nsi')
sys.modules['distutils.command.bdist_nsi'] = sys.modules[__name__]

class RegKey:
    """Stores the location of a registry key."""

    view = None
    """Registry view (32 or 64)."""

    root = None
    """Root of the key (HKLM, HKCU, and so on)."""
    
    key = None
    """Key."""

    name = None
    """Name."""

    def __init__(self, view=None, root=None, key=None, name=None):
        """Initialize key."""
        self.view = view
        self.root = root
        self.key = key
        self.name = name

    def __repr__(self):
        r"""String representation.

        >>> RegKey(view=32, root="HKLM", key=r"Software\BlenderFoundation",
        ...        name="Install_Dir")
        RegKey(view=32, root='HKLM', key='Software\\BlenderFoundation', name='Install_Dir')
        """
        return(
            "RegKey(view=%s, root=%s, key=%s, name=%s)"
            % (repr(self.view), repr(self.root),
               repr(self.key), repr(self.name)))

class AppInfo:
    """Information of an application which integrates Python."""

    name = None
    """Name of the application."""

    version = None
    """The version of the application."""

    label = None
    """A label which uniquely identifies the application."""

    regkeys = None  # list of registry keys
    """List of registry keys which are checked to determine whether the
    application is installed or not, and to get its installation path.
    """
    
    py_version = None # 2.4, 2.5, ...
    """A string of the form 'x.x' which determines the Python version
    for this application.
    """

    VERSIONS = []
    """List of (version, py_version, bits) tuples."""

    def __init__(self, name=None, label=None, regkeys=None, py_version=None):
        """Initialize application information."""
        self.name = name
        self.label = label
        self.regkeys = regkeys
        self.py_version = py_version

    def __repr__(self):
        r"""Return string representation.

        >>> regkey = RegKey(view=32, root="HKLM",
        ...                 key=r"Software\BlenderFoundation",
        ...                 name="Install_Dir")
        >>> AppInfo(name="Test", label="test", regkeys=[regkey],
        ...         py_version="3.2")
        AppInfo(name='Test', label='test', regkeys=[RegKey(view=32, root='HKLM', key='Software\\BlenderFoundation', name='Install_Dir')], py_version='3.2')
        """
        return (
            "AppInfo(name=%s, label=%s, regkeys=%s, py_version=%s)"
            % (repr(self.name), repr(self.label), repr(self.regkeys),
               repr(self.py_version)))

    @property
    def bits(self):
        """32 or 64.

        >>> PythonAppInfo(version="2.7", bits=64).bits
        64
        >>> PythonAppInfo(version="3.1", bits=32).bits
        32
        >>> MayaAppInfo(version="2009", py_version="2.5", bits=64).bits
        64
        >>> MayaAppInfo(version="2009", py_version="2.5", bits=32).bits
        32
        >>> BlenderAppInfo(version="2.4x", py_version="2.6", bits=64).bits
        64
        >>> BlenderAppInfo(version="2.4x", py_version="2.6", bits=32).bits
        32
        """
        return max(regkey.view for regkey in self.regkeys)

    def macro_get_registry_keys(self):
        r"""Returns NSIS script which defines a macro which jumps to
        if_found if the registry key is found in any of the listed
        registry keys, storing the result in $PATH_${label}.

        >>> regkey1 = RegKey(view=32, root="HKLM",
        ...                  key=r"Software\BlenderFoundation",
        ...                  name="Install_Dir")
        >>> regkey2 = RegKey(view=64, root="HKCU",
        ...                  key=r"SOFTWARE\Autodesk\Maya\2008\Setup\InstallPath",
        ...                  name="MAYA_INSTALL_LOCATION")
        >>> regkey3 = RegKey(view=32, root="HKCR",
        ...                  key="NSIS.Header",
        ...                  name="DefaultIcon")
        >>> app = AppInfo(name="Test", label="test",
        ...               regkeys=[regkey1, regkey2, regkey3],
        ...               py_version='3.2')
        >>> print("\n".join(app.macro_get_registry_keys()))
        !macro GET_REGISTRY_KEYS_test if_found
            !insertmacro GET_REGISTRY_KEY $PATH_test 32 HKLM "Software\BlenderFoundation" "Install_Dir" ${if_found}
            !insertmacro GET_REGISTRY_KEY $PATH_test 64 HKCU "SOFTWARE\Autodesk\Maya\2008\Setup\InstallPath" "MAYA_INSTALL_LOCATION" ${if_found}
            !insertmacro GET_REGISTRY_KEY $PATH_test 32 HKCR "NSIS.Header" "DefaultIcon" ${if_found}
        !macroend
        """
        yield "!macro GET_REGISTRY_KEYS_%s if_found" % self.label
        for regkey in self.regkeys:
            yield (
                '    !insertmacro GET_REGISTRY_KEY $PATH_%s %s %s "%s" "%s"'
                ' ${if_found}'
                % (self.label,
                   regkey.view, regkey.root, regkey.key, regkey.name))
        yield "!macroend"

    def macro_get_path_extra_check(self):
        """Returns NSIS script which validates a given path."""
        # default: do nothing
        return

    def insertmacro_variables(self):
        """Define variables."""
        yield "var PATH_%s" % self.label

    def macro_section_extra(self):
        """Define section install variables $0 to $5 (see the
        implementation of PythonAppInfo.macro_section_extra for an
        example).
        """
        raise NotImplementedError

    @staticmethod
    def make_version_bits_tuples(versions, bits=None):
        """Convert string versions into tuple versions.

        >>> list(AppInfo.make_version_bits_tuples(["2.5", "3.1"]))
        [('2.5', 32), ('2.5', 64), ('3.1', 32), ('3.1', 64)]
        >>> list(AppInfo.make_version_bits_tuples(["2.5", "3.1"], bits=64))
        [('2.5', 64), ('3.1', 64)]
        """
        for version in versions:
            if bits is None:
                for bits_ in [32, 64]:
                    yield version, bits_
            else:
                yield version, bits

    @classmethod
    def make_apps(cls, versions, bits=None):
        """Get all applications of maya that match given python versions,
        which is a list of the form ["2.3", "2.4"] etc.

        >>> MayaAppInfo.make_apps(["2.6"])
        [MayaAppInfo(version='2010', py_version='2.6', bits=32), MayaAppInfo(version='2010', py_version='2.6', bits=64)]
        >>> BlenderAppInfo.make_apps(["2.6"])
        [BlenderAppInfo(version='2.4x', py_version='2.6', bits=32)]
        """
        version_bits = list(
            cls.make_version_bits_tuples(versions, bits))
        return [
            cls(*args) for args in cls.VERSIONS
            if tuple(args[-2:]) in version_bits]

class PythonAppInfo(AppInfo):
    r"""Python application info.

    >>> print("\n".join(PythonAppInfo(version="2.5", bits=32).macro_get_registry_keys()))
    !macro GET_REGISTRY_KEYS_python_2_5_32 if_found
        !insertmacro GET_REGISTRY_KEY $PATH_python_2_5_32 32 HKLM "SOFTWARE\Python\PythonCore\2.5\InstallPath" "" ${if_found}
        !insertmacro GET_REGISTRY_KEY $PATH_python_2_5_32 32 HKCU "SOFTWARE\Python\PythonCore\2.5\InstallPath" "" ${if_found}
    !macroend
    """

    def __init__(self, version=None, bits=None):
        r"""Constructor.

        >>> print(AppInfo.__repr__(PythonAppInfo(version="2.7", bits=64)))
        AppInfo(name='Python 2.7 (64 bit)', label='python_2_7_64', regkeys=[RegKey(view=64, root='HKLM', key='SOFTWARE\\Python\\PythonCore\\2.7\\InstallPath', name=''), RegKey(view=64, root='HKCU', key='SOFTWARE\\Python\\PythonCore\\2.7\\InstallPath', name='')], py_version='2.7')
        >>> PythonAppInfo(version="2.7", bits=64).py_version
        '2.7'
        """
        self.py_version = version
        self.name = "Python %s (%i bit)" % (self.py_version, bits)
        self.label = "python_%s_%i" % (self.py_version.replace(".", "_"), bits)
        key = r"SOFTWARE\Python\PythonCore\%s\InstallPath" % self.py_version
        self.regkeys = [
            RegKey(view=bits, root="HKLM", key=key, name=""),
            RegKey(view=bits, root="HKCU", key=key, name=""),
            ]

    def __repr__(self):
        """String representation.

        >>> PythonAppInfo(version="2.7", bits=64)
        PythonAppInfo(version='2.7', bits=64)
        """
        return ("PythonAppInfo(version=%s, bits=%i)"
                % (repr(self.py_version), self.bits))

    @classmethod
    def make_apps(cls, versions=None, bits=None):
        """Get all applications of python that match versions, which is
        a list of the form ["2.3", "2.4"] etc.

        >>> PythonAppInfo.make_apps(["2.1", "2.2"])
        [PythonAppInfo(version='2.1', bits=32), PythonAppInfo(version='2.1', bits=64), PythonAppInfo(version='2.2', bits=32), PythonAppInfo(version='2.2', bits=64)]
        >>> PythonAppInfo.make_apps(["2.3", "3.0"], bits=32)
        [PythonAppInfo(version='2.3', bits=32), PythonAppInfo(version='3.0', bits=32)]
        """
        version_bits = cls.make_version_bits_tuples(versions, bits)
        return [PythonAppInfo(version=version, bits=bits)
                for version, bits in version_bits]

    def macro_get_path_extra_check(self):
        """Returns NSIS script which validates the python path."""
        yield '!macro GET_PATH_EXTRA_CHECK_%s' % self.label
        yield '    !insertmacro GET_PATH_EXTRA_CHECK_PYTHON %s' % self.label
        yield '!macroend'

    def macro_section_extra(self):
        """Returns NSIS script which sets up the installation variables
        in the section definition.
        """
        yield '!macro SECTION_EXTRA_%s' % self.label
        yield ('    !insertmacro SECTION_EXTRA_PYTHON %s %s'
               % (self.label, self.py_version))
        yield '!macroend'

class MayaAppInfo(AppInfo):
    r"""Maya application info.

    >>> print("\n".join(MayaAppInfo(version=2008, py_version="2.5", bits=32).macro_get_registry_keys()))
    !macro GET_REGISTRY_KEYS_maya_2008_32 if_found
        !insertmacro GET_REGISTRY_KEY $PATH_maya_2008_32 32 HKLM "SOFTWARE\Autodesk\Maya\2008\Setup\InstallPath" "MAYA_INSTALL_LOCATION" ${if_found}
        !insertmacro GET_REGISTRY_KEY $PATH_maya_2008_32 32 HKCU "SOFTWARE\Autodesk\Maya\2008\Setup\InstallPath" "MAYA_INSTALL_LOCATION" ${if_found}
    !macroend
    >>> print("\n".join(MayaAppInfo(version=2008, py_version="2.5", bits=64).macro_get_registry_keys()))
    !macro GET_REGISTRY_KEYS_maya_2008_64 if_found
        !insertmacro GET_REGISTRY_KEY $PATH_maya_2008_64 32 HKLM "SOFTWARE\Autodesk\Maya\2008-x64\Setup\InstallPath" "MAYA_INSTALL_LOCATION" ${if_found}
        !insertmacro GET_REGISTRY_KEY $PATH_maya_2008_64 32 HKCU "SOFTWARE\Autodesk\Maya\2008-x64\Setup\InstallPath" "MAYA_INSTALL_LOCATION" ${if_found}
        !insertmacro GET_REGISTRY_KEY $PATH_maya_2008_64 64 HKLM "SOFTWARE\Autodesk\Maya\2008-x64\Setup\InstallPath" "MAYA_INSTALL_LOCATION" ${if_found}
        !insertmacro GET_REGISTRY_KEY $PATH_maya_2008_64 64 HKCU "SOFTWARE\Autodesk\Maya\2008-x64\Setup\InstallPath" "MAYA_INSTALL_LOCATION" ${if_found}
        !insertmacro GET_REGISTRY_KEY $PATH_maya_2008_64 64 HKLM "SOFTWARE\Autodesk\Maya\2008\Setup\InstallPath" "MAYA_INSTALL_LOCATION" ${if_found}
        !insertmacro GET_REGISTRY_KEY $PATH_maya_2008_64 64 HKCU "SOFTWARE\Autodesk\Maya\2008\Setup\InstallPath" "MAYA_INSTALL_LOCATION" ${if_found}
    !macroend
    """

    VERSIONS = [
        ("2008", "2.5", 32),
        ("2008", "2.5", 64),
        ("2009", "2.5", 32),
        ("2009", "2.5", 64),
        ("2010", "2.6", 32),
        ("2010", "2.6", 64),
        ("2011", "2.6", 32),
        ("2011", "2.6", 64),
        ]
    """All versions of maya, as (version, py_version, bits)."""
    
    def __init__(self, version=None, py_version=None, bits=None):
        self.version = version
        self.py_version = py_version
        self.name = "Maya %s (%i bit)" % (version, bits)
        self.label = "maya_%s_%i" % (version, bits)
        key = (
            r"SOFTWARE\Autodesk\Maya\%s\Setup\InstallPath" % version)
        key_x64 = (
            r"SOFTWARE\Autodesk\Maya\%s-x64\Setup\InstallPath" % version)
        name = "MAYA_INSTALL_LOCATION"
        if bits == 32:
            self.regkeys = [
                RegKey(view=bits, root="HKLM", key=key, name=name),
                RegKey(view=bits, root="HKCU", key=key, name=name),
                ]
        else:
            self.regkeys = [
                RegKey(view=32, root="HKLM", key=key_x64, name=name),
                RegKey(view=32, root="HKCU", key=key_x64, name=name),
                RegKey(view=64, root="HKLM", key=key_x64, name=name),
                RegKey(view=64, root="HKCU", key=key_x64, name=name),
                RegKey(view=64, root="HKLM", key=key, name=name),
                RegKey(view=64, root="HKCU", key=key, name=name),
                ]

    def __repr__(self):
        """String representation.

        >>> MayaAppInfo(version="2009", py_version="2.5", bits=64)
        MayaAppInfo(version='2009', py_version='2.5', bits=64)
        """
        return ("MayaAppInfo(version=%s, py_version=%s, bits=%i)"
                % (repr(self.version), repr(self.py_version), self.bits))

    def macro_get_path_extra_check(self):
        """Returns NSIS script which validates the python path."""
        yield '!macro GET_PATH_EXTRA_CHECK_%s' % self.label
        yield '    !insertmacro GET_PATH_EXTRA_CHECK_MAYA %s' % self.label
        yield '!macroend'

    def macro_section_extra(self):
        """Returns NSIS script which sets up the installation variables
        in the section definition.
        """
        yield '!macro SECTION_EXTRA_%s' % self.label
        yield ('    !insertmacro SECTION_EXTRA_MAYA %s %s'
               % (self.label, self.py_version))
        yield '!macroend'

class BlenderAppInfo(AppInfo):
    r"""Blender application info.

    >>> print("\n".join(BlenderAppInfo(version="2.4x", py_version="2.6", bits=32).macro_get_registry_keys()))
    !macro GET_REGISTRY_KEYS_blender_2_4x_2_6_32 if_found
        !insertmacro GET_REGISTRY_KEY $PATH_blender_2_4x_2_6_32 32 HKLM "SOFTWARE\BlenderFoundation" "Install_Dir" ${if_found}
        !insertmacro GET_REGISTRY_KEY $PATH_blender_2_4x_2_6_32 32 HKCU "SOFTWARE\BlenderFoundation" "Install_Dir" ${if_found}
    !macroend
    """

    VERSIONS = [
        ("2.4x", "2.3", 32),
        ("2.4x", "2.4", 32),
        ("2.4x", "2.5", 32),
        ("2.4x", "2.6", 32),
        ]
    """All versions of blender, as (version, py_version, bits)."""

    def __init__(self, version=None, py_version=None, bits=None):
        self.version = version
        self.name = ("Blender %s (Python %s, %i bit)"
                     % (version, py_version, bits))
        self.label = (("blender_%s_%s_%i" % (version, py_version, bits))
                      .replace(".", "_"))
        self.py_version = py_version
        key = r"SOFTWARE\BlenderFoundation"
        name = r"Install_Dir"
        self.regkeys = [
            RegKey(view=bits, root="HKLM", key=key, name=name),
            RegKey(view=bits, root="HKCU", key=key, name=name),
            ]

    def __repr__(self):
        """String representation.

        >>> BlenderAppInfo(version="2.4x", py_version="2.6", bits=64)
        BlenderAppInfo(version='2.4x', py_version='2.6', bits=64)
        """
        return ("BlenderAppInfo(version=%s, py_version=%s, bits=%s)"
                % (repr(self.version),
                   repr(self.py_version), repr(self.bits)))

    def insertmacro_variables(self):
        """Define variables."""
        yield "var PATH_%s" % self.label
        yield "var SCRIPTS_%s" % self.label

    def macro_get_path_extra_check(self):
        """Returns NSIS script which validates the python path."""
        yield '!macro GET_PATH_EXTRA_CHECK_%s' % self.label
        yield ('    !insertmacro GET_PATH_EXTRA_CHECK_BLENDER %s %s'
               % (self.label, self.py_version))
        yield '!macroend'

    def macro_section_extra(self):
        """Returns NSIS script which sets up the installation variables
        in the section definition.
        """
        yield '!macro SECTION_EXTRA_%s' % self.label
        yield ('    !insertmacro SECTION_EXTRA_BLENDER %s %s'
               % (self.label, self.py_version))
        yield '!macroend'

    @staticmethod
    def insertmacro_push_blender_python_version(target_versions):
        """Push the python version, for use in the
        CHECK_BLENDER_PYTHON_VERSION macro.
        """
        if not target_versions:
            raise ValueError(
                "target_versions must contain at least one element")
        yield '    ; note: if user installs a newer version of Blender over'
        yield '    ; an older version then two python dll files could co-exist;'
        yield '    ; therefore, check the higher version numbers first'
        versions = sorted(target_versions, reverse=True)
        yield ('    ${If} ${FileExists} "$PATH_${label}\python%s.dll"'
               % versions[0].replace(".", ""))
        yield '        Push "%s"' % versions[0]
        for version in versions[1:]:
            yield ('    ${ElseIf} ${FileExists} "$PATH_${label}\python%s.dll"'
                   % version.replace(".", ""))
            yield '        Push "%s"' % version
        yield '    ${Else}'
        yield '        Push ""'
        yield '    ${EndIf}'

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
                raise DistutilsOptionError("target version can only be %s, or the '--skip_build'" \
                      " option must be specified" % (short_version,))
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
            nsiscript = get_nsi(target_versions=[self.target_version])
        elif self.target_versions:
            nsiscript = get_nsi(target_versions=self.target_versions.split(","))
        elif sys.version_info[0] < 3:
            # python 2.x
            target_versions = ["2.3", "2.4", "2.5", "2.6", "2.7"]
            if self.run2to3:
                target_versions.extend(["3.0", "3.1", "3.2"])
            nsiscript = get_nsi(target_versions=target_versions)
        else:
            # python 3.x
            target_versions = ["3.0", "3.1", "3.2"]
            # disable 2to3
            self.run2to3 = 0
            nsiscript = get_nsi(target_versions=target_versions)
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

        for dirpath, dirnames, filenames in os.walk(self.bdist_dir+os.sep+'_python'):
            self.visit(files, dirpath, filenames)

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

def get_nsi(target_versions=None, bits=None):
    # list all applications
    python_apps = PythonAppInfo.make_apps(target_versions, bits)
    maya_apps = MayaAppInfo.make_apps(target_versions, bits)
    blender_apps = BlenderAppInfo.make_apps(target_versions, bits)

    NSI_HEADER = r"""\
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
!define PRODUCT_UNINST_REG_VIEW 32
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

!ifdef MISC_BLENDER | MISC_MSVC2005 | MISC_MSVC2005SP1 | MISC_MSVC2008 | MISC_MSVC2008SP1
!define REQUIREOPENLINKNEWWINDOW "1"
!endif

; Various Settings
; ================

; solid lzma gives best compression in virtually all cases
SetCompressor /SOLID lzma

Name "${PRODUCT_NAME} ${PRODUCT_VERSION}"
OutFile "@installer_path@"
InstallDir "$PROGRAMFILES\${PRODUCT_NAME}"
ShowInstDetails show
ShowUnInstDetails show



; Includes
; ========

!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "x64.nsh"


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



; Variables
; =========

""" + "\n".join(
    "\n".join(app.insertmacro_variables())
    for app in python_apps) + r"""
!ifdef MISC_MAYA
""" + "\n".join(
    "\n".join(app.insertmacro_variables())
    for app in maya_apps) + r"""
!endif
!ifdef MISC_BLENDER
""" + "\n".join(
    "\n".join(app.insertmacro_variables())
    for app in blender_apps) + r"""
!endif

; Macros
; ======



!macro DEBUG_MSG text
!ifdef MISC_DEBUG
    MessageBox MB_OK "${text}"
!endif
!macroend

; jumps to registry_key_found if the registry key is found
!macro GET_REGISTRY_KEY variable reg_view reg_root reg_key reg_name if_found
    !insertmacro DEBUG_MSG "looking for ${reg_root}\${reg_key}\${reg_name} in ${reg_view} bit registry"
!if "${reg_view}" == "64"
    ; only check 64 bit registry keys on 64 bit systems
    ${If} ${RunningX64}
!endif
    SetRegView ${reg_view}
    ReadRegStr ${variable} ${reg_root} ${reg_key} "${reg_name}"
    IfErrors 0 ${if_found}
!if "${reg_view}" == "64"
    ${EndIf}
!endif
!macroend

""" + "\n".join(
    "\n".join(app.macro_get_registry_keys())
    for app in python_apps) + r"""
!ifdef MISC_MAYA
""" + "\n".join(
    "\n".join(app.macro_get_registry_keys())
    for app in maya_apps) + r"""
!endif
!ifdef MISC_BLENDER
""" + "\n".join(
    "\n".join(app.macro_get_registry_keys())
    for app in blender_apps) + r"""
!endif

; get path
!macro GET_PATH label

    ; check registry
    ClearErrors
    !insertmacro GET_REGISTRY_KEYS_${label} registry_key_found_${label}
    StrCpy $PATH_${label} ""
    !insertmacro DEBUG_MSG "not found in registry"
    Goto get_path_end_${label}

registry_key_found_${label}:

    ; remove trailing backslash using the $EXEDIR trick
    Push $PATH_${label}
    Exch $EXEDIR
    Exch $EXEDIR
    Pop $PATH_${label}
    !insertmacro DEBUG_MSG "found at $PATH_${label}"
    !insertmacro GET_PATH_EXTRA_CHECK_${label}

get_path_end_${label}:

!macroend

; validates python path
!macro GET_PATH_EXTRA_CHECK_PYTHON label

    IfFileExists "$PATH_${label}\python.exe" 0 python_exe_not_found_${label}
    !insertmacro DEBUG_MSG "found python executable at $PATH_${label}\python.exe"
    GoTo get_path_end_${label}

python_exe_not_found_${label}:

    !insertmacro DEBUG_MSG "python executable not found"
    StrCpy $PATH_${label} ""
!macroend

""" + "\n".join(
    "\n".join(app.macro_get_path_extra_check())
    for app in python_apps) + r"""
!ifdef MISC_MAYA
""" + "\n".join(
    "\n".join(app.macro_get_path_extra_check())
    for app in maya_apps) + r"""
!endif
!ifdef MISC_BLENDER
""" + "\n".join(
    "\n".join(app.macro_get_path_extra_check())
    for app in blender_apps) + r"""
!endif

!macro SECTION un name label
!ifndef HAVE_SECTION_${label}
!define HAVE_SECTION_${label}
!endif
Section "${un}${name}" ${un}section_${label}
    SetShellVarContext all
    StrCmp $PATH_${label} "" section_end_${label}
    !insertmacro SECTION_EXTRA_${label}
    Call ${un}InstallFiles
section_end_${label}:
SectionEnd
!macroend

; setup install vars for python
!macro SECTION_EXTRA_PYTHON label py_version
    StrCpy $0 "$PATH_${label}"
    StrCpy $1 "$PATH_${label}\python.exe"
    StrCpy $2 "${py_version}"
    StrCpy $3 "$PATH_${label}\Lib\site-packages"
    StrCpy $4 "$PATH_${label}\Scripts"
    StrCpy $5 "$PATH_${label}\Include"
!macroend

""" + "\n\n".join(
    "\n".join(app.macro_section_extra())
    for app in python_apps) + r"""
!ifdef MISC_MAYA
""" + "\n\n".join(
    "\n".join(app.macro_section_extra())
    for app in maya_apps) + r"""
!endif
!ifdef MISC_BLENDER
""" + "\n\n".join(
    "\n".join(app.macro_section_extra())
    for app in blender_apps) + r"""
!endif

!macro SECTION_SET_PROPERTIES label
    SectionSetSize ${section_${label}} ${MISC_PYSIZEKB}
    !insertmacro GET_PATH ${label}
    StrCmp $PATH_${label} "" 0 +2
    SectionSetFlags ${section_${label}} ${SF_RO}
!macroend



!ifdef MISC_MAYA

; validates python path for maya
!macro GET_PATH_EXTRA_CHECK_MAYA label
    IfFileExists $PATH_${label}\bin\mayapy.exe 0 mayapy_exe_not_found_${label}
    !insertmacro DEBUG_MSG "found python executable at $PATH_${label}\bin\mayapy.exe"
    GoTo get_path_end_${label}

mayapy_exe_not_found_${label}:

    !insertmacro DEBUG_MSG "python executable not found"
    StrCpy $PATH_${label} ""
!macroend


; setup install vars for maya
!macro SECTION_EXTRA_MAYA label py_version
    StrCpy $0 "$PATH_${label}\Python"
    StrCpy $1 "$PATH_${label}\bin\mayapy.exe"
    StrCpy $2 "${py_version}"
    StrCpy $3 "$PATH_${label}\Python\Lib\site-packages"
    StrCpy $4 "" ; no scripts
    StrCpy $5 "" ; no headers
!macroend

!endif ;MISC_MAYA



!ifdef MISC_BLENDER

!macro CLEAN_STRAY_BLENDER_USER_DATA_FILES path
    !insertmacro DEBUG_MSG "checking for stray Blender user data files in ${path}"
    IfFileExists "${path}" 0 +3
    MessageBox MB_YESNO|MB_ICONQUESTION "Clean stray Blender user data files in ${path} (highly recommended)?" IDNO +2
    RmDir /r "${path}"
!macroend

!macro CLEAN_ALL_STRAY_BLENDER_USER_DATA_FILES
    SetShellVarContext current
    !insertmacro CLEAN_STRAY_BLENDER_USER_DATA_FILES "$APPDATA\Blender Foundation"
    SetShellVarContext all
    !insertmacro CLEAN_STRAY_BLENDER_USER_DATA_FILES "$APPDATA\Blender Foundation"
    ReadEnvStr $0 "HOME"
    !insertmacro CLEAN_STRAY_BLENDER_USER_DATA_FILES "$0\.blender"
!macroend

!macro FILE_EXISTS_BLENDER_SCRIPTS label path if_found if_not_found
    !insertmacro DEBUG_MSG "checking for blender scripts ${path}"
    StrCpy $SCRIPTS_${label} "${path}"
    IfFileExists "$SCRIPTS_${label}\*.*" ${if_found} ${if_not_found}
!macroend

!macro CHECK_BLENDER_PYTHON_VERSION label py_version if_right if_wrong
    ; dll check for python version
""" + "\n".join(
        BlenderAppInfo.insertmacro_push_blender_python_version(
            target_versions)) + r"""
    Pop $0
    StrCmp $0 ${py_version} ${if_right} ${if_wrong}
!macroend

; validates path for blender
!macro GET_PATH_EXTRA_CHECK_BLENDER label py_version

    ; check if blender.exe exists
    IfFileExists "$PATH_${label}\blender.exe" 0 blender_exe_not_found_${label}
    !insertmacro DEBUG_MSG "found blender executable at $PATH_${label}\blender.exe"

    !insertmacro CHECK_BLENDER_PYTHON_VERSION ${label} ${py_version} 0 wrong_python_version_${label}

    ; clear variable
    StrCpy $SCRIPTS_${label} ""

    ; get Blender scripts dir
    !insertmacro FILE_EXISTS_BLENDER_SCRIPTS ${label} "$PATH_${label}\.blender\scripts" blender_scripts_found_in_install_dir_${label} 0
; extra sanity check during install: scripts not in default location, so warn, clean, and reinstall blender
!ifndef __UNINSTALL__
    MessageBox MB_YESNO|MB_ICONEXCLAMATION "Blender's user data files (such as scripts) do not reside in Blender's installation directory. Blender will sometimes only find its scripts if Blender's user data files reside in Blender's installation directory.$\r$\n$\r$\nDo you wish to abort installation, and first reinstall Blender?" IDNO blender_scripts_notininstallfolder_${label}
    MessageBox MB_YESNO|MB_ICONQUESTION "Please reinstall Blender, and select 'Use the installation directory' when asked where to install Blender's user data files. When you are done, rerun this installer.$\r$\n$\r$\nVisit the Blender download page?"  IDNO blender_scripts_skip_blender_download_page_${label}
    StrCpy $0 "http://www.blender.org/download/get-blender/"
    Call openLinkNewWindow
blender_scripts_skip_blender_download_page_${label}:
    Abort ; causes installer to quit
blender_scripts_notininstallfolder_${label}:
!endif
    SetShellVarContext current
    !insertmacro FILE_EXISTS_BLENDER_SCRIPTS ${label} "$APPDATA\Blender Foundation\Blender\.blender\scripts" blender_scripts_found_${label} 0
    SetShellVarContext all
    !insertmacro FILE_EXISTS_BLENDER_SCRIPTS ${label} "$APPDATA\Blender Foundation\Blender\.blender\scripts" blender_scripts_found_${label} 0
    ReadEnvStr $0 "HOME"
    !insertmacro FILE_EXISTS_BLENDER_SCRIPTS ${label} "$0\.blender\scripts" blender_scripts_found_${label} blender_scripts_not_found_${label}

blender_scripts_found_in_install_dir_${label}:
    ; extra cleaning if installing in default directory (only during install)
!ifndef __UNINSTALL__
    !insertmacro CLEAN_ALL_STRAY_BLENDER_USER_DATA_FILES
!endif

blender_scripts_found_${label}:
    !insertmacro DEBUG_MSG "found blender scripts in $SCRIPTS_${label}"
    ; remove trailing backslash using the $EXEDIR trick
    Push $SCRIPTS_${label}
    Exch $EXEDIR
    Exch $EXEDIR
    Pop $SCRIPTS_${label}
    GoTo blender_scripts_done_${label}

blender_exe_not_found_${label}:
wrong_python_version_${label}:
blender_scripts_not_found_${label}:
    !insertmacro DEBUG_MSG "blender scripts not found"
    StrCpy $SCRIPTS_${label} ""
    StrCpy $PATH_${label} ""

blender_scripts_done_${label}:
!macroend

!macro SECTION_EXTRA_BLENDER label py_version
    StrCpy $0 "" ; XXX todo: set python path
    StrCpy $1 "" ; XXX todo: set python executable
    StrCpy $2 "${py_version}"
    StrCpy $3 "$SCRIPTS_${label}\bpymodules"
    StrCpy $4 "" ; no scripts
    StrCpy $5 "" ; no headers
!macroend

!endif ;MISC_BLENDER



!include "FileFunc.nsh"
!include "WordFunc.nsh"

!insertmacro Locate
!insertmacro VersionCompare

!macro SearchDLL DLLLABEL DLLDESC DLLFILE DLLVERSION DLLLINK

Var DLLFound${DLLLABEL}

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

    NSI_FOOTER = r"""
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

!ifdef MISC_DEBUG
     ${If} ${RunningX64}
         MessageBox MB_OK "running on x64"
     ${EndIf}
!endif

  ; check python versions
""" + "\n".join(
    "    !insertmacro SECTION_SET_PROPERTIES %s"
    % app.label for app in python_apps) + r"""
  !ifdef MISC_MAYA
""" + "\n".join(
    "    !insertmacro SECTION_SET_PROPERTIES %s"
    % app.label for app in maya_apps) + r"""
  !endif ;MISC_MAYA
  !ifdef MISC_BLENDER
""" + "\n".join(
    "    !insertmacro SECTION_SET_PROPERTIES %s"
    % app.label for app in blender_apps) + r"""
  !endif ;MISC_BLENDER

FunctionEnd

Function un.onInit
""" + "\n".join(
    '    !insertmacro GET_PATH %s' % app.label
    for app in python_apps) + r"""
    !ifdef MISC_MAYA
""" + "\n".join(
    '        !insertmacro GET_PATH %s' % app.label
    for app in maya_apps) + r"""
    !endif ;MISC_MAYA
    !ifdef MISC_BLENDER
""" + "\n".join(
    '        !insertmacro GET_PATH %s' % app.label
    for app in blender_apps) + r"""
    !endif ;MISC_BLENDER
FunctionEnd

Section -Post
  SetOutPath "$INSTDIR"
  WriteUninstaller "$INSTDIR\${PRODUCT_NAME}_uninstall.exe"
  SetRegView ${PRODUCT_UNINST_REG_VIEW}
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

  Delete "$INSTDIR\${PRODUCT_NAME}_uninstall.exe"
  RmDir "$INSTDIR"
  SetRegView ${PRODUCT_UNINST_REG_VIEW}
  DeleteRegKey ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}"
SectionEnd
"""

    return (NSI_HEADER
            + "\nSectionGroup /e Python\n"
            + "\n".join(
                '!insertmacro SECTION "" "%s" %s' % (app.name, app.label)
                for app in python_apps)
            + "\nSectionGroupEnd\n\n"
            + "\nSectionGroup /e un.Python\n"
            + "\n".join(
                '!insertmacro SECTION "un." "%s" %s' % (app.name, app.label)
                for app in python_apps)
            + "\nSectionGroupEnd\n\n\n"
            + "!ifdef MISC_MAYA\n"
            + "\nSectionGroup /e Maya\n"
            + "\n".join(
                '!insertmacro SECTION "" "%s" %s' % (app.name, app.label)
                for app in maya_apps)
            + "\nSectionGroupEnd\n\n"
            + "\nSectionGroup /e un.Maya\n"
            + "\n".join(
                '!insertmacro SECTION "un." "%s" %s' % (app.name, app.label)
                for app in maya_apps)
            + "\nSectionGroupEnd\n\n"
            + "!endif ;MISC_MAYA\n\n\n"
            + "!ifdef MISC_BLENDER\n"
            + "\nSectionGroup /e Blender\n"
            + "\n".join(
                '!insertmacro SECTION "" "%s" %s' % (app.name, app.label)
                for app in blender_apps)
            + "\nSectionGroupEnd\n\n"
            + "\nSectionGroup /e un.Blender\n"
            + "\n".join(
                '!insertmacro SECTION "un." "%s" %s' % (app.name, app.label)
                for app in blender_apps)
            + "\nSectionGroupEnd\n\n\n"
            + "!endif ;MISC_BLENDER\n\n\n"
            + NSI_FOOTER)

if __name__=='__main__':
    import doctest
    doctest.testmod()
