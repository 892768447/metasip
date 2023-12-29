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


from abc import ABC, abstractmethod
from enum import auto, Enum
from xml.sax.saxutils import escape

from ...helpers import version_range

from .adapt import adapt


class AttributeType(Enum):
    """ The different types of element and model attributes. """

    BOOL = auto()
    LITERAL = auto()
    STRING = auto()
    STRING_LIST = auto()


class BaseAdapter(ABC):
    """ This is the base class for all adapters and provides the ability to
    load and save a model to a project file and to provide a user-friendly, one
    line string representation.
    """

    # The default attribute type map.
    ATTRIBUTE_TYPE_MAP = {}

    def __init__(self, model):
        """ Initialise the adapter. """

        self.model = model

    def as_str(self):
        """ Return the standard string representation. """

        # This method must be reimplemented by those adapters contribute to the
        # string representation of an API.  However we don't want to make it
        # abstract and have to provide a stub reimplementation in other
        # adapters.
        raise NotImplementedError

    @staticmethod
    def expand_type(type, name=None):
        """ Return the full type with an optional name. """

        # Handle the trivial case.
        if type == '':
            return ''

        # SIP can't handle every C++ fundamental type.
        # TODO: add the SIP support.
        s = type.replace('long int', 'long')

        # Append any name.
        if name:
            if s[-1] not in '&*':
                s += ' '

            s += name

        return s

    def generate_sip_detail(self, output):
        """ Write the detail to a .sip file. """

        # This default implementation does nothing.
        pass

    def generate_sip_directives(self, output):
        """ Write any directives to a .sip file. """

        # This default implementation does nothing.
        pass

    def load(self, element, ui):
        """ Load the model from the XML element.  An optional user interface
        may be available to inform the user of progress.
        """

        # This default implementation loads attributes define by
        # ATTRIBUTE_TYPE_MAP.
        for name, attribute_type in self.ATTRIBUTE_TYPE_MAP.items():
            if attribute_type is AttributeType.BOOL:
                value = bool(int(element.get(name, '0')))
            elif attribute_type is AttributeType.LITERAL:
                for subelement in element:
                    if subelement.tag == 'Literal' and subelement.get('type') == name:
                        value = subelement.text.strip()
                        break
                else:
                    value = ''
            elif attribute_type is AttributeType.STRING:
                value = element.get(name, '')
            elif attribute_type is AttributeType.STRING_LIST:
                value = element.get(name, '').split()

            setattr(self.model, name, value)

    def save(self, output):
        """ Save the model to an output file. """

        # This method must be reimplemented by those adapters that write their
        # own XML element.  However we don't want to make it abstract and have
        # to provide a stub reimplementation in other adapters.
        raise NotImplementedError

    @classmethod
    def save_attribute(cls, name, value, output):
        """ Save an attribute. """

        output.write(f' {name}="{cls._escape(value)}"')

    def save_attributes(self, output):
        """ Save the XML attributes of an adapter that does not write its own
        XML element.
        """

        # This default implementation assumes there are no attributes.
        pass

    def save_bool(self, name, output):
        """ Save a bool. """

        value = getattr(self.model, name)

        if value:
            self.save_attribute(name, '1', output)

    def save_literal(self, name, output):
        """ Save the value of a literal text attribute. """

        value = getattr(self.model, name)

        if value != '':
            output.write(f'<Literal type="{name}">\n{self._escape(value)}\n</Literal>\n', indent=False)

    def save_str(self, name, output):
        """ Save a string. """

        value = getattr(self.model, name)

        if value != '':
            self.save_attribute(name, value, output)

    def save_str_list(self, name, output):
        """ Save a list of strings. """

        value = getattr(self.model, name)

        if len(value) != 0:
            self.save_attribute(name, ' '.join(value), output)

    def save_subelements(self, output):
        """ Save the XML subelements of an adapter that does not write its own
        XML element.
        """

        # This default implementation assumes there are no subelements.
        pass

    @staticmethod
    def _escape(s):
        """ Return an XML escaped string. """

        return escape(s, {'"': '&quot;'})


class BaseApiAdapter(BaseAdapter):
    """ This is the base class for all adapters for models that are written to
    a .sip file and provide a user-friendly, one line string representation.
    """

    @abstractmethod
    def generate_sip(self, output):
        """ Generate the .sip file content. """

        ...

    def version_start(self, output):
        """ Write the start of the version tests for an API.  Returns the
        number of %End statements needed to be passed to the corresponding call
        to version_end().
        """

        api = self.model

        nr_ends = 0

        for vrange in api.versions:
            vr = version_range(vrange)
            output.write(f'%If ({vr})\n', indent=False)
            nr_ends += 1

        # Multiple platforms are logically or-ed.
        if len(api.platforms) != 0:
            platforms = ' || '.join(api.platforms)
            output.write(f'%If ({platforms})\n', indent=False)
            nr_ends += 1

        # Multiple features are nested (ie. logically and-ed).
        for feature in api.features:
            output.write(f'%If ({feature})\n', indent=False)
            nr_ends += 1

        return nr_ends

    @staticmethod
    def version_end(nr_ends, output):
        """ Write the end of the version tests for an API item. """

        for _ in range(nr_ends):
            output.write('%End\n', indent=False)
