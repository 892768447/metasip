# Copyright (c) 2012 Riverbank Computing Limited.
#
# This file is part of metasip.
#
# This file may be used under the terms of the GNU General Public License v3
# as published by the Free Software Foundation which can be found in the file
# LICENSE-GPL3.txt included in this package.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.


import os
import hashlib
import time
import fnmatch
from xml.sax import saxutils

from dip.shell import IDirty

from .logger import Logger
from .project_version import ProjectVersion


# The current project.
project = None


class ProjectElement(object):
    """
    This class is a base class for all project elements that can be modified.
    Specified attributes can be watched so that the instance records if any
    have been updated.  (This is where any undo/redo functionality would be
    added.)  
    """
    def __init__(self, annos='', status='unknown', sgen='', egen=''):
        """
        Initialise the instance.

        annos is the string of annotations.
        status is the element status.
        sgen is the start generation as a string, ie. the first generation in
        which it appeared.  None means the beginning of time.
        egen is the end generation as a string, ie. the first generation in
        which it was missing (and not the last generation in which it
        appeared).  None means the end of time.
        """
        self.annos = annos
        self.status = status
        self.sgen = sgen
        self.egen = egen

    def isCurrent(self):
        """
        Returns True if the element is current.
        """
        return (self.egen == '')

    def sipAnnos(self):
        """
        Return the annotations suitable for writing to a SIP file.
        """
        if self.annos != '':
            return " /%s/" % self.annos

        return ""

    def xmlAttributes(self):
        """
        Return the XML attributes as a string.
        """
        s = ''

        if self.annos != '':
            s += ' annos="%s"' % escape(self.annos)

        if self.status != '':
            s += ' status="%s"' % self.status

        if self.sgen != '':
            s += ' sgen="%s"' % self.sgen

        if not self.isCurrent():
            s += ' egen="%s"' % self.egen

        return s


