# Copyright (c) 2016 Riverbank Computing Limited.
#
# This file is part of metasip.
#
# This file may be used under the terms of the GNU General Public License v3
# as published by the Free Software Foundation which can be found in the file
# LICENSE-GPL3.txt included in this package.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.


from dip.model import Bool, Enum, Interface, List, Str

from .i_sip_file import ISipFile


class IModule(Interface):
    """ The IModule interface is implemented by models representing a Python
    module.
    """

    # Whether instances of classes defined in the module should call
    # super().__init().
    callsuperinit = Enum('undefined', 'no', 'yes')

    # The list of .sip files defining API items included in the module.
    content = List(ISipFile)

    # The SIP directives to be included at the start of the main .sip file for
    # the module.
    directives = Str()

    # The list of modules that this module depends on.
    imports = List(Str())

    # The name of the module.
    name = Str()

    # The optional suffix added to the output directory to create the full name
    # of the directory where the generated .sip files will be placed.
    outputdirsuffix = Str()

    # Set if the limited Python API should be used.
    uselimitedapi = Bool()

    # The version number of the module ABI.
    # FIXME: Convert to Int.
    version = Str()

    # The default virtual error handler.
    virtualerrorhandler = Str()
