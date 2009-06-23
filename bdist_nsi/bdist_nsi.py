"""bdist_nsi.bdist_nsi

Implements the Distutils 'bdist_nsi' command: create a Windows NSIS installer.
"""

# Created 2005/05/24, j-cg , inspired by the bdist_wininst of the python
# distribution

# June 2009: further developed by Amorilia

import sys, os, string, zlib, base64
from distutils.core import Command
from distutils.util import get_platform
from distutils.dir_util import create_tree, remove_tree
from distutils.errors import *
from distutils.spawn import spawn

class bdist_nsi(Command):

    description = "create an executable installer for MS Windows, using NSIS"

    user_options = [('bdist-dir=', None,
                    "temporary directory for creating the distribution"),
                    ('keep-temp', 'k',
                     "keep the pseudo-installation tree around after " +
                     "creating the distribution archive"),
                    ('target-version=', 'v',
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
                    ]

    boolean_options = ['keep-temp', 'no-target-compile', 'no-target-optimize',
                       'skip-build']

    def initialize_options (self):
        self.bdist_dir = None
        self.keep_temp = 0
        self.no_target_compile = 0
        self.no_target_optimize = 0
        self.target_version = None
        self.dist_dir = None
        self.nsis_dir = None
        self.bitmap = None
        self.title = None
        self.plat_name = None
        self.format = None

    # initialize_options()


    def finalize_options (self):
        if self.bdist_dir is None:
            bdist_base = self.get_finalized_command('bdist').bdist_base
            self.bdist_dir = os.path.join(bdist_base, 'nsi')
        if not self.target_version:
            self.target_version = ""
        if self.distribution.has_ext_modules():
            short_version = sys.version[:3]
            if self.target_version and self.target_version != short_version:
                raise DistutilsOptionError, \
                        "target version can only be" + short_version
            self.target_version = short_version
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
            makensis = os.path.join(path, "makensis.exe")
            if os.access(makensis, os.X_OK):
                self.nsis_dir = makensis
                break
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
        self.set_undefined_options('bdist',
                                   ('dist_dir', 'dist_dir'),
                                   ('nsis_dir', 'nsis_dir'))

    # finalize_options()


    def run (self):
        if (sys.platform != "win32" and (self.distribution.has_ext_modules() or self.distribution.has_c_libraries())):
                raise DistutilsPlatformError ("This distribution contains extensions and/or C libraries; must be compiled on a Windows 32 platform")
        
        
        self.run_command('build')

        install = self.reinitialize_command('install', reinit_subcommands=1)
        install.root = self.bdist_dir
        install.warn_dir = 0

        install.compile = 0
        install.optimize = 0
        

        for key in ('purelib', 'platlib', 'headers', 'scripts', 'data'):
            if key in ['purelib','platlib'] and sys.version > "2.2":
                value = '_python/Lib/site-packages'
            else:
                value = '_python'
            if key == 'headers':
                value = '_python/Include/$dist_name'
            if key == 'scripts':
                value = '_python/Scripts'
            setattr(install, 'install_' + key, value)
        self.announce("installing to %s" % self.bdist_dir)
        self.run_command('install')

        self.build_nsi()
        
        if not self.keep_temp:
            remove_tree(self.bdist_dir, self.verbose, self.dry_run)        

    # run()

    
    def build_nsi(self):
        nsiscript = NSIDATA
        metadata = self.distribution.metadata
        lic=""
        for name in ["author", "author_email", "maintainer",
                     "maintainer_email", "description", "name", "url", "version"]:
            data = getattr(metadata, name, "")
            if data:
                lic = lic + ("\n    %s: %s" % (string.capitalize(name), data))
                nsiscript=nsiscript.replace('@'+name+'@',data)
                
        if os.path.exists('license'):
            lic=lic + "\n\nLicense:\n" + open('license','r').read()
            
        if lic != "":
            lic="Infos:\n" +lic
            licfile=open(os.path.join(self.bdist_dir,'license'),'wt')
            licfile.write(lic)
            licfile.close()
                
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
        lastdir=""
        for each in files:
            if lastdir != each[0]:
                _f.append('  SetOutPath "$INSTDIR\%s"\n' % each[0])
                lastdir=each[0]
                if each[0] not in ['Lib\\site-packages','Scripts','Include','']:
                    _d.insert(0,'    RMDir "$INSTDIR\\'+each[0]+'\"\n')
            _f.append('  File "_python\\'+each[1]+'\"\n')
            
            if (each[1][len(each[1])-3:].lower() == ".py"):
                _fc.append('"'+each[1]+'",\n')
                _fd.append('    Delete "$INSTDIR\\'+each[1]+'o'+'\"\n')
                _fd.append('    Delete "$INSTDIR\\'+each[1]+'c'+'\"\n')
            _fd.append('    Delete "$INSTDIR\\'+each[1]+'\"\n')
        nsiscript=nsiscript.replace('@_files@',''.join(_f))
        nsiscript=nsiscript.replace('@_deletefiles@',''.join(_fd))
        nsiscript=nsiscript.replace('@_deletedirs@',''.join(_d))
        
        
        if (not self.no_target_compile) or (not self.no_target_optimize):
            bytecompilscript=BYTECOMPILE_DATA.replace('@py_files@',''.join(_fc))
            bytecompilfile=open(os.path.join(self.bdist_dir,'bytecompil.py'),'wt')
            bytecompilfile.write(bytecompilscript)
            bytecompilfile.close()
            
        
        if not self.no_target_compile:
            nsiscript=nsiscript.replace('@compile@','')
        else:
            nsiscript=nsiscript.replace('@compile@',';')        
            
        if not self.no_target_optimize:
            nsiscript=nsiscript.replace('@optimize@','')
        else:
            nsiscript=nsiscript.replace('@optimize@',';')   

        # icon files
        # XXX todo: make icons configurable
        nsiscript = nsiscript.replace(
            "@ico_install@",
            os.path.join(os.path.dirname(__file__), "python-install.ico"))
        nsiscript = nsiscript.replace(
            "@ico_uninstall@",
            os.path.join(os.path.dirname(__file__), "python-uninstall.ico"))
        nsiscript = nsiscript.replace(
            "@header_bitmap@",
            os.path.join(os.path.dirname(__file__), "python-install-150x57.bmp"))
        nsiscript = nsiscript.replace(
            "@welcome_bitmap@",
            os.path.join(os.path.dirname(__file__), "python-install-164x314.bmp"))

        nsifile=open(os.path.join(self.bdist_dir,'setup.nsi'),'wt')
        nsifile.write(nsiscript)
        nsifile.close()
        self.compile()
        
                
            
    def visit(self,arg,dir,fil):
        for each in fil:
            if not os.path.isdir(dir+os.sep+each):
                f=str(dir+os.sep+each)[len(self.bdist_dir+os.sep+'_python'+os.sep):]
                arg.append([os.path.dirname(f),f])
                
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

BYTECOMPILE_DATA="""\
from distutils.util import byte_compile
import sys
import os
d=os.path.dirname(sys.executable)
f=[@py_files@]
g=[]
for each in f:
    g.append(d+os.sep+each)
byte_compile(g, optimize=1, force=None,
                    prefix=d, base_dir=None,
                    verbose=1, dry_run=0,
                    direct=1)
"""

NSIDATA="""\
; @name@ self-installer for windows
; (@name@ - @url@)
; (NSIS - http://nsis.sourceforge.net)

SetCompressor /SOLID lzma

!define PRODUCT_NAME "@name@"
!define PRODUCT_VERSION "@version@"
!define PRODUCT_PUBLISHER "@author@ <@author_email@>"
!define PRODUCT_WEB_SITE "@url@"
!define PRODUCT_UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}"
!define PRODUCT_UNINST_ROOT_KEY "HKLM"
!define PRODUCT_STARTMENU_REGVAL "NSIS:StartMenuDir"
@haspythonversion@!define PRODUCT_PYTHONVERSION "@pythonversion@"
@compile@!define MISC_COMPILE "1"
@optimize@!define MISC_OPTIMIZE "1"

; MUI 1.67 compatible ------
!include "MUI.nsh"

; MUI Settings
!insertmacro MUI_DEFAULT MUI_HEADERIMAGE_BITMAP "@header_bitmap@"
!insertmacro MUI_DEFAULT MUI_WELCOMEFINISHPAGE_BITMAP "@welcome_bitmap@"
!define MUI_HEADERIMAGE
!define MUI_ABORTWARNING
!define MUI_ICON "@ico_install@"
!define MUI_UNICON "@ico_uninstall@"

; Language Selection Dialog Settings
!define MUI_LANGDLL_REGISTRY_ROOT "${PRODUCT_UNINST_ROOT_KEY}"
!define MUI_LANGDLL_REGISTRY_KEY "${PRODUCT_UNINST_KEY}"
!define MUI_LANGDLL_REGISTRY_VALUENAME "NSIS:Language"

; Welcome page
!insertmacro MUI_PAGE_WELCOME
; License page
!insertmacro MUI_PAGE_LICENSE "license"
; Components page
;!insertmacro MUI_PAGE_COMPONENTS
; Directory page
!insertmacro MUI_PAGE_DIRECTORY
; Start menu page

!define MUI_STARTMENUPAGE_NODISABLE
!define MUI_STARTMENUPAGE_DEFAULTFOLDER ""
!define MUI_STARTMENUPAGE_REGISTRY_ROOT "${PRODUCT_UNINST_ROOT_KEY}"
!define MUI_STARTMENUPAGE_REGISTRY_KEY "${PRODUCT_UNINST_KEY}"
!define MUI_STARTMENUPAGE_REGISTRY_VALUENAME "${PRODUCT_STARTMENU_REGVAL}"
; Instfiles page
!insertmacro MUI_PAGE_INSTFILES
; Finish page
!insertmacro MUI_PAGE_FINISH

; Uninstaller pages
!insertmacro MUI_UNPAGE_INSTFILES

; Language files
    !insertmacro MUI_LANGUAGE "English"
    !insertmacro MUI_LANGUAGE "French"
    !insertmacro MUI_LANGUAGE "German"
    !insertmacro MUI_LANGUAGE "Spanish"
    !insertmacro MUI_LANGUAGE "SimpChinese"
    !insertmacro MUI_LANGUAGE "TradChinese"
    !insertmacro MUI_LANGUAGE "Japanese"
    !insertmacro MUI_LANGUAGE "Korean"
    !insertmacro MUI_LANGUAGE "Italian"
    !insertmacro MUI_LANGUAGE "Dutch"
    !insertmacro MUI_LANGUAGE "Danish"
    !insertmacro MUI_LANGUAGE "Swedish"
    !insertmacro MUI_LANGUAGE "Norwegian"
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
    !insertmacro MUI_LANGUAGE "Catalan"
    !insertmacro MUI_LANGUAGE "Slovenian"
    !insertmacro MUI_LANGUAGE "Serbian"
    !insertmacro MUI_LANGUAGE "SerbianLatin"
    !insertmacro MUI_LANGUAGE "Arabic"
    !insertmacro MUI_LANGUAGE "Farsi"
    !insertmacro MUI_LANGUAGE "Hebrew"
    !insertmacro MUI_LANGUAGE "Indonesian"

; MUI end ------


Name "${PRODUCT_NAME} ${PRODUCT_VERSION}"
OutFile "@installer_path@"


InstallDir "C:\Python"
InstallDirRegKey HKLM "${PRODUCT_DIR_REGKEY}" ""
ShowInstDetails show
ShowUnInstDetails show



Function .onInit
    !insertmacro MUI_LANGDLL_DISPLAY
    Call CheckPython
FunctionEnd

!ifdef PRODUCT_PYTHONVERSION
Function GetSpecificPythonPath
    Push $R0
    ClearErrors
    ReadRegStr $R0 HKLM "SOFTWARE\Python\PythonCore\${PRODUCT_PYTHONVERSION}\InstallPath" ""
    IfErrors lbl_na
    Goto lbl_end
    lbl_na:
    StrCpy $R0 ""
    lbl_end:
    Exch $R0
FunctionEnd
!else
Function GetPythonPath
    Push $R0
    Push $0
    Push $1
    StrCpy $0 0
    ClearErrors
    loop:
    EnumRegKey $R0 HKLM "SOFTWARE\Python\PythonCore" $0
    StrCmp $R0 "" lbl_end
    ReadRegStr $1 HKLM "SOFTWARE\Python\PythonCore\$R0\InstallPath" ""    
    StrCmp $1 "" lbl_end
    StrCpy $INSTDIR $1
    IntOp $0 $0 + 1
    Goto loop
    lbl_end:
    Pop $1
    Pop $0
    Pop $R0
FunctionEnd
!endif


Section "main" SEC01
    SectionIn 1 32 RO
    SetOverwrite ifnewer
    SetOutPath $INSTDIR
@_files@
    
    

    !ifdef MISC_COMPILE
    SetOutPath "$TEMP\_python\${PRODUCT_NAME}_${PRODUCT_VERSION}"
    File "bytecompil.py"
    nsExec::Exec '$INSTDIR\python.exe $TEMP\_python\${PRODUCT_NAME}_${PRODUCT_VERSION}\\bytecompil.py' $9
    !endif
    !ifdef MISC_OPTIMIZE
    SetOutPath "$TEMP\_python\${PRODUCT_NAME}_${PRODUCT_VERSION}"
    File "bytecompil.py"
    nsExec::Exec '$INSTDIR\python.exe -OO $TEMP\_python\${PRODUCT_NAME}_${PRODUCT_VERSION}\\bytecompil.py' $9
    !endif
    RMDir /r "$TEMP\_python\${PRODUCT_NAME}_${PRODUCT_VERSION}"
    RMDir "$TEMP\_python"
    
SectionEnd

Function CheckPython
    !ifdef PRODUCT_PYTHONVERSION
    Push $9
    Call GetSpecificPythonPath
    Pop $9
    StrCmp $9 "" lbl_err lbl_ok
lbl_err:
    MessageBox MB_OK "Python ${PRODUCT_PYTHONVERSION} not found. Install it first."
    Abort
lbl_ok:
    StrCpy $INSTDIR $9
    !else
    Call GetPythonPath
    !endif
FunctionEnd

Function .onVerifyInstDir
    IfFileExists $INSTDIR\python.exe goodpath
        Abort 
    goodpath:
FunctionEnd

Section -Post
  WriteUninstaller "$INSTDIR\${PRODUCT_NAME}_uninst.exe"
  WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "DisplayName" "$(^Name)"
  WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "UninstallString" "$INSTDIR\${PRODUCT_NAME}_uninst.exe"
  WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "DisplayVersion" "${PRODUCT_VERSION}"
  WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "URLInfoAbout" "${PRODUCT_WEB_SITE}"
  WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "Publisher" "${PRODUCT_PUBLISHER}"
SectionEnd
Section Uninstall
    Delete "$INSTDIR\${PRODUCT_NAME}_uninst.exe"
@_deletefiles@
@_deletedirs@
    DeleteRegKey ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}"
    SetAutoClose true
SectionEnd

"""

# --- EOF ---