class Project(ProjectElement):
    """ This class represents a MetaSIP project. """

    # Note: name, generation and xinputdir are additional attributes (not in IProject).

    def __init__(self):
        """
        Initialise a project instance.

        pname is the project name or None if it is a new project.
        """
        super().__init__()

        # FIXME
        global project
        project = self

        self.version = ProjectVersion

        self.inputdir = ""
        self.xinputdir = ""
        self.webxmldir = ""
        self.name = ""
        self.rootmodule = ""
        self.outputdir = ""
        self.platforms = ""
        self.features = ""
        self.sipcomments = ""
        self.externalmodules = ""
        self.externalfeatures = ""
        self.ignorednamespaces = ""

        self.modules = []
        self.headers = []
        self.versions = []

    def nameArgumentsFromConventions(self, prj_item, update):
        """
        Name the arguments of all callables contained in a part of the project
        according to the conventions.  Returns a 2-tuple of a list of callables
        with invalid arguments and a list of updated Argument instances.

        prj_item is the part of the project.
        update is set if the project should be updated with the names.
        """

        invalid = []
        updated = []

        for callable in self._get_unnamed_callables(prj_item):
            more_invalid, more_updated = self._applyConventions(callable,
                    update)
            invalid += more_invalid
            updated += more_updated

        if len(updated) != 0:
            IDirty(self).dirty = True

        return invalid, updated

    def acceptArgumentNames(self, prj_item):
        """
        Mark the arguments of all callables contained in a part of the project
        as being named.  Return a list of the updated Argument instances.

        prj_item is the part of the project.
        """

        updated = []

        for callable in self._get_unnamed_callables(prj_item):
            for arg in callable.args:
                if arg.unnamed and arg.default is not None:
                    arg.unnamed = False
                    updated.append(arg)

        if len(updated) != 0:
            IDirty(self).dirty = True

        return updated

    def updateArgumentsFromWebXML(self, ui, module):
        """
        Update any unnamed arguments of all callables contained in a module
        from WebXML.  Returns a 2-tuple of a list of undocumented callables and
        a list of updated Argument instances.

        ui is the user interface.
        module is the module.
        """
        undocumented = []
        updated_args = []

        webxml = ui.loadWebXML()

        for hf in module:
            for callable in self._get_unnamed_callables(hf):
                # Convert the callable to the normalised form used by the
                # WebXML key.

                try:
                    static = callable.static
                except AttributeError:
                    static = False

                if static:
                    static = 'static '
                else:
                    static = ''

                try:
                    const = callable.const
                except AttributeError:
                    const = False

                if const:
                    const = ' const'
                else:
                    const = ''

                arg_types = []
                arg_names = []
                for arg in callable.args:
                    assert type(arg) is Argument

                    atype = arg.type.replace(' ', '')
                    if atype.startswith('const'):
                        atype = 'const ' + atype[5:]

                    # Function pointers may contain a format character.
                    if '%' in atype:
                        atype = atype % ''

                    arg_types.append(atype)

                    name = arg.name
                    if name is None:
                        name = ''

                    arg_names.append(name)

                sig = '%s%s(%s)%s' % (static, self._fullName(callable), ', '.join(arg_types), const)

                names = webxml.get(sig)
                if names is None:
                    undocumented.append(sig)
                else:
                    for name, arg in zip(names, callable.args):
                        if arg.unnamed and name:
                            arg.name = name
                            updated_args.append(arg)

        if len(updated_args) != 0:
            IDirty(self).dirty = True

        return undocumented, updated_args

    def _applyConventions(self, callable, update):
        """
        Apply the conventions to a callable.  Returns a 2-tuple of a list of
        callables with invalid arguments and a list of updated Argument
        instances.
        """
        invalid = []
        updated = []
        skip = False

        # Make sure copy ctors don't have a named argument.
        if type(callable) is Constructor:
            if len(callable.args) == 1:
                arg = callable.args[0]
                atype = arg.type.replace(' ', '')

                if atype == 'const%s&' % callable.name:
                    skip = True

                    if arg.name is not None and arg.default is not None:
                        if update:
                            arg.name = None
                            arg.unnamed = False
                            updated.append(arg)
                        else:
                            invalid.append("%s copy constructor has a named argument" % self._fullName(callable.container))

        if type(callable) in (Function, Method):
            if callable.name == 'event' or callable.name.endswith('Event'):
                # Make sure single argument event handlers don't have a named
                # argument.

                if len(callable.args) == 1:
                    skip = True

                    arg = callable.args[0]

                    if arg.default is not None:
                        if update:
                            arg.unnamed = False
                            updated.append(arg)

                        if arg.name is not None:
                            if update:
                                arg.name = None
                            else:
                                invalid.append("%s() event handler has a named argument" % self._fullName(callable))

        if not skip:
            for arg in callable.args:
                if arg.default is None:
                    continue

                if arg.unnamed:
                    aname = arg.name
                    if aname is None:
                        aname = ''

                    # Check that events are called 'event'.
                    if self._argType(arg).endswith('Event*'):
                        if update:
                            arg.unnamed = False
                            updated.append(arg)

                        if aname != 'event':
                            if update:
                                arg.name = 'event'
                            else:
                                invalid.append("%s() event argument name '%s' is not 'event'" % (self._fullName(callable), aname))

                        continue

                    # Check that objects are called 'object' or 'parent'.
                    if self._argType(arg) == 'QObject*':
                        if update:
                            arg.unnamed = False
                            updated.append(arg)

                        if aname not in ('object', 'parent'):
                            if update:
                                arg.name = 'object'
                            else:
                                invalid.append("%s() QObject argument name '%s' is not 'object' or 'parent'" % (self._fullName(callable), aname))

                        continue

                    # Check that widgets are called 'widget' or 'parent'.
                    if self._argType(arg) == 'QWidget*':
                        if update:
                            arg.unnamed = False
                            updated.append(arg)

                        if aname not in ('widget', 'parent'):
                            if update:
                                arg.name = 'widget'
                            else:
                                invalid.append("%s() QWidget argument name '%s' is not 'widget' or 'parent'" % (self._fullName(callable), aname))

                        continue

                    # Check other common suffixes.
                    suffixes = ("Index", "Device", "NamePool", "Handler",
                            "Binding", "Mode")

                    for s in suffixes:
                        if self._argType(arg).endswith(s):
                            if update:
                                arg.unnamed = False
                                updated.append(arg)

                            lc_s = s[0].lower() + s[1:]
                            if aname != lc_s:
                                if update:
                                    arg.name = lc_s
                                else:
                                    invalid.append("%s() '%s' argument name '%s' is not '%s'" % (self._fullName(callable), s, aname, lc_s))

                    # Check for non-standard acronyms.
                    acronyms = ("XML", "URI", "URL")

                    for a in acronyms:
                        if a in aname:
                            if update:
                                arg.unnamed = False
                                updated.append(arg)

                            lc_a = aname.replace(a, a[0] + a[1:].lower())
                            if update:
                                arg.name = lc_a
                            else:
                                invalid.append("%s() argument name '%s' should be '%s'" % (self._fullName(callable), aname, lc_a))

                    # Check the callable has arguments with names and that they
                    # are long enough that they don't need checking manually.
                    if len(aname) <= 2:
                        invalid.append("%s() argument name '%s' is too short" % (self._fullName(callable), aname))

        return invalid, updated

    @staticmethod
    def _argType(arg):
        """
        Return the normalised C++ type of an argument.

        arg is the argument.
        """
        return arg.type.replace(' ', '')

    @staticmethod
    def _fullName(item):
        """
        Return the C++ name of an item.

        item is the item.
        """
        names = []

        while type(item) is not HeaderFile:
            names.insert(0, item.name)
            item = item.container

        return '::'.join(names)

    def _get_unnamed_callables(self, part):
        """
        A generator for all the checked callables in a part of a project.

        part is the part of the project.
        """
        ptype = type(part)

        if ptype is HeaderFile:
            for sub in part:
                for callable in self._get_unnamed_callables(sub):
                    yield callable
        elif not part.status:
            if ptype is Function:
                for arg in part.args:
                    if arg.unnamed and arg.default is not None:
                        yield part
                        break
            elif ptype in (Constructor, Method):
                if part.access != 'private':
                    for arg in part.args:
                        if arg.unnamed and arg.default is not None:
                            yield part
                            break
            elif ptype in (Class, Namespace):
                for sub in part:
                    for callable in self._get_unnamed_callables(sub):
                        yield callable

    def addVersion(self, vers):
        """
        Add a new version to the project.

        vers is the new version.
        """
        self.versions.append(vers)
        self.generation = len(self.versions)

        IDirty(self).dirty = True

    def addPlatform(self, plat):
        """
        Add a new platform to the project.

        plat is the new platform.
        """
        if self.platforms != '':
            self.platforms += " "

        self.platforms += plat

        IDirty(self).dirty = True

    def addFeature(self, feat):
        """
        Add a new feature to the project.

        feat is the new feature.
        """
        if self.features != '':
            self.features += " "

        self.features += feat

        IDirty(self).dirty = True

    def addExternalModule(self, xm):
        """
        Add a new external module to the project.

        xm is the new external module.
        """
        if self.externalmodules:
            self.externalmodules += " "

        self.externalmodules += xm

        IDirty(self).dirty = True

    def addExternalFeature(self, xf):
        """
        Add a new external feature to the project.

        xf is the new external feature.
        """
        if self.externalfeatures != '':
            self.externalfeatures += " "

        self.externalfeatures += xf

        IDirty(self).dirty = True

    def addIgnoredNamespace(self, ns):
        """
        Add a new ignored namespace to the project.

        ns is the new ignored namespace.
        """
        if self.ignorednamespaces:
            self.ignorednamespaces += " "

        self.ignorednamespaces += ns

        IDirty(self).dirty = True

    def versionRange(self, sgen, egen):
        """
        Return the version string corresponding to a range of generations.

        sgen is the start generation.
        egen is the end generation.
        """
        if sgen == '':
            if egen == '':
                return ""

            return "- " + self.versions[int(egen) - 1]

        if egen == '':
            return self.versions[int(sgen) - 1] + " -"

        return self.versions[int(sgen) - 1] + " - " + self.versions[int(egen) - 1]

    def literal(self, ltype, text):
        """
        Accept some literal text.

        ltype is the type of the text.
        text is the text.
        """
        if ltype == "sipcomments":
            self.sipcomments = text

    def save(self, saveas=None):
        """
        Save the project and return True if the save was successful.

        saveas is the name of the file to save to, or None if the current file
        should be used.
        """
        if saveas is None:
            fname = self.name + ".new"
        else:
            fname = saveas

        # Open/create the file.
        f = _createIndentFile(self, fname)

        if f is None:
            return False

        # Handle the list of versions.
        if len(self.versions) != 0:
            vers = ' versions="%s"' % " ".join(self.versions)
        else:
            vers = ''

        # Handle the platforms.
        if self.platforms != '':
            plat = ' platforms="%s"' % self.platforms
        else:
            plat = ''

        # Handle the features.
        if self.features != '':
            feat = ' features="%s"' % self.features
        else:
            feat = ''

        # Handle the external modules.
        if self.externalmodules != '':
            xmod = ' externalmodules="%s"' % self.externalmodules
        else:
            xmod = ''

        # Handle the external features.
        if self.externalfeatures != '':
            xf = ' externalfeatures="%s"' % self.externalfeatures
        else:
            xf = ''

        # Handle the ignored namespaces.
        if self.ignorednamespaces != '':
            ins = ' ignorednamespaces="%s"' % self.ignorednamespaces
        else:
            ins = ''

        # Write the project using the current version.
        f.write('<?xml version="1.0"?>\n')
        f.write('<Project version="%u" rootmodule="%s"%s%s%s%s%s%s inputdir="%s" webxmldir="%s" outputdir="%s">\n' % (Version, self.rootmodule, vers, plat, feat, xmod, xf, ins, self.inputdir, self.webxmldir, self.outputdir))

        if self.sipcomments != '':
            _writeLiteralXML(f, "sipcomments", self.sipcomments)

        f += 1

        # Give each header file a unique ID, ignoring any current one.  The ID
        # is only used when the project file is written and read.  It is
        # undefined at all other times.
        hfid = 0

        for hdir in self.headers:
            f.write('<HeaderDirectory name="%s" parserargs="%s" inputdirsuffix="%s" filefilter="%s">\n' % (hdir.name, hdir.parserargs, hdir.inputdirsuffix, hdir.filefilter))
            f += 1

            for hf in hdir.content:
                hf.id = hfid
                hf.xml(f)
                hfid += 1

            f -= 1
            f.write('</HeaderDirectory>\n')

        for mod in self.modules:
            f.write('<Module name="%s"' % mod.name)

            if mod.outputdirsuffix:
                f.write(' outputdirsuffix="%s"' % mod.outputdirsuffix)

            if mod.version:
                f.write(' version="%s"' % mod.version)

            if mod.imports:
                f.write(' imports="%s"' % mod.imports)

            f.write('>\n')

            f += 1

            if mod.directives:
                _writeLiteralXML(f, "directives", mod.directives)

            for hf in mod:
                f.write('<ModuleHeaderFile id="%u"/>\n' % hf.id)

            f -= 1
            f.write('</Module>\n')

        f -= 1
        f.write('</Project>\n')

        # Tidy up, renaming the project as necessary.
        f.close()

        if saveas is None:
            # Remove any backup file.
            backup = self.name + "~"
            try:
                os.remove(backup)
            except:
                pass

            os.rename(self.name, backup)
            os.rename(fname, self.name)
            os.remove(backup)
        else:
            self.name = saveas

        return True

    def load(self):
        """ Load the project.

        :return:
            ``True`` if the project was successfully loaded.
        """

        from .project_parser import ProjectParser

        if ProjectParser().parse(self):
            return True

        return False

    def descriptiveName(self):
        """
        Return the descriptive name of the project.
        """
        if self.name == '':
            return "Untitled"

        # Remove the standard extension, but leave any non-standard one in
        # place.
        (root, ext) = os.path.splitext(self.name)

        if ext != ".msp":
            root = self.name

        return os.path.basename(root)

    def generateModule(self, ui, mod, od, saveod=True, latest_sip=True):
        """
        Generate the output for a module.  Return True if there was no error.

        ui is the user interface instance.
        mod is the module instance.
        od is the root of the output directory.
        saveod is True if od should be saved in the project.
        """
        # Remember the root directory used.
        od = os.path.abspath(od)

        if saveod and self.outputdir != od:
            self.outputdir = od

        # Generate each applicable header file.
        hfnames = []
        for hf in mod.content:
            f = self._createSIPFile(od, mod, hf)

            if f is None:
                return False

            Logger.log("Generating %s" % f.name)
            hf.sip(f, latest_sip)
            hfnames.append(os.path.basename(f.name))

            f.close()

        f = self._createSIPFile(od, mod)

        if f is None:
            return False

        Logger.log("Generating %s" % f.name)

        rname = self.rootmodule

        if rname:
            rname += "."

        if mod.version != "":
            version = ", version=%s" % mod.version
        else:
            version = ""

        if latest_sip:
            f.write("%%Module(name=%s%s, keyword_arguments=\"Optional\"%s)\n\n" % (rname, mod.name, version))
        else:
            f.write("%%Module %s%s 0\n\n" % (rname, mod.name))

        top_level_module = True
        external = self.externalmodules.split()

        if mod.imports:
            for m in mod.imports.split():
                f.write("%%Import %s/%smod.sip\n" % (m, m))

                if m not in external:
                    top_level_module = False

            f.write("\n")

        if top_level_module:
            # Add any version, platform and feature information to all top
            # level modules (ie. those that don't import anything).

            if len(self.versions) != 0:
                f.write("%%Timeline {%s}\n\n" % " ".join(self.versions))

            if self.platforms != '':
                f.write("%%Platforms {%s}\n\n" % self.platforms)

            if self.features != '':
                for feat in self.features.split():
                    f.write("%%Feature %s\n" % feat)

                f.write("\n")

        if mod.directives:
            f.write(mod.directives)
            f.write("\n\n")

        for inc in hfnames:
            f.write("%%Include %s\n" % inc)

        f.close()

        return True

    def _createSIPFile(self, od, mod, hf=None):
        """
        Return a boilerplate SIP file.

        od is the root of the output directory.
        mod is the module instance.
        hf is the header file instance.
        """
        # Work out the name of the file.
        if mod.outputdirsuffix:
            od = os.path.join(od, mod.outputdirsuffix)

        if hf is None:
            fname = mod.name + "mod"
        else:
            (fname, ext) = os.path.splitext(os.path.basename(hf.name))

        fname += ".sip"

        # Make sure the output directory exists.
        try:
            os.makedirs(od)
        except:
            pass

        pname = str(os.path.join(od, fname))

        f = _createIndentFile(self, pname, 4)

        if f:
            # Add the standard header.
            f.write(
"""// %s generated by MetaSIP on %s
//
// This file is part of the %s Python extension module.
""" % (fname, time.asctime(), mod.name))

            if self.sipcomments:
                f.write("//\n%s\n" % self.sipcomments)

            f.write("\n")
            f.blank()

        return f

    def newModule(self, name, odirsuff="", version="", imports=""):
        """
        Add a new module to the project.

        name is the name of the module.
        odirsuff is the optional output directory suffix.
        version is the module version number.
        imports is the optional space separated list of imported modules.
        """
        mod = Module(name=name, outputdirsuffix=odirsuff, version=version,
                imports=imports)
        self.modules.append(mod)

        IDirty(self).dirty = True

        return mod

    def newHeaderDirectory(self, name, pargs="", inputdirsuffix="", filefilter=""):
        """
        Add a new header directory to the project and return it.

        name is the descriptive name of the header directory.
        pargs is the optional string of parser arguments.
        inputdirsuffix when joined to the inputdir gives the absolute name of
        the header directory.
        filefilter is the optional pattern used to select only those files of
        interest.
        """
        hdir = HeaderDirectory(name=name, parserargs=pargs,
                inputdirsuffix=inputdirsuffix, filefilter=filefilter)
        self.headers.append(hdir)

        IDirty(self).dirty = True

        return hdir

    def findHeaderDirectory(self, target):
        """
        Return the header directory instance of a header file.

        target is the header file instance.
        """
        for hdir in self.headers:
            for hf in hdir.content:
                if hf is target:
                    return hdir

        # This should never happen.
        return None


class Code(ProjectElement):
    """ This class is the base class for all elements of parsed C++ code. """

    def __init__(self, platforms='', features='', annos='', status='unknown', sgen='', egen=''):
        """
        Initialise the class instance.

        platforms is the space separated list of platforms.
        features is the space separated list of features.
        annos is the string of annotations.
        status is the class status.
        sgen is the start generation.
        egen is the end generation.
        """
        self.platforms = platforms
        self.features = features

        super().__init__(annos, status, sgen, egen)

    def signature(self):
        """
        Return a C/C++ representation for comparison purposes.
        """
        # Return the user friendly representation by default.
        return self.user()

    def sip(self, f, hf, latest_sip):
        """
        Write the code to a SIP file.  This only calls the method for each
        child code.  This method should be reimplemented to write the code
        specific data.

        f is the file.
        hf is the corresponding header file instance.
        """
        for c in self.content:
            if c.status:
                continue

            # FIXME
            vrange = project.versionRange(c.sgen, c.egen)

            if vrange != '':
                f.write("%%If (%s)\n" % vrange, False)

            if c.platforms != '':
                f.write("%%If (%s)\n" % " || ".join(c.platforms.split()), False)

            if c.features != '':
                f.write("%%If (%s)\n" % " || ".join(c.features.split()), False)

            c.sip(f, hf, latest_sip)

            if c.features != '':
                f.write("%End\n", False)

            if c.platforms != '':
                f.write("%End\n", False)

            if vrange != '':
                f.write("%End\n", False)

    def xml(self, f):
        """
        Write the code to an XML file.  This only calls the method for each
        child code.  This method should be reimplemented to write the code
        specific data.

        f is the file.
        """
        for c in self.content:
            c.xml(f)

    def xmlAttributes(self):
        """
        Return the XML attributes as a string.
        """
        s = super(Code, self).xmlAttributes()

        if self.platforms != '':
            s += ' platforms="%s"' % self.platforms

        if self.features != '':
            s += ' features="%s"' % self.features

        return s


