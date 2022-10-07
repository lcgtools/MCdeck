# -*- coding: utf-8 -*-
#
# Copyright (C) 2022 Cloudberries
#
# This file is part of MCdeck
#
# MCdeck is free software: you can redistribute it and/or modify it under the
# terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.
#
# MCdeck is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# MCdeck.  If not, see <https://www.gnu.org/licenses/>.
#

"""Functionality related to OCTGN support."""

import os
import pathlib
import platform
import shutil
import uuid
from xml.etree import ElementTree

from PySide6 import QtWidgets, QtCore, QtGui

from lcgtools import LcgException
from lcgtools.graphics import LcgImage

from mcdeck.util import ErrorDialog


# The OCTGN game ID for Marvel Champions: The Card Game, ref.
# https://twistedsistem.wixsite.com/octgnmarvelchampions/octgn
mc_game_id = '055c536f-adba-4bc2-acbf-9aefb9756046'


class OctgnCardSetData(object):
    """Data for a card set.

    :param  name: the name of the set
    :type   name: str
    :param set_id: the uuid of the set (generated if not provided)
    :type  set_id: str

    """

    def __init__(self, name='', set_id=None):
        self._name = name
        if set_id is None:
            set_id = str(uuid.uuid4())
        if set_id.lower() == mc_game_id:
            raise ValueError('Set ID is the same as the game ID')
        self._set_id = str(uuid.UUID('{' + set_id + '}'))

    @property
    def name(self):
        return self._name

    @property
    def set_id(self):
        return self._set_id

    def to_str(self, cards):
        """Generates string representation of a data for a card set.

        :param  cards: list of (front) card data for cards in set (in order)
        :type   cards: list(:class:`OctgnCardData`)
        :return:       encoded string representation
        :rtype:        str

        String representation starts with a line "CARDSET:[set_id]:[name]"
        followed by a blank line. After this follows a concatenation of the
        string representation of each card in 'cards' (in order), with each
        set separated by an empty line.

        """
        image_ids = set()
        for card in cards:
            image_ids.add(card.image_id.lower())
        if len(image_ids) != len(cards):
            raise ValueError('Cards have duplicate card IDs')
        if self.set_id.lower() in image_ids:
            raise ValueError('Set ID is also included as a card ID')
        if mc_game_id in image_ids:
            raise ValueError('Image IDs includes the game ID')

        out_list = []
        name = OctgnCardData._escape_value(self.name)
        out_list.append(f'CARDSET:{self.set_id}:{name}\n\n')
        for card in cards:
            out_list.append(card.to_str())
            out_list.append('\n')
            if card._alt_data:
                out_list.append(card._alt_data.to_str())
                out_list.append('\n')
        return ''.join(out_list)

    @classmethod
    def to_xml(cls, deck):
        """Generate OCTGN set.xml XML for a deck with OCTGN metadata.

        :param deck: the deck for which to generate XML
        :type  deck: :class:`mcdeck.script.Deck`
        :return:     <set> root node
        :rtype:      :class:`xml.etree.Element`

        Card type (player/encounter/scheme/villain) is inferred from
        OCTGN property "Type", alternatively card type set in deck view. If
        type cannot be resolved, it is assumed to be a player card.

        """
        if not deck._octgn:
            raise LcgException('The deck does not have OCTGN metadata')
        card_set = ElementTree.Element('set')
        card_set.set('name', deck._octgn.name)
        card_set.set('id', deck._octgn.set_id)
        card_set.set('gameId', mc_game_id)
        card_set.set('gameVersion', '0.0.0.0')
        card_set.set('version', '1.0.0.0')

        cards = ElementTree.SubElement(card_set, 'cards')

        for card in deck._card_list_copy:
            props = card._octgn.properties
            # Generate XML for card data
            e = ElementTree.SubElement(cards, 'card')
            e.set('name', card._octgn.name)
            e.set('id', card._octgn.image_id)
            # Resolve "size" parameter
            _pla_typ_l = ('ally', 'alter_ego', 'event', 'hero', 'resource',
                          'support', 'upgrade')
            _sch_typ_l = ('main_scheme', 'side_scheme')
            _enc_typ_l = ('attachment', 'environment', 'minion', 'obligation',
                          'treachery')
            _type = props.get('Type')
            if _type in _pla_typ_l or card.ctype == card.type_player:
                pass
            elif _type in _sch_typ_l:
                e.set('size', 'SchemeCard')
            elif _type in _enc_typ_l:
                e.set('size', 'EncounterCard')
            elif _type == 'villain':
                e.set('size', 'VillainCard')
            elif card.ctype == card.type_player:
                pass
            elif card.ctype == card.type_encounter:
                e.set('size', 'EncounterCard')
            elif card.ctype == card.type_villain:
                e.set('size', 'VillainCard')
            else:
                # Unresolved card type, leaving it as a player card
                pass

            for prop in props.properties_set():
                value = str(props.get(prop))
                e2 = ElementTree.SubElement(e, 'property')
                e2.set('name', prop)
                if prop not in ('Text', 'Quote'):
                    e2.set('value', value)
                else:
                    e2.text = value
            if card._octgn.alt_data:
                # Generate XML for alternate side of card
                alt = ElementTree.SubElement(e, 'alternate')
                alt.set('name', card._octgn.alt_data.name)
                alt.set('type', 'b')
                props = card._octgn.alt_data.properties
                for prop in props.properties_set():
                    value = str(props.get(prop))
                    e2 = ElementTree.SubElement(alt, 'property')
                    e2.set('name', prop)
                    if prop not in ('Text', 'Quote'):
                        e2.set('value', value)
                    else:
                        e2.text = value
        return card_set

    @classmethod
    def to_xml_str(cls, deck):
        """Generate OCTGN set.xml XML for a deck with OCTGN metadata.

        :param deck: the deck for which to generate XML
        :type  deck: :class:`mcdeck.script.Deck`
        :return:     generated XML as a string
        :rtype:      str

        """
        xml = cls.to_xml(deck)
        ElementTree.indent(xml, '  ')
        s = ElementTree.tostring(xml, encoding='utf-8',
                                 xml_declaration=True).decode('utf-8')
        # Workaround for missing option to set standalone in XML declaration
        s_list = s.splitlines()
        header = s_list[0]
        pos = header.find('?>')
        header = header[:pos] + ' standalone=\'yes\'' + header[pos:]
        s_list[0] = header
        return '\n'.join(s_list)

    @classmethod
    def validate_legal_deck(cls, deck):
        """Validate deck can legally be exported.

        :param     deck: the deck to export
        :type      deck: :class:`mcdeck.script.Deck`
        :return:         True if deck validates ok, otherwise False

        Validation includes checking deck has octgn metadata, verifying that
        all card IDs are different, and checking that all cards with alt data
        have a valid back image set.

        """
        if not deck._octgn:
            return False
        ids = set()
        for card in deck._card_list_copy:
            img_id = card._octgn.image_id
            if img_id in ids:
                return False
            ids.add(img_id)
            if card._octgn.alt_data:
                img_id = card._octgn.alt_data.image_id
                if img_id in ids:
                    return False
                ids.add(img_id)
                if not card.specified_back_img:
                    return False
        else:
            return True

    @classmethod
    def export_octgn_card_set(cls, deck, zipfile, settings):
        """Exports card set into a zipfile which can be used with Octgn.

        :param     deck: the deck to export
        :type      deck: :class:`mcdeck.script.Deck`
        :param  zipfile: zip file object to write card set data to
        :type   zipfile: zipfile.ZipFile
        :param settings: settings object for the app
        :type  settings: :class:`mcdeck.util.Settings`

        The zip file is intended to be unzipped in the Data/ directory
        of the OCTGN installation, which is typically the directory
        ~/AppData/Local/Programs/OCTGN/Data/

        It may be a good idea to call :meth:`validate_legal_deck` before
        calling this method (to detect export problems beforehand).

        """
        # Hardcoded for now
        img_format = 'PNG'
        img_width = 400

        if not deck._octgn:
            raise LcgException('The deck does not have OCTGN metadata')
        elif not deck.has_cards():
            raise LcgException('The deck has no cards')

        # Validate deck first
        if not cls.validate_legal_deck(deck):
            _msg = ('Deck is not valid (duplicate image IDs and/or alt card '
                    'without a back image set)')
            raise LcgException(_msg)

        # Generate set.xml and add to zip file
        xml_str = cls.to_xml_str(deck)
        uuid.UUID('{' + deck._octgn.set_id + '}')  # Validates UUID Format
        l = ('GameDatabase', mc_game_id, 'Sets', deck._octgn.set_id, 'set.xml')
        set_xml_path = os.path.join(*l)
        zipfile.writestr(set_xml_path, xml_str)

        # Add images
        _s_c_height = settings.card_height_mm
        _s_c_width = settings.card_width_mm
        img_height = int(img_width*(_s_c_height/_s_c_width))
        img_size = QtCore.QSize(img_width, img_height)
        mode = QtCore.Qt.SmoothTransformation
        for card in deck._card_list_copy:
            img = LcgImage(card.front_img.scaled(img_size, mode=mode))
            img_data = img.saveToBytes(format=img_format)
            _path_l = ['ImageDatabase', mc_game_id, 'Sets', deck._octgn.set_id,
                       'Cards']
            _img_id = card._octgn.image_id
            uuid.UUID('{' + _img_id + '}')  # Validates UUID Format
            _name = f'{_img_id}.{img_format.lower()}'
            _path_l.append(_name)
            img_path = os.path.join(*_path_l)
            zipfile.writestr(img_path, img_data)
            if card._octgn.alt_data:
                img = LcgImage(card.specified_back_img.scaled(img_size,
                                                              mode=mode))
                img_data = img.saveToBytes(format=img_format)
                _path_l = ['ImageDatabase', mc_game_id, 'Sets',
                           deck._octgn.set_id, 'Cards']
                _img_id = card._octgn.alt_data.image_id
                _name = f'{_img_id}.{img_format.lower()}'
                _path_l.append(_name)
                img_path = os.path.join(*_path_l)
                zipfile.writestr(img_path, img_data)

    @classmethod
    def install_octgn_card_set(cls, parent, deck, settings, data_path=None):
        """Installs card set into the OCTGN installation's Data/ directory.

        :param    parent: parent widget for dialogs
        :type     parent: :class:`QtWidgets.QWidget`
        :param      deck: the deck to export
        :type       deck: :class:`mcdeck.script.Deck`
        :param  settings: settings object for the app
        :type   settings: :class:`mcdeck.util.Settings`
        :param data_path: path to OCTGN's Data/ directory (use default if None)
        :type  data_path: str
        :return:          True upon success

        The default location of the Data/ directory of the OCTGN installation
        is ~/AppData/Local/Programs/OCTGN/Data/

        It may be a good idea to call :meth:`validate_legal_deck` before
        calling this method (to detect export problems beforehand).

        """
        # Hardcoded for now
        img_format = 'PNG'
        img_width = 400

        if not deck._octgn:
            raise LcgException('The deck does not have OCTGN metadata')
        elif not deck.has_cards():
            raise LcgException('The deck has no cards')
        uuid.UUID('{' + deck._octgn.set_id + '}')  # Validates UUID Format

        # Validate deck
        if not cls.validate_legal_deck(deck):
            _msg = ('Deck is not valid (duplicate image IDs and/or alt card '
                    'without a back image set)')
            raise LcgException(_msg)

        # Validate we are in Windows platform (OCTGN only runs on Windows)
        if platform.system() != 'Windows':
            raise LcgException('Installation to OCTN requires Windows')

        # Verify existence of required paths
        if not data_path:
            data_path = os.path.join(str(pathlib.Path.home()), 'AppData',
                                     'Local', 'Programs', 'OCTGN', 'Data')
        cls._validate_octgn_data_path(data_path)

        # Identify paths for card set directories
        if not deck._octgn.set_id:
            raise RuntimeError('Should never happen')
        game_db_path = os.path.join(data_path, 'GameDatabase', mc_game_id,
                                    'Sets', deck._octgn.set_id)
        img_db_path = os.path.join(data_path, 'ImageDatabase', mc_game_id,
                                   'Sets', deck._octgn.set_id)
        for _p in game_db_path, img_db_path:
            if os.path.exists(_p):
                _dfun = QtWidgets.QMessageBox.question
                _keys = QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel
                k = _dfun(parent, 'Set already installed', 'A card set with '
                          'the same GUID is already installed. Remove the '
                          'existing installation and install this set?', _keys,
                          QtWidgets.QMessageBox.Cancel)
                if k == QtWidgets.QMessageBox.Cancel:
                    return False
                if not cls.uninstall_octgn_card_set(parent, deck, data_path):
                    return False

        try:
            # Create database directories for the card set
            for _p in game_db_path, img_db_path:
                os.mkdir(_p)
            os.mkdir(os.path.join(img_db_path, 'Cards'))

            # Store set.xml
            xml_str = cls.to_xml_str(deck)
            set_xml_path = os.path.join(game_db_path, 'set.xml')
            with open(set_xml_path, 'w') as f:
                f.write(xml_str)

            # Add images
            _s_c_height = settings.card_height_mm
            _s_c_width = settings.card_width_mm
            img_height = int(img_width*(_s_c_height/_s_c_width))
            img_size = QtCore.QSize(img_width, img_height)
            mode = QtCore.Qt.SmoothTransformation
            for card in deck._card_list_copy:
                img = LcgImage(card.front_img.scaled(img_size, mode=mode))
                img_data = img.saveToBytes(format=img_format)
                _img_id = card._octgn.image_id
                uuid.UUID('{' + _img_id + '}')  # Validates UUID Format
                _name = f'{_img_id}.{img_format.lower()}'
                img_path = os.path.join(img_db_path, 'Cards', _name)
                with open(img_path, 'wb') as f:
                    f.write(img_data)
                if card._octgn.alt_data:
                    img = LcgImage(card.specified_back_img.scaled(img_size,
                                                                  mode=mode))
                    img_data = img.saveToBytes(format=img_format)
                    _img_id = card._octgn.alt_data.image_id
                    _name = f'{_img_id}.{img_format.lower()}'
                    img_path = os.path.join(img_db_path, 'Cards', _name)
                    with open(img_path, 'wb') as f:
                        f.write(img_data)
        except Exception as e:
            # Incomplete installation, remove card set directories
            for _p in game_db_path, img_db_path:
                if os.path.isdir(_p):
                    shutil.rmtree(_p)
            raise(e)
        else:
            return True

    @classmethod
    def uninstall_octgn_card_set(cls, parent, deck, data_path=None):
        """Uninstalls card set from the OCTGN installation's Data/ directory.

        :param    parent: parent widget for dialogs
        :type     parent: :class:`QtWidgets.QWidget`
        :param      deck: the deck to export
        :type       deck: :class:`mcdeck.script.Deck`
        :param data_path: path to OCTGN's Data/ directory (use default if None)
        :type  data_path: str
        :return:          True if card set no longer exists after calling

        The default location of the Data/ directory of the OCTGN installation
        is ~/AppData/Local/Programs/OCTGN/Data/

        """
        if not data_path:
            data_path = os.path.join(str(pathlib.Path.home()), 'AppData',
                                     'Local', 'Programs', 'OCTGN', 'Data')
        cls._validate_octgn_data_path(data_path)

        # Perform uninstall
        game_db_path = os.path.join(data_path, 'GameDatabase', mc_game_id,
                                    'Sets', deck._octgn.set_id)
        img_db_path = os.path.join(data_path, 'ImageDatabase', mc_game_id,
                                   'Sets', deck._octgn.set_id)
        if not (os.path.exists(game_db_path) or os.path.exists(img_db_path)):
            return True
        elif os.path.isdir(game_db_path) or os.path.isdir(img_db_path):
            _dfun = QtWidgets.QMessageBox.question
            _keys = QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel
            k = _dfun(parent, 'Confirm uninstall', 'Uninstalling the card set '
                      f'{deck._octgn.name} will remove the directories '
                      f'{game_db_path} and {img_db_path} including all '
                      'contents. Proceed with deletion?', _keys,
                      QtWidgets.QMessageBox.Cancel)
            if k == QtWidgets.QMessageBox.Cancel:
                return False
            for _p in game_db_path, img_db_path:
                if os.path.isdir(_p):
                    shutil.rmtree(_p)
            return True
        else:
            return False

    @classmethod
    def from_str(cls, *s):
        """Decodes string representation of a card data set with cards.

        :param s: (list of) string(s)
        :return:  tuple (card data set, list of card data)
        :rtype:   (:class:`OctgnCardSetData, [:class:`OctgnCardData`]`)

        Decodes data in the format generated by
        :meth:`OctgnCardSetData.to_str`.

        """
        # Prepare line sets for parsing
        lines = []
        for _s in s:
            lines.extend(_s.split('\n'))
        lines = [l for l in lines if not l.startswith('#')]
        line_sets = []
        current = []
        for line in lines:
            if not line.strip():
                if current:
                    line_sets.append(current)
                    current = []
            else:
                current.append(line)
        if current:
            line_sets.append(current)
            current = []
        if not line_sets:
            raise ValueError('No blocks of strings to decode')

        # Parse card set header
        header_set = line_sets.pop(0)
        if len(header_set) != 1:
            raise ValueError('Card set header must be a single line')
        header, = header_set
        header_s_l = header.split(':')
        if len(header_s_l) < 3:
            raise ValueError('Header must be "CARDSET:[set_id]:[name]"')
        keyword, set_id = header_s_l[0], header_s_l[1]
        if keyword.lower() != 'cardset':
            raise ValueError('Expected card set header keyword "CARDSET"')
        if not set_id:
            raise ValueError('The set must have a set_id')
        set_id = str(uuid.UUID('{' + set_id + '}'))
        name = OctgnCardData._unescape_value(':'.join(header_s_l[2:]))
        set_data = OctgnCardSetData(name, set_id)

        # Parse card data and alt card data
        card_data = []
        _decoded_ids = {mc_game_id, set_id}
        previous = None
        for line_set in line_sets:
            card = OctgnCardData.from_str(previous, *line_set)
            if card:
                card_data.append(card)
                if card.image_id in _decoded_ids:
                    raise ValueError(f'Duplicate ID {card.image_id}')
                _decoded_ids.add(card.image_id)
            previous = card
        return (set_data, card_data)

    @classmethod
    def _validate_octgn_data_path(cls, data_path):
        # Verify existence of required paths
        if not os.path.isdir(data_path):
            raise LcgException(f'No such directory {data_path}')
        for sub in 'GameDatabase', 'ImageDatabase':
            if not os.path.isdir(os.path.join(data_path, sub)):
                raise LcgException(f'{data_path} appears not to be a valid '
                                   f'OCTGN data directory, it has no subdir '
                                   f'{sub}')
        for sub in 'GameDatabase', 'ImageDatabase':
            if not os.path.isdir(os.path.join(data_path, sub, mc_game_id)):
                _msg = ('Support for MC: TCG seems not to have been enabled '
                        'in The OCTGN installation, see https://twistedsistem.'
                        'wixsite.com/octgnmarvelchampions/ for instructions')
                raise LcgException(_msg)
        for sub in 'GameDatabase', 'ImageDatabase':
            _p = os.path.join(data_path, sub, mc_game_id, 'Sets')
            if not os.path.isdir(_p):
                raise LcgException(f'Directory does not exist: {_p}')


