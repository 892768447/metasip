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


import glob
import hashlib
import os

from PyQt4.QtGui import QInputDialog

from dip.model import Instance, List, observe
from dip.shell import IDirty
from dip.ui import (Application, Controller, IGroupBox, IOptionSelector, IView,
        IViewStack)

from ...interfaces.project import (ICodeContainer, IHeaderDirectory,
        IHeaderFile, IProject)
from ...logger import Logger
from ...Project import (HeaderDirectory, HeaderFile, HeaderFileVersion,
        Project, SipFile)

from .scanner_view import ScannerView


class ScannerController(Controller):
    """ The ScannerController implements the controller for the scanner tool
    GUI.
    """

    # The current header directory.
    current_header_directory = Instance(IHeaderDirectory)

    # The current header files.
    current_header_files = List(IHeaderFile)

    # The current project.
    current_project = Instance(IProject)

    # The current project specific user interface.
    current_project_ui = Instance(IView)

    def activate_project(self, project):
        """ Activate a project. """

        self.current_project = project
        self.current_project_ui = project_ui = self._find_view(project)

        # Make sure the project's view is current.
        IViewStack(self.project_views_view).current_view = project_ui

        # Configure the versions.
        self._update_from_versions()
        self.model.working_version = project_ui.working_version

        # Configure the Scan form.
        self.model.source_directory = project_ui.source_directory
        self._update_from_headers()

        # Configure from the selection.
        project_ui.refresh_selection()

    def close_project(self, project):
        """ Close a project. """

        project_views = IViewStack(self.project_views_view).views

        # Remove the observers.
        observe('headers', project, self.__on_headers_changed, remove=True)
        observe('versions', project, self.__on_versions_changed, remove=True)

        # Remove the project specific part of the GUI.
        del project_views[self._find_view(project)]

        # Hide the GUI if there are no more projects.
        if len(project_views) == 0:
            IViewStack(self.view).current_view = self.no_project_view

    def open_project(self, project):
        """ Open a project. """

        project_views = IViewStack(self.project_views_view).views

        # Show the GUI if it was previously hidden.
        if len(project_views) == 0:
            IViewStack(self.view).current_view = self.splitter_view

        # Create the project specific part of the GUI.
        view = ScannerView(self, project)
        IViewStack(self.project_views_view).views.append(view)

        # Observe any changes to the header directories and versions.
        observe('headers', project, self.__on_headers_changed)
        observe('versions', project, self.__on_versions_changed)

    def update_view(self):
        """ Reimplemented to update the state of the view after a change. """

        # This is called very early.
        if self.current_project_ui is None:
            return

        model = self.model

        # Check the validity of the source directory.
        if self.is_valid(self.source_directory_editor):
            self.current_project_ui.source_directory = model.source_directory

        self._update_from_source_directory()

        # Update the working version.
        self.current_project_ui.set_working_version(model.working_version)

        # Configure the state of the file Update and Parse buttons and the
        # assigned module editor.
        module_enabled = False
        parse_enabled = False
        update_enabled = False

        if model.ignored:
            model.module = ''
            update_enabled = True
        else:
            module_enabled = True

            if self.is_valid(self.module_editor):
                update_enabled = True

                if model.source_directory != '' and model.module != '' and len(self.current_header_files) == 1:
                    parse_enabled = True

        IView(self.module_editor).enabled = module_enabled
        IView(self.parse_editor).enabled = parse_enabled
        IView(self.update_file_editor).enabled = update_enabled

        super().update_view()

    def selection(self, selected_items):
        """ This is called by the project specific view when the selected items
        changes.
        """

        # Only multiple header files within the same directory are allowed.
        header_directory = None
        header_files = []

        if len(selected_items) == 1:
            selection = selected_items[0]

            if isinstance(selection, HeaderFile):
                header_files = [selection]
                header_directory = self.current_project.findHeaderDirectory(
                        selection)
            elif isinstance(selection, HeaderDirectory):
                header_directory = selection

        elif len(selected_items) > 1:
            hdir = None

            for selection in selected_items:
                if not isinstance(selection, HeaderFile):
                    break

                if hdir is None:
                    hdir = self.current_project.findHeaderDirectory(selection)
                elif hdir is not self.current_project.findHeaderDirectory(selection):
                    break
            else:
                header_files = selected_items
                header_directory = hdir

        model = self.model

        if header_directory is not None:
            self.current_header_directory = header_directory
            model.header_directory_name = header_directory.name
            model.file_filter = header_directory.filefilter
            model.suffix = header_directory.inputdirsuffix
            model.parser_arguments = header_directory.parserargs
            IGroupBox(self.directory_group_view).enabled = True
            IView(self.delete_editor).enabled = True
        else:
            self.current_header_directory = None
            model.header_directory_name = ''
            model.file_filter = ''
            model.suffix = ''
            model.parser_arguments = ''
            IGroupBox(self.directory_group_view).enabled = False
            IView(self.delete_editor).enabled = False

        if len(header_files) != 0:
            # Create an amalgamation of the selected header files.
            hfile = header_files[0]
            names = [hfile.name]
            ignored = hfile.ignored
            module = hfile.module

            if len(header_files) > 1:
                names.append("...")

            for hfile in header_files[1:]:
                # If the files have different values then fall back to the
                # defaults.
                if ignored != hfile.ignored:
                    ignored = False

                if module != hfile.module:
                    module = ''

            self.current_header_files = header_files
            model.header_file_name = (", ").join(names)
            model.ignored = ignored
            model.module = module
            IGroupBox(self.file_group_view).enabled = True
        else:
            self.current_header_files = []
            model.header_file_name = ''
            model.ignored = False
            model.module = ''
            IGroupBox(self.file_group_view).enabled = False

        self._update_from_source_directory()

    def _find_view(self, project):
        """ Find the project specific part of the GUI for a project. """

        for view in IViewStack(self.project_views_view).views:
            if view.project == project:
                return view

        # This should never happen.
        return None

    @observe('model.delete')
    def __on_delete_triggered(self, change):
        """ Invoked when the Delete button is triggered. """

        project = self.current_project

        window_title = "Delete Header Directory"

        hdir = self.current_header_directory

        if len(hdir.content) != 0:
            Application.warning(window_title,
                    "Deleting a scanned header directory is not yet supported.",
                    self.delete_editor)
        else:
            project.headers.remove(hdir)
            IDirty(project).dirty = True

    @observe('model.hide_ignored')
    def __on_hide_ignored_triggered(self, change):
        """ Invoked when the Hide Ignored button is triggered. """

        self.current_project_ui.hide_ignored(self.current_header_directory,
                hide=True)

    @observe('model.new')
    def __on_new_triggered(self, change):
        """ Invoked when the New button is triggered. """

        project = self.current_project
        window_title = "New Header Directory"

        # Get the name of the header directory.
        (hname, ok) = QInputDialog.getText(self.new_editor, window_title,
                "Descriptive name")

        if ok:
            hname = hname.strip()

            if hname == '':
                Application.warning(window_title,
                        "The name of a header directory must not be blank.",
                        self.new_editor)
            elif hname in [hdir.name for hdir in project.headers]:
                Application.warning(window_title,
                        "'{0}' is already used as the name of a header directory.".format(hname),
                        self.new_editor)
            else:
                working_version = self._working_version_as_string()

                hdir = HeaderDirectory(name=hname, scan=[working_version])
                project.headers.append(hdir)

                IDirty(project).dirty = True

    @observe('model.parse')
    def __on_parse_triggered(self, change):
        """ Invoked when the Parse button is triggered. """

        from ...GccXML import GccXMLParser

        hdir = self.current_header_directory
        hfile = self.current_header_files[0]

        parser = GccXMLParser()

        phf = parser.parse(self.model.source_directory, hdir, hfile)

        if phf is None:
            Application.warning("Parse", parser.diagnostic, self.parser_editor)
        else:
            project = self.current_project

            # Find the corresponding .sip file creating it if is a new header
            # file.
            # FIXME: Assuming we ultimately want to be able to create a
            #        complete project without parsing .h files then we will
            #        need the ability (in the main editor) to manually create
            #        a SipFile instance.
            for mod in project.modules:
                if mod.name == hfile.module:
                    for sfile in mod.content:
                        if sfile.name == hfile.name:
                            break
                    else:
                        sfile = SipFile(name=hfile.name)
                        mod.content.append(sfile)

                    self._merge_code(sfile, phf)

                    break

            # The file version no longer needs parsing.
            working_version = self._working_version_as_string()

            for hfile_version in hfile.versions:
                if hfile_version.version == working_version:
                    hfile_version.parse = False
                    break

            IDirty(project).dirty = True

    def merge_code(self, dsc, ssc):
        """ Merge source code into destination code. """

        working_version = self.model.working_version

        # Go though each existing code item.
        for dsi in dsc.content:
            # Manual code is always retained.
            if isinstance(dsi, ManualCode):
                continue

            # Go through each potentially new code item.
            for ssi in ssc:
                if type(dsi) is type(ssi) and dsi.signature() == ssi.signature():
                    # Make sure the versions include the working version.
                    if working_version is not None:
                        self._update_with_working_version(dsi, True)

                    # Discard the new code item.
                    ssc.remove(ssi)

                    # Merge any child code.
                    if isinstance(dsi, ICodeContainer):
                        self._merge_code(dsi, ssi.content)

                    break
            else:
                # The existing one doesn't exist in the working version.
                if working_version is None:
                    # Forget about it because there are no other versions that
                    # might refer to it.
                    dsc.remove(dsi)
                elif not self._update_with_working_version(dsi, False):
                    # Forget about it because there are no other versions that
                    # refer to it.
                    dsc.remove(dsi)

        # Anything left in the source code is new.

        if working_version is None:
            startversion = endversion = None
        else:
            versions = self.current_project.versions
            working_idx = versions.index(working_version)

            # If the working version is the first then assume that the new item
            # will appear in earlier versions, otherwise it is restricted to
            # this version.
            startversion = None if working_idx == 0 else working_version

            # If the working version is the latest then assume that the new
            # item will appear in later versions, otherwise it is restricted to
            # this version.
            try:
                endversion = versions[working_idx + 1]
            except IndexError:
                endversion = None

        for ssi in ssc:
            if startversion is not None or endversion is not None:
                ssi.versions.append(
                        VersionRange(startversion=startversion,
                                endversion=endversion))

            dsc.content.append(ssi)

    def _update_with_working_version(self, api_item, add_working):
        """ Update a list of version ranges to include or exclude the working
        version.  Return True if the item is still present in some version as a
        result.
        """

        project = self.current_project

        # Construct the existing list of version ranges to a version map.
        if len(api_item.versions) == 0:
            if add_working:
                # Take a shortcut when the item is present in all versions.
                return True

            vmap = project.vmap_create(True)
        else:
            vmap = project.vmap_create(False)
            project.vmap_or_version_ranges(vmap, version_range)

        # Update the version map appropriately using the working version.
        # First take a shortcut to see if anything has changed.
        working_idx = project.versions.index(self.model.working_version)

        if vmap[working_idx] == add_working:
            return True

        vmap[working_idx] = add_working

        # Convert the version map back to a list of version ranges.
        versions = project.vmap_to_version_ranges(vmap)

        if versions is None:
            return False

        api_item.versions = versions

        return True

    @observe('model.reset_workflow')
    def __on_reset_workflow_triggered(self, change):
        """ Invoked when the Reset Workflow button is triggered. """

        project = self.current_project
        working_version = self._working_version_as_string()

        for hdir in project.headers:
            if working_version not in hdir.scan:
                hdir.scan.append(working_version)

        IDirty(project).dirty = True

    @observe('model.scan')
    def __on_scan_triggered(self, change):
        """ Invoked when the Scan button is triggered. """

        project = self.current_project
        hdir = self.current_header_directory

        sd = os.path.abspath(self.model.source_directory)

        if hdir.inputdirsuffix != '':
            sd = os.path.join(sd, hdir.inputdirsuffix)

        Logger.log("Scanning header directory {0}".format(sd))

        if hdir.filefilter != '':
            sd = os.path.join(sd, hdir.filefilter)

        # Save the files that were in the directory.
        saved = list(hdir.content)

        for hpath in glob.iglob(sd):
            if not os.path.isfile(hpath):
                continue

            if os.access(hpath, os.R_OK):
                hfile = self._scan_header_file(hpath)

                for shf in saved:
                    if shf is hfile:
                        saved.remove(shf)
                        break
                else:
                    # It's a new header file.
                    hdir.content.append(hfile)
                    IDirty(project).dirty = True

                Logger.log("Scanned {0}".format(hpath))
            else:
                Logger.log("Skipping unreadable header file {0}".format(hpath))

        # Anything left in the saved list has gone missing or was already
        # missing.
        working_version = self._working_version_as_string()

        for hfile in saved:
            for hfile_version in hfile.versions:
                if hfile_version.version == working_version:
                    hfile.versions.remove(hfile_versions)

                    # If there are no versions left then remove the file
                    # itself.
                    if len(hfile.versions) == 0:
                        hdir.remove(hfile)

                    IDirty(project).dirty = True

                    Logger.log(
                            "{0} is no longer in the header directory".format(
                                    hfile.name))

                    break

        # This version no longer needs scanning.
        if working_version in hdir.scan:
            hdir.scan.remove(working_version)
            IDirty(project).dirty = True

    def _scan_header_file(self, hpath):
        """ Scan a header file and return the header file instance.  hpath is
        the full pathname of the header file.
        """

        # Calculate the MD5 signature ignoring any comments.  Note that nested
        # C style comments aren't handled very well.
        m = hashlib.md5()

        f = open(hpath, 'r')
        src = f.read()
        f.close()

        lnr = 1
        state = 'copy'
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
            if state == 'ccmnt':
                if ch == "/" and prev == "*":
                    state = 'copy'

                continue

            # Handle the end of a C++ style comment.
            if state == 'cppcmnt':
                if ch == "\n":
                    state = 'copy'

                continue

            # We must be in the copy state.

            if ch == "*" and prev == "/":
                # The start of a C style comment.
                state = 'ccmnt'
                continue

            if ch == "/" and prev == "/":
                # The start of a C++ style comment.
                state = 'cppcmnt'
                continue

            # At this point we know the previous character wasn't part of a
            # comment.
            if prev:
                m.update(prev.encode(f.encoding))

        # Note that we didn't add the last character, but it would normally be
        # a newline.
        md5 = m.hexdigest()

        # See if we already know about the file.
        hdir = self.current_header_directory
        hfile_name = os.path.basename(hpath)

        for hfile in hdir.content:
            if hfile.name == hfile_name:
                break
        else:
            # It's a new file.
            hfile = HeaderFile(name=hfile_name)

        # See if we already know about this version.
        working_version = self._working_version_as_string()

        for hfile_version in hfile.versions:
            if hfile_version.version == working_version:
                break
        else:
            # It's a new version.
            hfile_version = HeaderFileVersion(version=working_version)
            hfile.versions.append(hfile_version)

        if hfile_version.md5 != md5:
            hfile_version.md5 = md5
            hfile_version.parse = True
            IDirty(self.current_project).dirty = True

        return hfile

    @observe('model.show_ignored')
    def __on_show_ignored_triggered(self, change):
        """ Invoked when the Show Ignored button is triggered. """

        self.current_project_ui.hide_ignored(self.current_header_directory,
                hide=False)

    @observe('model.update_directory')
    def __on_update_directory_triggered(self, change):
        """ Invoked when the Update header directory button is triggered. """

        hdir = self.current_header_directory
        model = self.model

        hdir.filefilter = model.file_filter
        hdir.inputdirsuffix = model.suffix
        hdir.parserargs = model.parser_arguments

        IDirty(self.current_project).dirty = True

    @observe('model.update_file')
    def __on_update_file_triggered(self, change):
        """ Invoked when the Update header file button is triggered. """

        model = self.model

        for hfile in self.current_header_files:
            hfile.ignored = model.ignored
            hfile.module = model.module

        IDirty(self.current_project).dirty = True

    def __on_headers_changed(self, change):
        """ Invoked when the list of project header directories changes. """

        if change.model is self.current_project:
            self._update_from_headers()

    def __on_versions_changed(self, change):
        """ Invoked when the list of project versions changes. """

        # FIXME: This code assumes that versions will only ever be appended.

        if change.model is self.current_project:
            self._update_from_versions()

    def _update_from_headers(self):
        """ Update the GUI from the current project's list of header
        directories.
        """

        enabled = (len(self.current_project.headers) != 0)

        IView(self.scan_form_view).enabled = enabled
        IView(self.reset_workflow_editor).enabled = enabled

    def _update_from_source_directory(self):
        """ Update the Gui from the source directory. """

        model = self.model

        scan_enabled = (model.source_directory != '' and self.current_header_directory is not None)
        IView(self.scan_editor).enabled = scan_enabled

        parse_enabled = (model.source_directory != '' and model.module != '' and len(self.current_header_files) == 1)
        IView(self.parse_editor).enabled = parse_enabled

    def _update_from_versions(self):
        """ Update the GUI from the current project's list of versions. """

        versions = self.current_project.versions
        ioptionselector = IOptionSelector(self.working_version_editor)

        ioptionselector.options = reversed(versions)
        ioptionselector.visible = (len(versions) != 0)

    def _working_version_as_string(self):
        """ Return the working version as a string.  This will be an empty
        string if versions haven't been explicitly defined.
        """

        working_version = self.model.working_version
        if working_version is None:
            working_version = ''

        return working_version