class Access(object):
    """ This class is derived by all code that is affected by class access. """

    def __init__(self, access):
        """
        Initialise the access instance.

        access is the access.
        """
        self.access = access

    def sigAccess(self):
        """
        Return a C/C++ representation for comparison purposes.
        """
        # Any Qt specific part isn't part of the signature.
        try:
            s = self.access.split()[0]
        except IndexError:
            s = ""

        if s == "signals":
            s = "protected"
        elif s == "public":
            s = ""

        return s

    def xmlAccess(self):
        """
        Return an XML representation of the access.
        """
        if self.access != '':
            s = ' access="%s"' % self.access
        else:
            s = ''

        return s


class Module(ProjectElement):
    """ This class represents a project module. """

    def __init__(self, name, outputdirsuffix, version, imports):
        """
        Initialise a module instance.

        name is the module name.
        outputdirsuffix is the output directory suffix.
        version is the module version number.
        imports is the space separated list of module imports.
        """
        self.name = name
        self.outputdirsuffix = outputdirsuffix
        self.version = version
        self.imports = imports
        self.directives = ""
        self.content = []

        super().__init__()

    def literal(self, ltype, text):
        """
        Accept some literal text.

        ltype is the type of the text.
        text is the text.
        """
        if ltype == "directives":
            self.directives = text


class HeaderDirectory(ProjectElement):
    """ This class represents a project header directory. """

    def __init__(self, name, parserargs="", inputdirsuffix="", filefilter=""):
        """
        Initialise a header directory instance.

        name is the descriptive name of the header directory.
        parserargs is the optional string of parser arguments.
        inputdirsuffix when joined to the inputdir gives the absolute name of
        the header directory.
        filefilter is the optional pattern used to select only those files of
        interest.
        """
        self.name = name
        self.parserargs = parserargs
        self.inputdirsuffix = inputdirsuffix
        self.filefilter = filefilter
        self.content = []

        super().__init__()

    def newHeaderFile(self, id, name, md5, parse, status, sgen, egen=''):
        """
        Add a new header file to the project and return it.

        id is the ID.
        name is the path name of the header file excluding the header
        directory.
        md5 is the file's MD5 signature.
        parse is the file parse status.
        status is the file status.
        sgen is the start generation.
        egen is the end generation.
        """
        hf = HeaderFile(id=id, name=name, md5=md5, parse=parse, status=status,
                sgen=sgen, egen=egen)
        self.content.append(hf)

        # FIXME
        IDirty(project).dirty = True

        return hf

    def addParsedHeaderFile(self, hf, phf):
        """
        Add a parsed header file to the project.

        hf is the header file instance.
        phf is the parsed header file.
        """
        self._mergeCode(hf, phf)

        # Assume something has changed.
        # FIXME
        IDirty(project).dirty = True

    def _mergeCode(self, dsc, ssc):
        """
        Merge source code into destination code.

        dsc is the destination code instance.
        ssc is the list of parsed source code items.
        """
        # Go though each existing code item.
        for dsi in dsc.content:
            # Ignore anything that isn't current.
            if not dsi.isCurrent():
                continue

            # Manual code is sticky.
            if isinstance(dsi, ManualCode):
                continue

            # Go through each potentially new code item.
            for ssi in ssc:
                if type(dsi) is type(ssi) and dsi.signature() == ssi.signature():
                    break
            else:
                ssi = None

            if ssi is None:
                # The existing one no longer exists.
                # FIXME
                dsi.egen = str(project.generation)
            else:
                # Discard the new code item.
                ssc.remove(ssi)

                # Merge any child code.
                if isinstance(dsi, (Class, Namespace)):
                    self._mergeCode(dsi, ssi.content)

        # Anything left in the source code is new.
        for ssi in ssc:
            # FIXME
            ssi.sgen = str(project.generation)

            dsc.content.append(ssi)

    def scan(self, sd, ui):
        """
        Scan a header directory and process it's contents.

        sd is the name of the directory to scan.
        ui is the user interface instance.
        """
        sd = os.path.abspath(sd)
        sdlen = len(sd) + len(os.path.sep)

        # Save the files that were in the directory.
        saved = self[:]

        Logger.log("Scanning header directory %s" % sd)

        for (root, dirs, files) in os.walk(sd):
            for f in files:
                hpath = os.path.join(root, f)
                hfile = hpath[sdlen:]

                # Apply any file name filter.
                if self.filefilter:
                    if not fnmatch.fnmatch(hfile, self.filefilter):
                        continue

                if os.access(hpath, os.R_OK):
                    hf = self._scanHeaderFile(hpath, hfile)

                    for shf in saved:
                        if shf.name == hf.name:
                            saved.remove(shf)
                            break

                    Logger.log("Scanned %s" % hfile)
                else:
                    Logger.log("Skipping unreadable header file %s" % hfile)

        # Anything left in the known list has gone missing or was already
        # missing.
        for hf in saved:
            if hf.isCurrent():
                Logger.log("%s is no longer in the header directory" % hf.name)

                # If it is unknown then just forget about it.
                if hf.status == "unknown":
                    self.content.remove(hf)
                else:
                    # FIXME
                    hf.egen = project.generation

        # Assume something has changed.
        # FIXME
        IDirty(project).dirty = True

    def _scanHeaderFile(self, hpath, hfile):
        """
        Scan a header file and return the header file instance.

        hpath is the full pathname of the header file.
        hfile is the pathname relative to the header directory.
        """
        # Calculate the MD5 signature ignoring any comments.  Note that nested
        # C style comments aren't handled very well.
        m = hashlib.md5()

        f = open(hpath, "r")
        src = f.read()
        f.close()

        lnr = 1
        state = "copy"
        copy = ""
        idx = 0

        for ch in src:
            # Get the previous character.
            if idx > 0:
                prev = src[idx - 1]
            else:
                prev = ""

            idx += 1

            # Line numbers must be accurate.
            if ch == "\n":
                lnr += 1

            # Handle the end of a C style comment.
            if state == "ccmnt":
                if ch == "/" and prev == "*":
                    state = "copy"

                continue

            # Handle the end of a C++ style comment.
            if state == "cppcmnt":
                if ch == "\n":
                    state = "copy"

                continue

            # We must be in the copy state.

            if ch == "*" and prev == "/":
                # The start of a C style comment.
                state = "ccmnt"
                continue

            if ch == "/" and prev == "/":
                # The start of a C++ style comment.
                state = "cppcmnt"
                continue

            # At this point we know the previous character wasn't part of a
            # comment.
            if prev:
                m.update(prev.encode(f.encoding))

        # Note that we didn't add the last character, but it would normally be
        # a newline.
        sig = m.hexdigest()

        # See if we already know about the file.
        for hf in self.content:
            if hf.name == hfile:
                if hf.isCurrent():
                    if hf.md5 != sig:
                        hf.md5 = sig
                        hf.parse = "needed"

                    return hf

                break

        # It is a new file, or the reappearence of an old one.
        # FIXME
        return self.newHeaderFile(None, hfile, sig, "needed", "unknown", project.generation)


class HeaderFile(Code):
    """
    This class represents a project header file.
    """
    def __init__(self, id, name, md5, parse, status, sgen, egen):
        """
        Initialise a header file instance.

        id is the file's ID.
        name is the path name of the header file excluding the header directory
        root.
        md5 is the file's MD5 signature.
        parse is the file's parse status (either "" or "needed").
        status is the file status.
        sgen is the start generation.
        egen is the end generation.
        """
        self.id = id
        self.name = name
        self.md5 = md5
        self.parse = parse
        self.exportedheadercode = ""
        self.moduleheadercode = ""
        self.modulecode = ""
        self.preinitcode = ""
        self.initcode = ""
        self.postinitcode = ""
        self.content = []

        super().__init__(None, None, None, status, sgen, egen)

    def literal(self, ltype, text):
        """
        Accept some literal text.

        ltype is the type of the text.
        text is the text.
        """
        if ltype == "exportedheadercode":
            self.exportedheadercode = text

        if ltype == "moduleheadercode":
            self.moduleheadercode = text

        if ltype == "modulecode":
            self.modulecode = text

        if ltype == "preinitcode":
            self.preinitcode = text

        if ltype == "initcode":
            self.initcode = text

        if ltype == "postinitcode":
            self.postinitcode = text

    def sip(self, f, latest_sip):
        """
        Write the header file to a SIP file.

        f is the output file.
        """
        if self.status:
            return 

        # See if we need a %ModuleCode directive for things which will be
        # implemented at the module level.
        for c in self.content:
            if c.status:
                continue

            if isinstance(c, Function) or isinstance(c, OperatorFunction) or isinstance(c, Variable) or isinstance(c, Enum):
                # FIXME
                vrange = project.versionRange(self.sgen, self.egen)

                if vrange:
                    f.write("%%If (%s)\n" % vrange, False)

                f.write(
"""%%ModuleCode
#include <%s>
%%End
""" % self.name)

                if vrange:
                    f.write("%End\n", False)

                f.blank()

                break

        super(HeaderFile, self).sip(f, self, latest_sip)

        f.blank()

        if self.exportedheadercode:
            _writeCodeSIP(f, "%ExportedHeaderCode", self.exportedheadercode, False)

        if self.moduleheadercode:
            _writeCodeSIP(f, "%ModuleHeaderCode", self.moduleheadercode, False)

        if self.modulecode:
            _writeCodeSIP(f, "%ModuleCode", self.modulecode, False)

        if self.preinitcode:
            _writeCodeSIP(f, "%PreInitialisationCode", self.preinitcode, False)

        if self.initcode:
            _writeCodeSIP(f, "%InitialisationCode", self.initcode, False)

        if self.postinitcode:
            _writeCodeSIP(f, "%PostInitialisationCode", self.postinitcode, False)

    def xml(self, f):
        """
        Write the header file to an XML file.

        f is the file.
        """
        f.write('<HeaderFile%s>\n' % self.xmlAttributes())

        f += 1
        super(HeaderFile, self).xml(f)
        f -= 1

        if self.exportedheadercode:
            _writeLiteralXML(f, "exportedheadercode", self.exportedheadercode)

        if self.moduleheadercode:
            _writeLiteralXML(f, "moduleheadercode", self.moduleheadercode)

        if self.modulecode:
            _writeLiteralXML(f, "modulecode", self.modulecode)

        if self.preinitcode:
            _writeLiteralXML(f, "preinitcode", self.preinitcode)

        if self.initcode:
            _writeLiteralXML(f, "initcode", self.initcode)

        if self.postinitcode:
            _writeLiteralXML(f, "postinitcode", self.postinitcode)

        f.write('</HeaderFile>\n')

    def xmlAttributes(self):
        """
        Return the XML attributes as a string.
        """
        s = super(HeaderFile, self).xmlAttributes()

        s += ' id="%u"' % self.id
        s += ' name="%s"' % self.name
        s += ' md5="%s"' % self.md5

        if self.parse:
            s += ' parse="%s"' % self.parse

        return s