class OctgnCardData(object):
    """Card data for a single card object.

    :param     name: card name
    :type      name: str
    :param     prop: card properties (create empty set if None)
    :type      prop: :class:`OctgnProperties`
    :param image_id: uuid for front side image (random if None)
    :type  image_id: str

    """

    def __init__(self, name, prop=None, image_id=None, _val_id=True):
        self._name = name
        if prop is None:
            prop = OctgnProperties()
        self._prop = prop
        if image_id is None:
            self._image_id = str(uuid.uuid4())
        else:
            if _val_id:
                self._image_id = str(uuid.UUID('{' + image_id + '}'))
            else:
                # Allows overriding for image ID set for alt cards
                self._image_id = image_id
        self._alt_data = None

    def create_alt_card_data(self, name, prop=None, type_str='b'):
        """Card an alt card data object for this card data.

        :param     name: card name
        :type      name: str
        :param     prop: card properties (create empty set if None)
        :type      prop: :class:`OctgnProperties`
        :param type_str: type string for the alt card (determines image ID)
        :type  type_str: str
        :return:         alt card data set for this card data set
        :rtype:          :class:`OctgnAltCardData`

        If this card data set already has alt data, that alt data set is
        replaced by this new object.

        """
        result = OctgnAltCardData(self, name=name, prop=prop,
                                  type_str=type_str, _internal=True)
        self._alt_data = result
        return result

    def copy(self):
        """Return a copy of this card data object.

        If the card data holds a reference alt card data, that object
        is also copied (with a reference to the new parent card data).

        """
        c = OctgnCardData(self._name, self._prop, self._image_id)
        if self._alt_data:
            c.create_alt_card_data(self._alt_data._name, self._alt_data._prop,
                                   self._alt_data._type_str)
        return c

    def to_str(self):
        """Generates a multiline string representation of card data.

        :return: multiline string representation appropriate for .txt file
        :rtype:  str

        """
        result = f'CARD:{self._image_id}:{self._name}\n'
        result += self._prop.to_str()
        return result

    @classmethod
    def from_str(cls, parent, *s):
        """Generates card data object from a list of strings.

        :param parent: parent card to apply if decoding an alt (or None)
        :type  parent: :class:`OctgnCardData`
        :param      s: string(s) to decode
        :return:       card data object (or None if decoding alt card data)
        :rtype:        :class:`OctgnCardData`

        For each string `s` if it has multiple lines, it is split up into
        individual lines. If there are any blank single lines, the decoding
        fails (not allowed). Lines starting with '#' are ignored.

        The first non-comment line must have the format "CARD:[img_id]:[name]"
        or #ALTCARD:[name]".

        """
        lines = []
        for _s in s:
            lines.extend(_s.split('\n'))
        lines = [l for l in lines if not l.startswith('#')]
        if not lines:
            raise ValueError('no (non-comment) lines to decode')
        header, lines = lines[0], lines[1:]

        _split = header.split(':')
        if len(_split) < 2:
            raise ValueError('Invalid card header: too few arguments')
        keyword, _split = _split[0], _split[1:]
        if keyword.lower() == 'card':
            is_card = True
        elif keyword.lower() == 'altcard':
            is_card = False
        else:
            raise ValueError('Card header must start with "[ALT]CARD:"')

        property = OctgnProperties.from_str(*lines)

        if is_card:
            img_id, _split = _split[0], _split[1:]
            if not _split:
                raise ValueError('Invalid card header: too few arguments')
            if not img_id:
                raise ValueError('Card must have card ID')
            img_id = str(uuid.UUID('{' + img_id + '}'))
            name = OctgnCardData._unescape_value(':'.join(_split))
            return OctgnCardData(name, property, img_id)
        else:
            if parent is None:
                raise ValueError('Must have parent when decoding alt card')
            img_id = None
            name = OctgnCardData._unescape_value(':'.join(_split))
            parent.create_alt_card_data(name, property)
            return None

    @property
    def name(self):
        """The name set on this card."""
        return self._name

    @property
    def properties(self):
        """The :class:`OctgnProperties` object of this data set."""
        return self._prop

    @property
    def image_id(self):
        """Image identifier for the card (side) image."""
        return self._image_id

    @property
    def alt_data(self):
        """Data set for alt card (back side) to this card (None if not set)."""
        return self._alt_data

    @classmethod
    def _escape_value(cls, s):
        return s.replace('\\', '\\\\').replace('\n', '\\n')

    @classmethod
    def _unescape_value(cls, s):
        _out_c = []
        _escaping = False
        for c in s:
            if _escaping:
                if c == '\\':
                    _out_c.append('\\')
                elif c == 'n':
                    _out_c.append('\n')
                else:
                    raise ValueError('Invalid encoding of string')
                _escaping = False
                continue
            elif c == '\\':
                _escaping = True
            else:
                _out_c.append(c)
        if _escaping:
            raise ValueError('Invalid encoding of string')
        return ''.join(_out_c)


