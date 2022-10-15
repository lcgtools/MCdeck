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

import functools
import importlib
import os
import pathlib
import shutil
import uuid
import zipfile
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

    _octgn_sets = None

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

    def to_str(self, cards, dup_ok=True):
        """Generates string representation of a data for a card set.

        :param  cards: list of (front) card data for cards in set (in order)
        :type   cards: list(:class:`OctgnCardData`)
        :param dup_ok: if True allow duplicate card IDs on cards
        :return:       encoded string representation
        :rtype:        str

        String representation starts with a line "CARDSET:[set_id]:[name]"
        followed by a blank line. After this follows a concatenation of the
        string representation of each card in 'cards' (in order), with each
        set separated by an empty line.

        Duplicate copies would happen if a deck has multiple copies of the
        same card, but also if the same ID was set on two different cards
        by mistake.

        """
        if not dup_ok:
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
    def load_all_octgn_sets(cls, data_path=None, force=False):
        """Parse the OCTGN card database (if not already parsed).

        :param data_path: path to the OCTGN Data/ directory
        :param     force: if True, reload the OCTGN database

        """
        if force:
            cls._octgn_sets = None
        elif cls._octgn_sets:
            return

        data_path = OctgnCardSetData.get_octgn_data_path(data_path, val=True)

        db_sets_root = os.path.join(data_path, 'GameDatabase', mc_game_id,
                                    'Sets')
        set_files = dict()
        for path, subdirs, files in os.walk(db_sets_root):
            for f in files:
                if f.lower() == 'set.xml':
                    set_dir = os.path.relpath(path, db_sets_root)
                    try:
                        set_id = str(uuid.UUID('{' + set_dir + '}'))
                    except ValueError:
                        pass
                    else:
                        filename = os.path.join(path, f)
                        set_files[set_id] = filename

        card_sets = dict()
        Exc = LcgException
        for set_id, filename in set_files.items():
            try:
                _set = ElementTree.parse(filename).getroot()
                if _set.tag != 'set':
                    raise Exc('XML: missing <set> tag')
                name = _set.attrib['name']
                if set_id != _set.attrib['id']:
                    raise Exc('set.xml set ID does not match folder')
                card_set = OctgnCardSetData(name, set_id)
                cards = dict()
                for _cards in _set:
                    if not _cards.tag == 'cards':
                        raise Exc('XML: missing <cards> tag')
                    for c in _cards:
                        num_alt = 0
                        if not c.tag == 'card':
                            raise Exc('XML: expected <card> tag')
                        name = c.attrib['name']
                        card_id = c.attrib['id']
                        card = OctgnCardData(name, image_id=card_id)
                        props = card.properties
                        # card_size = card.attrib['size']
                        for prop in c:
                            if prop.tag == 'property':
                                name = prop.attrib['name']
                                if name not in ('Text', 'Quote'):
                                    value = prop.attrib['value']
                                else:
                                    value = prop.text
                                if value:
                                    props.set_from_string(name, value)
                            elif prop.tag == 'alternate':
                                if num_alt == 1:
                                    raise Exc('XML: too many <alternate> tags')
                                alt = prop
                                name = alt.attrib['name']
                                type_str = alt.attrib['type']
                                # size = alt.attrib['size']
                                _create = card.create_alt_card_data
                                alt_card = _create(name, type_str=type_str)
                                alt_props = alt_card.properties
                                for prop in alt:
                                    if prop.tag != 'property':
                                        raise Exc('Unexpected tag in <alt..>')
                                    name = prop.attrib['name']
                                    if name not in ('Text', 'Quote'):
                                        value = prop.attrib['value']
                                    else:
                                        value = prop.text
                                    if value:
                                        alt_props.set_from_string(name, value)
                            else:
                                raise Exc(f'XML: unexpected tag <{prop.tag}>')
                        cards[card_id] = card
                card_sets[set_id] = (card_set, cards)
            except Exception as e:
                print(f'Error parsing {filename}: {e}')
        cls._octgn_sets = card_sets

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
    def export_o8d_deck(cls, parent, deck):
        """Export a deck as an .o8d file.

        :param    parent: parent widget for dialogs
        :type     parent: :class:`QtWidgets.QWidget`
        :param      deck: the deck to export
        :type       deck: :class:`mcdeck.script.Deck`

        """
        err = lambda s1, s2: ErrorDialog(parent, s1, s2).exec()

        # Validate deck can be exported
        if not deck._octgn:
            raise RuntimeError('Should never happen')
        cards = deck._card_list_copy
        if not cards:
            _msg = 'The deck has no cards to export'
            err('Nothing to export', _msg)
            return
        for i, card in enumerate(cards):
            if not card._octgn:
                raise RuntimeError('Should never happen')
            if not card._octgn.image_id:
                err(f'Card without OCTGN card id', f'Card number {i + 1} '
                    f'(name "{card._octgn.name}") has no OCTGN card ID')
                return
            if card._octgn._o8d_type is None:
                err(f'Card without card type', f'Card number {i + 1} '
                    f'(name "{card._octgn.name}") does not have card type '
                    'set (need to edit OCTGN data on the Export tab)')
                return

        # Aggregate cards for .o8d encoding
        card_types = OctgnCardData._o8d_player_types.copy()
        card_types.extend(OctgnCardData._o8d_global_types.copy())
        card_d = dict()
        for i in range(len(card_types)):
            card_d[i] = dict()
        for card in cards:
            d = card_d[card._octgn._o8d_type]
            card_id = card._octgn.image_id
            if card_id not in d:
                d[card_id] = (card._octgn.name, 0)
            name, count = d[card_id]
            d[card_id] = (name, count + 1)

        # Encode .o8d deck as XML
        root = ElementTree.Element('deck')
        root.set('game', mc_game_id)
        # Encode player card types
        for i, c_type in enumerate(OctgnCardData._o8d_player_types):
            section = ElementTree.SubElement(root, 'section')
            section.set('name', c_type)
            section.set('shared', 'False')
            section_index = i
            for card_id, value in card_d[section_index].items():
                name, count = value
                card_e = ElementTree.SubElement(section, 'card')
                card_e.set('qty', str(count))
                card_e.set('id', card_id)
                if name:
                    card_e.text = name
        # Encode global card types
        for i, c_type in enumerate(OctgnCardData._o8d_global_types):
            section = ElementTree.SubElement(root, 'section')
            section.set('name', c_type)
            section.set('shared', 'True')
            section_index = i + len(OctgnCardData._o8d_player_types)
            for card_id, value in card_d[section_index].items():
                name, count = value
                card_e = ElementTree.SubElement(section, 'card')
                card_e.set('qty', str(count))
                card_e.set('id', card_id)
                if name:
                    card_e.text = name

        # Convert XML to string representation
        ElementTree.indent(root, '  ')
        s = ElementTree.tostring(root, encoding='utf-8',
                                 xml_declaration=True).decode('utf-8')
        # Workaround for missing option to set standalone in XML declaration
        s_list = s.splitlines()
        header = s_list[0]
        pos = header.find('?>')
        header = header[:pos] + ' standalone=\'yes\'' + header[pos:]
        s_list[0] = header
        xml_encoding = '\n'.join(s_list)

        # Save file
        _get = QtWidgets.QFileDialog.getSaveFileName
        _filter = 'Zip files (*.o8d)'
        data_path = OctgnCardSetData.get_octgn_data_path()
        d = os.path.join(data_path, 'GameDatabase', mc_game_id, 'FanMade')
        if not os.path.isdir(d):
            d = os.path.join(data_path, 'Decks')
        if not os.path.isdir(d):
            d = None
        path, _f = _get(parent, 'Select deck filename', dir=d, filter=_filter)
        if not path:
            return
        with open(path, 'w') as f:
            f.write(xml_encoding)

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

        # Set data path for installation
        data_path = OctgnCardSetData.get_octgn_data_path(data_path, val=True)

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
        # Set data path for uninstalling
        data_path = OctgnCardSetData.get_octgn_data_path(data_path, val=True)

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
    def from_str(cls, *s, dup_ok=True):
        """Decodes string representation of a card data set with cards.

        :param      s: (list of) string(s)
        :param dup_ok: if True allow duplicate IDs in loaded card set
        :return:       tuple (card data set, list of card data)
        :rtype:        (:class:`OctgnCardSetData, [:class:`OctgnCardData`]`)

        Decodes data in the format generated by
        :meth:`OctgnCardSetData.to_str`.

        See :meth:`to_str` for information regarding the dup_ok parameter.

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
                if not dup_ok:
                    if card.image_id in _decoded_ids:
                        raise ValueError(f'Duplicate ID {card.image_id}')
                _decoded_ids.add(card.image_id)
            previous = card
        return (set_data, card_data)

    @classmethod
    def validate_octgn_data_path(cls, data_path=None):
        data_path = OctgnCardSetData.get_octgn_data_path(data_path, val=False)

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

    @classmethod
    def _standard_octgn_data_path(cls):
        return os.path.join(str(pathlib.Path.home()), 'AppData', 'Local',
                            'Programs', 'OCTGN', 'Data')

    @classmethod
    def get_octgn_data_path(cls, data_path=None, val=False):
        if not data_path:
            _mod = importlib.import_module('mcdeck.script')
            data_path = _mod.MCDeck.settings.octgn_path
            if not data_path:
                data_path = cls._standard_octgn_data_path()

        if val:
            cls.validate_octgn_data_path(data_path)

        return data_path


class OctgnCardData(object):
    """Card data for a single card object.

    :param     name: card name
    :type      name: str
    :param     prop: card properties (create empty set if None)
    :type      prop: :class:`OctgnProperties`
    :param image_id: uuid for front side image (random if None)
    :type  image_id: str

    """

    # External card data sources
    _source_internal = 0
    _source_marvelcdb = 1
    _source_octgn = 2

    # Card types for .o8d export
    _o8d_player_types = ['Cards', 'PreBuiltCards', 'Special', 'Nemesis',
                         'Setup']
    _o8d_global_types = ['Encounter', 'Side', 'Special', 'Villain', 'Scheme',
                         'Campaign', 'Removed', 'Setup', 'Recommended']

    def __init__(self, name, prop=None, image_id=None, _val_id=True,
                 _source=_source_internal):
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
        self._source = _source
        self._o8d_type = None

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
        c._o8d_type = self._o8d_type
        if self._alt_data:
            c.create_alt_card_data(self._alt_data._name, self._alt_data._prop,
                                   self._alt_data._type_str)
        return c

    def to_str(self):
        """Generates a multiline string representation of card data.

        :return: multiline string representation appropriate for .txt file
        :rtype:  str

        """
        o8d_type = self._o8d_type if self._o8d_type is not None else -1
        result = f'CARD:{self._image_id}:{o8d_type}:{self._name}\n'
        result += self._prop.to_str()
        return result

    def load_image(self, data_path=None):
        """Tries to load the card's image from the OCTGN images database.

        :param data_path: path to OCTGN Data/ directory (standard if None)
        :return:          loaded image (or None if not in image database)
        :rtype:           :class:`QtGui.QImage`

        """
        try:
            data_path = OctgnCardSetData.get_octgn_data_path(data_path,
                                                             val=True)
        except LcgException:
            return None

        img_root = os.path.join(data_path, 'ImageDatabase', mc_game_id, 'Sets')

        # Try to find an image file match in the OCTGN image database
        image_id = self.image_id
        img_path = None
        for path, subdirs, files in os.walk(img_root):
            for name in files:
                _split = name.split('.')
                if len(_split) != 2:
                    continue
                basename, extension = _split
                if basename != image_id:
                    continue
                if extension.lower() not in ('jpg', 'png'):
                    continue
                img_path = os.path.join(path, name)
                break
            if img_path:
                break
        else:
            # No match
            return None
        return QtGui.QImage(img_path)

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
            img_id, o8d_type, _split = _split[0], _split[1], _split[2:]
            if not _split:
                raise ValueError('Invalid card header: too few arguments')
            if not img_id:
                raise ValueError('Card must have card ID')
            img_id = str(uuid.UUID('{' + img_id + '}'))
            o8d_type = int(o8d_type)
            o8d_type = o8d_type if o8d_type >= 0 else None
            name = OctgnCardData._unescape_value(':'.join(_split))
            card = OctgnCardData(name, property, img_id)
            card._o8d_type = o8d_type
            return card
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
              'Unique': (tuple, None, ('True', 'False')),
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
              'HP_Per_Hero': (tuple, None, ('True', 'False')),

              # Schemes
              'Threat': (int, lambda x: x >= 0, None),
              'EscalationThreat': (int, lambda x: x >= 0, None),
              'EscalationThreatFixed': (tuple, None, ('True', 'False')),
              'BaseThreat': (int, lambda x: x >= 0, None),
              'BaseThreatFixed': (tuple, None, ('True', 'False')),
              'Scheme_Acceleration': (int, lambda x: x >= 0, None),
              'Scheme_Crisis': (int, lambda x: x >= 0, None),
              'Scheme_Hazard': (int, lambda x: x >= 0, None),
              'Scheme_Boost': (int, lambda x: x >= 0, None),

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

    def set_from_string(self, name, value):
        """Sets property of given name to given value represented as a string.

        :param  name: name of property to set
        :type   name: str
        :param value: value to set
        :type  value: str

        """
        if name not in OctgnProperties.fields:
            raise ValueError(f'{name} is not an allowed property name')
        f_type, f_val, f_params = OctgnProperties.fields[name]
        if f_type is int:
            if value == 'None':
                value = '0'
            elif value.lower() == 'x':
                # Cannot represent 'X' as number, we silently skip it
                return
            elif int(value) < 0:
                # We do not represent negative numbers, silently skip it
                return
            self.set(name, int(value))
        elif f_type is tuple:
            # Set as case insensitive; if no direct match, ignore case
            try:
                self.set(name, value)
            except ValueError as e:
                for _val in f_params:
                    if value.lower() == _val.lower():
                        self.set(name, _val)
                        break
                else:
                    raise(e)
        else:
            self.set(name, value)

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

    def __contains__(self, name):
        """True if property 'name' has been set."""
        return name in self.__data

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
                _mod = importlib.import_module('mcdeck.script')
                _mod.MCDeck.root.enableOctgn(True)

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
        self._export_tab = OctgnDataDialogDeckExportTab(self)
        self._data_tabs.addTab(self._export_tab, 'Export (.o8d)')
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
        for _tab in self._gen_tab, self._other_tab, self._export_tab:
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
            self._err('Exception', f'Exception performing operation: {e}')
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
        ErrorDialog(self, s1, s2).exec()


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
                    self._err('Exception', f'Exception: {e}')

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
                self._err('Exception', f'Exception performing operation: {e}')

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
            self._err('Exception', f'Exception performing operation: {e}')

    def _err(self, s1, s2):
        ErrorDialog(self, s1, s2).exec()


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
        row += 1
        self._sch_boost_chk = QtWidgets.QCheckBox()
        self._sch_boost_chk.setFocusPolicy(QtCore.Qt.ClickFocus)
        _l.addWidget(self._sch_boost_chk, row, 0)
        _l.addWidget(lbl('Hazard Icons:'), row, 1)
        self._sch_boost_le = QtWidgets.QLineEdit()
        self._sch_boost_le.setValidator(_int_val)
        self._sch_boost_le.setToolTip('Scheme\'s number of hazard icons')
        _l.addWidget(self._sch_boost_le, row, 2)
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
                    # Hazard icons
                    _val = prop.get('Scheme_Boost')
                    _val = '' if _val is None else str(_val)
                    self._sch_boost_le.setText(_val)
                else:
                    for w in (self._atk_le, self._thw_le, self._def_le,
                              self._rec_le, self._hp_le, self._atk_cost_le,
                              self._thw_cost_le, self._hand_size_le,
                              self._sch_le, self._boost_le, self._threat_le,
                              self._esc_threat_le, self._base_threat_le,
                              self._accel_le, self._crisis_le,
                              self._hazard_le, self._sch_boost_le):
                        w.setText('')
                    for w in (self._hp_per_hero_cb, self._fixed_base_threat_cb,
                              self._fixed_esc_threat_cb):
                        w.setCurrentText('')

                self._current_index = index
            except Exception as e:
                self._err('Exception', f'Exception performing operation: {e}')

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
                  self._accel_chk, self._crisis_chk, self._hazard_chk,
                  self._sch_boost_chk):
            w.setChecked(True)

    @QtCore.Slot()
    def markNone(self):
        for w in (self._atk_chk, self._thw_chk, self._def_chk,
                  self._rec_chk, self._hp_chk, self._atk_cost_chk,
                  self._thw_cost_chk, self._hand_size_chk, self._atk2_chk,
                  self._sch_chk, self._hp2_chk, self._hp_per_hero_chk,
                  self._boost_chk, self._threat_chk, self._esc_threat_chk,
                  self._base_threat_chk, self._fix_base_threat_chk,
                  self._accel_chk, self._crisis_chk, self._hazard_chk,
                  self._sch_boost_chk):
            w.setChecked(False)

    @QtCore.Slot()
    def applyAll(self):
        # Commit currently selected values for all card data
        for index in range(self._dialog._card_cb.count()):
            try:
                self.commit(index, checked_only=True)
            except Exception as e:
                self._err('Exception', f'Exception performing operation: {e}')

    @QtCore.Slot()
    def enableTabDataInput(self, enable):
        for w in (self._atk_le, self._thw_le, self._def_le, self._rec_le,
                  self._hp_le, self._atk_cost_le, self._thw_cost_le,
                  self._hand_size_le, self._atk2_le, self._sch_le,
                  self._hp2_le, self._boost_le, self._threat_le,
                  self._esc_threat_le, self._base_threat_le,
                  self._accel_le, self._crisis_le, self._hazard_le,
                  self._sch_boost_le, self._hp_per_hero_cb,
                  self._fixed_base_threat_cb, self._fixed_esc_threat_cb):
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
        if not checked_only or self._sch_boost_chk.isChecked():
            _commit('Scheme_Boost', self._sch_boost_le.text(), int)

    def commit_current(self):
        """Commits the dialog with the current inputs and selected data."""
        index = self._dialog._card_cb.currentIndex()
        try:
            self.commit(index)
        except Exception as e:
            self._err('Exception', f'Exception performing operation: {e}')

    def _err(self, s1, s2):
        ErrorDialog(self, s1, s2).exec()


class OctgnDataDialogDeckExportTab(QtWidgets.QWidget):
    """Tab for settings related to .o8d export."""

    def __init__(self, dialog, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._dialog = dialog
        self._current_index = -1

        lbl = QtWidgets.QLabel
        _int_val = QtGui.QIntValidator()
        _int_val.setBottom(0)
        main_layout = QtWidgets.QVBoxLayout()
        _txt_l = lbl('Note: This setting is not a property of the card itself;'
                     ' it applies (only) when exporting the deck as an OCTGN '
                     'deck (not a card set) with the .o8d extension.')
        main_layout.addWidget(_txt_l)

        # Card type for .o8d export
        _box = QtWidgets.QGroupBox()
        _box.setTitle('Card type for .o8d export')
        _l = QtWidgets.QHBoxLayout()
        self._card_type_chk = QtWidgets.QCheckBox()
        self._card_type_chk.setFocusPolicy(QtCore.Qt.ClickFocus)
        _l.addWidget(self._card_type_chk)
        _l.addWidget(lbl('Card Type:'))
        self._card_type_cb = QtWidgets.QComboBox()
        for type_name in OctgnCardData._o8d_player_types:
            self._card_type_cb.addItem(f'{type_name} (Player)')
        for type_name in OctgnCardData._o8d_global_types:
            self._card_type_cb.addItem(f'{type_name} (Global)')
        _l.addWidget(self._card_type_cb)
        _l.addStretch(1)
        _box.setLayout(_l)
        main_layout.addWidget(_box)

        # Bottom "apply all" button
        _apply_l = QtWidgets.QHBoxLayout()
        self._mark_all_btn = QtWidgets.QPushButton('Mark all')
        self._mark_all_btn.setToolTip('Set all checkmarks')
        _apply_l.addWidget(self._mark_all_btn)
        self._mark_none_btn = QtWidgets.QPushButton('Mark none')
        self._mark_none_btn.setToolTip('Clear all checkmarks')
        _apply_l.addWidget(self._mark_none_btn)
        _apply_l.addStretch(1)
        self._auto_detect_btn = QtWidgets.QPushButton('Auto-detect')
        _tip = ('For all cards, if the card type is not set, try to guess a '
                'reasonable value based on other card properties')
        self._auto_detect_btn.setToolTip(_tip)
        _apply_l.addWidget(self._auto_detect_btn)
        self._apply_all_btn = QtWidgets.QPushButton('Apply marked')
        _tip = ('Apply data in checked fields to all cards in the card list')
        self._apply_all_btn.setToolTip(_tip)
        _apply_l.addWidget(self._apply_all_btn)
        main_layout.addLayout(_apply_l)
        main_layout.addStretch(1)
        self.setLayout(main_layout)

        self._mark_all_btn.clicked.connect(self.markAll)
        self._mark_none_btn.clicked.connect(self.markNone)
        self._auto_detect_btn.clicked.connect(self.autoDetect)
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
                if data and not is_alt:
                    o8d_t = -1 if data._o8d_type is None else data._o8d_type
                    self._card_type_cb.setCurrentIndex(o8d_t)
                    self._card_type_cb.setEnabled(True)
                else:
                    self._card_type_cb.setCurrentIndex(-1)
                    self._card_type_cb.setEnabled(False)

            except Exception as e:
                self._err('Exception', f'Exception performing operation: {e}')

    @QtCore.Slot()
    def markAll(self):
        for w in (self._card_type_chk,):
            w.setChecked(True)

    @QtCore.Slot()
    def markNone(self):
        for w in (self._card_type_chk,):
            w.setChecked(False)

    @QtCore.Slot()
    def autoDetect(self):
        # Try to set default value based on card type. Note: unable to
        # categorize nemesis cards (they are added as encounters), as well as
        # e.g. special cards. Also, all player cards are considered "Cards"
        # rather than Pre-Made.
        for pos, is_alt, card, data in self._dialog._cards:
            if data._o8d_type is None:
                _type = data.properties.get('Type')
                _owner = data.properties.get('Owner')

                if _type in ('hero', 'alter_ego', 'ally', 'event', 'resource',
                             'support', 'upgrade'):
                    o8d_type = 0  # Card (Player)
                elif _type == 'obligation':
                    o8d_type = 3  # Nemesis (Player)
                elif _type in ('minion', 'attachment', 'treachery',
                               'environment'):
                    # (Try to) categorize nemesis cards based on Owner name
                    if _owner and _owner.lower().endswith('_nemesis'):
                        o8d_type = 3  # Nemesis (Player)
                    else:
                        o8d_type = 5  # Encounter (Global)
                elif _type == 'side_scheme':
                    # (Try to) categorize nemesis cards based on Owner name
                    if _owner and _owner.lower().endswith('_nemesis'):
                        o8d_type = 3  # Nemesis (Player)
                    else:
                        o8d_type = 6  # Scheme (Global)
                elif _type == 'villain':
                    o8d_type = 8  # Villain (Global)
                elif _type == 'main_scheme':
                    o8d_type = 9  # Scheme (Global)
                else:
                    o8d_type = None  # Unknown; cannot infer
                if o8d_type is not None:
                    data._o8d_type = o8d_type

        # A trick to refresh widgets on this tab
        idx = self._current_index
        self.cardSelected(-1)
        self.cardSelected(idx)

    @QtCore.Slot()
    def applyAll(self):
        # Commit currently selected values for all card data
        for index in range(self._dialog._card_cb.count()):
            try:
                self.commit(index, checked_only=True)
            except Exception as e:
                self._err('Exception', f'Exception performing operation: {e}')

    @QtCore.Slot()
    def enableTabDataInput(self, enable):
        for w in (self._card_type_chk,):
            w.setEnabled(enable)

    def commit(self, index, checked_only=False):
        """Commit the dialog inputs to card data.

        :param        index: the index of the card for which to commit data
        :param checked_only: if True only commit checked values

        """
        pos, is_alt, card, data = self._dialog._cards[index]
        if data and not is_alt:
            value = self._card_type_cb.currentIndex()
            if value >= 0:
                data._o8d_type = value

    def commit_current(self):
        """Commits the dialog with the current inputs and selected data."""
        index = self._dialog._card_cb.currentIndex()
        self.commit(index)

    def _err(self, s1, s2):
        ErrorDialog(self, s1, s2).exec()


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


class OctgnCardImportDialog(QtWidgets.QDialog):
    """Dialog for importing cards directly from local OCTGN installation."""

    _Card = None    # Reference to the class mcdeck.script.Card
    _MCDeck = None  # Reference to the class mcdeck.script.MCDeck

    addedCards = QtCore.Signal()
    selectedSingleCardId = QtCore.Signal(str)

    def __init__(self, parent=None, data_path=None):
        super().__init__(parent)
        self.setWindowTitle('Import cards from OCTGN')

        if OctgnCardImportDialog._Card is None:
            _mod = importlib.import_module('mcdeck.script')
            OctgnCardImportDialog._Card = _mod.Card
            OctgnCardImportDialog._MCDeck = _mod.MCDeck

        err = lambda s1, s2: ErrorDialog(self.parentWidget(), s1, s2).exec()
        try:
            _fun = OctgnCardSetData.get_octgn_data_path
            data_path = _fun(data_path, val=True)
        except Exception as e:
            raise LcgException(f'Invalid OCTGN Data/ dir {data_path}: {e}')
        OctgnCardSetData.load_all_octgn_sets(data_path)
        self._data_path = data_path
        self._filtered_db = None
        self._imported_cards = False

        # Create an index of all installed OCTGN card images
        self._image_d = dict()
        image_root = os.path.join(data_path, 'ImageDatabase', mc_game_id,
                                  'Sets')
        for path, subdirs, files in os.walk(image_root):
            for f in files:
                base, ext = f[:-4], f[-4:]
                if ext.lower() in ('.png', '.jpg'):
                    if '.' not in base:
                        guid = base
                    else:
                        guid = base[:-2]
                try:
                    uuid.UUID('{' + guid + '}')
                except ValueError:
                    pass
                else:
                    self._image_d[base.lower()] = os.path.join(path, f)

        main_layout = QtWidgets.QVBoxLayout()

        # Card set information
        box = QtWidgets.QGroupBox('Filter: Set/owner')
        lbl = QtWidgets.QLabel
        box_l = QtWidgets.QHBoxLayout()
        box_l.addWidget(lbl('Set Name:'))
        self._set_name_cb = QtWidgets.QComboBox()
        _tip = 'Name of the card set'
        self._set_name_cb.setToolTip(_tip)
        box_l.addWidget(self._set_name_cb)
        box_l.addWidget(lbl('Set Id:'))
        self._set_id_le = QtWidgets.QLineEdit()
        _tip = 'Card set\'s unique (GUID) identifier'
        self._set_id_le.setToolTip(_tip)
        box_l.addWidget(self._set_id_le)
        box_l.addWidget(lbl('Owner:'))
        self._owner_cb = QtWidgets.QComboBox()
        _tip = 'Owner - typically identifies (part of) a card set'
        self._owner_cb.setToolTip(_tip)
        box_l.addWidget(self._owner_cb)
        box.setLayout(box_l)
        main_layout.addWidget(box)
        # Card information
        box = QtWidgets.QGroupBox('Filter: Card')
        box_l = QtWidgets.QVBoxLayout()
        line_l = QtWidgets.QHBoxLayout()
        line_l.addWidget(lbl('Name:'))
        self._card_name_le = QtWidgets.QLineEdit()
        self._card_name_le.setToolTip('Card name')
        line_l.addWidget(self._card_name_le)
        line_l.addWidget(lbl('Type:'))
        self._card_type_cb = QtWidgets.QComboBox()
        self._card_type_cb.setToolTip('Card type')
        line_l.addWidget(self._card_type_cb)
        line_l.addWidget(lbl('Attribute(s):'))
        self._card_attribute_le = QtWidgets.QLineEdit()
        _tip = 'Attribute(s) printed under card image.'
        self._card_attribute_le.setToolTip(_tip)
        line_l.addWidget(self._card_attribute_le)
        line_l.addWidget(lbl('Text:'))
        self._card_text_le = QtWidgets.QLineEdit()
        _tip = 'Text printed on card.'
        self._card_text_le.setToolTip(_tip)
        line_l.addWidget(self._card_text_le)
        line_l.addWidget(lbl('Id:'))
        self._card_id_le = QtWidgets.QLineEdit()
        self._card_id_le.setToolTip('Card\'s unique (GUID) identifier')
        line_l.addWidget(self._card_id_le)
        box_l.addLayout(line_l)
        box.setLayout(box_l)
        main_layout.addWidget(box)
        # Card properties
        box = QtWidgets.QGroupBox('Filter: Card properties')
        box_l = QtWidgets.QVBoxLayout()
        line_l = QtWidgets.QHBoxLayout()
        line_l.addWidget(lbl('Cost:'))
        self._card_cost_le = QtWidgets.QLineEdit()
        self._card_cost_le.setToolTip('Printed card cost')
        _int_val = QtGui.QIntValidator()
        self._card_cost_le.setValidator(_int_val)
        line_l.addWidget(self._card_cost_le)
        line_l.addWidget(lbl('Res. Physical:'))
        self._card_r_phy_le = QtWidgets.QLineEdit()
        self._card_r_phy_le.setToolTip('Physical resources printed on card')
        self._card_r_phy_le.setValidator(_int_val)
        line_l.addWidget(self._card_r_phy_le)
        line_l.addWidget(lbl('Res. Mental:'))
        self._card_r_men_le = QtWidgets.QLineEdit()
        self._card_r_men_le.setToolTip('Mental resources printed on card')
        self._card_r_men_le.setValidator(_int_val)
        line_l.addWidget(self._card_r_men_le)
        line_l.addWidget(lbl('Res. Energy:'))
        self._card_r_ene_le = QtWidgets.QLineEdit()
        self._card_r_ene_le.setToolTip('Energy resources printed on card')
        self._card_r_ene_le.setValidator(_int_val)
        line_l.addWidget(self._card_r_ene_le)
        line_l.addWidget(lbl('Res. Wild:'))
        self._card_r_wild_le = QtWidgets.QLineEdit()
        self._card_r_wild_le.setToolTip('Wild resources printed on card')
        self._card_r_wild_le.setValidator(_int_val)
        line_l.addWidget(self._card_r_wild_le)
        box_l.addLayout(line_l)
        line_l = QtWidgets.QHBoxLayout()
        line_l.addWidget(lbl('Filter:'))
        self._filter_le = QtWidgets.QLineEdit()
        _tip = ('Enter filter command. Filter expressions can be:\n\n'
                '[key]# (key is defined),  [key]$ (key is undefined)\n'
                '[key]:[val] (key contains), [key]!:[val] (does not contain)\n'
                '[key]=[val] (key equals), [key]!=[val] (unequal)\n'
                '[key][op][val] with [op] one of <=, >=, < or > (comparison)\n'
                '\n[key] is a unique (sub)string of one of: Type, CardNumber, '
                'Unique, Cost, Attribute, Text, Resource_Physical,\n'
                'Resource_Mental, Resource_Energy, Resource_Wild, Quote, '
                'Owner, Attack, Thwart, Defense, Recovery, Scheme,\n'
                'AttackCost, ThwartCost, HandSize, HP, HP_Per_Hero, Threat, '
                'EscalationThreat, EscalationThreatFixed, BaseThreat,\n'
                'BaseThreatFixed, Scheme_Acceleration, Scheme_Crisis, '
                'Scheme_Hazard, Scheme_Boost, Boost\n\n'
                'Expressions can be surrounded by () parentheses. Placing '
                '& operator between expressions yields an expression which\n'
                'the logical and of the individual expressions, and similar '
                'with | for logical or.')
        self._filter_le.setToolTip(_tip)
        line_l.addWidget(self._filter_le)
        box_l.addLayout(line_l)
        box.setLayout(box_l)
        main_layout.addWidget(box)

        # Show filter results
        box = QtWidgets.QGroupBox('Matches')
        box_l = QtWidgets.QVBoxLayout()
        line_l = QtWidgets.QHBoxLayout()
        _l = QtWidgets.QVBoxLayout()
        _l2 = QtWidgets.QHBoxLayout()
        self._include_no_img_chk = QtWidgets.QCheckBox()
        _tip = ('If not checked, exclude cards in OCTGN database without '
                'installed card image(s)')
        self._include_no_img_chk.setToolTip(_tip)
        self._include_no_img_chk.setChecked(False)
        _l2.addWidget(self._include_no_img_chk)
        _l2.addWidget(lbl('No img ok'))
        #_l2.addStretch(1)
        self._only_alt_chk = QtWidgets.QCheckBox()
        self._only_alt_chk.setToolTip('Only list 2-sided cards')
        self._only_alt_chk.setChecked(False)
        _l2.addWidget(self._only_alt_chk)
        _l2.addWidget(lbl('2-sided'))
        _l2.addStretch(1)
        self._show_alt_chk = QtWidgets.QCheckBox()
        self._show_alt_chk.setToolTip('Show alt-side info for 2-sided cards')
        self._show_alt_chk.setChecked(False)
        _l2.addWidget(self._show_alt_chk)
        _l2.addWidget(lbl('Alt card'))
        self._show_stats_chk = QtWidgets.QCheckBox()
        self._show_stats_chk.setToolTip('Include key card stats')
        self._show_stats_chk.setChecked(False)
        _l2.addWidget(self._show_stats_chk)
        _l2.addWidget(lbl('Stats'))
        self._show_attr_chk = QtWidgets.QCheckBox()
        _tip = 'Include attributes printed under card image'
        self._show_attr_chk.setToolTip(_tip)
        self._show_attr_chk.setChecked(False)
        _l2.addWidget(self._show_attr_chk)
        _l2.addWidget(lbl('Attribute(s)'))
        self._show_owner_chk = QtWidgets.QCheckBox()
        self._show_owner_chk.setToolTip('Include card owner entry')
        self._show_owner_chk.setChecked(False)
        _l2.addWidget(self._show_owner_chk)
        _l2.addWidget(lbl('Owner'))
        _l.addLayout(_l2)
        self._matches_lw = QtWidgets.QListWidget()
        _tip = ('Filtered card index. Use "Add to Deck" or double-click to '
                'import card(s).')
        self._matches_lw.setToolTip(_tip)
        _mode = QtWidgets.QAbstractItemView.ExtendedSelection
        self._matches_lw.setSelectionMode(_mode)
        self._matches_lw.itemSelectionChanged.connect(self.cardSelectionChange)
        self._matches_lw.itemDoubleClicked.connect(self.doubleClickAddCard)
        self._matches_data = []  # data objects for each line in list
        _l.addWidget(self._matches_lw, 1)
        line_l.addLayout(_l, 3)
        _l = QtWidgets.QVBoxLayout()
        _l2 = QtWidgets.QHBoxLayout()
        _l2.addStretch(1)
        self._show_back_chk = QtWidgets.QCheckBox()
        _tip = ('If the card has a back side, show that image instead of the '
                'front side image')
        self._show_back_chk.setToolTip(_tip)
        self._show_back_chk.stateChanged.connect(self.cardSelectionChange)
        _l2.addWidget(self._show_back_chk)
        _l2.addWidget(lbl('Show back side (if any)'))
        _l2.addStretch(1)
        _l.addLayout(_l2)
        self._image_viewer = OctgnDbImageViewer(self)
        self._image_viewer.setMinimumWidth(400)
        self.selectedSingleCardId.connect(self._image_viewer.showCard)
        _l.addWidget(self._image_viewer, 1)
        line_l.addLayout(_l, 1)
        box_l.addLayout(line_l)
        line_l = QtWidgets.QHBoxLayout()
        self._match_status_lbl = QtWidgets.QLabel('')
        line_l.addWidget(self._match_status_lbl)
        line_l.addStretch(1)
        line_l.addWidget(lbl('.o8d card type'))
        self._o8d_card_type_cb = QtWidgets.QComboBox()
        _tip = ('Set card type for .o8d files; if (Automatic) then the '
                'importer tries to set an appropriate value (not always )'
                'possible, e.g. hero nemesis cards cannot be identified)')
        self._o8d_card_type_cb.setToolTip(_tip)
        self._o8d_card_type_cb.addItem('(Automatic)')
        for _t in OctgnCardData._o8d_player_types:
            self._o8d_card_type_cb.addItem(f'{_t} (Player)')
        for _t in OctgnCardData._o8d_global_types:
            self._o8d_card_type_cb.addItem(f'{_t} (Global)')
        line_l.addWidget(self._o8d_card_type_cb)
        line_l.addStretch(1)
        self._add_cards_btn = QtWidgets.QPushButton('Add to Deck')
        self._add_cards_btn.setToolTip('Add selected card(s) to the deck')
        self._add_cards_btn.setEnabled(False)
        self._add_cards_btn.clicked.connect(self.AddCardsAction)
        line_l.addWidget(self._add_cards_btn)
        box_l.addLayout(line_l)
        box.setLayout(box_l)
        main_layout.addWidget(box, 1)

        # Status line
        line_l = QtWidgets.QHBoxLayout()
        self._filter_status_le = QtWidgets.QLabel()
        line_l.addWidget(self._filter_status_le)
        line_l.addStretch(1)
        if not self._MCDeck.deck._octgn:
            # If OCTGN data not enabled, add a message about that
            line_l.addWidget(lbl('Note: Importing enables OCTGN metadata'))
        main_layout.addLayout(line_l)

        # Buttons
        line_l = QtWidgets.QHBoxLayout()
        self._clear_filters_btn = QtWidgets.QPushButton('Clear Filters')
        self._clear_filters_btn.setToolTip('Clear all filter values')
        self._clear_filters_btn.clicked.connect(self.clearFilters)
        line_l.addWidget(self._clear_filters_btn)
        self._restrict_btn = QtWidgets.QPushButton('Restrict Index')
        _tip = ('Restricts the card index to the card set that is currently '
                'listed; this allows further filtering on the current set '
                'of cards.')
        self._restrict_btn.setToolTip(_tip)
        self._restrict_btn.clicked.connect(self.restrictAction)
        line_l.addWidget(self._restrict_btn)
        self._full_btn = QtWidgets.QPushButton('Full Index')
        _tip = ('Undo the effects of Restrict Index (reset the card index to '
                'the full set of cards available in the OCTGN database)')
        self._full_btn.setToolTip(_tip)
        self._full_btn.clicked.connect(self.fullIndexAction)
        line_l.addWidget(self._full_btn)
        self._reset_all_btn = QtWidgets.QPushButton('Reset All')
        self._reset_all_btn.setToolTip('Clear filters and reset to full index')
        self._reset_all_btn.clicked.connect(self.resetAllAction)
        line_l.addWidget(self._reset_all_btn)
        line_l.addStretch(1)
        self._done_btn = QtWidgets.QPushButton('Done')
        self._done_btn.setDefault(True)
        self._done_btn.clicked.connect(self.accept)
        line_l.addWidget(self._done_btn)
        main_layout.addLayout(line_l)

        # Populate combo boxes
        self._reset_filter_cb_values()

        box.setLayout(box_l)
        self.setLayout(main_layout)

        for _w in (self._set_id_le, self._card_name_le,
                   self._card_attribute_le, self._card_text_le,
                   self._card_id_le, self._card_cost_le, self._card_r_phy_le,
                   self._card_r_men_le, self._card_r_ene_le,
                   self._card_r_wild_le, self._filter_le):
            _w.textChanged.connect(self.filterUpdate)
        for _w in (self._include_no_img_chk, self._only_alt_chk):
            _w.stateChanged.connect(self.filterUpdate)
        for _w in (self._show_attr_chk, self._show_stats_chk,
                   self._show_alt_chk, self._show_owner_chk):
            _w.stateChanged.connect(self.infoChoiceUpdate)
        for _w in (self._set_name_cb, self._owner_cb, self._card_type_cb):
            _w.currentIndexChanged.connect(self.filterUpdate)

        # Update cards list
        self.filterUpdate()

    @QtCore.Slot()
    def infoChoiceUpdate(self):
        self.filterUpdate(keep_selection=True)

    @QtCore.Slot()
    def filterUpdate(self, *args, **kwargs):
        keep_selection = kwargs.get('keep_selection', False)
        if keep_selection:
            _sel = self._matches_lw.selectedItems()
            _sel = [self._matches_lw.indexFromItem(_item) for _item in _sel]

        filtered_db = self._apply_filter()

        matches = []
        for card_set, card_data_d in filtered_db.values():
            for card_data in card_data_d.values():
                matches.append(card_data)

        def _cmp(m1, m2):
            if m1.name < m2.name:
                return -1
            elif m1.name == m2.name:
                return 0
            else:
                return 1
        matches.sort(key=functools.cmp_to_key(_cmp))

        self._matches_lw.clear()
        self._matches_data = []
        for card_data in matches:
            props = card_data.properties

            # If specified, exclude cards without an image
            if not self._include_no_img_chk.isChecked():
                if not card_data.image_id in self._image_d:
                    continue
                if card_data.alt_data:
                    if card_data.alt_data.image_id not in self._image_d:
                        continue

            # If specified, include only 2-sided cards
            if self._only_alt_chk.isChecked() and not card_data.alt_data:
                continue

            # If specified, show alt card information for 2-sided card
            front_data = card_data
            if self._show_alt_chk.isChecked() and card_data.alt_data:
                card_data = card_data.alt_data

            _get = lambda k: props.get(k) if k in props else None
            _get_l = lambda k: props.get(k).lower() if k in props else None
            _txt = card_data.name
            if _get_l('Unique') == 'true':
                _txt += ' ✦'
            _stats = []
            if self._show_stats_chk.isChecked():
                # Type
                if not self._card_type_cb.currentText():
                    _typ = _get('Type')
                    if _typ is not None:
                        _stats.append(_typ)
                # Cost
                if not self._card_cost_le.text():
                    _cost = _get('Cost')
                    if _cost is not None:
                        _stats.append(f'€{_cost}')
                # Resources
                _res_l = []
                for s in ('Physical', 'Mental', 'Energy', 'Wild'):
                    _res_l.append(_get(f'Resource_{s}'))
                if sum(1 for v in _res_l if v) > 0:
                    _code = ('phy', 'mental', 'energy', 'wild')
                    for val, c in zip(_res_l, _code):
                        if val:
                            _stats.append(f'{c}:{val}')
                # Basic abilities
                def _fun(key, prefix):
                    _val = _get(key)
                    if _val is not None:
                        _stats.append(f'{prefix}:{_val}')
                _l = (('HP', 'hp'), ('Attack', 'atk'), ('Thwart', 'thw'),
                      ('Defense', 'def'), ('Recovery', 'rec'),
                      ('Scheme', 'sch'), ('AttackCost', 'a€'),
                      ('ThwartCost', 't€'))
                for key, pre in _l:
                    _fun(key, pre)
                _val = _get('Boost')
                if _val is not None and int(_val) > 0:
                    _stats.append('✭'*int(_val))
                _l = (('Threat', 'threat'), ('EscalationThreat', 'esc.threat'),
                      ('BaseThreat', 'basethreat'),
                      ('Scheme_Acceleration', 'acceleration'),
                      ('Scheme_Crisis', 'crisis'), ('Scheme_Hazard', 'hazard'),
                      ('Scheme_Boost', 'scheme_boost'))

            if _stats:
                _txt += '   [' + ', '.join(_stats) + ']'

            if self._show_attr_chk.isChecked():
                # Attribute
                _attr = _get('Attribute')
                if _attr is not None:
                    _txt += (f'   {{{_attr}}}')

            if self._show_owner_chk.isChecked():
                # Attribute
                _attr = _get('Owner')
                if _attr is not None:
                    _txt += (f'   ({_attr})')

            if card_data.alt_data or isinstance(card_data, OctgnAltCardData):
                _txt += '   <2-sided>'

            self._matches_lw.addItem(_txt)
            self._matches_data.append(front_data)
        _status = f'{len(matches)} match(es)'
        if self._filtered_db is not None:
            _status += '. Acting on a filtered database.'
        self._match_status_lbl.setText(_status)

        if keep_selection:
            _cmd = QtCore.QItemSelectionModel.Toggle
            for _index in _sel:
                _item = self._matches_lw.itemFromIndex(_index)
                self._matches_lw.setCurrentItem(_item, _cmd)

    @QtCore.Slot()
    def clearFilters(self, *args):
        for _w in (self._set_id_le, self._card_name_le,
                   self._card_attribute_le, self._card_text_le,
                   self._card_id_le, self._card_cost_le, self._card_r_phy_le,
                   self._card_r_men_le, self._card_r_ene_le,
                   self._card_r_wild_le, self._filter_le):
            _w.clear()
        for _w in (self._set_name_cb, self._owner_cb, self._card_type_cb):
            _w.setCurrentIndex(0)
        self._include_no_img_chk.setChecked(False)

    @QtCore.Slot()
    def restrictAction(self, *args):
        self._filtered_db = self._apply_filter()
        w_l = (self._set_name_cb, self._owner_cb, self._card_type_cb)
        t_l = [w.currentText() for w in w_l]
        self._reset_filter_cb_values()
        for w, t in zip(w_l, t_l):
            w.setCurrentText(t)
        self.filterUpdate()

    @QtCore.Slot()
    def fullIndexAction(self, *args):
        self._filtered_db = None
        w_l = (self._set_name_cb, self._owner_cb, self._card_type_cb)
        t_l = [w.currentText() for w in w_l]
        self._reset_filter_cb_values()
        for w, t in zip(w_l, t_l):
            w.setCurrentText(t)
        self.filterUpdate()

    @QtCore.Slot()
    def resetAllAction(self, *args):
        self.fullIndexAction()
        self.clearFilters()

    @QtCore.Slot()
    def cardSelectionChange(self, *args):
        selection = self._matches_lw.selectedItems()
        selection = [self._matches_lw.row(_item) for _item in selection]
        self._add_cards_btn.setEnabled(bool(selection))

        if len(selection) == 1:
            index, = selection
            card_data = self._matches_data[index]
            image_id = card_data.image_id
            if (self._show_back_chk.isChecked() or
                self._show_alt_chk.isChecked()):
                if card_data.alt_data and card_data.alt_data.image_id:
                    image_id = card_data.alt_data.image_id
            self.selectedSingleCardId.emit(image_id)
        else:
            self.selectedSingleCardId.emit(None)

    @QtCore.Slot()
    def doubleClickAddCard(self, item):
        num = self._matches_lw.row(item)
        card_data = self._matches_data[num]
        self._add_cards([card_data])

    @QtCore.Slot()
    def AddCardsAction(self, *args):
        selection = self._matches_lw.selectedItems()
        selection = [self._matches_lw.row(_item) for _item in selection]
        card_data_l = [self._matches_data[i] for i in selection]
        self._add_cards(card_data_l)

    def _add_cards(self, card_data_l):
        MCCard = OctgnCardImportDialog._Card
        MCDeck = OctgnCardImportDialog._MCDeck

        cards = []
        for card_data in card_data_l:
            front_img = QtGui.QImage(self._image_d[card_data.image_id])
            if front_img.isNull():
                break
            if card_data.alt_data:
                _fname = self._image_d[card_data.alt_data.image_id]
                back_img = QtGui.QImage(_fname)
                if back_img.isNull():
                    break
            else:
                back_img = None

            # Handle aspect transformation
            _images = [front_img, back_img]
            for i, img in enumerate(_images):
                if img:
                    img = LcgImage(img)
                    _s = MCDeck.settings
                    aspect_rotation = _s.aspect_rotation
                    if aspect_rotation != 'none':
                        if aspect_rotation == 'clockwise':
                            clockwise = True
                        if aspect_rotation == 'anticlockwise':
                            clockwise = False
                        else:
                            raise RuntimeError('Should never happen')
                        portrait = (_s.card_height_mm >= _s.card_width_mm)
                        c_portrait = (img.heightMm() >= img.widthMM())
                        if portrait ^ c_portrait:
                            # Wrong aspect, rotate
                            if clockwise:
                                img = img.rotateClockwise()
                            else:
                                img = img.rotateAntiClockwise()
                    _images[i] = img
            front_img, back_img = _images

            # Resolve card type
            _type = card_data.properties.get('Type')
            _owner = card_data.properties.get('Owner')
            if _type is not None:
                if _type in ('ally', 'alter_ego', 'event', 'resource',
                             'support', 'upgrade'):
                    c_type = MCCard.type_player
                elif _type in  ('side_scheme', 'attachment', 'environment',
                                'minion', 'obligation', 'treachery'):
                    c_type = MCCard.type_encounter
                elif _type == 'villain':
                    c_type = MCCard.type_villain
                else:
                    c_type = MCCard.type_unspecified

            card = MCCard(front=front_img, back=back_img, ctype=c_type)
            card._octgn = card_data.copy()
            # Set _o8d_type for .o8d exports
            o8d_type = self._o8d_card_type_cb.currentIndex()
            if o8d_type > 0:
                o8d_type -= 1
            else:
                # Try to set default value based on card type. Note: unable to
                # categorize nemesis cards (they are added as encounters), as
                # well as e.g. special cards. Also, all player cards are
                # considered "Cards" rather than Pre-Made.
                if _type in ('hero', 'alter_ego', 'ally', 'event', 'resource',
                             'support', 'upgrade'):
                    o8d_type = 0  # Card (Player)
                elif _type == 'obligation':
                    o8d_type = 3  # Nemesis (Player)
                elif _type in ('minion', 'attachment', 'treachery',
                               'environment'):
                    # (Try to) categorize nemesis cards based on Owner name
                    if _owner and _owner.lower().endswith('_nemesis'):
                        o8d_type = 3  # Nemesis (Player)
                    else:
                        o8d_type = 5  # Encounter (Global)
                elif _type == 'side_scheme':
                    # (Try to) categorize nemesis cards based on Owner name
                    if _owner and _owner.lower().endswith('_nemesis'):
                        o8d_type = 3  # Nemesis (Player)
                    else:
                        o8d_type = 6  # Scheme (Global)
                elif _type == 'villain':
                    o8d_type = 8  # Villain (Global)
                elif _type == 'main_scheme':
                    o8d_type = 9  # Scheme (Global)
                else:
                    o8d_type = None  # Unknown; cannot infer
            card._octgn._o8d_type = o8d_type
            cards.append(card)
        else:
            if cards:
                if not MCDeck.deck._octgn:
                    MCDeck.root.menu_octgn_enable()
                for card in cards:
                    MCDeck.deck.addCardObject(card)
                    self._imported_cards = True
                self.addedCards.emit()
            return

        # If we did not return in else: clause, one of the card imports failed
        err = lambda s1, s2: ErrorDialog(self, s1, s2).exec()
        _msg = f'Was unable to import card {card_data.name}'
        err(self, 'Card import error', _msg)

    def _apply_filter(self):
        """Apply filters to db being acted on, and generate filtered db."""
        str_f_le_l = (('Attribute', self._card_attribute_le),
                      ('Text', self._card_text_le))
        str_f_cb_l = (('Type', self._card_type_cb),
                      ('Owner', self._owner_cb))
        int_f_le_l = (('Cost', self._card_cost_le),
                      ('Resource_Physical', self._card_r_phy_le),
                      ('Resource_Mental', self._card_r_men_le),
                      ('Resource_Energy', self._card_r_ene_le),
                      ('Resource_Wild', self._card_r_wild_le))

        filtered_d = dict()
        # print('IN:\n', filtered_d)  # OUTPUT
        _str_match = lambda c, t: self._is_filter_match(c, t, or_char='|',
                                                        and_char='&')

        db = self._filtered_db
        db = OctgnCardSetData._octgn_sets if db is None else db
        for set_id, value in db.items():
            card_set, card_data_d = value
            _val = self._set_name_cb.currentText()
            if _val and _val != card_set.name:
                continue
            if not _str_match(self._set_id_le.text(), set_id):
                continue
            for card_id, card_data in card_data_d.items():
                _l = ((self._card_name_le.text(), card_data.name),
                      (self._card_id_le.text(), card_id))
                _match = True
                for cr, t_v in _l:
                    if not _str_match(cr, t_v):
                        _match = False
                        break
                if not _match:
                    continue

                # Handle string matching with '&' as delimiter
                _match = True
                for _key, _w in str_f_le_l:
                    _criteria = _w.text().strip()
                    if not _criteria:
                        continue
                    _test_val = card_data.properties.get(_key)
                    if not _criteria.strip():
                        # Blank criteria is not tested against
                        continue
                    if not _test_val:
                        _match = False
                        break
                    if not _str_match(_criteria, _test_val):
                        _match = False
                        break
                if not _match:
                    continue
                _match = True
                for _key, _w in str_f_cb_l:
                    criteria = _w.currentText().strip()
                    if not criteria:
                        continue
                    _test_val = card_data.properties.get(_key)
                    if not _test_val:
                        _match = False
                        break
                    if criteria != _test_val:
                        _match = False
                        break
                if not _match:
                    continue

                # Handle integer value matching
                _match = True
                for _key, _w in int_f_le_l:
                    criteria = _w.text().strip()
                    if not criteria:
                        continue
                    criteria = int(criteria)
                    _test_val = card_data.properties.get(_key)
                    if _test_val is None:
                        _match = False
                        break
                    if criteria != _test_val:
                        _match = False
                        break
                if not _match:
                    continue

                # If we got this far, the card is a match - add to db
                if set_id not in filtered_d:
                    filtered_d[set_id] = (card_set, dict())
                c_data_d = filtered_d[set_id][1]
                c_data_d[card_id] = card_data

        # Parse generic filter field
        expr = self._filter_le.text()
        if expr:
            try:
                filtered_d = self._apply_filter_expression(filtered_d, expr)
            except Exception as e:
                self._filter_status_le.setText(f'Filter error: {e}')
                self._filter_le.setStyleSheet('color: red')
            else:
                self._filter_status_le.setText('')
                self._filter_le.setStyleSheet('color: black')
        return filtered_d

    def _apply_filter_expression(self, filter_db, expression):
        expression = expression.strip()

        # Split expression into logical OR components, process if multiple
        _or_l = []
        while expression:
            par_count = 0
            for i, c in enumerate(expression):
                if c == '|' and par_count == 0:
                    _or_l.append(expression[:i].strip())
                    expression = expression[(i+1):].strip()
                    if not expression:
                        raise LcgException('Trying to OR with empty statement')
                    break
                elif c == '(':
                    par_count += 1
                elif c == ')':
                    par_count -= 1
                    if par_count < 0:
                        raise LcgException('Too many ")" parentheses')
            else:
                if expression:
                    _or_l.append(expression)
                    break
        if par_count != 0:
            raise LcgException('Mismatched number of "(" and ")" parentheses')
        if len(_or_l) > 1:
            _result = dict()
            _fun = self._apply_filter_expression
            _parsed_l = [_fun(filter_db, _expr) for _expr in _or_l]
            for set_id, value in filter_db.items():
                set_data, cards = value
                card_ids = list(cards.keys())
                _include_set = set()
                for _db in _parsed_l:
                    _val = _db.get(set_id)
                    if _val:
                        _c_l = _val[1]
                        _inc = set(_c_l.keys())
                        _include_set |= _inc
                for card_id in card_ids:
                    if card_id in _include_set:
                        if set_id not in _result:
                            _result[set_id] = (set_data, dict())
                        _result[set_id][1][card_id] = cards[card_id]
            return _result

        # Split expression into logical AND components, process if multiple
        _and_l = []
        expression, = _or_l
        while expression:
            par_count = 0
            for i, c in enumerate(expression):
                if c == '&' and par_count == 0:
                    _and_l.append(expression[:i].strip())
                    expression = expression[(i+1):].strip()
                    if not expression:
                        raise LcgException('Trying to AND with empty statement')
                    break
                elif c == '(':
                    par_count += 1
                elif c == ')':
                    par_count -= 1
                    if par_count < 0:
                        raise LcgException('Too many ")" parentheses')
            else:
                if expression:
                    _and_l.append(expression)
                    break
        if par_count != 0:
            raise LcgException('Mismatched number of "(" and ")" parentheses')
        if len(_and_l) > 1:
            _result = dict()
            _fun = self._apply_filter_expression
            _parsed_l = [_fun(filter_db, _expr) for _expr in _and_l]
            for set_id, value in filter_db.items():
                set_data, cards = value
                card_ids = list(cards.keys())
                _include_set = set(card_ids)
                for _db in _parsed_l:
                    _val = _db.get(set_id)
                    if _val:
                        _c_l = _val[1]
                        _inc = set(_c_l.keys())
                        _include_set &= _inc
                    else:
                        _include_set = set()
                        break
                for card_id in card_ids:
                    if card_id in _include_set:
                        if set_id not in _result:
                            _result[set_id] = (set_data, dict())
                        _result[set_id][1][card_id] = cards[card_id]
            return _result

        # What should remain if not returned, is a single filter statement
        expr, = _and_l
        if expr.startswith('(') and expr.endswith(')'):
            return self._apply_filter_expression(filter_db, expr[1:-1])
        operators = (':', '=', '!:', '!=','<=', '>=',  '<', '>', '#', '$')
        matches = [(expr.find(op), i, op) for i, op in enumerate(operators)]
        matches = [v for v in matches if v[0] >= 0]
        matches.sort()
        if not matches:
            raise LcgException(f'Expression has no operator: {expr}')
        pos, _tmp, op = matches[0]
        key, criteria = expr[:pos].strip(), expr[(pos+len(op)):].strip()
        if not key:
            raise LcgException(f'No key: {expr}')
        if not criteria and op not in ('#', '$'):
            raise LcgException(f'Operator requires an argument: {op}')
        elif criteria and op in ('#', '$'):
            raise LcgException(f'Operator takes no argument: {op}')
        _k_s = set()
        for _k in OctgnProperties.fields.keys():
            if key.lower() in _k.lower():
                _k_s.add(_k)
        if not _k_s:
            raise LcgException('No matching keys')
        elif len(_k_s) > 1:
            _k_s_in = _k_s
            _k_s = set(_k for _k in _k_s if _k.lower() == key.lower())
            if len(_k_s) != 1:
                raise LcgException(f'Too many matching keys ({len(_k_s_in)} '
                                   f'matches with {key})')
        key, = _k_s
        key_type = OctgnProperties.fields[key][0]
        criteria = criteria.lower()

        _result = dict()
        for set_id, value in filter_db.items():
            set_data, cards = value
            for card_id, card_data in cards.items():
                if op in ('#', '$'):
                    if op == '#' and key not in card_data.properties:
                        continue
                    elif op == '$' and key in card_data.properties:
                        continue
                else:
                    if key not in card_data.properties:
                        continue
                    val = card_data.properties.get(key)
                    if key_type is int and op not in (':', '!:'):
                        try:
                            criteria = int(criteria)
                        except ValueError:
                            continue
                    else:
                        val = str(val).lower()
                    if op in ('<=', '<', '>', '>='):
                        try:
                            val = int(val)
                        except ValueError:
                            continue
                    if op == ':' and criteria not in val:
                        continue
                    elif op == '=' and criteria != val:
                        continue
                    elif op == '!:' and criteria in val:
                        continue
                    elif op == '!=' and criteria == val:
                        continue
                    elif op == '<=' and val > criteria:
                        continue
                    elif op == '<' and val >= criteria:
                        continue
                    elif op == '>' and val <= criteria:
                        continue
                    elif op == '>=' and val < criteria:
                        continue
                # If we did not continue above, include card
                if set_id not in _result:
                    _result[set_id] = (set_data, dict())
                _result[set_id][1][card_id] = card_data
        return _result

    def _reset_filter_cb_values(self):
        # Populate combo boxes
        for _w in self._set_name_cb, self._owner_cb, self._card_type_cb:
            _w.clear()
        _set_names, _owners, _types = set(), set(), set()
        db = self._filtered_db
        db = OctgnCardSetData._octgn_sets if db is None else db
        for card_set, card_data_d in db.values():
            _s = card_set.name
            if _s:
                _set_names.add(_s)
            for card_data in card_data_d.values():
                props = card_data.properties
                _s = props.get('Owner')
                if _s:
                    _owners.add(_s)
                _s = props.get('Type')
                if _s:
                    _types.add(_s)
        _set_names = [''] + sorted(_set_names)
        for _s in _set_names:
            self._set_name_cb.addItem(_s)
        _owners = [''] + sorted(_owners)
        for _s in _owners:
            self._owner_cb.addItem(_s)
        _types = [''] + sorted(_types)
        for _s in _types:
            self._card_type_cb.addItem(_s)

    @classmethod
    def _is_filter_match(cls, criteria, test_val, or_char=None, and_char=None,
                         case_sensitive=False):
        if not case_sensitive:
            criteria = criteria.lower()
            test_val = test_val.lower()

        if or_char:
            or_l = criteria.split(or_char)
        else:
            or_l = [criteria]
        or_l = [_v.strip() for _v in or_l if _v.strip()]

        # Return True if no criteria
        if not or_l:
            return True

        for sub_c in or_l:
            if and_char:
                _l = sub_c.split(and_char)
            else:
                _l = [sub_c]
            _l = [_v.strip() for _v in _l if _v.strip()]

            # If no criteria to test, return True
            if not _l:
                return True

            # Return True if all and components match
            _match = True
            for c in _l:
                if c not in test_val:
                    _match = False
                    break
            if _match:
                return True
        return False


class OctgnDbImageViewer(QtWidgets.QWidget):
    """Show card image retreived from OCTGN image database."""

    def __init__(self, dialog):
        super().__init__()
        self._dialog = dialog
        self._img_cache = dict()
        self._invalid_cache = set()
        self._img = None
        self._scaled_img = None
        self._image_id = None

    @QtCore.Slot()
    def showCard(self, image_id):
        # If image ID changed, identify/load new image
        if image_id != self._image_id:
            self._scaled_img = None
            if image_id in self._invalid_cache:
                self._img = None
            elif image_id in self._img_cache:
                self._img = self._img_cache[image_id]
            elif image_id in self._dialog._image_d:
                img = QtGui.QImage(self._dialog._image_d[image_id])
                if img.isNull():
                    self._invalid_cache.add(image_id)
                    self._img = None
                else:
                    self._img_cache[image_id] = img
                    self._img = img
            else:
                self._img = None
        img = self._img

        # Scale image to fit window (if required)
        if img:
            scale = min(self.width()/img.width(), self.height()/img.height())
            width, height = int(img.width()*scale), int(img.height()*scale)
            if (not self._scaled_img or self._scaled_img.width() != width or
                self._scaled_img.height() != height):
                _mode = QtCore.Qt.SmoothTransformation
                self._scaled_img = img.scaled(width, height, mode=_mode)

        self.update()

    def resizeEvent(self, event):
        self.showCard(self._image_id)

    def paintEvent(self, event):
        if self._scaled_img:
            painter = QtGui.QPainter(self)
            x = (self.width() - self._scaled_img.width())/2
            y = (self.height() - self._scaled_img.height())/2
            painter.drawImage(QtCore.QPoint(x, y), self._scaled_img)
            painter.end()


def load_o8d_cards(o8d_file, data_path=None, parent=None):
    """Tries to load a set of cards from an .o8d file.

    :param  o8d_file: path to the .o8d file
    :type   o8d_file: str
    :param data_path: path to OCTGN Data/ directory (default if None)
    :type  data_path: str

    """
    err = lambda s1, s2: ErrorDialog(parent, s1, s2).exec()

    # Load OCTGN card database and indexes to images
    data_path = OctgnCardSetData.get_octgn_data_path(data_path, val=True)
    OctgnCardSetData.load_all_octgn_sets(data_path)
    image_d = dict()
    image_root = os.path.join(data_path, 'ImageDatabase', mc_game_id, 'Sets')
    for path, subdirs, files in os.walk(image_root):
        for f in files:
            base, ext = f[:-4], f[-4:]
            if ext.lower() in ('.png', '.jpg'):
                if '.' not in base:
                    guid = base
                else:
                    guid = base[:-2]
            try:
                uuid.UUID('{' + guid + '}')
            except ValueError:
                pass
            else:
                image_d[base.lower()] = os.path.join(path, f)

    # Parse the .o8d file
    root = ElementTree.parse(o8d_file).getroot()
    if root.tag != 'deck':
        raise LcgException('Missing <deck> tag')
    game = root.attrib['game']
    if game is None or game != mc_game_id:
        raise LcgException('Deck is not for Marvel Champions: The Card Game')
    sections_p = dict()
    sections_g = dict()
    for section in root:
        if section.tag == 'notes':
            continue
        if section.tag != 'section':
            raise LcgException('Expected <section> tag')
        _name = section.attrib['name']
        if not _name:
            raise LcgException('<section> without a name attribute')
        _shared = section.attrib['shared']
        if _shared.lower() not in ('true', 'false'):
            raise LcgException('<section> with invalid shared attribute')
        _sections = sections_g if _shared.lower() == 'true' else sections_p
        if _name in _sections:
            raise LcgException(f'<section> with duplicate name {_name}')
        cards = dict()
        _sections[_name] = cards
        for card in section:
            if card.tag != 'card':
                raise LcgException('Expected <card> tag')
            _qty = card.attrib['qty']
            _id = card.attrib['id']
            _name = card.text
            if _qty is None or _id is None:
                raise LcgException('<card> without qty and/or id attribute')
            try:
                _qty = int(_qty)
            except ValueError:
                raise LcgException(f'Invalid qty value {_qty}')
            if _qty <= 0:
                raise LcgException('qty must be >= 1')
            if _id in cards:
                _q, _n = section[_id]
                if _n != _name:
                    raise LcgException('Cards with same ID but different name')
                else:
                    _qty += _q
            cards[_id] = (_qty, _name)

    # Validate section names
    _p_types = set(sections_p.keys())
    _valid_p_types = set(OctgnCardData._o8d_player_types)
    _diff = _p_types - _valid_p_types
    if _diff:
        raise LcgException(f'Player sections have illegal names {_diff}')
    _g_types = set(sections_g.keys())
    _valid_g_types = set(OctgnCardData._o8d_global_types)
    _diff = _g_types - _valid_g_types
    if _diff:
        raise LcgException(f'Global sections have illegal names {_diff}')

    # Generate card data for the cards
    card_data_l, failed = [], []
    _num_p, _num_g = len(_valid_p_types), len(_valid_g_types)
    _p_sec = list(zip([sections_p]*_num_p, OctgnCardData._o8d_player_types,
                      range(_num_p)))
    _g_sec = list(zip([sections_g]*_num_g, OctgnCardData._o8d_global_types,
                      range(_num_p, _num_p+_num_g)))
    _sec = _p_sec + _g_sec
    for sections, chk_type, o8d_type in _sec:
        if chk_type not in sections:
            continue
        section = sections[chk_type]
        for card_id, card_data in section.items():
            _qty, _name = card_data
            # Look up card in OCTGN database
            for set_id, _val in OctgnCardSetData._octgn_sets.items():
                card_set, card_data_d = _val
                card_data = card_data_d.get(card_id, None)
                if card_data:
                    break
            else:
                failed.append((card_id, _qty, _name))
                continue
            card_data_l.append((card_data, _qty, _name, o8d_type))
    if not card_data_l:
        raise LcgException('None of the cards are in the OCTGN database')
    if failed:
        _dfun = QtWidgets.QMessageBox.question
        _keys = QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel
        _l = ', '.join([_f[2] for _f in failed])
        k = _dfun(parent, 'Some cards not in database', f'{len(failed)} cards '
                  f'were not found in the OCTGN database: {_l}. Proceed '
                  'while ignoring these cards?', _keys)
        if k == QtWidgets.QMessageBox.Cancel:
            return

    # Generate card objects for importing into deck
    _mod = importlib.import_module('mcdeck.script')
    MCCard = _mod.Card
    MCDeck = _mod.MCDeck
    cards = []
    failed = []
    for card_data, qty, name, o8d_type in card_data_l:
        front_img = QtGui.QImage(image_d[card_data.image_id])
        if front_img.isNull():
            failed.append((card_data, qty, name))
            continue
        if card_data.alt_data:
            _fname = image_d[card_data.alt_data.image_id]
            back_img = QtGui.QImage(_fname)
            if back_img.isNull():
                failed.append((card_data, qty, name))
                continue
        else:
            back_img = None

        # Handle aspect transformation
        _images = [front_img, back_img]
        for i, img in enumerate(_images):
            if img:
                img = LcgImage(img)
                _s = MCDeck.settings
                aspect_rotation = _s.aspect_rotation
                if aspect_rotation != 'none':
                    if aspect_rotation == 'clockwise':
                        clockwise = True
                    if aspect_rotation == 'anticlockwise':
                        clockwise = False
                    else:
                        raise RuntimeError('Should never happen')
                    portrait = (_s.card_height_mm >= _s.card_width_mm)
                    c_portrait = (img.heightMm() >= img.widthMM())
                    if portrait ^ c_portrait:
                        # Wrong aspect, rotate
                        if clockwise:
                            img = img.rotateClockwise()
                        else:
                            img = img.rotateAntiClockwise()
                _images[i] = img
        front_img, back_img = _images

        # Resolve card type
        _type = card_data.properties.get('Type')
        _owner = card_data.properties.get('Owner')
        if _type is not None:
            if _type in ('ally', 'alter_ego', 'event', 'resource',
                         'support', 'upgrade'):
                c_type = MCCard.type_player
            elif _type in  ('side_scheme', 'attachment', 'environment',
                            'minion', 'obligation', 'treachery'):
                c_type = MCCard.type_encounter
            elif _type == 'villain':
                c_type = MCCard.type_villain
            else:
                c_type = MCCard.type_unspecified

        # Generate Card objects
        for i in range(qty):
            card = MCCard(front=front_img, back=back_img, ctype=c_type)
            card._octgn = card_data.copy()
            card._octgn._o8d_type = o8d_type
            if not card._octgn.name:
                card._octgn._name = name
            cards.append(card)

    if failed:
        _dfun = QtWidgets.QMessageBox.question
        _keys = QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel
        _l = ', '.join([_f[2] for _f in failed])
        k = _dfun(parent, 'Some images not in database', f'{len(failed)} cards '
                  'were missing image(s) in the OCTGN image database: {_l}. '
                  'Proceed while ignoring these cards?', _keys)
        if k == QtWidgets.QMessageBox.Cancel:
            return

    if cards:
        if not MCDeck.deck._octgn:
            MCDeck.root.menu_octgn_enable()
        for card in cards:
            MCDeck.deck.addCardObject(card)
    return len(cards)


def install_card_sets(data_path, paths):
    """Install a set of .zip format card sets into Data/.

    :param data_path: path to OCTGN Data/ directory
    :param     paths: list of paths to .zip files to install

    """
    OctgnCardSetData.validate_octgn_data_path(data_path)

    pending, skipped = [], []

    for path in paths:
        status, data = _validate_card_set_file(data_path, path)
        if not status:
            skipped.append((path, data))
            continue
        else:
            pending.append((path, data))

    installed = []
    for path, data in pending:
        # Uninstall card set if already installed
        _uninst_l, _skip_l = uninstall_card_sets(data_path, [path])
        if not _uninst_l:
            _msg = 'Could not uninstall card set'
            skipped.append((path, _msg))
            continue

        # Install card set .zip file
        zf = zipfile.ZipFile(path)
        dest_dir = data_path
        zf.extractall(path=dest_dir)
        installed.append(path)

    return (installed, skipped)


def uninstall_card_sets(data_path, paths):
    """Uninstall a set of .zip format card sets into Data/.

    :param data_path: path to OCTGN Data/ directory
    :param     paths: list of paths to .zip files to install

    """
    OctgnCardSetData.validate_octgn_data_path(data_path)

    pending, skipped = [], []

    for path in paths:
        status, data = _validate_card_set_file(data_path, path)
        if not status:
            _msg = data
            skipped.append((path, _msg))
            continue
        else:
            pending.append((path, data))

    uninstalled = []
    for path, data in pending:
        set_id, fanmade_l = data
        game_set_path = os.path.join(data_path, 'GameDatabase', mc_game_id,
                                     'Sets', set_id)
        image_set_path = os.path.join(data_path, 'ImageDatabase', mc_game_id,
                                      'Sets', set_id)
        fanmade_paths = []
        for _p, _f in fanmade_l:
            fanmade_paths.append(os.path.join(data_path, 'GameDatabase',
                                              mc_game_id, 'FanMade', _p, _f))

        for _dir in game_set_path, image_set_path:
            if os.path.isdir(_dir):
                shutil.rmtree(_dir)

        for _f in fanmade_paths:
            if os.path.isfile(_f):
                os.remove(_f)

        uninstalled.append(path)

    return (uninstalled, skipped)

def _validate_card_set_file(data_path, path):
    installed, skipped = [], []

    if not os.path.isfile(path):
        _msg = f'Not a file: {path}'
        return (False, _msg)
    try:
        zf = zipfile.ZipFile(path)

        p_tree = (dict(), [])
        for info in zf.infolist():
            _p = info.filename.split('/')
            if not _p[-1]:
                _p = _p[:-1]
            _tree = p_tree
            for _sub in _p[:-1]:
                if _sub not in _tree[0]:
                    _tree[0][_sub] = (dict(), [])
                _tree = _tree[0][_sub]
            _sub = _p[-1]
            if info.is_dir():
                _tree[0][_sub] = (dict(), [])
            else:
                _tree[1].append(info)

        if (len(p_tree[0]) != 2 or 'GameDatabase' not in p_tree[0] or
            'ImageDatabase' not in p_tree[0] or p_tree[1]):
            _msg = 'Invalid top directory structure'
            return (False, _msg)

        game_db = p_tree[0]['GameDatabase']
        image_db = p_tree[0]['ImageDatabase']
        for _db in game_db, image_db:
            if len(_db[0]) != 1 or mc_game_id not in _db[0] or _db[1]:
                _msg = 'Databases must contain a single MC game directory'
                return (False, _msg)
        game_db = game_db[0][mc_game_id]
        image_db = image_db[0][mc_game_id]

        if not (1 <= len(game_db[0]) <= 2 or game_db[1]):
            _msg = 'Invalid structure of GameDatabase dir for game'
            return (False, _msg)
        if ('Sets' not in game_db[0] or
            (len(game_db[0]) == 2 and 'FanMade' not in game_db[0]) or
            game_db[1]):
                _msg = 'Invalid structure of GameDatabase dir for game'
                return (False, _msg)
        if (len(image_db[0]) != 1 or 'Sets' not in image_db[0] or
            image_db[1]):
            _msg = 'Invalid structure of ImageDatabase game directory'
            return (False, _msg)

        game_set_db = game_db[0]['Sets']
        image_set_db = image_db[0]['Sets']
        _set_ids = set()
        for _db in game_set_db, image_set_db:
            if len(_db[0]) != 1:
                _msg = 'Database set dir(s) must contain single directory'
                return (False, _msg)
            _name, = _db[0].keys()
            _name = _name.lower()
            try:
                uuid.UUID('{' + _name + '}')
            except ValueError:
                _msg = 'set ID directory name is not correct GUID format'
                return (False, _msg)
            _set_ids.add(_name)
        if len(_set_ids) != 1:
            _msg = 'Set ID mismatch for GameDatabase and ImageDatabase'
            return (False, _msg)
        set_id, = _set_ids

        game_set_sub_db, = game_set_db[0].values()
        if game_set_sub_db[0] or len(game_set_sub_db[1]) != 1:
            _msg = 'GameDatabase Sets must contain a single file'
            return (False, _msg)
        _info = game_set_sub_db[1][0]
        if _info.filename.split('/')[-1].lower() != 'set.xml':
            _msg = 'GameDatabase Sets must contain set.xml'
            return (False, _msg)
        set_xml_info = _info

        image_set_sub_db, = image_set_db[0].values()
        if (len(image_set_sub_db[0]) != 1 or
            'Cards' not in image_set_sub_db[0] or image_set_sub_db[1]):
            _msg = 'Image database set must include a single dir Cards'
            return (False, _msg)

        image_cards_db, = image_set_sub_db[0].values()
        if image_cards_db[0]:
            _msg = 'ImageDatabase Sets cannot have subfolders'
            return (False, _msg)
        for _f_info in image_cards_db[1]:
            ext = _f_info.filename[-4:]
            if ext.lower() not in ('.jpg', '.png'):
                _msg = 'All ImageDatabase Sets files must be .png or .jpg'
                return (False, _msg)

        fanmade_l = []
        _mod = importlib.import_module('mcdeck.script')
        allow_non_o8d = _mod.MCDeck.settings.octgn_allow_fanmade_non_o8d
        if 'FanMade' in game_db[0] and not allow_non_o8d:
            _fan_db = game_db[0]['FanMade'][0]
            for _sub in ('Heroes', 'Modulars', 'Villains'):
                if _sub not in _fan_db:
                    continue
                for _f_info in _fan_db[_sub][1]:
                    _ext = _f_info.filename[-4:]
                    if _ext.lower() == '.o8d':
                        _filename = _f_info.filename
                        _filename = _filename.split('/')[-1]
                        fanmade_l.append((_sub, _filename))
                    else:
                        _msg = 'FanMade folder includes non-.o8d files'
                        return (False, _msg)

        # Do a rough check of set.xml
        with zf.open(set_xml_info.filename) as _set_xml_f:
            _set = ElementTree.parse(_set_xml_f).getroot()
            if _set.tag != 'set' or set_id != _set.attrib['id']:
                _msg = 'Invalid set.xml structure or mismatching set ID'
                return (False, _msg)

    except Exception as e:
        return (False, str(e))
    else:
        if not set_id:
            return (False, 'Invalid set ID')  # Should never happen ...
        else:
            return (True, (set_id, fanmade_l))
