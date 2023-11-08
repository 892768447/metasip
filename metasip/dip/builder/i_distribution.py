# Copyright (c) 2018 Riverbank Computing Limited.
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


from ..model import Interface, Str


class IDistribution(Interface):
    """ The IDistribution interface defines the API of a distribution. """

    # The identifier of the distribution.  By convention we use the identifier
    # of the corresponding plugin.
    id = Str()

    def create_distribution(self, project, defaults, title, parent):
        """ Create a distribution.

        :param project:
            is the project (an implementation of IBuilderProject).
        :param defaults:
            is the set of defaults (an implementation of
            IDistributionDefaults).
        :param title:
            is the window title to be used for any dialogs or wizards.
        :param parent:
            is the parent of any dialogs or wizards.
        :return:
            ``True`` if the distribution was created and ``False`` if the user
            cancelled.  An exception is raised if there was an error.
        """

    def defaults_factory(self):
        """ Create a default set of defaults.

        :return:
            the default defaults.
        """