class OctgnAltCardData(OctgnCardData):
    """Card data for a single card object.

    :param   parent: card data of parent card (cannot be alt card data)
    :type    parent: :class:`OctgnCardData`
    :param     name: card name
    :type      name: str
    :param     prop: card properties (create empty set if None)
    :type      prop: :class:`OctgnProperties`
    :param type_str: type string for the alt card (determines image ID)
    :type  type_str: str

    Should not be instantiated directly by clients (use factory methods).

    """

    def __init__(self, parent, name, prop, type_str='b', _internal=False):
        if not _internal:
            raise LcgException('Clients should not instantiate directly')
        if isinstance(parent, OctgnAltCardData):
            raise TypeError('parent cannot refer to alt card data')
        elif not isinstance(parent, OctgnCardData):
            raise TypeError('parent must be OctgnCardData')
        image_id = parent._image_id + f'.{type_str}'
        super().__init__(name, prop, image_id, _val_id=False)
        self._type_str = type_str

    def to_str(self):
        result = f'ALTCARD:{self._name}\n'
        result += self._prop.to_str()
        return result

    def copy(self):
        raise LcgException('Cannot copy alt card data directly')


class OctgnProperties(object):
    """Holds <property> name/value pairs for a <card> in settings.xml."""

    # format {name: (type, validator, params)}. For a tuple tupe, params
    # has a tuple of allowed values. If params ends with None, it is allowed
    # to enter values outside this list (None is not itself a legal value).
    fields = {
              # Card generic properties
              'Type': (tuple, None,
                       ('ally', 'alter_ego', 'attachment', 'environment',
                        'event', 'hero', 'main_scheme', 'minion', 'obligation',
                        'resource', 'side_scheme', 'support', 'treachery',
                        'upgrade', 'villain', None)),
              'CardNumber': (str, None, None),
              'Unique': (tuple, None, ('True',)),
              'Cost': (int, lambda x: x >= 0, None),
              'Attribute': (str, None, None),
              'Text': (str, None, None),
              'Resource_Physical': (int, lambda x: x >= 0, None),
              'Resource_Mental': (int, lambda x: x >= 0, None),
              'Resource_Energy': (int, lambda x: x >= 0, None),
              'Resource_Wild': (int, lambda x: x >= 0, None),
              'Quote': (str, None, None),
              'Owner': (str, None, None),

              # Heros, allies, villains, minions (not applicable to all)
              'Attack': (int, lambda x: x >= 0, None),
              'Thwart': (int, lambda x: x >= 0, None),  # "0" should be "None"?
              'Defense': (int, lambda x: x >= 0, None),
              'Recovery': (int, lambda x: x >= 0, None),
              'Scheme': (int, lambda x: x >= 0, None),

              # Allies
              'AttackCost': (int, lambda x: x >= 0, None),
              'ThwartCost': (int, lambda x: x >= 0, None),

              # Heros
              'HandSize': (int, lambda x: x >= 0, None),
              'HP': (int, lambda x: x >= 0, None),

              # Villain HP setting
              'HP_Per_Hero': (tuple, None, ('True',)),

              # Schemes
              'Threat': (int, lambda x: x >= 0, None),
              'EscalationThreat': (int, lambda x: x >= 0, None),
              'EscalationThreatFixed': (tuple, None, ('True', 'False')),
              'BaseThreat': (int, lambda x: x >= 0, None),
              'BaseThreatFixed': (tuple, None, ('True', 'False')),
              'Scheme_Acceleration': (int, lambda x: x >= 0, None),
              'Scheme_Crisis': (int, lambda x: x >= 0, None),
              'Scheme_Hazard': (int, lambda x: x >= 0, None),

              # Encounter card generic
              'Boost': (int, lambda x: x >= 0, None)  # "0" should be "None"?
              }

    def __init__(self):
        self.__data = dict()

    def get(self, name):
        """Get value of property 'name' (None if not set)."""
        return self.__data.get(name, None)

    def has_property(self, name):
        """True if property 'name' has been set."""
        return name in self.__data

    def has_set_properties(self):
        """True if any properties have been set."""
        return bool(self.__data)

    def properties_set(self):
        """Returns a list of names of properties which have been set."""
        return tuple(self.__data.keys())

    def set(self, name, value):
        """Sets property of given name to given value."""
        if name not in OctgnProperties.fields:
            raise ValueError(f'{name} is not an allowed property name')
        f_type, f_val, f_params = OctgnProperties.fields[name]
        if f_type is tuple:
            if not self.property_custom_tuple(name) and value not in f_params:
                raise ValueError(f'Illegal value {value} for property '
                                 f'{f_type}')
        elif type(value) is not f_type:
            raise TypeError(f'{name} property must have type {f_type}')
        if f_val:
            if not f_val(value):
                raise TypeError(f'Value {value} is illegal for this property')
        if isinstance(value, str) and value == '':
            raise TypeError('Cannot set empty string as value')
        self.__data[name] = value

    def clear(self, name):
        """Removes property 'name' setting (if set)."""
        self.__data.pop(name, None)

    def clear_all(self):
        """Removes all values set."""
        self.__data = dict()

    def to_str(self):
        """Generate a string encoding suitable for config files.

        :return: string encoding

        Generated string will use one line per parameter, in the format
        'property_name:value'. Values will be escaped using
        :meth:`escape_value` in order to ensure it is kept on a single line.
        Trailing whitespace in the value is assumed to be part of the value,
        except if there is one trailing '\r' character, that character is
        discarded.

        If no values are held by the object, then a single line of three '-'
        dashes plus a newline is returned.

        """
        if self.__data:
            out_l = []
            for key, value in self.__data.items():
                enc_val = OctgnCardData._escape_value(str(value))
                out_l.append(f'{key}:{enc_val}')
            return '\n'.join(out_l) + '\n\n'
        else:
            return '---\n\n'

    @classmethod
    def from_str(cls, *s):
        """Generates properties object from a list of strings.

        :param  s: string(s) to decode
        :return:   properties object, decoded
        :rtype:    :class:`OctgnProperties`

        For each string `s` if it has multiple lines, it is split up into
        individual lines. If there are any blank single lines, the decoding
        fails (not allowed).

        """
        result = OctgnProperties()
        lines = []
        for _s in s:
            lines.extend(_s.split('\n'))
        if len(lines) == 1 and lines[0] == '---':
            return result
        for line in lines:
            if line.endswith('\r'):
                line = line[:-1]
            if not line.strip():
                raise ValueError('Cannot decode from string(s) that '
                                 'include blank (only whitespace) line(s)')
            pos = line.find(':')
            if pos < 0:
                raise ValueError('All lines must contain a colon')
            key, value = line[:pos], line[(pos+1):]
            if not key:
                raise ValueError('Missing key')
            elif not value:
                raise ValueError('No value set')
            if result.has_property(key):
                raise ValueError(f'Property {key} set more than once')
            if key not in cls.property_list():
                raise ValueError(f'No such property name {key}')
            value = OctgnCardData._unescape_value(value)
            f_type, f_chk, f_params = OctgnProperties.fields[key]
            if not (f_type is str or f_type is tuple):
                value = f_type(value)
            if not f_chk or f_chk(value):
                result.set(key, value)
            else:
                raise ValueError(f'Value {value} failed value test for '
                                 f'property {key}')
        return result

    @classmethod
    def property_list(cls):
        """Returns a list of property names which can be set."""
        return tuple(cls.fields.keys())

    @classmethod
    def property_type(cls, property):
        """Returns required type for given property."""
        if property not in cls.fields:
            raise ValueError(f'Invalid property {property}')
        return cls.fields[property][0]

    @classmethod
    def property_params(cls, property):
        """Returns field parameters for given property."""
        if property not in cls.fields:
            raise ValueError(f'Invalid property {property}')
        f = cls.fields[property]
        if f[2][-1] is None:
            return tuple(f[2][:-1])
        else:
            return tuple(f[2])

    @classmethod
    def property_custom_tuple(cls, property):
        """True if type is a tuple and value can be outside list in params."""
        if property not in cls.fields:
            raise ValueError(f'Invalid property {property}')
        f = cls.fields[property]
        return (f[0] is tuple and f[2][-1] is None)


