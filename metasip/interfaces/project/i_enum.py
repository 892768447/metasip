# Copyright (c) 2023 Riverbank Computing Limited.
#
# This file is part of metasip.
#
# This file may be used under the terms of the GNU General Public License v3
# as published by the Free Software Foundation which can be found in the file
# LICENSE-GPL3.txt included in this package.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.


from ...dip.model import Bool, List, Str

from .i_access import IAccess
from .i_code import ICode
from .i_enum_value import IEnumValue


class IEnum(ICode, IAccess):
    """ The IEnum interface is implemented by models representing an enum. """

    # The list of enum values.
    content = List(IEnumValue)

    # Set if the enum is a C++11 enum class.
    enum_class = Bool()

    # The optional name of the enum.
    name = Str()
