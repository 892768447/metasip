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


from ..dip.model import Interface, Str


class ISchema(Interface):
    """ The ISchema interface is implemented by schemas that can be used to
    validate XML files.
    """

    # The name of the schema file relative to the directory containing the
    # module implementing the schema object.
    schema_file = Str()