class OctgnDataDialog(QtWidgets.QDialog):
    """Widget for editing OCTGN data for a deck and a selection of cards.

    :param   parent: parent widget for this dialog
    :type    parent: :class:`QtWidgets.QWidget`
    :param     deck: the deck for which to edit OCTGN data
    :type      deck: :class:`mcdeck.script.Deck`
    :param cardlist: list of cards to edit (if None edit all cards in deck)
    :type  cardlist: list(:class:`mcdeck.script.card`)
    :param    title: dialog title
    :type     title: str

    """

    # Enable or disable data entry for tabs
    enableTabDataInput = QtCore.Signal(bool)

    def __init__(self, parent, deck, cardlist=None, title=None):
        super().__init__(parent)
        self._deck = deck
        self._exec_allowed = True
        if title:
            self.setWindowTitle(title)

        # If deck has no Octgn metadata, ask about adding
        if deck._octgn is None:
            _dfun = QtWidgets.QMessageBox.question
            _keys = QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel
            k = _dfun(self, 'No Octgn Metadata', 'The deck currently does '
                      'not include metadata. Add Octgn metadata?', _keys)
            if k == QtWidgets.QMessageBox.Cancel:
                self._exec_allowed = False
                return
            else:
                deck._octgn = OctgnCardSetData(name='')
                for i, card in enumerate(deck._card_list_copy):
                    card._octgn = OctgnCardData(name='')

        # The dialog operates on a copy of card data objects
        deck_cards = deck._card_list_copy
        if cardlist is None:
            cardlist = deck_cards

        # Sort cards with list of (pos_in_deck, is_alt, card_obj, data_cpy).
        _deck_card_d = dict()
        for i, card in enumerate(deck_cards):
            _deck_card_d[card] = i
        if len(_deck_card_d) != len(deck_cards):
            raise RuntimeError('Should never happen')
        _ordered = []
        for card in cardlist:
            _ordered.append((_deck_card_d[card], card))
        _ordered.sort()
        self._cards = []
        for pos, card in _ordered:
            _data_cpy = card._octgn.copy()
            self._cards.append((pos, False, card, _data_cpy))
            if card.specified_back_img:
                self._cards.append((pos, True, card, _data_cpy))

        main_layout = QtWidgets.QVBoxLayout()

        set_box = QtWidgets.QGroupBox()
        set_box.setTitle('Card Set')
        sb_layout = QtWidgets.QHBoxLayout()
        lbl = QtWidgets.QLabel
        sb_layout.addWidget(lbl('Name:'))
        self._set_name_le = QtWidgets.QLineEdit()
        self._set_name_le.setText(deck._octgn.name)
        self._set_name_le.setToolTip('Name of card set')
        sb_layout.addWidget(self._set_name_le)
        sb_layout.addWidget(lbl('ID:'))
        self._set_uuid_le = QtWidgets.QLineEdit()
        _tip = 'Unique OCTGN card set ID (UUID format)'
        self._set_uuid_le.setToolTip(_tip)
        _uuid_val = OctgnUuidValidator()
        self._set_uuid_le.setValidator(_uuid_val)
        self._set_uuid_le.setText(deck._octgn.set_id)
        self._set_uuid_le.setMinimumWidth(280)
        sb_layout.addWidget(self._set_uuid_le)
        sb_layout.addStretch(1)
        set_box.setLayout(sb_layout)
        main_layout.addWidget(set_box)

        card_box = QtWidgets.QGroupBox()
        card_box.setTitle('Card')
        cl_layout = QtWidgets.QVBoxLayout()
        # Card data
        data_box = QtWidgets.QGroupBox()
        data_box.setTitle('Card data')
        data_layout = QtWidgets.QVBoxLayout()
        data_split = QtWidgets.QSplitter()
        img_viewer = OctgnImageViewer(dialog=self)
        img_viewer.setMinimumSize(140, 180)
        _img_w = QtWidgets.QWidget()
        _img_l = QtWidgets.QVBoxLayout()
        _img_l.addStretch(1)
        _img_l.addWidget(img_viewer)
        _img_l.addStretch(1)
        _img_w.setLayout(_img_l)
        data_split.addWidget(_img_w)
        self._data_tabs = QtWidgets.QTabWidget()
        self._gen_tab = OctgnDataDialogGeneralTab(self)
        self._data_tabs.addTab(self._gen_tab, 'General')
        self._other_tab = OctgnDataDialogOtherTab(self)
        self._data_tabs.addTab(self._other_tab, 'Other')
        data_split.addWidget(self._data_tabs)
        data_split.setMinimumHeight(400)
        data_layout.addWidget(data_split)
        data_box.setLayout(data_layout)
        cl_layout.addWidget(data_box)
        # Card selector
        sel_box = QtWidgets.QGroupBox()
        sel_box.setTitle('Card selector')
        sel_layout = QtWidgets.QHBoxLayout()
        self._prev_btn = QtWidgets.QPushButton()
        self._prev_btn.setText('Previous')
        self._prev_btn.setToolTip('Go to previous card (shortcut: Meta+P)')
        sel_layout.addWidget(self._prev_btn)
        self._card_cb = QtWidgets.QComboBox()  # Card selector
        self._card_cb.setMinimumWidth(300)
        self._card_cb.setToolTip('Currently selected card')
        for _pos, _is_alt, _card, _data in self._cards:
            _txt = f'{_pos:02}' if not _is_alt else f'{_pos:02}B'
            if _is_alt:
                _data = _data.alt_data
            if _data and _data.name:
                _txt += f' - {_data.name}'
            self._card_cb.addItem(_txt)
        sel_layout.addWidget(self._card_cb)
        self._next_btn = QtWidgets.QPushButton()
        self._next_btn.setText('Next')
        self._next_btn.setToolTip('Go to next card (shortcut: Meta+N)')
        sel_layout.addWidget(self._next_btn)
        sel_layout.addStretch(1)
        self._alt_chk = QtWidgets.QCheckBox()
        self._alt_chk.clicked.connect(self.enableAltStatus)
        sel_layout.addWidget(self._alt_chk)
        self._alt_lbl = lbl('Alt card enabled')
        sel_layout.addWidget(self._alt_lbl)
        sel_box.setLayout(sel_layout)
        cl_layout.addWidget(sel_box)
        card_box.setLayout(cl_layout)
        main_layout.addWidget(card_box)

        btns_layout = QtWidgets.QHBoxLayout()
        btns_layout.addStretch(1)
        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok |
                                          QtWidgets.QDialogButtonBox.Apply |
                                          QtWidgets.QDialogButtonBox.Cancel)
        btns.rejected.connect(self.reject)
        btns.accepted.connect(self.accept)
        _apply_btn = btns.button(QtWidgets.QDialogButtonBox.Apply)
        _apply_btn.clicked.connect(self.apply)
        btns_layout.addWidget(btns)
        main_layout.addLayout(btns_layout)

        main_layout.addStretch(1)
        self.setLayout(main_layout)

        self._prev_btn.clicked.connect(self.prevClicked)
        self._next_btn.clicked.connect(self.nextClicked)

        # Shortcut: Meta+N (next card data)
        _key = QtCore.QKeyCombination(QtCore.Qt.ControlModifier,
                                      QtCore.Qt.Key_N)
        _short = QtGui.QShortcut(QtGui.QKeySequence(_key), self)
        _short.activated.connect(self._next_btn.click)
        # Shortcut: Meta+P (previous card data)
        _key = QtCore.QKeyCombination(QtCore.Qt.ControlModifier,
                                      QtCore.Qt.Key_P)
        _short = QtGui.QShortcut(QtGui.QKeySequence(_key), self)
        _short.activated.connect(self._prev_btn.click)
        # Shortcut: Meta+G (switch to general tab)
        _key = QtCore.QKeyCombination(QtCore.Qt.ControlModifier,
                                      QtCore.Qt.Key_G)
        _short = QtGui.QShortcut(QtGui.QKeySequence(_key), self)
        _short.activated.connect(self.switchToGeneralTab)
        # Shortcut: Meta+O (switch to other tab)
        _key = QtCore.QKeyCombination(QtCore.Qt.ControlModifier,
                                      QtCore.Qt.Key_O)
        _short = QtGui.QShortcut(QtGui.QKeySequence(_key), self)
        _short.activated.connect(self.switchToOtherTab)

        self._card_cb.setCurrentIndex(-1)  # Required for below trigger
        self._card_cb.currentIndexChanged.connect(self.cardSelected)
        self._card_cb.currentIndexChanged.connect(img_viewer.cardSelected)
        for _tab in self._gen_tab, self._other_tab:
            self._card_cb.currentIndexChanged.connect(_tab.cardSelected)
            self.enableTabDataInput.connect(_tab.enableTabDataInput)
        self._card_cb.setCurrentIndex(0)   # Trigger currentIndexChanged()

    def accept(self):
        if self.apply():
            super().accept()

    @QtCore.Slot()
    def apply(self):
        try:
            # Store card set name and ID
            set_name = self._set_name_le.text()
            set_id = self._set_uuid_le.text()
            set_id = str(uuid.UUID('{' + set_id.lower() + '}'))
            if (set_name != self._deck._octgn.name or
                set_id != self._deck._octgn.set_id):
                _dfun = QtWidgets.QMessageBox.question
                _keys = QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel
                _msg = ('Card set name and/or ID were edited. This change '
                        'cannot be undone. Proceed to change card set info?')
                k = _dfun(self, 'Card set name/ID changed', _msg, _keys)
                if k == QtWidgets.QMessageBox.Cancel:
                    return
                else:
                    self._deck._octgn._name = set_name
                    self._deck._octgn._set_id = set_id

            # Commit any pending changes on current card
            for i in range(self._data_tabs.count()):
                tab = self._data_tabs.widget(i)
                tab.commit_current()
            # Replace card data objects
            for pos, is_alt, card, data in self._cards:
                if not is_alt:
                    card._octgn = data

            # Update card name in card list
            idx = self._card_cb.currentIndex()
            pos, is_alt, card, data = self._cards[idx]
            _txt = f'{pos:02}' if not is_alt else f'{pos:02}B'
            if is_alt:
                data = data.alt_data
            if data and data.name:
                _txt += f' - {data.name}'
            self._card_cb.setItemText(idx, _txt)

        except Exception as e:
            self._err('Exception', 'Exception performing operation: {e}')
            return False
        else:
            return True

    def exec(self):
        if not self._exec_allowed:
            return False
        else:
            super().exec()

    @QtCore.Slot()
    def prevClicked(self):
        idx = self._card_cb.currentIndex()
        new_idx = max(idx - 1, 0)
        if idx != new_idx:
            self._card_cb.setCurrentIndex(new_idx)

    @QtCore.Slot()
    def cardSelected(self, index):
        self._prev_btn.setEnabled(index > 0)
        self._next_btn.setEnabled(index < self._card_cb.count() - 1)

        pos, is_alt, card, data = self._cards[index]

        if is_alt:
            data = data.alt_data
            self._alt_chk.setEnabled(True)
            self._alt_chk.setChecked(data is not None)
            self._alt_lbl.setEnabled(True)
            self.enableTabDataInput.emit(data is not None)
        else:
            self._alt_chk.setEnabled(False)
            self._alt_chk.setChecked(False)
            self._alt_lbl.setEnabled(False)
            self.enableTabDataInput.emit(True)

    @QtCore.Slot()
    def nextClicked(self):
        idx = self._card_cb.currentIndex()
        new_idx = min(idx + 1, self._card_cb.count() - 1)
        if idx != new_idx:
            self._card_cb.setCurrentIndex(new_idx)

    @QtCore.Slot()
    def enableAltStatus(self, status):
        idx = self._card_cb.currentIndex()
        pos, is_alt, card, data = self._cards[idx]
        if status:
            if is_alt and not data.alt_data:
                # Add a card data object for the alt card, and refresh
                data.create_alt_card_data(name='')
                self._card_cb.setCurrentIndex(-1)
                self._card_cb.setCurrentIndex(idx)
        else:
            if is_alt and data.alt_data:
                _dfun = QtWidgets.QMessageBox.question
                _keys = QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel
                _msg = ('Disabling alt card data for this card will remove '
                        'current data for alt card. Proceed with removing alt '
                        'card data?')
                k = _dfun(self, 'Confirm removing alt card data', _msg, _keys)
                if k == QtWidgets.QMessageBox.Cancel:
                    self._alt_chk.setChecked(True)
                    return
                else:
                    data._alt_data = None
                    self._card_cb.setCurrentIndex(-1)
                    self._card_cb.setCurrentIndex(idx)

    @QtCore.Slot()
    def switchToGeneralTab(self):
        self._data_tabs.setCurrentIndex(0)

    @QtCore.Slot()
    def switchToOtherTab(self):
        self._data_tabs.setCurrentIndex(1)

    def _err(self, s1, s2):
        ErrorDialog(s1, s2).exec()


