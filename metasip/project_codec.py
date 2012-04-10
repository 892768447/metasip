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


from dip.io import ICodec, StorageError
from dip.model import implements, Model

from .logger import Logger
from .i_project import IProject


@implements(ICodec)
class ProjectCodec(Model):
    """ The ProjectCodec class implements a codec for a project. """

    # The decoder interface that a model implements to be used with this codec.
    decoder_interface = IProject

    # The encoder interface that a model implements to be used with this codec.
    encoder_interface = IProject

    # The identifier of the format.
    format = 'metasip.formats.project'

    def decode(self, model, source, location):
        """ A model is decoded from a byte stream.

        :param model:
            is the model.
        :param source:
            is an iterator that will return the byte stream to be decoded.
        :param location:
            is the storage location where the encoded model is being read from.
            It is mainly used for error reporting.
        :return:
            the decoded model.  This may be the original model populated from
            the storage location, or it may be a different model (of an
            appropriate type) created from the storage location.
        """

        # Note that we ignore the source iterator and assume that the location
        # refers to the filesystem.

        model.name = str(location)

        if not model.load(Logger):
            raise StorageError(model.diagnostic, location)

        return model

    def encode(self, model, location):
        """ A model is encoded as a byte stream.

        :param model:
            is the model.
        :param location:
            is the storage location where the encoded model will be written to.
            It is mainly used for error reporting.
        :return:
            a generator that will return sections of the encoded byte stream.
        """

        raise NotImplementedError