class Argument(ProjectElement):
    """ This class represents an argument. """

    def __init__(self, type, name='', unnamed=True, default='', pytype='', annos=''):
        """
        Initialise the argument instance.

        type is the type of the argument.
        name is the optional name of the argument.
        unnamed is set if the name is not "official".
        default is the optional default value of the argument.
        pytype is the Python type.
        annos is the string of annotations.
        """
        self.type = type
        self.name = name
        self.unnamed = unnamed
        self.default = default
        self.pytype = pytype

        super().__init__(annos, status='')

    def signature(self):
        """
        Return a C/C++ representation for comparison purposes.
        """
        s = _expandType(self.type)

        if self.default != '':
            s += " = " + self.default

        return s

    def user(self):
        """
        Return a user friendly representation of the argument.
        """
        s = _expandType(self.type)

        if self.name != '':
            if s[-1] not in "&*":
                s += " "

            s += self.name

        if self.default != '':
            s += " = " + self.default

        return s

    def sip(self, latest_sip, ignore_namespaces=True):
        """
        Return the argument suitable for writing to a SIP file.
        """
        if self.pytype != '':
            s = self.pytype
        else:
            s = _expandType(self.type, ignore_namespaces=ignore_namespaces)

        if self.name != '':
            if s[-1] not in "&*":
                s += " "

            s += self.name

        s += self.sipAnnos()

        if self.default != '':
            s += " = " + _ignoreNamespaces(self.default)

        return s

    def xml(self, f):
        """
        Write the argument to an XML file.

        f is the file.
        """
        f.write('<Argument%s/>\n' % self.xmlAttributes())

    def xmlAttributes(self):
        """
        Return the XML attributes as a string.
        """
        s = super(Argument, self).xmlAttributes()

        s += ' type="%s"' % escape(self.type)

        if self.unnamed:
            s += ' unnamed="1"'

        if self.name != '':
            s += ' name="%s"' % escape(self.name)

        if self.default != '':
            s += ' default="%s"' % escape(self.default)

        if self.pytype != '':
            s += ' pytype="%s"' % escape(self.pytype)

        return s


class Class(Code, Access):
    """ This class represents a class. """

    def __init__(self, name, container, bases, struct, access, pybases='', platforms='', features='', annos='', status='unknown', sgen='', egen=''):
        """
        Initialise the class instance.

        name is the name of the class.
        container is the container of the class.
        bases is the list of base classes.
        struct set if the class is a struct.
        access is the access.
        pybases is the list of Python base classes.
        platforms is the space separated list of platforms.
        features is the space separated list of features.
        annos is the string of annotations.
        status is the class status.
        sgen is the start generation.
        egen is the end generation.
        """
        self.name = name
        self.container = container
        self.bases = bases
        self.struct = struct
        self.pybases = pybases
        self.docstring = ""
        self.typeheadercode = ""
        self.typecode = ""
        self.convtotypecode = ""
        self.subclasscode = ""
        self.gctraversecode = ""
        self.gcclearcode = ""
        self.bigetbufcode = ""
        self.birelbufcode = ""
        self.bireadbufcode = ""
        self.biwritebufcode = ""
        self.bisegcountcode = ""
        self.bicharbufcode = ""
        self.picklecode = ""
        self.content = []

        Code.__init__(self, platforms, features, annos, status, sgen, egen)
        Access.__init__(self, access)

    def literal(self, ltype, text):
        """
        Accept some literal text.

        ltype is the type of the text.
        text is the text.
        """
        if ltype == "docstring":
            self.docstring = text
        elif ltype == "typeheadercode":
            self.typeheadercode = text
        elif ltype == "typecode":
            self.typecode = text
        elif ltype == "convtotypecode":
            self.convtotypecode = text
        elif ltype == "subclasscode":
            self.subclasscode = text
        elif ltype == "gctraversecode":
            self.gctraversecode = text
        elif ltype == "gcclearcode":
            self.gcclearcode = text
        elif ltype == "bigetbufcode":
            self.bigetbufcode = text
        elif ltype == "birelbufcode":
            self.birelbufcode = text
        elif ltype == "bireadbufcode":
            self.bireadbufcode = text
        elif ltype == "biwritebufcode":
            self.biwritebufcode = text
        elif ltype == "bisegcountcode":
            self.bisegcountcode = text
        elif ltype == "bicharbufcode":
            self.bicharbufcode = text
        elif ltype == "picklecode":
            self.picklecode = text

    def signature(self):
        """
        Return a C/C++ representation for comparison purposes.
        """
        if self.struct:
            s = "struct"
        else:
            s = "class"

        if self.name != '':
            s += " " + self.name

        if self.bases != '':
            s += " : " + self.bases

        s += self.sigAccess()

        return s

    def user(self):
        """
        Return a user friendly representation of the class.
        """
        if self.struct:
            s = "struct"
        else:
            s = "class"

        if self.name != '':
            s += " " + self.name

        if self.bases != '':
            s += " : " + self.bases

        s += self.sipAnnos()

        return s

    def sip(self, f, hf, latest_sip):
        """
        Write the class to a SIP file.

        f is the file.
        hf is the corresponding header file instance.
        """
        if self.status != '':
            return 

        f.blank()

        bstr = ""

        if self.struct:
            tname = "struct "
        else:
            tname = "class "

        if self.pybases != '':
            # Treat None as meaning no super classes:
            if self.pybases != "None":
                bstr = " : " + ", ".join(self.pybases.split())
        elif self.bases != '':
            clslst = []

            for b in self.bases.split(", "):
                acc, cls = b.split()

                # Handle any ignored namespace.
                cls = _ignoreNamespaces(cls)

                # Remove public to maintain compatibility with old SIPs.
                if acc == "public":
                    clslst.append(cls)
                else:
                    clslst.append("%s %s" % (acc, cls))

            bstr = " : " + ", ".join(clslst)

        f.write(tname + self.name + bstr + self.sipAnnos() + "\n{\n")

        _writeDocstringSIP(f, self.docstring)

        f.write("%TypeHeaderCode\n", False)

        if self.typeheadercode:
            f.write(self.typeheadercode + "\n", False)
        else:
            f.write("#include <%s>\n" % hf.name, False)

        f.write("%End\n", False)

        f.blank()

        if self.typecode:
            _writeCodeSIP(f, "%TypeCode", self.typecode, False)

        if self.convtotypecode:
            _writeCodeSIP(f, "%ConvertToTypeCode", self.convtotypecode, False)

        if self.subclasscode:
            _writeCodeSIP(f, "%ConvertToSubClassCode", self.subclasscode)

        if self.gctraversecode:
            _writeCodeSIP(f, "%GCTraverseCode", self.gctraversecode)

        if self.gcclearcode:
            _writeCodeSIP(f, "%GCClearCode", self.gcclearcode)

        if self.bigetbufcode:
            _writeCodeSIP(f, "%BIGetBufferCode", self.bigetbufcode)

        if self.birelbufcode:
            _writeCodeSIP(f, "%BIReleaseBufferCode", self.birelbufcode)

        if self.bireadbufcode:
            _writeCodeSIP(f, "%BIGetReadBufferCode", self.bireadbufcode)

        if self.biwritebufcode:
            _writeCodeSIP(f, "%BIGetWriteBufferCode", self.biwritebufcode)

        if self.bisegcountcode:
            _writeCodeSIP(f, "%BIGetSegCountCode", self.bisegcountcode)

        if self.bicharbufcode:
            _writeCodeSIP(f, "%BIGetCharBufferCode", self.bicharbufcode)

        if self.picklecode:
            _writeCodeSIP(f, "%PickleCode", self.picklecode)

        f += 1

        if self.struct:
            access = ""
        else:
            access = "private"

        for c in self.content:
            if c.status != '':
                continue

            if isinstance(c, Access):
                if access != c.access:
                    f -= 1
                    access = c.access

                    if access != '':
                        astr = access
                    else:
                        astr = "public"

                    f.blank()
                    f.write(astr + ":\n")
                    f += 1

            # FIXME
            vrange = project.versionRange(c.sgen, c.egen)

            if vrange != '':
                f.write("%%If (%s)\n" % vrange, False)

            if c.platforms != '':
                f.write("%%If (%s)\n" % " || ".join(c.platforms.split()), False)

            if c.features != '':
                f.write("%%If (%s)\n" % " || ".join(c.features.split()), False)

            c.sip(f, hf, latest_sip)

            if c.features != '':
                f.write("%End\n", False)

            if c.platforms != '':
                f.write("%End\n", False)

            if vrange != '':
                f.write("%End\n", False)

        f -= 1
        f.write("};\n")

        f.blank()

    def xml(self, f):
        """
        Write the class to an XML file.

        f is the file.
        """
        f.write('<Class%s>\n' % self.xmlAttributes())

        _writeDocstringXML(f, self.docstring)

        if self.typeheadercode:
            _writeLiteralXML(f, "typeheadercode", self.typeheadercode)

        if self.typecode:
            _writeLiteralXML(f, "typecode", self.typecode)

        if self.convtotypecode:
            _writeLiteralXML(f, "convtotypecode", self.convtotypecode)

        if self.subclasscode:
            _writeLiteralXML(f, "subclasscode", self.subclasscode)

        if self.gctraversecode:
            _writeLiteralXML(f, "gctraversecode", self.gctraversecode)

        if self.gcclearcode:
            _writeLiteralXML(f, "gcclearcode", self.gcclearcode)

        if self.bigetbufcode:
            _writeLiteralXML(f, "bigetbufcode", self.bigetbufcode)

        if self.birelbufcode:
            _writeLiteralXML(f, "birelbufcode", self.birelbufcode)

        if self.bireadbufcode:
            _writeLiteralXML(f, "bireadbufcode", self.bireadbufcode)

        if self.biwritebufcode:
            _writeLiteralXML(f, "biwritebufcode", self.biwritebufcode)

        if self.bisegcountcode:
            _writeLiteralXML(f, "bisegcountcode", self.bisegcountcode)

        if self.bicharbufcode:
            _writeLiteralXML(f, "bicharbufcode", self.bicharbufcode)

        if self.picklecode:
            _writeLiteralXML(f, "picklecode", self.picklecode)

        f += 1
        super(Class, self).xml(f)
        f -= 1
        f.write('</Class>\n')

    def xmlAttributes(self):
        """
        Return the XML attributes as a string.
        """
        s = super(Class, self).xmlAttributes()

        s += self.xmlAccess()

        s += ' name="'

        if self.name != '':
            s += escape(self.name)

        s += '"'

        if self.bases != '':
            s += ' bases="%s"' % escape(self.bases)

        if self.pybases != '':
            s += ' pybases="%s"' % escape(self.pybases)

        if self.struct:
            s += ' struct="1"'

        return s


