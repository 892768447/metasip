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


from dip.model import adapt, Adapter, implements, Model
from dip.ui import IDisplay

from .. import ISchema


@implements(ISchema)
class ProjectV1Schema(Model):
    """ The ProjectV1Schema class validates an XML file against the project v1
    schema.
    """

    # The name of the schema file relative to this file.
    schema_file = 'project_v1.xsd'


@adapt(ProjectV1Schema, to=IDisplay)
class ProjectV1SchemaIDisplayAdapter(Adapter):
    """ Adapt ProjectV1Schema to the IDisplay interface. """

    # The name to be displayed to the user.
    name = "MetaSIP project v1"
