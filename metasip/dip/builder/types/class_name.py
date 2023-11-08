# Copyright (c) 2012 Riverbank Computing Limited.
#
# This file is part of dip.
#
# This file may be used under the terms of the GNU General Public License
# version 3.0 as published by the Free Software Foundation and appearing in
# the file LICENSE included in the packaging of this file.  Please review the
# following information to ensure the GNU General Public License version 3.0
# requirements will be met: http://www.gnu.org/copyleft/gpl.html.
#
# If you do not wish to use this file under the terms of the GPL version 3.0
# then you may purchase a commercial license.  For more information contact
# info@riverbankcomputing.com.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.


from ...model import Str


class ClassName(Str):
    """ The ClassName class is a string for holding the name of a Python class.
    """

    def __init__(self, default='', **metadata):
        """ Initialise the object. """

        # Provide default meta-data.
        metadata.setdefault('required', 'stripped')
        metadata.setdefault('tool_tip', "The name of the Python class")
        metadata.setdefault('whats_this',
                "This is the name of the Python class.")

        super().__init__(default, **metadata)