class Callable(Code):
    """
    This class represents a callable.
    """
    def __init__(self, name, container, rtype, pytype, pyargs, platforms, features, annos, status, sgen, egen):
        """
        Initialise the callable instance.

        name is the name of the callable.
        container is the container of the callable.
        rtype is the C/C++ return type (which will be None for constructors and
        operator casts).
        pytype is the Python return type (which will be None for constructors
        and operator casts).
        pyargs is the Python signature excluding any return type (which will be
        None for operator casts).
        platforms is the space separated list of platforms.
        features is the space separated list of features.
        annos is the string of annotations.
        status is the callable status.
        sgen is the start generation.
        egen is the end generation.
        """
        self.name = name
        self.container = container
        self.rtype = rtype
        self.pytype = pytype
        self.pyargs = pyargs
        self.args = []
        self.docstring = ""
        self.methcode = ""

        super().__init__(platforms, features, annos, status, sgen, egen)

    def literal(self, ltype, text):
        """
        Accept some literal text.

        ltype is the type of the text.
        text is the text.
        """
        if ltype == "docstring":
            self.docstring = text
        elif ltype == "methcode":
            self.methcode = text

    def signature(self):
        """
        Return a C/C++ representation for comparison purposes.
        """
        return _expandType(self.rtype) + self.name + "(" + ", ".join([a.signature() for a in self.args]) + ")"

    def user(self):
        """
        Return a user friendly representation of the callable.
        """
        # Note that we do include a separate C++ signature if it is different
        # to the Python signature.  This is so we always hint to the user that
        # something has been manually changed.

        s = self.returnType() + self.name

        if self.pyargs != '':
            s += self.pyargs
        else:
            s += "(" + ", ".join([a.sip(latest_sip=True, ignore_namespaces=False) for a in self.args]) + ")"

        s += self.sipAnnos()

        if self.pytype != '' or self.pyargs != '' or self.hasPyArgs():
            s += " [%s (%s)]" % (_expandType(self.rtype), ", ".join([a.user() for a in self.args]))

        return s

    def sip(self, f, hf, latest_sip):
        """
        Write the callable to a SIP file.

        f is the file.
        hf is the corresponding header file instance.
        """
        # Note that we don't include a separate C++ signature.  This is handled
        # where needed by sub-classes.

        f.write(self.returnType(ignore_namespaces=True) + self.name)

        if self.pyargs != '':
            f.write(self.pyargs)
        else:
            f.write("(" + ", ".join([a.sip(latest_sip) for a in self.args]) + ")")

        f.write(self.sipAnnos())

    def returnType(self, ignore_namespaces=False):
        """
        Return the return type as a string.
        """
        if self.pytype != '':
            s = self.pytype
        elif self.rtype != '':
            s = _expandType(self.rtype, ignore_namespaces=ignore_namespaces)
        else:
            return ""

        if s[-1] not in "&*":
            s += " "

        return s

    def sipDocstring(self, f):
        """
        Write any docstring to a SIP file.

        f is the file.
        """
        _writeDocstringSIP(f, self.docstring)

    def sipMethcode(self, f):
        """
        Write any method code to a SIP file.

        f is the file.
        """
        _writeMethCodeSIP(f, self.methcode)

    def xmlAttributes(self):
        """
        Return the XML attributes as a string.
        """
        s = super(Callable, self).xmlAttributes()
        s += ' name="%s"' % escape(self.name)

        if self.rtype != '':
            s += ' rtype="%s"' % escape(self.rtype)

        if self.pytype != '':
            s += ' pytype="%s"' % escape(self.pytype)

        if self.pyargs != '':
            s += ' pyargs="%s"' % escape(self.pyargs)

        return s

    def xmlDocstring(self, f):
        """
        Write any docstring to an XML file.

        f is the file.
        """
        _writeDocstringXML(f, self.docstring)

    def xmlMethcode(self, f):
        """
        Write any method code to an XML file.

        f is the file.
        """
        _writeMethCodeXML(f, self.methcode)

    def hasPyArgs(self):
        """
        Returns true if any of the arguments has a different Python type.
        """
        for a in self.args:
            if a.pytype != '':
                # We treat SIP_SIGNAL and SIP_SLOT as synonyms for const char *.
                if a.pytype not in ("SIP_SIGNAL", "SIP_SLOT") or a.type != "const char *":
                    return True

        return False


class EnumValue(ProjectElement):
    """ This class represents an enum value. """

    def __init__(self, name, annos='', status='unknown', sgen='', egen=''):
        """
        Initialise the enum value instance.

        name is the name of the enum value.
        annos is the string of annotations.
        status is the status.
        sgen is the start generation.
        egen is the end generation.
        """
        self.name = name

        super().__init__(annos, status, sgen, egen)

    def signature(self):
        """
        Return a C/C++ representation for comparison purposes.
        """
        return self.user()

    def user(self):
        """
        Return a user friendly representation of the enum value.
        """
        return self.name

    def sip(self, latest_sip):
        """
        Return the enum value suitable for writing to a SIP file.
        """
        return self.name + self.sipAnnos()

    def xml(self, f):
        """
        Write the enum value to an XML file.

        f is the file.
        """
        f.write('<EnumValue%s/>\n' % self.xmlAttributes())

    def xmlAttributes(self):
        """
        Return the XML attributes as a string.
        """
        s = super(EnumValue, self).xmlAttributes()

        s += ' name="%s"' % self.name

        return s


class Enum(Code, Access):
    """ This class represents an enum. """

    def __init__(self, name, access, platforms='', features='', annos='', status='unknown', sgen='', egen=''):
        """
        Initialise the enum instance.

        name is the name of the enum.
        access is the access.
        platforms is the space separated list of platforms.
        features is the space separated list of features.
        annos is the string of annotations.
        status is the enum status.
        sgen is the start generation.
        egen is the end generation.
        """
        self.name = name
        self.content = []

        Code.__init__(self, platforms, features, annos, status, sgen, egen)
        Access.__init__(self, access)

    def signature(self):
        """
        Return a C/C++ representation for comparison purposes.
        """
        return super(Enum, self).signature() + self.sigAccess()

    def user(self):
        """
        Return a user friendly representation of the enum.
        """
        s = "enum"

        if self.name != '':
            s += " " + self.name

        return s

    def sip(self, f, hf, latest_sip):
        """
        Write the enum to a SIP file.

        f is the file.
        hf is the corresponding header file instance.
        """
        f.blank()

        f.write("enum")

        if self.name != '':
            f.write(" " + self.name)

        f.write(self.sipAnnos() + "\n{\n")
        f += 1

        for e in self.content:
            if e.status != '':
                continue

            # FIXME
            vrange = project.versionRange(e.sgen, e.egen)

            if vrange != '':
                f.write("%%If (%s)\n" % vrange, False)

            f.write(e.sip(latest_sip) + ",\n")

            if vrange != '':
                f.write("%End\n", False)

        f -= 1
        f.write("};\n")
        f.blank()

    def xml(self, f):
        """
        Write the enum to an XML file.

        f is the file.
        """
        f.write('<Enum%s>\n' % self.xmlAttributes())
        f += 1

        for e in self.content:
            e.xml(f)

        f -= 1
        f.write('</Enum>\n')

    def xmlAttributes(self):
        """
        Return the XML attributes as a string.
        """
        s = super(Enum, self).xmlAttributes()

        s += self.xmlAccess()

        s += ' name="%s"' % self.name

        return s


class ClassCallable(Callable, Access):
    """ This class represents a callable in a class context. """

    def __init__(self, name, container, access, rtype, pytype, pyargs, platforms, features, annos, status, sgen, egen):
        """
        Initialise the callable instance.

        name is the name of the callable.
        container is the container of the callable.
        access is the access.
        rtype is the C/C++ return type (which will be None for constructors and
        operator casts).
        pytype is the Python return type (which will be None for constructors
        and operator casts).
        pyargs is the Python signature excluding any return type (which will be
        None for operator casts).
        platforms is the space separated list of platforms.
        features is the space separated list of features.
        annos is the string of annotations.
        status is the callable status.
        sgen is the start generation.
        egen is the end generation.
        """

        Callable.__init__(self, name, container, rtype, pytype, pyargs, platforms, features, annos, status, sgen, egen)
        Access.__init__(self, access)

    def signature(self):
        """ Return a C/C++ representation for comparison purposes. """

        return super(ClassCallable, self).signature() + self.sigAccess()

    def xmlAttributes(self):
        """
        Return the XML attributes as a string.
        """
        return super(ClassCallable, self).xmlAttributes() + self.xmlAccess()


class Constructor(ClassCallable):
    """
    This class represents a constructor.
    """
    def __init__(self, name, container, access, explicit, pyargs='', platforms='', features='', annos='', status='unknown', sgen='', egen=''):
        """
        Initialise the constructor instance.

        name is the name of the constructor.
        container is the container of the constructor.
        access is the access.
        explicit is set if the ctor is explicit.
        pyargs is the Python signature.
        platforms is the space separated list of platforms.
        features is the space separated list of features.
        annos is the string of annotations.
        status is the constructor status.
        sgen is the start generation.
        egen is the end generation.
        """
        self.explicit = explicit

        super().__init__(name, container, access, '', '', pyargs, platforms, features, annos, status, sgen, egen)

    def signature(self):
        """
        Return a C/C++ representation for comparison purposes.
        """
        s = super(Constructor, self).signature()

        if self.explicit:
            s = "explicit " + s

        return s

    def user(self):
        """
        Return a user friendly representation of the constructor.
        """
        s = super(Constructor, self).user()

        if self.explicit:
            s = "explicit " + s

        return s

    def sip(self, f, hf, latest_sip):
        """
        Write the constructor to a SIP file.

        f is the file.
        hf is the corresponding header file instance.
        """
        if self.explicit:
            f.write("explicit ")

        super(Constructor, self).sip(f, hf, latest_sip)

        if self.pyargs != '' or self.hasPyArgs():
            f.write(" [(%s)]" % ", ".join([a.user() for a in self.args]))

        f.write(";\n")

        self.sipDocstring(f)
        self.sipMethcode(f)

    def xml(self, f):
        """
        Write the constructor to an XML file.

        f is the file.
        """
        f.write('<Constructor%s>\n' % self.xmlAttributes())

        f += 1

        for a in self.args:
            a.xml(f)

        f -= 1

        self.xmlDocstring(f)
        self.xmlMethcode(f)
        f.write('</Constructor>\n')

    def xmlAttributes(self):
        """
        Return the XML attributes as a string.
        """
        s = super(Constructor, self).xmlAttributes()

        if self.explicit:
            s += ' explicit="1"'

        return s


