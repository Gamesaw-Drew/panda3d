""" This module is used to build a "Package", a collection of files
within a Panda3D Multifile, which can be easily be downloaded and/or
patched onto a client machine, for the purpose of running a large
application. """

import sys
import os
import glob
import marshal
import new
from direct.showutil import FreezeTool
from direct.directnotify.DirectNotifyGlobal import *
from pandac.PandaModules import *

class PackagerError(StandardError):
    pass

class OutsideOfPackageError(PackagerError):
    pass

class ArgumentError(PackagerError):
    pass

class Packager:
    notify = directNotify.newCategory("Packager")

    class PackFile:
        def __init__(self, filename, newName = None, deleteTemp = False):
            self.filename = filename
            self.newName = newName
            self.deleteTemp = deleteTemp

    class Package:
        def __init__(self, packageName):
            self.packageName = packageName
            self.version = 'dev'
            self.files = []

            # This records the current list of modules we have added so
            # far.
            self.freezer = FreezeTool.Freezer()

        def close(self):
            """ Writes out the contents of the current package. """

            packageFilename = self.packageName
            packageFilename += '_' + self.version
            packageFilename += '.mf'
            
            try:
                os.unlink(packageFilename)
            except OSError:
                pass
            
            multifile = Multifile()
            multifile.openReadWrite(packageFilename)

            sourceFilename = {}
            targetFilename = {}
            for file in self.files:
                if not file.newName:
                    file.newName = file.filename
                sourceFilename[file.filename] = file
                targetFilename[file.newName] = file

            for file in self.files:
                ext = file.filename.getExtension()
                if ext == 'py':
                    self.addPyFile(file)
                else:
                    # An ordinary file.
                    multifile.addSubfile(file.newName, file.filename, 0)

            # Pick up any unfrozen Python files.
            self.freezer.done()
            self.freezer.addToMultifile(multifile)

            multifile.repack()
            multifile.close()

            # Now that all the files have been packed, we can delete
            # the temporary files.
            for file in self.files:
                if file.deleteTemp:
                    os.unlink(file.filename)

        def addPyFile(self, file):
            """ Adds the indicated python file, identified by filename
            instead of by module name, to the package. """

            # Convert the raw filename back to a module name, so we
            # can see if we've already loaded this file.  We assume
            # that all Python files within the package will be rooted
            # at the top of the package.

            filename = file.newName.rsplit('.', 1)[0]
            moduleName = filename.replace("/", ".")
            if moduleName.endswith('.__init__'):
                moduleName = moduleName.rsplit('.', 1)[0]

            if moduleName in self.freezer.modules:
                # This Python file is already known.  We don't have to
                # deal with it again.
                return

            self.freezer.addModule(moduleName, newName = moduleName,
                                   filename = file.filename)

    def __init__(self):

        # The following are config settings that the caller may adjust
        # before calling any of the command methods.

        # These should each be a Filename, or None if they are not
        # filled in.
        self.installDir = None
        self.persistDir = None

        # The platform string.
        self.platform = PandaSystem.getPlatform()

        # Optional signing and encrypting features.
        self.encryptionKey = None
        self.prcEncryptionKey = None
        self.prcSignCommand = None

        # This is a list of filename extensions and/or basenames that
        # indicate files that should be encrypted within the
        # multifile.  This provides obfuscation only, not real
        # security, since the decryption key must be part of the
        # client and is therefore readily available to any hacker.
        # Not only is this feature useless, but using it also
        # increases the size of your patchfiles, since encrypted files
        # don't patch as tightly as unencrypted files.  But it's here
        # if you really want it.
        self.encryptExtensions = ['ptf', 'dna', 'txt', 'dc']
        self.encryptFiles = []

        # This is the list of DC import suffixes that should be
        # available to the client.  Other suffixes, like AI and UD,
        # are server-side only and should be ignored by the Scrubber.
        self.dcClientSuffixes = ['OV']

    def setup(self):
        """ Call this method to initialize the class after filling in
        some of the values in the constructor. """

        # We need a stack of packages for managing begin_package
        # .. end_package.
        self.packageStack = []
        self.currentPackage = None

        # The persist dir is the directory in which the results from
        # past publishes are stored so we can generate patches against
        # them.  There must be a nonempty directory name here.
        assert(self.persistDir)

        # If the persist dir names an empty or nonexistent directory,
        # we will be generating a brand new publish with no previous
        # patches.
        self.persistDir.makeDir()

        # Within the persist dir, we make a temporary holding dir for
        # generating multifiles.
        self.mfTempDir = Filename(self.persistDir, Filename('mftemp/'))
        #self.mfTempDir.makeDir()

        # We also need a temporary holding dir for squeezing py files.
        self.pyzTempDir = Filename(self.persistDir, Filename('pyz/'))
        #self.pyzTempDir.makeDir()

        # Change to the persist directory so the temp files will be
        # created there
        os.chdir(self.persistDir.toOsSpecific())


    def readPackageDef(self, packageDef):
        """ Reads the lines in packageDef and dispatches to the
        appropriate handler method for each line. """

        self.notify.info('Reading %s' % (packageDef))
        file = open(packageDef.toOsSpecific())
        lines = file.readlines()
        file.close()

        lineNum = [0]
        def getNextLine(lineNum = lineNum):
            """
            Read in the next line of the packageDef
            """
            while lineNum[0] < len(lines):
                line = lines[lineNum[0]].strip()
                lineNum[0] += 1
                if not line:
                    # Skip the line, it was just a blank line
                    pass
                elif line[0] == '#':
                    # Eat python-style comments.
                    pass
                else:
                    # Remove any trailing comment.
                    hash = line.find(' #')
                    if hash != -1:
                        line = line[:hash].strip()
                    # Return the line as an array split at whitespace.
                    return line.split()

            # EOF.
            return None

        # Now start parsing the packageDef lines
        try:
            lineList = getNextLine()
            while lineList:
                command = lineList[0]
                try:
                    methodName = 'parse_%s' % (command)
                    method = getattr(self, methodName, None)
                    if method:
                        method(lineList)

                    else:
                        message = 'Unknown command %s' % (command)
                        raise PackagerError, message
                except ArgumentError:
                    message = 'Wrong number of arguments for command %s' %(command)
                    raise ArgumentError, message
                except OutsideOfPackageError:
                    message = '%s command encounted outside of package specification' %(command)
                    raise OutsideOfPackageError, message

                lineList = getNextLine()

        except PackagerError:
            # Append the line number and file name to the exception
            # error message.
            inst = sys.exc_info()[1]
            inst.args = (inst.args[0] + ' on line %s of %s' % (lineNum[0], packageDef),)
            raise

    def parse_setenv(self, lineList):
        """
        setenv variable value
        """
        
        try:
            command, variable, value = lineList
        except ValueError:
            raise ArgumentNumber

        value = ExecutionEnvironment.expandString(value)
        ExecutionEnvironment.setEnvironmentVariable(variable, value)
            
    def parse_begin_package(self, lineList):
        """
        begin_package packageName
        """
        
        try:
            command, packageName = lineList
        except ValueError:
            raise ArgumentNumber

        self.beginPackage(packageName)

    def parse_end_package(self, lineList):
        """
        end_package packageName
        """

        try:
            command, packageName = lineList
        except ValueError:
            raise ArgumentError

        self.endPackage(packageName)

    def parse_module(self, lineList):
        """
        module moduleName [newName]
        """
        newName = None

        try:
            if len(lineList) == 2:
                command, moduleName = lineList
            else:
                command, moduleName, newName = lineList
        except ValueError:
            raise ArgumentError

        self.module(moduleName, newName = newName)

    def parse_freeze_exe(self, lineList):
        """
        freeze_exe path/to/basename
        """

        try:
            command, filename = lineList
        except ValueError:
            raise ArgumentError

        self.freeze(filename, compileToExe = True)

    def parse_freeze_dll(self, lineList):
        """
        freeze_dll path/to/basename
        """

        try:
            command, filename = lineList
        except ValueError:
            raise ArgumentError

        self.freeze(filename, compileToExe = False)

    def parse_file(self, lineList):
        """
        file filename [newNameOrDir]
        """

        newNameOrDir = None

        try:
            if len(lineList) == 2:
                command, filename = lineList
            else:
                command, filename, newNameOrDir = lineList
        except ValueError:
            raise ArgumentError

        self.file(filename, newNameOrDir = newNameOrDir)
    
    def beginPackage(self, packageName):
        """ Begins a new package specification.  packageName is the
        basename of the package.  Follow this with a number of calls
        to file() etc., and close the package with endPackage(). """
        
        package = self.Package(packageName)
        if self.currentPackage:
            package.freezer.excludeFrom(self.currentPackage.freezer)
            
        self.packageStack.append(package)
        self.currentPackage = package

    def endPackage(self, packageName):
        """ Closes a package specification.  This actually generates
        the package file.  The packageName must match the previous
        call to beginPackage(). """
        
        if not self.currentPackage:
            raise PackagerError, 'unmatched end_package %s' % (packageName)
        if self.currentPackage.packageName != packageName:
            raise PackagerError, 'end_package %s where %s expected' % (
                packageName, self.currentPackage.packageName)

        package = self.currentPackage
        package.close()

        del self.packageStack[-1]
        if self.packageStack:
            self.currentPackage = self.packageStack[-1]
            self.currentPackage.freezer.excludeFrom(package.freezer)
        else:
            self.currentPackage = None

    def module(self, moduleName, newName = None):
        """ Adds the indicated Python module to the current package. """

        if not self.currentPackage:
            raise OutsideOfPackageError

        self.currentPackage.freezer.addModule(moduleName, newName = newName)

    def freeze(self, filename, compileToExe = False):
        """ Freezes all of the current Python code into either an
        executable (if compileToExe is true) or a dynamic library (if
        it is false).  The resulting compiled binary is added to the
        current package under the indicated filename.  The filename
        should not include an extension; that will be added. """

        if not self.currentPackage:
            raise OutsideOfPackageError

        package = self.currentPackage
        freezer = package.freezer
        freezer.done()

        dirname = ''
        basename = filename
        if '/' in basename:
            dirname, basename = filename.rsplit('/', 1)
            dirname += '/'
        basename = freezer.generateCode(basename, compileToExe = compileToExe)

        package.files.append(self.PackFile(basename, newName = dirname + basename, deleteTemp = True))

        # Reset the freezer for more Python files.
        freezer.reset()


    def file(self, filename, newNameOrDir = None):
        """ Adds the indicated arbitrary file to the current package.

        The file is placed in the named directory, or the toplevel
        directory if no directory is specified.

        The filename may include environment variable references and
        shell globbing characters.

        Certain special behavior is invoked based on the filename
        extension.  For instance, .py files may be automatically
        compiled and stored as Python modules.

        If newNameOrDir ends in a slash character, it specifies the
        directory in which the file should be placed.  In this case,
        all files matched by the filename expression are placed in the
        named directory.

        If newNameOrDir ends in something other than a slash
        character, it specifies a new filename.  In this case, the
        filename expression must match only one file.

        If newNameOrDir is unspecified or None, the file is placed in
        the toplevel directory, regardless of its source directory.
        
        """

        if not self.currentPackage:
            raise OutsideOfPackageError

        expanded = Filename.expandFrom(filename)
        files = glob.glob(expanded.toOsSpecific())
        if not files:
            self.notify.warning("No such file: %s" % (expanded))
            return

        newName = None
        prefix = ''
        
        if newNameOrDir:
            if newNameOrDir[-1] == '/':
                prefix = newNameOrDir
            else:
                newName = newNameOrDir
                if len(files) != 1:
                    message = 'Cannot install multiple files on target filename %s' % (newName)
                    raise PackagerError, message

        package = self.currentPackage

        for filename in files:
            filename = Filename.fromOsSpecific(filename)
            basename = filename.getBasename()
            if newName:
                self.addFile(filename, newName = newName)
            else:
                self.addFile(filename, newName = prefix + basename)

    def addFile(self, filename, newName = None):
        """ Adds the named file, giving it the indicated name within
        the package. """

        if not self.currentPackage:
            raise OutsideOfPackageError

        self.currentPackage.files.append(
            self.PackFile(filename, newName = newName))