class OctgnDataDialogGeneralTab(QtWidgets.QWidget):
    """Tab for general card settings."""

    def __init__(self, dialog, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._dialog = dialog
        self._current_index = -1

        lbl = QtWidgets.QLabel
        _int_val = QtGui.QIntValidator()
        _int_val.setBottom(0)
        main_layout = QtWidgets.QVBoxLayout()
        groups_layout = QtWidgets.QHBoxLayout()

        # General settings
        gen_box = QtWidgets.QGroupBox()
        gen_box.setTitle('General')
        gen_box.setMinimumWidth(280)
        gen_l = QtWidgets.QGridLayout()
        row = 0
        self._name_chk = QtWidgets.QCheckBox()
        self._name_chk.setFocusPolicy(QtCore.Qt.ClickFocus)
        gen_l.addWidget(self._name_chk, row, 0)
        gen_l.addWidget(lbl('Name:'), row, 1)
        self._name_le = QtWidgets.QLineEdit()
        self._name_le.setToolTip('Printed name on card')
        gen_l.addWidget(self._name_le, row, 2)
        row += 1
        self._unique_chk = QtWidgets.QCheckBox()
        self._unique_chk.setFocusPolicy(QtCore.Qt.ClickFocus)
        gen_l.addWidget(self._unique_chk, row, 0)
        gen_l.addWidget(lbl('Unique:'), row, 1)
        self._unique_cb = QtWidgets.QComboBox()
        self._unique_cb.addItem('')
        self._unique_cb.addItem('True')
        self._unique_cb.setToolTip('True if card is marked as "unique"')
        gen_l.addWidget(self._unique_cb, row, 2)
        row += 1
        self._cost_chk = QtWidgets.QCheckBox()
        self._cost_chk.setFocusPolicy(QtCore.Qt.ClickFocus)
        gen_l.addWidget(self._cost_chk, row, 0)
        gen_l.addWidget(lbl('Cost:'), row, 1)
        self._cost_le = QtWidgets.QLineEdit()
        self._cost_le.setValidator(_int_val)
        self._cost_le.setToolTip('Card\'s printed cost')
        gen_l.addWidget(self._cost_le, row, 2)
        row += 1
        self._type_chk = QtWidgets.QCheckBox()
        self._type_chk.setFocusPolicy(QtCore.Qt.ClickFocus)
        gen_l.addWidget(self._type_chk, row, 0)
        gen_l.addWidget(lbl('Type:'), row, 1)
        self._type_cb = QtWidgets.QComboBox()
        for _t in OctgnProperties.fields['Type'][2]:
            self._type_cb.addItem(_t)
        self._type_cb.setEditable(True)
        self._type_cb.setToolTip('Card type')
        gen_l.addWidget(self._type_cb, row, 2)
        row += 1
        self._attr_chk = QtWidgets.QCheckBox()
        self._attr_chk.setFocusPolicy(QtCore.Qt.ClickFocus)
        gen_l.addWidget(self._attr_chk, row, 0)
        gen_l.addWidget(lbl('Attribute:'), row, 1)
        self._attr_le = QtWidgets.QLineEdit()
        self._attr_le.setToolTip('Attribute string printed under card image')
        gen_l.addWidget(self._attr_le, row, 2)
        row += 1
        self._owner_chk = QtWidgets.QCheckBox()
        self._owner_chk.setFocusPolicy(QtCore.Qt.ClickFocus)
        gen_l.addWidget(self._owner_chk, row, 0)
        gen_l.addWidget(lbl('Owner:'), row, 1)
        self._owner_le = QtWidgets.QLineEdit()
        _tip = ('Card set (printed on bottom of card), for custom cards '
                'recommend using the format [author] - [set name]')
        self._owner_le.setToolTip(_tip)
        gen_l.addWidget(self._owner_le, row, 2)
        row += 1
        gen_l.addWidget(lbl('MCDB#:'), row, 1)
        self._num_le = QtWidgets.QLineEdit()
        _tip = ('Card ID in the MarvelCDB database (likely not applicable '
                'to custom cards)')
        self._num_le.setToolTip(_tip)
        gen_l.addWidget(self._num_le, row, 2)
        _vl = QtWidgets.QVBoxLayout()
        _vl.addLayout(gen_l)
        _vl.addStretch(1)
        gen_box.setLayout(_vl)
        groups_layout.addWidget(gen_box)

        # Resources
        res_box = QtWidgets.QGroupBox()
        res_box.setTitle('Resources')
        res_box.setMinimumWidth(180)
        res_v = QtWidgets.QVBoxLayout()
        res_l = QtWidgets.QGridLayout()
        row = 0
        self._r_phy_chk = QtWidgets.QCheckBox()
        self._r_phy_chk.setFocusPolicy(QtCore.Qt.ClickFocus)
        res_l.addWidget(self._r_phy_chk, row, 0)
        res_l.addWidget(lbl('Physical:'), row, 1)
        self._r_phy_le = QtWidgets.QLineEdit()
        self._r_phy_le.setValidator(_int_val)
        self._r_phy_le.setToolTip('Card\'s printed physical resources')
        res_l.addWidget(self._r_phy_le, row, 2)
        row += 1
        self._r_men_chk = QtWidgets.QCheckBox()
        self._r_men_chk.setFocusPolicy(QtCore.Qt.ClickFocus)
        res_l.addWidget(self._r_men_chk, row, 0)
        res_l.addWidget(lbl('Mental:'), row, 1)
        self._r_men_le = QtWidgets.QLineEdit()
        self._r_men_le.setValidator(_int_val)
        self._r_men_le.setToolTip('Card\'s printed mental resources')
        res_l.addWidget(self._r_men_le, row, 2)
        row += 1
        self._r_ene_chk = QtWidgets.QCheckBox()
        self._r_ene_chk.setFocusPolicy(QtCore.Qt.ClickFocus)
        res_l.addWidget(self._r_ene_chk, row, 0)
        res_l.addWidget(lbl('Energy:'), row, 1)
        self._r_ene_le = QtWidgets.QLineEdit()
        self._r_ene_le.setValidator(_int_val)
        self._r_ene_le.setToolTip('Card\'s printed energy resources')
        res_l.addWidget(self._r_ene_le, row, 2)
        row += 1
        self._r_wil_chk = QtWidgets.QCheckBox()
        self._r_wil_chk.setFocusPolicy(QtCore.Qt.ClickFocus)
        res_l.addWidget(self._r_wil_chk, row, 0)
        res_l.addWidget(lbl('Wild:'), row, 1)
        self._r_wil_le = QtWidgets.QLineEdit()
        self._r_wil_le.setValidator(_int_val)
        self._r_wil_le.setToolTip('Card\'s printed wild resources')
        res_l.addWidget(self._r_wil_le, row, 2)
        res_v.addLayout(res_l)
        res_v.addStretch(1)
        res_box.setLayout(res_v)
        groups_layout.addWidget(res_box)

        # Right panel free text multiline edits
        text_box = QtWidgets.QGroupBox()
        text_box.setTitle('Card text')
        text_box.setMinimumWidth(260)
        text_l = QtWidgets.QVBoxLayout()
        text_gl = QtWidgets.QGridLayout()
        self._text_chk = QtWidgets.QCheckBox()
        self._text_chk.setFocusPolicy(QtCore.Qt.ClickFocus)
        text_gl.addWidget(self._text_chk, 0, 0, QtCore.Qt.AlignTop)
        text_gl.addWidget(lbl('Text:'), 0, 1, QtCore.Qt.AlignTop)
        self._text_te = QtWidgets.QTextEdit()
        self._text_te.setAcceptRichText(False)
        self._text_te.setTabChangesFocus(True)
        self._text_te.setToolTip('Text printed on card')
        text_gl.addWidget(self._text_te, 0, 2)
        self._quote_chk = QtWidgets.QCheckBox()
        self._quote_chk.setFocusPolicy(QtCore.Qt.ClickFocus)
        text_gl.addWidget(self._quote_chk, 1, 0, QtCore.Qt.AlignTop)
        text_gl.addWidget(lbl('Quote:'), 1, 1, QtCore.Qt.AlignTop)
        self._quote_te = QtWidgets.QTextEdit()
        self._quote_te.setAcceptRichText(False)
        self._quote_te.setTabChangesFocus(True)
        self._quote_te.setToolTip('Quote printed on card')
        text_gl.addWidget(self._quote_te, 1, 2)
        text_l.addLayout(text_gl)
        text_l.addStretch(1)
        text_box.setLayout(text_l)
        groups_layout.addWidget(text_box)

        # Bottom "apply all" button
        _apply_l = QtWidgets.QHBoxLayout()
        self._mark_all_btn = QtWidgets.QPushButton('Mark all')
        self._mark_all_btn.setToolTip('Set all checkmarks')
        _apply_l.addWidget(self._mark_all_btn)
        self._mark_none_btn = QtWidgets.QPushButton('Mark none')
        self._mark_none_btn.setToolTip('Clear all checkmarks')
        _apply_l.addWidget(self._mark_none_btn)
        _apply_l.addStretch(1)
        _apply_l.addWidget(lbl('Card ID:'))
        self._uuid_le = QtWidgets.QLineEdit()
        _uuid_val = OctgnUuidValidator()
        self._uuid_le.setValidator(_uuid_val)
        self._uuid_le.setMinimumWidth(280)
        self._uuid_le.setToolTip('Unique OCTGN card ID (UUID format)')
        _apply_l.addWidget(self._uuid_le)
        _apply_l.addStretch(1)
        self._apply_all_btn = QtWidgets.QPushButton('Apply marked')
        _tip = ('Apply data in checked fields to all cards in the card list')
        self._apply_all_btn.setToolTip(_tip)
        _apply_l.addWidget(self._apply_all_btn)

        main_layout.addLayout(groups_layout)
        main_layout.addLayout(_apply_l)
        main_layout.addStretch(1)
        self.setLayout(main_layout)

        self._mark_all_btn.clicked.connect(self.markAll)
        self._mark_none_btn.clicked.connect(self.markNone)
        self._apply_all_btn.clicked.connect(self.applyAll)

    @QtCore.Slot()
    def cardSelected(self, index):
        if index >= 0:
            try:
                if self._current_index >= 0:
                    # Commit values of previous index before switching card
                    _prev_idx = self._current_index
                    self.commit(_prev_idx)
                    pos, is_alt, card, data = self._dialog._cards[_prev_idx]
                    _txt = f'{pos:02}' if not is_alt else f'{pos:02}B'
                    if is_alt:
                        data = data.alt_data
                    if data and data.name:
                        _txt += f' - {data.name}'
                    self._dialog._card_cb.setItemText(_prev_idx, _txt)
                self._current_index = index

                # Initialize card data values
                pos, is_alt, card, data = self._dialog._cards[index]
                if is_alt:
                    data = data.alt_data
                if data:
                    prop = data.properties
                    # Name
                    self._name_le.setText(data.name)
                    # Type
                    _val = prop.get('Type')
                    _val = '' if _val is None else str(_val)
                    self._type_cb.setCurrentText(_val)
                    # Attribute
                    _val = prop.get('Attribute')
                    _val = '' if _val is None else str(_val)
                    self._attr_le.setText(_val)
                    # Unique
                    _val = prop.get('Unique')
                    if not _val:
                        _val = ''
                    self._unique_cb.setCurrentText(_val)
                    # Cost
                    _val = prop.get('Cost')
                    _val = '' if _val is None else str(_val)
                    self._cost_le.setText(_val)
                    # Owner
                    _val = prop.get('Owner')
                    _val = '' if _val is None else str(_val)
                    self._owner_le.setText(_val)
                    # Card ID
                    self._uuid_le.setText(data.image_id)
                    # Card number
                    _val = prop.get('CardNumber')
                    _val = '' if _val is None else str(_val)
                    self._num_le.setText(_val)
                    # Resources 1
                    _val = prop.get('Resource_Physical')
                    _val = '' if _val is None else str(_val)
                    self._r_phy_le.setText(_val)
                    # Resources 2
                    _val = prop.get('Resource_Mental')
                    _val = '' if _val is None else str(_val)
                    self._r_men_le.setText(_val)
                    # Resources 3
                    _val = prop.get('Resource_Energy')
                    _val = '' if _val is None else str(_val)
                    self._r_ene_le.setText(_val)
                    # Resources 4
                    _val = prop.get('Resource_Wild')
                    _val = '' if _val is None else str(_val)
                    self._r_wil_le.setText(_val)
                    # Text
                    _val = prop.get('Text')
                    _val = '' if _val is None else str(_val)
                    self._text_te.setText(_val)
                    # Quote
                    _val = prop.get('Quote')
                    _val = '' if _val is None else str(_val)
                    self._quote_te.setText(_val)
                else:
                    for w in (self._name_le, self._attr_le, self._cost_le,
                              self._owner_le, self._uuid_le, self._num_le,
                              self._r_phy_le, self._r_men_le, self._r_ene_le,
                              self._r_wil_le, self._text_te, self._quote_te):
                        w.setText('')
                    for w in self._type_cb, self._unique_cb:
                        w.setCurrentText('')

                # Disable "alt enabled" widget for non-alt cards
                self._uuid_le.setEnabled(not is_alt)

                self._current_index = index
            except Exception as e:
                    self._err('Exception', 'Exception: {e}')

    @QtCore.Slot()
    def markAll(self):
        for w in (self._name_chk, self._type_chk, self._attr_chk,
                  self._unique_chk, self._cost_chk, self._owner_chk,
                  self._r_phy_chk, self._r_men_chk, self._r_ene_chk,
                  self._r_wil_chk, self._text_chk, self._quote_chk):
            w.setChecked(True)

    @QtCore.Slot()
    def markNone(self):
        for w in (self._name_chk, self._type_chk, self._attr_chk,
                  self._unique_chk, self._cost_chk, self._owner_chk,
                  self._r_phy_chk, self._r_men_chk, self._r_ene_chk,
                  self._r_wil_chk, self._text_chk, self._quote_chk):
            w.setChecked(False)

    @QtCore.Slot()
    def applyAll(self):
        # Commit currently selected values for all card data
        for index in range(self._dialog._card_cb.count()):
            try:
                self.commit(index, checked_only=True)
            except Exception as e:
                self._err('Exception', 'Exception performing operation: {e}')

    @QtCore.Slot()
    def enableTabDataInput(self, enable):
        for w in (self._name_le, self._attr_le, self._cost_le, self._owner_le,
                  self._uuid_le, self._num_le, self._r_phy_le, self._r_men_le,
                  self._r_ene_le, self._r_wil_le, self._text_te,
                  self._quote_te, self._type_cb, self._unique_cb):
            w.setEnabled(enable)

    def commit(self, index, checked_only=False):
        """Commit the dialog inputs to card data.

        :param        index: the index of the card for which to commit data
        :param checked_only: if True only commit checked values

        """

        pos, is_alt, card, data = self._dialog._cards[index]
        if is_alt:
            data = data.alt_data

        if not data:
            # If there is no data object, there is nothing to commit
            return

        def _commit(prop, val, typ=None):
            try:
                if val is None or (isinstance(val, str) and not val):
                    data.properties.clear(prop)
                else:
                    if typ:
                        val = typ(val)
                    data.properties.set(prop, val)
            except Exception as e:
                raise LcgException(f'Could not commit property "{prop}" '
                                   f'value "{val}": {e}')

        if not checked_only or self._name_chk.isChecked():
            data._name = self._name_le.text()
        if not checked_only or self._type_chk.isChecked():
            _commit('Type', self._type_cb.currentText())
        if not checked_only or self._attr_chk.isChecked():
            _commit('Attribute', self._attr_le.text())
        # 'Unique' property
        if not checked_only or self._unique_chk.isChecked():
            if self._unique_cb.currentText() == 'True':
                data.properties.set('Unique', 'True')
            else:
                data.properties.clear('Unique')
        if not checked_only or self._cost_chk.isChecked():
            _commit('Cost', self._cost_le.text(), int)
        if not checked_only or self._owner_chk.isChecked():
            _commit('Owner', self._owner_le.text())
        # Card ID
        if not checked_only and not is_alt:
            card_id = self._uuid_le.text()
            if not card_id:
                raise LcgException('Card must have a card ID')
            try:
                card_id = str(uuid.UUID('{' + card_id.lower() + '}'))
            except Exception as e:
                raise LcgException(f'Invalid card ID format: {e}')
            data._image_id = card_id
        if not checked_only:
            _commit('CardNumber', self._num_le.text())
        if not checked_only or self._r_phy_chk.isChecked():
            _commit('Resource_Physical', self._r_phy_le.text(), int)
        if not checked_only or self._r_men_chk.isChecked():
            _commit('Resource_Mental', self._r_men_le.text(), int)
        if not checked_only or self._r_ene_chk.isChecked():
            _commit('Resource_Energy', self._r_ene_le.text(), int)
        if not checked_only or self._r_wil_chk.isChecked():
            _commit('Resource_Wild', self._r_wil_le.text(), int)
        if not checked_only or self._text_chk.isChecked():
            _commit('Text', self._text_te.toPlainText())
        if not checked_only or self._quote_chk.isChecked():
            _commit('Quote', self._quote_te.toPlainText())

    def commit_current(self):
        """Commits the dialog with the current inputs and selected data."""
        index = self._dialog._card_cb.currentIndex()
        try:
            self.commit(index)
        except Exception as e:
            self._err('Exception', 'Exception performing operation: {e}')

    def _err(self, s1, s2):
        ErrorDialog(s1, s2).exec()


class OctgnDataDialogOtherTab(QtWidgets.QWidget):
    """Tab for card specific settings."""

    def __init__(self, dialog, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._dialog = dialog
        self._current_index = -1

        lbl = QtWidgets.QLabel
        _int_val = QtGui.QIntValidator()
        _int_val.setBottom(0)
        main_layout = QtWidgets.QVBoxLayout()
        groups_layout = QtWidgets.QHBoxLayout()

        # Character
        _box = QtWidgets.QGroupBox()
        _box.setTitle('Characters')
        _l = QtWidgets.QGridLayout()
        row = 0
        self._thw_chk = QtWidgets.QCheckBox()
        self._thw_chk.setFocusPolicy(QtCore.Qt.ClickFocus)
        _l.addWidget(self._thw_chk, row, 0)
        _l.addWidget(lbl('THW:'), row, 1)
        self._thw_le = QtWidgets.QLineEdit()
        self._thw_le.setValidator(_int_val)
        self._thw_le.setToolTip('Card\'s printed THW (thwart) value')
        _l.addWidget(self._thw_le, row, 2)
        row += 1
        self._atk_chk = QtWidgets.QCheckBox()
        self._atk_chk.setFocusPolicy(QtCore.Qt.ClickFocus)
        _l.addWidget(self._atk_chk, row, 0)
        _l.addWidget(lbl('ATK:'), row, 1)
        self._atk_le = QtWidgets.QLineEdit()
        self._atk_le.setValidator(_int_val)
        self._atk_le.setToolTip('Card\'s printed ATK (attack) value')
        self._atk_le.textChanged.connect(self.characterAtkChanged)
        _l.addWidget(self._atk_le, row, 2)
        row += 1
        self._def_chk = QtWidgets.QCheckBox()
        self._def_chk.setFocusPolicy(QtCore.Qt.ClickFocus)
        _l.addWidget(self._def_chk, row, 0)
        _l.addWidget(lbl('DEF:'), row, 1)
        self._def_le = QtWidgets.QLineEdit()
        self._def_le.setValidator(_int_val)
        self._def_le.setToolTip('Card\'s printed DEF (defense) value')
        _l.addWidget(self._def_le, row, 2)
        row += 1
        self._rec_chk = QtWidgets.QCheckBox()
        self._rec_chk.setFocusPolicy(QtCore.Qt.ClickFocus)
        _l.addWidget(self._rec_chk, row, 0)
        _l.addWidget(lbl('REC:'), row, 1)
        self._rec_le = QtWidgets.QLineEdit()
        self._rec_le.setValidator(_int_val)
        self._rec_le.setToolTip('Card\'s printed REC (recovery) value')
        _l.addWidget(self._rec_le, row, 2)
        row += 1
        self._hp_chk = QtWidgets.QCheckBox()
        self._hp_chk.setFocusPolicy(QtCore.Qt.ClickFocus)
        _l.addWidget(self._hp_chk, row, 0)
        _l.addWidget(lbl('HP:'), row, 1)
        self._hp_le = QtWidgets.QLineEdit()
        self._hp_le.setValidator(_int_val)
        self._hp_le.setToolTip('Card\'s printed number of HP (hit points)')
        self._hp_le.textChanged.connect(self.characterHpChanged)
        _l.addWidget(self._hp_le, row, 2)
        row += 1
        self._atk_cost_chk = QtWidgets.QCheckBox()
        self._atk_cost_chk.setFocusPolicy(QtCore.Qt.ClickFocus)
        _l.addWidget(self._atk_cost_chk, row, 0)
        _l.addWidget(lbl('Attack Cost:'), row, 1)
        self._atk_cost_le = QtWidgets.QLineEdit()
        self._atk_cost_le.setValidator(_int_val)
        self._atk_cost_le.setToolTip('Attack cost (applies to allies)')
        _l.addWidget(self._atk_cost_le, row, 2)
        row += 1
        self._thw_cost_chk = QtWidgets.QCheckBox()
        self._thw_cost_chk.setFocusPolicy(QtCore.Qt.ClickFocus)
        _l.addWidget(self._thw_cost_chk, row, 0)
        _l.addWidget(lbl('Thwart Cost:'), row, 1)
        self._thw_cost_le = QtWidgets.QLineEdit()
        self._thw_cost_le.setValidator(_int_val)
        self._thw_cost_le.setToolTip('Thwart cost (applies to allies)')
        _l.addWidget(self._thw_cost_le, row, 2)
        row += 1
        self._hand_size_chk = QtWidgets.QCheckBox()
        self._hand_size_chk.setFocusPolicy(QtCore.Qt.ClickFocus)
        _l.addWidget(self._hand_size_chk, row, 0)
        _l.addWidget(lbl('Hand Size:'), row, 1)
        self._hand_size_le = QtWidgets.QLineEdit()
        self._hand_size_le.setValidator(_int_val)
        self._hand_size_le.setToolTip('Hero/Alter-Ego hand size')
        _l.addWidget(self._hand_size_le, row, 2)
        _vl = QtWidgets.QVBoxLayout()
        _vl.addLayout(_l)
        _vl.addStretch(1)
        _box.setLayout(_vl)
        groups_layout.addWidget(_box)

        # Enemy or encounter
        _vl = QtWidgets.QVBoxLayout()
        _box = QtWidgets.QGroupBox()
        _box.setTitle('Enemies')
        _l = QtWidgets.QGridLayout()
        row = 0
        self._sch_chk = QtWidgets.QCheckBox()
        self._sch_chk.setFocusPolicy(QtCore.Qt.ClickFocus)
        _l.addWidget(self._sch_chk, row, 0)
        _l.addWidget(lbl('SCH:'), row, 1)
        self._sch_le = QtWidgets.QLineEdit()
        self._sch_le.setValidator(_int_val)
        self._sch_le.setToolTip('Card\'s printed SCH (scheme) value')
        _l.addWidget(self._sch_le, row, 2)
        row += 1
        self._atk2_chk = QtWidgets.QCheckBox()
        self._atk2_chk.setFocusPolicy(QtCore.Qt.ClickFocus)
        _l.addWidget(self._atk2_chk, row, 0)
        _l.addWidget(lbl('ATK:'), row, 1)
        self._atk2_le = QtWidgets.QLineEdit()
        self._atk2_le.setValidator(_int_val)
        self._atk2_le.setToolTip('Card\'s printed ATK (attack) value')
        self._atk2_le.textChanged.connect(self.enemyAtkChanged)
        _l.addWidget(self._atk2_le, row, 2)
        row += 1
        self._hp2_chk = QtWidgets.QCheckBox()
        self._hp2_chk.setFocusPolicy(QtCore.Qt.ClickFocus)
        _l.addWidget(self._hp2_chk, row, 0)
        _l.addWidget(lbl('HP:'), row, 1)
        self._hp2_le = QtWidgets.QLineEdit()
        self._hp2_le.setValidator(_int_val)
        self._hp2_le.setToolTip('Card\'s printed number of HP (hit points)')
        self._hp2_le.textChanged.connect(self.enemyHpChanged)
        _l.addWidget(self._hp2_le, row, 2)
        row += 1
        self._hp_per_hero_chk = QtWidgets.QCheckBox()
        self._hp_per_hero_chk.setFocusPolicy(QtCore.Qt.ClickFocus)
        _l.addWidget(self._hp_per_hero_chk, row, 0)
        _l.addWidget(lbl('HP per hero:'), row, 1)
        self._hp_per_hero_cb = QtWidgets.QComboBox()
        self._hp_per_hero_cb.addItem('')
        self._hp_per_hero_cb.addItem('True')
        _msg = 'If true multiply HP by number of heroes'
        self._hp_per_hero_cb.setToolTip(_msg)
        _l.addWidget(self._hp_per_hero_cb, row, 2)
        _box.setLayout(_l)
        _vl.addWidget(_box)
        # Encounter
        _box = QtWidgets.QGroupBox()
        _box.setTitle('Encounter card')
        _l = QtWidgets.QGridLayout()
        row = 0
        self._boost_chk = QtWidgets.QCheckBox()
        self._boost_chk.setFocusPolicy(QtCore.Qt.ClickFocus)
        _l.addWidget(self._boost_chk, row, 0)
        _l.addWidget(lbl('Boost icons:'), row, 1)
        self._boost_le = QtWidgets.QLineEdit()
        self._boost_le.setValidator(_int_val)
        _msg = 'Number of printed boost icons (excluding any star)'
        self._boost_le.setToolTip(_msg)
        _l.addWidget(self._boost_le, row, 2)
        _l2 = QtWidgets.QVBoxLayout()
        _l2.addLayout(_l)
        _l2.addStretch(1)
        _box.setLayout(_l2)
        _vl.addWidget(_box)
        groups_layout.addLayout(_vl)

        # Scheme
        _box = QtWidgets.QGroupBox()
        _box.setTitle('Scheme')
        _l = QtWidgets.QGridLayout()
        row = 0
        self._threat_chk = QtWidgets.QCheckBox()
        self._threat_chk.setFocusPolicy(QtCore.Qt.ClickFocus)
        _l.addWidget(self._threat_chk, row, 0)
        _l.addWidget(lbl('Threat Limit:'), row, 1)
        self._threat_le = QtWidgets.QLineEdit()
        self._threat_le.setValidator(_int_val)
        self._threat_le.setToolTip('Threat limit on scheme (possibly '
                                   'multiplied by the number of players)')
        _l.addWidget(self._threat_le, row, 2)
        row += 1
        self._base_threat_chk = QtWidgets.QCheckBox()
        self._base_threat_chk.setFocusPolicy(QtCore.Qt.ClickFocus)
        _l.addWidget(self._base_threat_chk, row, 0)
        _l.addWidget(lbl('Initial Threat:'), row, 1)
        self._base_threat_le = QtWidgets.QLineEdit()
        self._base_threat_le.setValidator(_int_val)
        _msg = ('Initial threat on scheme when placed (possibly multiplied, '
                'see "Initial Threat is Fixed")')
        self._base_threat_le.setToolTip(_msg)
        _l.addWidget(self._base_threat_le, row, 2)
        row += 1
        self._fix_base_threat_chk = QtWidgets.QCheckBox()
        self._fix_base_threat_chk.setFocusPolicy(QtCore.Qt.ClickFocus)
        _l.addWidget(self._fix_base_threat_chk, row, 0)
        _l.addWidget(lbl('Initial Threat is Fixed:'), row, 1)
        self._fixed_base_threat_cb = QtWidgets.QComboBox()
        self._fixed_base_threat_cb.addItem('')
        self._fixed_base_threat_cb.addItem('True')
        self._fixed_base_threat_cb.addItem('False')
        _msg = 'If False then base threat is multiplied by number of players'
        self._fixed_base_threat_cb.setToolTip(_msg)
        _l.addWidget(self._fixed_base_threat_cb, row, 2)
        row += 1
        self._esc_threat_chk = QtWidgets.QCheckBox()
        self._esc_threat_chk.setFocusPolicy(QtCore.Qt.ClickFocus)
        _l.addWidget(self._esc_threat_chk, row, 0)
        _l.addWidget(lbl('Threat Acceleration:'), row, 1)
        self._esc_threat_le = QtWidgets.QLineEdit()
        self._esc_threat_le.setValidator(_int_val)
        _msg = ('Threat acceleration printed next to Initial Threat (possibly '
                'multiplied, see "Threat Acceleration is Fixed")')
        self._esc_threat_le.setToolTip(_msg)
        _l.addWidget(self._esc_threat_le, row, 2)
        row += 1
        self._fix_esc_threat_chk = QtWidgets.QCheckBox()
        self._fix_esc_threat_chk.setFocusPolicy(QtCore.Qt.ClickFocus)
        _l.addWidget(self._fix_esc_threat_chk, row, 0)
        _l.addWidget(lbl('Threat Acceleration is Fixed:'), row, 1)
        self._fixed_esc_threat_cb = QtWidgets.QComboBox()
        self._fixed_esc_threat_cb.addItem('')
        self._fixed_esc_threat_cb.addItem('True')
        self._fixed_esc_threat_cb.addItem('False')
        _msg = ('If False then threat acceleration is multiplied by number '
                'of players')
        self._fixed_esc_threat_cb.setToolTip(_msg)
        _l.addWidget(self._fixed_esc_threat_cb, row, 2)
        row += 1
        self._accel_chk = QtWidgets.QCheckBox()
        self._accel_chk.setFocusPolicy(QtCore.Qt.ClickFocus)
        _l.addWidget(self._accel_chk, row, 0)
        _l.addWidget(lbl('Acceleration Icons:'), row, 1)
        self._accel_le = QtWidgets.QLineEdit()
        self._accel_le.setValidator(_int_val)
        _msg = ('Scheme\'s number of acceleration icons (in addition to '
                '"Threat Acceleration")')
        self._accel_le.setToolTip(_msg)
        _l.addWidget(self._accel_le, row, 2)
        row += 1
        self._crisis_chk = QtWidgets.QCheckBox()
        self._crisis_chk.setFocusPolicy(QtCore.Qt.ClickFocus)
        _l.addWidget(self._crisis_chk, row, 0)
        _l.addWidget(lbl('Crisis Icons:'), row, 1)
        self._crisis_le = QtWidgets.QLineEdit()
        self._crisis_le.setValidator(_int_val)
        self._crisis_le.setToolTip('Scheme\'s number of crisis icons')
        _l.addWidget(self._crisis_le, row, 2)
        row += 1
        self._hazard_chk = QtWidgets.QCheckBox()
        self._hazard_chk.setFocusPolicy(QtCore.Qt.ClickFocus)
        _l.addWidget(self._hazard_chk, row, 0)
        _l.addWidget(lbl('Hazard Icons:'), row, 1)
        self._hazard_le = QtWidgets.QLineEdit()
        self._hazard_le.setValidator(_int_val)
        self._hazard_le.setToolTip('Scheme\'s number of hazard icons')
        _l.addWidget(self._hazard_le, row, 2)
        _vl = QtWidgets.QVBoxLayout()
        _vl.addLayout(_l)
        _vl.addStretch(1)
        _box.setLayout(_vl)
        groups_layout.addWidget(_box)

        # Bottom "apply all" button
        _apply_l = QtWidgets.QHBoxLayout()
        self._mark_all_btn = QtWidgets.QPushButton('Mark all')
        self._mark_all_btn.setToolTip('Set all checkmarks')
        _apply_l.addWidget(self._mark_all_btn)
        self._mark_none_btn = QtWidgets.QPushButton('Mark none')
        self._mark_none_btn.setToolTip('Clear all checkmarks')
        _apply_l.addWidget(self._mark_none_btn)
        _apply_l.addStretch(1)
        self._apply_all_btn = QtWidgets.QPushButton('Apply marked')
        _tip = ('Apply data in checked fields to all cards in the card list')
        self._apply_all_btn.setToolTip(_tip)
        _apply_l.addWidget(self._apply_all_btn)

        main_layout.addLayout(groups_layout)
        main_layout.addLayout(_apply_l)
        main_layout.addStretch(1)
        self.setLayout(main_layout)

        self._mark_all_btn.clicked.connect(self.markAll)
        self._mark_none_btn.clicked.connect(self.markNone)
        self._apply_all_btn.clicked.connect(self.applyAll)

    @QtCore.Slot()
    def cardSelected(self, index):
        if index >= 0:
            try:
                if self._current_index >= 0:
                    # Commit values of previous index before switching card
                    _prev_idx = self._current_index
                    self.commit(_prev_idx)
                self._current_index = index

                # Initialize card data values
                pos, is_alt, card, data = self._dialog._cards[index]
                if is_alt:
                    data = data.alt_data

                if data:
                    prop = data.properties
                    # ATK
                    _val = prop.get('Attack')
                    _val = '' if _val is None else str(_val)
                    self._atk_le.setText(_val)
                    # THW
                    _val = prop.get('Thwart')
                    _val = '' if _val is None else str(_val)
                    self._thw_le.setText(_val)
                    # DEF
                    _val = prop.get('Defense')
                    _val = '' if _val is None else str(_val)
                    self._def_le.setText(_val)
                    # REC
                    _val = prop.get('Recovery')
                    _val = '' if _val is None else str(_val)
                    self._rec_le.setText(_val)
                    # HP
                    _val = prop.get('HP')
                    _val = '' if _val is None else str(_val)
                    self._hp_le.setText(_val)
                    # Attack Cost
                    _val = prop.get('AttackCost')
                    _val = '' if _val is None else str(_val)
                    self._atk_cost_le.setText(_val)
                    # Thwart Cost
                    _val = prop.get('ThwartCost')
                    _val = '' if _val is None else str(_val)
                    self._thw_cost_le.setText(_val)
                    # Hand size
                    _val = prop.get('HandSize')
                    _val = '' if _val is None else str(_val)
                    self._hand_size_le.setText(_val)
                    # SCH
                    _val = prop.get('Scheme')
                    _val = '' if _val is None else str(_val)
                    self._sch_le.setText(_val)
                    # HP per hero
                    _val = prop.get('HP_Per_Hero')
                    if not _val:
                        _val = ''
                    self._hp_per_hero_cb.setCurrentText(_val)
                    # Boost icons
                    _val = prop.get('Boost')
                    _val = '' if _val is None else str(_val)
                    self._boost_le.setText(_val)
                    # Threat
                    _val = prop.get('Threat')
                    _val = '' if _val is None else str(_val)
                    self._threat_le.setText(_val)
                    # Escalation threat
                    _val = prop.get('EscalationThreat')
                    _val = '' if _val is None else str(_val)
                    self._esc_threat_le.setText(_val)
                    # Base threat
                    _val = prop.get('BaseThreat')
                    _val = '' if _val is None else str(_val)
                    self._base_threat_le.setText(_val)
                    # Fixed base threat
                    _val = prop.get('BaseThreatFixed')
                    _val = '' if _val is None else str(_val)
                    self._fixed_base_threat_cb.setCurrentText(_val)
                    # Acceleration icons
                    _val = prop.get('Scheme_Acceleration')
                    _val = '' if _val is None else str(_val)
                    self._accel_le.setText(_val)
                    # Fixed threat escalation
                    _val = prop.get('EscalationThreatFixed')
                    _val = '' if _val is None else str(_val)
                    self._fixed_esc_threat_cb.setCurrentText(_val)
                    # Crisis icons
                    _val = prop.get('Scheme_Crisis')
                    _val = '' if _val is None else str(_val)
                    self._crisis_le.setText(_val)
                    # Hazard icons
                    _val = prop.get('Scheme_Hazard')
                    _val = '' if _val is None else str(_val)
                    self._hazard_le.setText(_val)
                else:
                    for w in (self._atk_le, self._thw_le, self._def_le,
                              self._rec_le, self._hp_le, self._atk_cost_le,
                              self._thw_cost_le, self._hand_size_le,
                              self._sch_le, self._boost_le, self._threat_le,
                              self._esc_threat_le, self._base_threat_le,
                              self._accel_le, self._crisis_le,
                              self._hazard_le):
                        w.setText('')
                    for w in (self._hp_per_hero_cb, self._fixed_base_threat_cb,
                              self._fixed_esc_threat_cb):
                        w.setCurrentText('')

                self._current_index = index
            except Exception as e:
                self._err('Exception', 'Exception performing operation: {e}')

    @QtCore.Slot()
    def characterHpChanged(self, value):
        if self._hp2_le.text() != value:
            self._hp2_le.setText(value)

    @QtCore.Slot()
    def enemyHpChanged(self, value):
        if self._hp_le.text() != value:
            self._hp_le.setText(value)

    @QtCore.Slot()
    def characterAtkChanged(self, value):
        if self._atk2_le.text() != value:
            self._atk2_le.setText(value)

    @QtCore.Slot()
    def enemyAtkChanged(self, value):
        if self._atk_le.text() != value:
            self._atk_le.setText(value)

    @QtCore.Slot()
    def markAll(self):
        for w in (self._atk_chk, self._thw_chk, self._def_chk,
                  self._rec_chk, self._hp_chk, self._atk_cost_chk,
                  self._thw_cost_chk, self._hand_size_chk, self._atk2_chk,
                  self._sch_chk, self._hp2_chk, self._hp_per_hero_chk,
                  self._boost_chk, self._threat_chk, self._esc_threat_chk,
                  self._base_threat_chk, self._fix_base_threat_chk,
                  self._accel_chk, self._crisis_chk, self._hazard_chk):
            w.setChecked(True)

    @QtCore.Slot()
    def markNone(self):
        for w in (self._atk_chk, self._thw_chk, self._def_chk,
                  self._rec_chk, self._hp_chk, self._atk_cost_chk,
                  self._thw_cost_chk, self._hand_size_chk, self._atk2_chk,
                  self._sch_chk, self._hp2_chk, self._hp_per_hero_chk,
                  self._boost_chk, self._threat_chk, self._esc_threat_chk,
                  self._base_threat_chk, self._fix_base_threat_chk,
                  self._accel_chk, self._crisis_chk, self._hazard_chk):
            w.setChecked(False)

    @QtCore.Slot()
    def applyAll(self):
        # Commit currently selected values for all card data
        for index in range(self._dialog._card_cb.count()):
            try:
                self.commit(index, checked_only=True)
            except Exception as e:
                self._err('Exception', 'Exception performing operation: {e}')

    @QtCore.Slot()
    def enableTabDataInput(self, enable):
        for w in (self._atk_le, self._thw_le, self._def_le, self._rec_le,
                  self._hp_le, self._atk_cost_le, self._thw_cost_le,
                  self._hand_size_le, self._atk2_le, self._sch_le,
                  self._hp2_le, self._boost_le, self._threat_le,
                  self._esc_threat_le, self._base_threat_le,
                  self._accel_le, self._crisis_le, self._hazard_le,
                  self._hp_per_hero_cb, self._fixed_base_threat_cb,
                  self._fixed_esc_threat_cb):
            w.setEnabled(enable)

    def commit(self, index, checked_only=False):
        """Commit the dialog inputs to card data.

        :param        index: the index of the card for which to commit data
        :param checked_only: if True only commit checked values

        """
        pos, is_alt, card, data = self._dialog._cards[index]
        if is_alt:
            data = data.alt_data

        if not data:
            # No data object, nothing to commit
            return

        def _commit(prop, val, typ=None):
            try:
                if val is None or (isinstance(val, str) and not val):
                    data.properties.clear(prop)
                else:
                    if typ:
                        val = typ(val)
                    data.properties.set(prop, val)
            except Exception as e:
                raise LcgException(f'Could not commit property "{prop}" '
                                   f'value "{val}": {e}')

        if not checked_only or self._atk_chk.isChecked():
            _commit('Attack', self._atk_le.text(), int)
        if not checked_only or self._thw_chk.isChecked():
            _commit('Thwart', self._thw_le.text(), int)
        if not checked_only or self._def_chk.isChecked():
            _commit('Defense', self._def_le.text(), int)
        if not checked_only or self._rec_chk.isChecked():
            _commit('Recovery', self._rec_le.text(), int)
        if not checked_only or self._hp_chk.isChecked():
            _commit('HP', self._hp_le.text(), int)
        if not checked_only or self._atk_cost_chk.isChecked():
            _commit('AttackCost', self._atk_cost_le.text(), int)
        if not checked_only or self._thw_cost_chk.isChecked():
            _commit('ThwartCost', self._thw_cost_le.text(), int)
        if not checked_only or self._hand_size_chk.isChecked():
            _commit('HandSize', self._hand_size_le.text(), int)
        if not checked_only or self._sch_chk.isChecked():
            _commit('Scheme', self._sch_le.text(), int)
        if not checked_only or self._hp_per_hero_chk.isChecked():
            if self._hp_per_hero_cb.currentText() == 'True':
                data.properties.set('HP_Per_Hero', 'True')
            else:
                data.properties.clear('HP_Per_Hero')
        if not checked_only or self._boost_chk.isChecked():
            _commit('Boost', self._boost_le.text(), int)
        if not checked_only or self._threat_chk.isChecked():
            _commit('Threat', self._threat_le.text(), int)
        if not checked_only or self._base_threat_chk.isChecked():
            _commit('BaseThreat', self._base_threat_le.text(), int)
        if not checked_only or self._fixed_base_threat_chk.isChecked():
            _txt = self._fixed_base_threat_cb.currentText()
            if _txt in ('True', 'False'):
                data.properties.set('BaseThreatFixed', _txt)
            else:
                data.properties.clear('BaseThreatFixed')
        if not checked_only or self._esc_threat_chk.isChecked():
            _commit('EscalationThreat', self._esc_threat_le.text(), int)
        if not checked_only or self._fixed_esc_threat_chk.isChecked():
            _txt = self._fixed_esc_threat_cb.currentText()
            if _txt in ('True', 'False'):
                data.properties.set('EscalationThreatFixed', _txt)
            else:
                data.properties.clear('EscalationThreatFixed')
        if not checked_only or self._accel_chk.isChecked():
            _commit('Scheme_Acceleration', self._accel_le.text(), int)
        if not checked_only or self._crisis_chk.isChecked():
            _commit('Scheme_Crisis', self._crisis_le.text(), int)
        if not checked_only or self._hazard_chk.isChecked():
            _commit('Scheme_Hazard', self._hazard_le.text(), int)

    def commit_current(self):
        """Commits the dialog with the current inputs and selected data."""
        index = self._dialog._card_cb.currentIndex()
        try:
            self.commit(index)
        except Exception as e:
            self._err('Exception', 'Exception performing operation: {e}')

    def _err(self, s1, s2):
        ErrorDialog(s1, s2).exec()


class OctgnImageViewer(QtWidgets.QWidget):
    """Show card front (or alt) image in OCTGN data dialog."""

    def __init__(self, dialog, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._dialog = dialog
        self._img_cache = dict()  # (width, height, scaled)
        self._paint_img = None

    @QtCore.Slot()
    def cardSelected(self, index):
        if index < 0:
            self._paint_img = None
            self.repaint()
            return
        pos, is_alt, card, data = self._dialog._cards[index]
        if is_alt:
            img = card.specified_back_img
        else:
            img = card.front_img
        width = self.width()
        height = int(card._calcWidgetAspectHeight(width))

        scaled_img = None
        if id(img) in self._img_cache:
            _w, _h, _scaled = self._img_cache[id(img)]
            if width == _w and height == _h:
                scaled_img = _scaled
            else:
                self._img_cache.pop(id(img))
        if not scaled_img:
            scaled_img = img.scaled(width, height,
                                    mode=QtCore.Qt.SmoothTransformation)
            self._img_cache[id(img)] = (width, height, scaled_img)
        self._paint_img = scaled_img

        if height != self.height():
            self.setFixedHeight(height)

        self.repaint()

    def resizeEvent(self, event):
        # Forces rescale and repaint if size changed
        self.cardSelected(self._dialog._card_cb.currentIndex())

    def paintEvent(self, event):
        if self._paint_img:
            painter = QtGui.QPainter(self)
            painter.drawImage(QtCore.QPoint(0, 0), self._paint_img)
            painter.end()


class OctgnUuidValidator(QtGui.QValidator):
    """Validator for UUID arguments."""

    def validate(self, s, i):
        valid_chars = set('1234567890abcdef-')
        for c in s:
            if c not in valid_chars:
                return QtGui.QValidator.Invalid
        try:
            uuid.UUID('{' + s + '}')
        except Exception:
            return QtGui.QValidator.Intermediate
        else:
            return QtGui.QValidator.Acceptable