class Destructor(Code, Access):
    """
    This class represents a destructor.
    """
    def __init__(self, name, container, access, virtual, platforms='', features='', annos='', status='unknown', sgen='', egen=''):
        """
        Initialise the destructor instance.

        name is the name of the destructor.
        container is the container of the destructor.
        access is the access.
        virtual is set if the destructor is virtual.
        platforms is the space separated list of platforms.
        features is the space separated list of features.
        annos is the string of annotations.
        status is the destructor status.
        sgen is the start generation.
        egen is the end generation.
        """
        self.name = name
        self.container = container
        self.virtual = virtual
        self.methcode = ""
        self.virtcode = ""

        Code.__init__(self, platforms, features, annos, status, sgen, egen)
        Access.__init__(self, access)

    def literal(self, ltype, text):
        """
        Accept some literal text.

        ltype is the type of the text.
        text is the text.
        """
        if ltype == "methcode":
            self.methcode = text
        elif ltype == "virtcode":
            self.virtcode = text

    def signature(self):
        """
        Return a C/C++ representation for comparison purposes.
        """
        s = self.name + self.sigAccess()

        if self.virtual:
            s = "virtual " + s

        return s

    def user(self):
        """
        Return a user friendly representation of the destructor.
        """
        s = "~" + self.name + "()"

        if self.virtual:
            s = "virtual " + s

        return s

    def sip(self, f, hf, latest_sip):
        """
        Write the destructor to a SIP file.

        f is the file.
        hf is the corresponding header file instance.
        """
        if self.virtual:
            f.write("virtual ")

        f.write("~" + self.name + "()" + self.sipAnnos() + ";\n")

        _writeMethCodeSIP(f, self.methcode)
        _writeVirtCodeSIP(f, self.virtcode)

    def xml(self, f):
        """
        Write the destructor to an XML file.

        f is the file.
        """
        f.write('<Destructor%s>\n' % self.xmlAttributes())

        _writeMethCodeXML(f, self.methcode)
        _writeVirtCodeXML(f, self.virtcode)

        f.write('</Destructor>\n')

    def xmlAttributes(self):
        """
        Return the XML attributes as a string.
        """
        s = super(Destructor, self).xmlAttributes() + self.xmlAccess()

        s += ' name="%s"' % escape(self.name)

        if self.virtual:
            s += ' virtual="1"'

        return s


class OperatorCast(ClassCallable):
    """
    This class represents an operator cast.
    """
    def __init__(self, name, container, access, const, platforms='', features='', annos='', status='unknown', sgen='', egen=''):
        """
        Initialise the operator cast instance.

        name is the name of the operator cast (ie. the type being cast to).
        container is the container of the operator cast.
        access is the access.
        const is set if the method is const.
        platforms is the space separated list of platforms.
        features is the space separated list of features.
        annos is the string of annotations.
        status is the constructor status.
        sgen is the start generation.
        egen is the end generation.
        """
        self.const = const

        super().__init__(name, container, access, '', '', '', platforms, features, annos, status, sgen, egen)

    def signature(self):
        """
        Return a C/C++ representation for comparison purposes.
        """
        s = "operator " + super(OperatorCast, self).signature()

        if self.const:
            s += " const"

        return s

    def user(self):
        """
        Return a user friendly representation of the operator cast.
        """
        s = "operator " + super(OperatorCast, self).user()

        if self.const:
            s += " const"

        return s

    def sip(self, f, hf, latest_sip):
        """
        Write the operator cast to a SIP file.

        f is the file.
        hf is the corresponding header file instance.
        """
        f.write("operator ")

        super(OperatorCast, self).sip(f, hf, latest_sip)

        if self.const:
            f.write(" const")

        f.write(";\n")

        self.sipMethcode(f)

    def xml(self, f):
        """
        Write the operator cast to an XML file.

        f is the file.
        """
        f.write('<OperatorCast%s>\n' % self.xmlAttributes())

        f += 1

        for a in self.args:
            a.xml(f)

        f -= 1

        self.xmlMethcode(f)
        f.write('</OperatorCast>\n')

    def xmlAttributes(self):
        """
        Return the XML attributes as a string.
        """
        s = super(OperatorCast, self).xmlAttributes()

        if self.const:
            s += ' const="1"'

        return s


class Method(ClassCallable):
    """
    This class represents a method.
    """
    def __init__(self, name, container, access, rtype, virtual, const, static, abstract, pytype='', pyargs='', platforms='', features='', annos='', status='unknown', sgen='', egen=''):
        """
        Initialise the method instance.

        name is the name of the method.
        container is the container of the method.
        access is the access.
        rtype is the C/C++ return type.
        virtual is set if the method is virtual.
        const is set if the method is const.
        static is set if the method is static.
        abstract is set if the method is pure virtual.
        pytype is the Python return type.
        pyargs is the Python signature excluding the return type.
        platforms is the space separated list of platforms.
        features is the space separated list of features.
        annos is the string of annotations.
        status is the method status.
        sgen is the start generation.
        egen is the end generation.
        """
        self.virtual = virtual
        self.const = const
        self.static = static
        self.abstract = abstract
        self.virtcode = ""

        super().__init__(name, container, access, rtype, pytype, pyargs, platforms, features, annos, status, sgen, egen)

    def literal(self, ltype, text):
        """
        Accept some literal text.

        ltype is the type of the text.
        text is the text.
        """
        if ltype == "virtcode":
            self.virtcode = text
        else:
            super(Method, self).literal(ltype, text)

    def signature(self):
        """
        Return a C/C++ representation for comparison purposes.
        """
        s = ""

        if self.virtual:
            s += "virtual "

        if self.static:
            s += "static "

        s += _expandType(self.rtype) + self.name + "(" + ", ".join([a.signature() for a in self.args]) + ")"

        if self.const:
            s += " const"

        if self.abstract:
            s += " = 0"

        s += self.sigAccess()

        return s

    def user(self):
        """
        Return a user friendly representation of the method.
        """
        # We can't use the super class version because we might need to stick
        # some text in the middle of it.
        s = ""

        if self.virtual:
            s += "virtual "

        if self.static:
            s += "static "

        s += self.returnType() + self.name

        if self.pyargs:
            s += self.pyargs
        else:
            s += "(" + ", ".join([a.sip(latest_sip=True, ignore_namespaces=False) for a in self.args]) + ")"

        if self.const:
            s += " const"

        if self.abstract:
            s += " = 0"

        s += self.sipAnnos()

        if self.pytype or self.pyargs or self.hasPyArgs():
            s += " [%s (%s)]" % (_expandType(self.rtype), ", ".join([a.user() for a in self.args]))

        return s

    def sip(self, f, hf, latest_sip):
        """
        Write the method to a SIP file.

        f is the file.
        hf is the corresponding header file instance.
        """
        # We can't use the super class version because we might need to stick
        # some text in the middle of it.
        s = ""

        if self.virtual:
            s += "virtual "

        if self.static:
            s += "static "

        s += self.returnType(ignore_namespaces=True) + self.name

        if self.pyargs:
            s += self.pyargs
        else:
            s += "(" + ", ".join([a.sip(latest_sip) for a in self.args]) + ")"

        if self.const:
            s += " const"

        if self.abstract:
            s += " = 0"

        s += self.sipAnnos()

        if (self.virtual or self.access.startswith("protected") or not self.methcode) and (self.pytype or self.pyargs or self.hasPyArgs()):
            s += " [%s (%s)]" % (_expandType(self.rtype, ignore_namespaces=True), ", ".join([a.user() for a in self.args]))

        f.write(s + ";\n")

        self.sipDocstring(f)
        self.sipMethcode(f)
        _writeVirtCodeSIP(f, self.virtcode)

    def xml(self, f):
        """
        Write the method to an XML file.

        f is the file.
        """
        f.write('<Method%s>\n' % self.xmlAttributes())

        f += 1

        for a in self.args:
            a.xml(f)

        f -= 1

        self.xmlDocstring(f)
        self.xmlMethcode(f)
        _writeVirtCodeXML(f, self.virtcode)

        f.write('</Method>\n')

    def xmlAttributes(self):
        """
        Return the XML attributes as a string.
        """
        s = super(Method, self).xmlAttributes()

        if self.virtual:
            s += ' virtual="1"'

        if self.const:
            s += ' const="1"'

        if self.static:
            s += ' static="1"'

        if self.abstract:
            s += ' abstract="1"'

        return s


class OperatorMethod(ClassCallable):
    """
    This class represents a scoped operator.
    """
    def __init__(self, name, container, access, rtype, virtual, const, abstract, pytype='', pyargs='', platforms='', features='', annos='', status='unknown', sgen='', egen=''):
        """
        Initialise the operator instance.

        name is the name of the operator.
        container is the container of the operator.
        access is the access.
        rtype is the C/C++ return type.
        virtual is set if the operator is virtual.
        const is set if the operator is const.
        abstract is set if the operator is pure virtual.
        pytype is the Python return type.
        pyargs is the Python signature excluding the return type.
        platforms is the space separated list of platforms.
        features is the space separated list of features.
        annos is the string of annotations.
        status is the operator status.
        sgen is the start generation.
        egen is the end generation.
        """
        self.virtual = virtual
        self.const = const
        self.abstract = abstract
        self.virtcode = ""

        super().__init__(name, container, access, rtype, pytype, pyargs, platforms, features, annos, status, sgen, egen)

    def literal(self, ltype, text):
        """
        Accept some literal text.

        ltype is the type of the text.
        text is the text.
        """
        if ltype == "virtcode":
            self.virtcode = text
        else:
            super(OperatorMethod, self).literal(ltype, text)

    def signature(self):
        """
        Return a C/C++ representation for comparison purposes.
        """
        s = ""

        if self.virtual:
            s += "virtual "

        s += _expandType(self.rtype) + "operator" + self.name + "(" + ", ".join([a.signature() for a in self.args]) + ")"

        if self.const:
            s += " const"

        if self.abstract:
            s += " = 0"

        s += self.sigAccess()

        return s

    def user(self):
        """
        Return a user friendly representation of the operator.
        """
        s = ""

        if self.virtual:
            s += "virtual "

        s += self.returnType() + "operator" + self.name

        if self.pyargs != '':
            s += self.pyargs
        else:
            s += "(" + ", ".join([a.sip(latest_sip=True, ignore_namespaces=False) for a in self.args]) + ")"

        if self.const:
            s += " const"

        if self.abstract:
            s += " = 0"

        s += self.sipAnnos()

        if self.pytype != '' or self.pyargs != '' or self.hasPyArgs():
            s += " [%s (%s)]" % (_expandType(self.rtype), ", ".join([a.user() for a in self.args]))

        return s

    def sip(self, f, hf, latest_sip):
        """
        Write the operator to a SIP file.

        f is the file.
        hf is the corresponding header file instance.
        """
        s = ""

        if self.virtual:
            s += "virtual "

        s += self.returnType(ignore_namespaces=True) + "operator" + self.name

        if self.pyargs != '':
            s += self.pyargs
        else:
            s += "(" + ", ".join([a.sip(latest_sip) for a in self.args]) + ")"

        if self.const:
            s += " const"

        if self.abstract:
            s += " = 0"

        s += self.sipAnnos()

        if (self.virtual or self.access.startswith("protected") or not self.methcode) and (self.pytype or self.pyargs or self.hasPyArgs()):
            s += " [%s (%s)]" % (_expandType(self.rtype, ignore_namespaces=True), ", ".join([a.user() for a in self.args]))

        f.write(s + ";\n")

        self.sipMethcode(f)
        _writeVirtCodeSIP(f, self.virtcode)

    def xml(self, f):
        """
        Write the operator to an XML file.

        f is the file.
        """
        f.write('<OperatorMethod%s>\n' % self.xmlAttributes())

        f += 1

        for a in self.args:
            a.xml(f)

        f -= 1

        self.xmlMethcode(f)
        _writeVirtCodeXML(f, self.virtcode)

        f.write('</OperatorMethod>\n')

    def xmlAttributes(self):
        """
        Return the XML attributes as a string.
        """
        s = super(OperatorMethod, self).xmlAttributes()

        if self.virtual:
            s += ' virtual="1"'

        if self.const:
            s += ' const="1"'

        if self.abstract:
            s += ' abstract="1"'

        return s


class Function(Callable):
    """
    This class represents a function.
    """
    def __init__(self, name, container, rtype, pytype='', pyargs='', platforms='', features='', annos='', status='unknown', sgen='', egen=''):
        """
        Initialise the function instance.

        name is the name of the function.
        container is the container of the function.
        rtype is the C/C++ return type.
        pytype is the Python return type.
        pyargs is the Python signature excluding the return type.
        platforms is the space separated list of platforms.
        features is the space separated list of features.
        annos is the string of annotations.
        status is the function status.
        sgen is the start generation.
        egen is the end generation.
        """
        Callable.__init__(self, name, container, rtype, pytype, pyargs, platforms, features, annos, status, sgen, egen)

    def sip(self, f, hf, latest_sip):
        """
        Write the destructor to a SIP file.

        f is the file.
        hf is the corresponding header file instance.
        """
        super(Function, self).sip(f, hf, latest_sip)
        f.write(";\n")
        self.sipDocstring(f)
        self.sipMethcode(f)

    def xml(self, f):
        """
        Write the function to an XML file.

        f is the file.
        """
        f.write('<Function%s>\n' % self.xmlAttributes())

        f += 1

        for a in self.args:
            a.xml(f)

        f -= 1

        self.xmlDocstring(f)
        self.xmlMethcode(f)
        f.write('</Function>\n')


class OperatorFunction(Callable):
    """
    This class represents a global operator.
    """
    def __init__(self, name, container, rtype, pytype='', pyargs='', platforms='', features='', annos='', status='unknown', sgen='', egen=''):
        """
        Initialise the operaror instance.

        name is the name of the operator.
        container is the container of the operator.
        rtype is the C/C++ return type.
        pytype is the Python return type.
        pyargs is the Python signature excluding the return type.
        platforms is the space separated list of platforms.
        features is the space separated list of features.
        annos is the string of annotations.
        status is the operator status.
        sgen is the start generation.
        egen is the end generation.
        """
        Callable.__init__(self, name, container, rtype, pytype, pyargs, platforms, features, annos, status, sgen, egen)

    def signature(self):
        """
        Return a C/C++ representation for comparison purposes.
        """
        return _expandType(self.rtype) + "operator" + self.name + "(" + ", ".join([a.signature() for a in self.args]) + ")"

    def user(self):
        """
        Return a user friendly representation of the operator.
        """
        s = self.returnType() + "operator" + self.name

        if self.pyargs != '':
            s += self.pyargs
        else:
            s += "(" + ", ".join([a.sip(latest_sip=True, ignore_namespaces=False) for a in self.args]) + ")"

        s += self.sipAnnos()

        if self.pytype != '' or self.pyargs != '' or self.hasPyArgs():
            s += " [%s (%s)]" % (_expandType(self.rtype), ", ".join([a.user() for a in self.args]))

        return s

    def sip(self, f, hf, latest_sip):
        """
        Write the operator to a SIP file.

        f is the file.
        hf is the corresponding header file instance.
        """
        f.write(self.returnType(ignore_namespaces=True) + "operator" + self.name)

        if self.pyargs != '':
            f.write(self.pyargs)
        else:
            f.write("(" + ", ".join([a.sip(latest_sip) for a in self.args]) + ")")

        f.write(self.sipAnnos())

        f.write(";\n")

        self.sipMethcode(f)

    def xml(self, f):
        """
        Write the operator to an XML file.

        f is the file.
        """
        f.write('<OperatorFunction%s>\n' % self.xmlAttributes())

        f += 1

        for a in self.args:
            a.xml(f)

        f -= 1

        self.xmlMethcode(f)
        f.write('</OperatorFunction>\n')


class Variable(Code, Access):
    """
    This class represents a variable.
    """
    def __init__(self, name, type, static, access, platforms='', features='', annos='', status='unknown', sgen='', egen=''):
        """
        Initialise the variable instance.

        name is the name of the variable.
        type is the type of the variable.
        static is set if the variable is static.
        access is the access.
        platforms is the space separated list of platforms.
        features is the space separated list of features.
        annos is the string of annotations.
        status is the variable status.
        sgen is the start generation.
        egen is the end generation.
        """
        self.name = name
        self.type = type
        self.static = static
        self.accesscode = ""
        self.getcode = ""
        self.setcode = ""

        Code.__init__(self, platforms, features, annos, status, sgen, egen)
        Access.__init__(self, access)

    def literal(self, ltype, text):
        """
        Accept some literal text.

        ltype is the type of the text.
        text is the text.
        """
        if ltype == "accesscode":
            self.accesscode = text
        elif ltype == "getcode":
            self.getcode = text
        elif ltype == "setcode":
            self.setcode = text

    def signature(self):
        """
        Return a C/C++ representation for comparison purposes.
        """
        return super(Variable, self).signature() + self.sigAccess()

    def user(self):
        """
        Return a user friendly representation of the variable.
        """
        s = _expandType(self.type, self.name) + self.sipAnnos()

        if self.static:
            s = "static " + s

        return s

    def sip(self, f, hf, latest_sip):
        """
        Write the variable to a SIP file.

        f is the file.
        hf is the corresponding header file instance.
        """
        s = _expandType(self.type, self.name, ignore_namespaces=True)

        if self.static:
            s = "static " + s

        f.write(s + self.sipAnnos())

        if latest_sip:
            need_brace = True
        else:
            need_brace = False
            f.write(";\n", indent=False)

        if self.accesscode:
            if need_brace:
                f.write(" {\n", indent=False)
                need_brace = False

            _writeCodeSIP(f, "%AccessCode", self.accesscode)

        if self.getcode:
            if need_brace:
                f.write(" {\n", indent=False)
                need_brace = False

            _writeCodeSIP(f, "%GetCode", self.getcode)

        if self.setcode:
            if need_brace:
                f.write(" {\n", indent=False)
                need_brace = False

            _writeCodeSIP(f, "%SetCode", self.setcode)

        if latest_sip:
            if not need_brace:
                f.write("}")

            f.write(";\n", indent=False)

    def xml(self, f):
        """
        Write the variable to an XML file.

        f is the file.
        """
        if self.accesscode or self.getcode or self.setcode:
            f.write('<Variable%s>\n' % self.xmlAttributes())

            if self.accesscode:
                _writeLiteralXML(f, "accesscode", self.accesscode)

            if self.getcode:
                _writeLiteralXML(f, "getcode", self.getcode)

            if self.setcode:
                _writeLiteralXML(f, "setcode", self.setcode)

            f.write('</Variable>\n')
        else:
            f.write('<Variable%s/>\n' % self.xmlAttributes())

    def xmlAttributes(self):
        """
        Return the XML attributes as a string.
        """
        s = super(Variable, self).xmlAttributes() + self.xmlAccess()

        s += ' name="%s"' % escape(self.name)
        s += ' type="%s"' % escape(self.type)

        if self.static:
            s += ' static="1"'

        return s


class Typedef(Code):
    """
    This class represents a typedef.
    """
    def __init__(self, name, type, platforms='', features='', annos='', status='unknown', sgen='', egen=''):
        """
        Initialise the typedef instance.

        name is the name of the typedef.
        type is the type of the typedef.
        platforms is the space separated list of platforms.
        features is the space separated list of features.
        annos is the string of annotations.
        status is the typedef status.
        sgen is the start generation.
        egen is the end generation.
        """
        self.name = name
        self.type = type

        Code.__init__(self, platforms, features, annos, status, sgen, egen)

    def user(self):
        """
        Return a user friendly representation of the typedef.
        """
        return "typedef " + _expandType(self.type, self.name) + self.sipAnnos()

    def sip(self, f, hf, latest_sip):
        """
        Write the code to a SIP file.

        f is the file.
        hf is the corresponding header file instance.
        """
        f.write("typedef " + _expandType(self.type, self.name, ignore_namespaces=True) + self.sipAnnos() + ";\n")

    def xml(self, f):
        """
        Write the typedef to an XML file.

        f is the file.
        """
        f.write('<Typedef%s/>\n' % self.xmlAttributes())

    def xmlAttributes(self):
        """
        Return the XML attributes as a string.
        """
        s = super(Typedef, self).xmlAttributes()

        s += ' name="%s"' % escape(self.name)
        s += ' type="%s"' % escape(self.type)

        return s


class Namespace(Code):
    """
    This class represents a namespace.
    """
    def __init__(self, name, container, platforms='', features='', status='unknown', sgen='', egen=''):
        """
        Initialise the namespace instance.

        name is the name of the namespace.
        container is the container of the namespace.
        platforms is the space separated list of platforms.
        features is the space separated list of features.
        status is the namespace status.
        sgen is the start generation.
        egen is the end generation.
        """
        self.name = name
        self.container = container
        self.typeheadercode = ""
        self.content = []

        super().__init__(platforms, features, None, status, sgen, egen)

    def literal(self, ltype, text):
        """
        Accept some literal text.

        ltype is the type of the text.
        text is the text.
        """
        if ltype == "typeheadercode":
            self.typeheadercode = text

    def user(self):
        """
        Return a user friendly representation of the namespace.
        """
        return "namespace " + self.name

    def sip(self, f, hf, latest_sip):
        """
        Write the code to a SIP file.

        f is the file.
        hf is the corresponding header file instance.
        """
        if self.status:
            return 

        # FIXME
        if self.name in project.ignorednamespaces.split():
            super(Namespace, self).sip(f, hf, latest_sip)
            return

        f.blank()

        f.write("namespace " + self.name + "\n{\n")

        f.write("%TypeHeaderCode\n", False)

        if self.typeheadercode:
            f.write(self.typeheadercode + "\n", False)
        else:
            f.write("#include <%s>\n" % hf.name, False)

        f.write("%End\n", False)

        f.blank()

        f += 1
        super(Namespace, self).sip(f, hf, latest_sip)
        f -= 1

        f.write("};\n")

        f.blank()

    def xml(self, f):
        """
        Write the namespace to an XML file.

        f is the file.
        """
        f.write('<Namespace%s>\n' % self.xmlAttributes())

        if self.typeheadercode:
            _writeLiteralXML(f, "typeheadercode", self.typeheadercode)

        f += 1
        super(Namespace, self).xml(f)
        f -= 1
        f.write('</Namespace>\n')

    def xmlAttributes(self):
        """
        Return the XML attributes as a string.
        """
        s = super(Namespace, self).xmlAttributes()

        s += ' name="%s"' % escape(self.name)

        return s


class OpaqueClass(Code, Access):
    """
    This class represents an opaque class.
    """
    def __init__(self, name, container, access, platforms='', features='', annos='', status='unknown', sgen='', egen=''):
        """
        Initialise the opaque class instance.

        name is the name of the opaque class.
        container is the container of the opaque class.
        access is the access.
        platforms is the space separated list of platforms.
        features is the space separated list of features.
        annos is the string of annotations.
        status is the opaque class status.
        sgen is the start generation.
        egen is the end generation.
        """
        self.name = name
        self.container = container

        Code.__init__(self, platforms, features, annos, status, sgen, egen)
        Access.__init__(self, access)

    def signature(self):
        """
        Return a C/C++ representation for comparison purposes.
        """
        return super(OpaqueClass, self).signature() + self.sigAccess()

    def user(self):
        """
        Return a user friendly representation of the opaque class.
        """
        return "class " + self.name + self.sipAnnos()

    def sip(self, f, hf, latest_sip):
        """
        Write the code to a SIP file.

        f is the file.
        hf is the corresponding header file instance.
        """
        f.write("class " + self.name + self.sipAnnos() + ";\n")

    def xml(self, f):
        """
        Write the opaque class to an XML file.

        f is the file.
        """
        f.write('<OpaqueClass%s/>\n' % self.xmlAttributes())

    def xmlAttributes(self):
        """
        Return the XML attributes as a string.
        """
        s = super(OpaqueClass, self).xmlAttributes() + self.xmlAccess()

        s += ' name="%s"' % escape(self.name)

        return s


class ManualCode(Code, Access):
    """
    This class represents some manual code.
    """
    def __init__(self, precis, access='', platforms='', features='', status='unknown', sgen='', egen=''):
        """
        Initialise the manual code instance.

        precis is the name of the manual code (or the code itself if it is one
        line).
        access is the access specifier.
        platforms is the space separated list of platforms.
        features is the space separated list of features.
        status is the opaque class status.
        sgen is the start generation.
        egen is the end generation.
        """
        self.precis = precis
        self.body = ""
        self.docstring = ""
        self.methcode = ""

        Code.__init__(self, platforms, features, '', status, sgen, egen)
        Access.__init__(self, access)

    def literal(self, ltype, text):
        """
        Accept some literal text.

        ltype is the type of the text.
        text is the text.
        """
        if ltype == "body":
            self.body = text
        elif ltype == "docstring":
            self.docstring = text
        elif ltype == "methcode":
            self.methcode = text

    def signature(self):
        """
        Return a C/C++ representation for comparison purposes.
        """
        return super(ManualCode, self).signature() + self.sigAccess()

    def user(self):
        """
        Return a user friendly representation of the manual code.
        """
        return self.precis

    def sip(self, f, hf, latest_sip):
        """
        Write the code to a SIP file.

        f is the file.
        hf is the corresponding header file instance.
        """
        if self.body:
            f.write("// " + self.precis + "\n" + self.body + "\n", False)
        elif self.precis.startswith('%'):
            f.write(self.precis + "\n", False)
        else:
            f.write(self.precis + ";\n")

        _writeDocstringSIP(f, self.docstring)
        _writeMethCodeSIP(f, self.methcode)

    def xml(self, f):
        """
        Write the manual code to an XML file.

        f is the file.
        """
        f.write('<ManualCode%s>\n' % self.xmlAttributes())

        if self.body:
            _writeLiteralXML(f, "body", self.body)

        _writeDocstringXML(f, self.docstring)
        _writeMethCodeXML(f, self.methcode)

        f.write('</ManualCode>\n')

    def xmlAttributes(self):
        """
        Return the XML attributes as a string.
        """
        s = super(ManualCode, self).xmlAttributes() + self.xmlAccess()

        s += ' precis="%s"' % escape(self.precis)

        return s


class _IndentFile:
    """
    This is a thin wrapper around a file object that supports indentation.
    """
    def __init__(self, fname, indent):
        """
        Create a file for writing.

        fname is the name of the file.
        indent is the default indentation step.
        """
        self._f = open(fname, "w")
        self._indent = indent
        self._nrindents = 0
        self._indentnext = True
        self._blank = False
        self._suppressblank = False

        self.name = fname

    def write(self, data, indent=True):
        """
        Write some data to the file with optional automatic indentation.

        data is the data to write.
        indent is True if the data should be indented.
        """
        if data:
            if self._blank:
                self._f.write("\n")
                self._blank = False

            lines = data.split("\n")

            for l in lines[:-1]:
                if indent and self._indentnext:
                    self._f.write(" " * (self._indent * self._nrindents))

                self._f.write(l + "\n")
                self._indentnext = True

            # Handle the last line.
            l = lines[-1]

            if l:
                if indent and self._indentnext:
                    self._f.write(" " * (self._indent * self._nrindents))

                self._f.write(l)
                self._indentnext = False
            else:
                self._indentnext = True

            self._suppressblank = False

    def blank(self):
        """
        Write a blank line.
        """
        if not self._suppressblank:
            self._blank = True

    def close(self):
        """
        Close the file.
        """
        self._f.close()

    def __iadd__(self, n):
        """
        Increase the indentation.

        n is the increase in the number of levels of indentation.
        """
        self._nrindents += n
        self._suppressblank = True

        return self

    def __isub__(self, n):
        """
        Decrease the indentation.

        n is the decrease in the number of levels of indentation.
        """
        self._nrindents -= n
        self._blank = False
        self._suppressblank = False

        return self


def _createIndentFile(prj, fname, indent=2):
    """
    Return an indent file or None if there was an error.

    prj is the project instance.
    fname is the name of the file.
    indent is the default indentation step.
    """
    try:
        f = _IndentFile(fname, indent)
    except IOError as detail:
        prj.diagnostic = "Unable to create file %s: %s" % (fname, detail)
        return None

    return f


def _ignoreNamespaces(typ):
    """
    Return the name of a type with any namespaces to be ignored removed.

    typ is the type.
    """
    # FIXME
    for ins in project.ignorednamespaces.split():
        ns_name = ins + "::"

        if typ.startswith(ns_name):
            typ = typ[len(ns_name):]
            break

    # Handle any template arguments.
    t_start = typ.find('<')
    t_end = typ.rfind('>')

    if t_start > 0 and t_end > t_start:
        xt = []

        # Note that this doesn't handle nested template arguments properly.
        for t_arg in typ[t_start + 1:t_end].split(','):
            xt.append(_ignoreNamespaces(t_arg.strip()))

        typ = typ[:t_start + 1] + ', '.join(xt) + typ[t_end:]

    return typ


def _expandType(typ, name="", ignore_namespaces=False):
    """
    Return the full type for a name.

    typ is the type.
    name is the optional name.
    ignore_namespaces is True if any ignored namespaces should be ignored.
    """
    # Handle the trivial case.
    if not typ:
        return ""

    if ignore_namespaces:
        const = 'const '
        if typ.startswith(const):
            typ = typ[len(const):]
        else:
            const = ''

        typ = const + _ignoreNamespaces(typ)

    # SIP can't handle every C++ fundamental type.
    typ = typ.replace("long int", "long")

    # If there is no embedded %s then just append the name.
    if "%s" in typ:
        s = typ % name
    else:
        s = typ

        if name:
            if typ[-1] not in "&*":
                s += " "
            
            s += name

    return s


def _writeLiteralXML(f, type, text):
    """
    Write some literal text to an XML file.

    f is the file.
    type is the type of the text.
    text is the text.
    """
    f.write('<Literal type="%s">\n%s\n</Literal>\n' % (type, escape(text)), False)


def _writeCodeSIP(f, directive, code, indent=True):
    """
    Write some code to a SIP file.

    f is the file.
    directive is the SIP directive.
    code is the code.
    indent is True if the code should be indented.
    """
    f.write(directive + "\n", False)
    f += 1
    f.write(code + "\n", indent)
    f -= 1
    f.write("%End\n", False)
    f.blank()


def _writeDocstringSIP(f, docstring):
    """
    Write an optional docstring to a SIP file.

    f is the file.
    docstring is the docstring.
    """
    if docstring:
        _writeCodeSIP(f, "%Docstring", docstring, indent=False)


def _writeDocstringXML(f, docstring):
    """
    Write an optional docstring to an XML file.

    f is the file.
    docstring is the docstring.
    """
    if docstring:
        _writeLiteralXML(f, "docstring", docstring)


def _writeMethCodeSIP(f, code):
    """
    Write some optional method code to a SIP file.

    f is the file.
    code is the code.
    """
    if code:
        _writeCodeSIP(f, "%MethodCode", code)


def _writeMethCodeXML(f, code):
    """
    Write some optional method code to an XML file.

    f is the file.
    code is the code.
    """
    if code:
        _writeLiteralXML(f, "methcode", code)


def _writeVirtCodeSIP(f, code):
    """
    Write some optional virtual catcher code to a SIP file.

    f is the file.
    code is the code.
    """
    if code:
        _writeCodeSIP(f, "%VirtualCatcherCode", code)


def _writeVirtCodeXML(f, code):
    """
    Write some optional virtual catcher code to an XML file.

    f is the file.
    code is the code.
    """
    if code:
        _writeLiteralXML(f, "virtcode", code)


def escape(s):
    """
    Return an XML escaped string.
    """
    return saxutils.escape(s, {'"': '&quot;'})
