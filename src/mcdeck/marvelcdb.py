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

"""Public access to MarvelCDB database."""

import http
import importlib
import json
import urllib.error
import urllib.request

from PySide6 import QtGui, QtCore

from lcgtools import LcgException
from lcgtools.graphics import LcgImage

from mcdeck.octgn import OctgnCardData, OctgnProperties
from mcdeck.util import download_image


class MarvelCDB(object):
    """Interface to public accessible MarvelCDB data.

    See see https://marvelcdb.com/api/ for information on what information
    is accessible, how it is accessed, and restrictions on usage.

    """

    _pack_json_l = None  # Parsed JSON structures for each MarvelCDB pack
    _pack_data_l = None  # List of raw application/json data for each pack
    _cards = None        # Dictionary {code:Card} for the cards

    @classmethod
    def load_cards(cls, all=False, progress=None):
        """Loads the public API cards database from MarvelCDB.

        :param      all: if True load all cards, if False load player cards
        :type       all: bool
        :param progress: if set, a progress dialog to update with progress
        :type  progress: :class:`QtWidgets.QProgressDialog`
        :raises:         :exc:`lcgtools.LcgException` in case of failure

        If 'all' is set, then cards are downloaded from each pack separately;
        this takes more time and more server interactions, however it will
        enable download of all cards (not only player cards).

        The method will not return any value, however it initializes
        internal data structures for card database access.

        The method will only load data once. Upon successful load (whether it
        be from the server or from a local cache), any later call to
        :meth:`load` will simply return without updating data, and any later
        value of the 'all' argument is ignored.

        """
        if cls._cards:
            return
        if all:
            # Get list of packs and parse pack codes
            packlist_url = 'https://marvelcdb.com/api/public/packs/'
            try:
                response = urllib.request.urlopen(packlist_url)
            except urllib.error.URLError as e:
                _msg = f'Failed to open URL {packlist_url}: {e}'
                raise LcgException(_msg)
            data = None
            if isinstance(response, http.client.HTTPResponse):
                ctype = response.getheader('Content-Type', '')
                mime_types = ctype.split(';')
                if 'application/json' in mime_types:
                    data = response.read()
            if data is None:
                raise LcgException('Unexpected server response')
            try:
                packlist_json = json.loads(data)
            except json.JSONDecodeError as e:
                _msg = ('Could not read MarvelCDB cards list, failed '
                        f'to decode server response as JSON: {e}')
                raise LcgException(_msg)
            pack_names = []
            for pack_entry in packlist_json:
                pack_names.append(pack_entry['code'])
            if progress:
                progress.setMaximum(len(pack_names) + 2)
                progress.setValue(1)
                QtCore.QCoreApplication.processEvents()  # Force Qt update

            # Get list of cards for each pack
            cards_d = {}
            pack_data_l = []
            pack_json_l = []
            for pack_name in pack_names:
                url = f'https://marvelcdb.com/api/public/cards/{pack_name}'
                try:
                    response = urllib.request.urlopen(url)
                except urllib.error.URLError as e:
                    _msg = f'Failed to open URL {url}: {e}'
                    raise LcgException(_msg)
                data = None
                if isinstance(response, http.client.HTTPResponse):
                    ctype = response.getheader('Content-Type', '')
                    mime_types = ctype.split(';')
                    if 'application/json' in mime_types:
                        data = response.read()
                if data is None:
                    raise LcgException('Unexpected server response')
                try:
                    pack_json = json.loads(data)
                except json.JSONDecodeError as e:
                    _msg = ('Could not read MarvelCDB cards list, failed '
                            f'to decode server response as JSON: {e}')
                    raise LcgException(_msg)
                pack_data_l.append(data)
                pack_json_l.append(pack_json)
                for card_json in pack_json:
                    code = card_json['code']
                    card = Card(card_json, _internal=True)
                    cards_d[code] = card
                if progress:
                    progress.setValue(progress.value() + 1)
                    QtCore.QCoreApplication.processEvents()  # Force Qt update

            # Store results as class properties
            cls._pack_json_l = pack_json_l
            cls._pack_data_l = pack_data_l
            cls._cards = cards_d

            # Also get the standard cards list (required for hero backsides)
            # Read raw JSON file into 'data'
            cards_d = dict()
            url = 'https://marvelcdb.com/api/public/cards/'
            try:
                response = urllib.request.urlopen(url)
            except urllib.error.URLError as e:
                _msg = f'Failed to open URL {url}: {e}'
                raise LcgException(_msg)
            data = None
            if isinstance(response, http.client.HTTPResponse):
                ctype = response.getheader('Content-Type', '')
                mime_types = ctype.split(';')
                if 'application/json' in mime_types:
                    data = response.read()
            if data is None:
                raise LcgException('Unexpected server response')

            # Parse JSON file and initialize internal data structures
            try:
                cards_json = json.loads(data)
            except json.JSONDecodeError as e:
                _msg = ('Could not read MarvelCDB cards list, failed '
                        f'to decode server response as JSON: {e}')
                raise LcgException(_msg)
            cards_d = {}
            for card_json in cards_json:
                code = card_json['code']
                card = Card(card_json, _internal=True)
                cards_d[code] = card
            if progress:
                progress.setValue(progress.value() + 1)
                QtCore.QCoreApplication.processEvents()  # Force Qt update

            cls._pack_json_l.append(cards_json)
            cls._pack_data_l.append(data)
            for key, val in cards_d.items():
                cls._cards[key] = val
        else:
            if progress:
                progress.setMaximum(1)

            # Read raw JSON file into 'data'
            url = 'https://marvelcdb.com/api/public/cards/'
            try:
                response = urllib.request.urlopen(url)
            except urllib.error.URLError as e:
                _msg = f'Failed to open URL {url}: {e}'
                raise LcgException(_msg)
            data = None
            if isinstance(response, http.client.HTTPResponse):
                ctype = response.getheader('Content-Type', '')
                mime_types = ctype.split(';')
                if 'application/json' in mime_types:
                    data = response.read()
            if data is None:
                raise LcgException('Unexpected server response')

            # Parse JSON file and initialize internal data structures
            try:
                cards_json = json.loads(data)
            except json.JSONDecodeError as e:
                _msg = ('Could not read MarvelCDB cards list, failed '
                        f'to decode server response as JSON: {e}')
                raise LcgException(_msg)
            cards_d = {}
            for card_json in cards_json:
                code = card_json['code']
                card = Card(card_json, _internal=True)
                cards_d[code] = card
            if progress:
                progress.setValue(progress.value() + 1)
                QtCore.QCoreApplication.processEvents()  # Force Qt update

            # Store results as class properties
            cls._pack_json_l = [cards_json]
            cls._pack_data_l = [data]
            cls._cards = cards_d

    @classmethod
    def load_deck(cls, deck_id):
        """Loads a decklist from the public MarvelCDB database.

        :param deck_id: ID of deck (e.g. '21035')
        :type  deck_id: str
        :return:       deck object
        :rtype:        :class:`Deck`
        :raises:       :exc:`lcgtools.LcgException` in case of failure

        The method will not return any value, however it initializes
        internal data structures for card database access.

        The method will only load data once. Upon successful load (whether it
        be from the server or from a local cache), any later call to
        :meth:`load` will simply return without updating data.

        """
        if isinstance(deck_id, int):
            deck_id = f'{deck_id:05}'
        # Read raw JSON file into 'data'
        url = f'https://marvelcdb.com/api/public/decklist/{deck_id}'
        try:
            response = urllib.request.urlopen(url)
        except urllib.error.URLError as e:
            _msg = f'Failed to open URL {url}: {e}'
            raise LcgException(_msg)
        else:
            data = None
            if isinstance(response, http.client.HTTPResponse):
                ctype = response.getheader('Content-Type', '')
                mime_types = ctype.split(';')
                if 'application/json' in mime_types:
                    data = response.read()
            if data is None:
                raise LcgException('Unexpected server response')

        # Parse JSON file and initialize internal data structures
        try:
            deck_json = json.loads(data)
        except json.JSONDecodeError as e:
            _msg = ('Could not read MarvelCDB cards list, failed '
                    f'to decode server response as JSON: {e}')
            raise LcgException(_msg)
        else:
            return Deck(deck_json, _internal=True)

    @classmethod
    def cards(cls):
        """Returns a list of all the cards in the database."""
        cls.load_cards()
        return list(cls._cards.values())

    @classmethod
    def card(cls, code):
        """Returns a Card for the provided MarvelCDB card code (or None).

        :param code: MarvelCDB code for the card (e.g. "01002" for Black Cat)
        :type  code: str

        """
        if isinstance(code, int):
            code = f'{code:05}'
        cls.load_cards()
        return cls._cards.get(code, None)

        # https://marvelcdb.com/api/public/card/03030


class Card(object):
    """Represents a card in MarvelCDB.

    Overloads __getattr__ so that card database values can be retreived by
    using their key as properties on the object, e.g. for a Card object c,
    then c.name resolves to the same value as c.value('name'). However, if
    the key is not defined, then AttributeError is raised.

    The class is not intended to be instantiated directly by clients, but
    should be instantiated via :class:`MarvelCDB`.

    """

    # Translation matrix for converting to OCTGN database format
    _octgn_trans = {'code': 'CardNumber', 'type_code': 'Type', 'cost': 'Cost',
                    'traits': 'Attribute', 'text': 'Text',
                    'resource_energy': 'Resource_Energy',
                    'resource_mental': 'Resource_Mental',
                    'resource_physical': 'Resource_Physical',
                    'resource_wild': 'Resource_Wild', 'flavor': 'Quote',
                    'card_set_name': 'Owner', 'attack': 'Attack',
                    'thwart': 'Thwart', 'defense': 'Defense',
                    'recover': 'Recovery', 'scheme': 'Scheme',
                    'attack_cost': 'AttackCost', 'thwart_cost': 'ThwartCost',
                    'hand_size': 'HandSize', 'health': 'HP',
                    'threat': 'Threat', 'base_threat': 'BaseThreat',
                    'escalation_threat': 'EscalationThreat',
                    'scheme_acceleration': 'Scheme_Acceleration',
                    'scheme_crisis': 'Scheme_Crisis',
                    'scheme_hazard': 'Scheme_Hazard', 'boost': 'Boost'
                    }
    _octgn_bool = {'is_unique': 'Unique', 'health_per_hero': 'HP_Per_Hero',
                   'escalation_threat_fixed': 'EscalationThreatFixed',
                   'base_threat_fixed': 'BaseThreatFixed'}

    _Card = None

    def __init__(self, card_json, _internal=False):
        if not _internal:
            raise LcgException('Should not be instantiated by clients')
        self._json = card_json

    def keys(self):
        """Returns a list of keys for which the card has values set."""
        return list(self._json.keys())

    def has_key(self, key):
        """Return True if card has data for the provided key."""
        return (key in self._json)

    def value(self, key, default=None):
        """Return value for the given key (None if not defined)."""
        if key in self._json:
            return self._json[key]
        else:
            return default

    def belongs_to_hero_set(self):
        """Return True if the card is from a set of hero cards."""
        return (self.value('card_set_type_name_code') == 'hero')

    def has_player_backside(self):
        """True if card is of a type that has player backside."""
        _player_l = ('ally', 'event', 'upgrade', 'support', 'resource')
        return self.value('type_code') in _player_l

    def has_encounter_backside(self):
        """True if card is of a type that has an encounter backside."""
        _encounter_l = ('attachment', 'environment', 'minion', 'side_scheme',
                        'treachery', 'obligation')
        return self.value('type_code') in _encounter_l

    def has_villain_backside(self):
        """True if card is of a type that has a villain backside."""
        return (self.value('type_code') == 'villain')

    def is_hero(self):
        """True if the card is a hero."""
        return (self.value('type_code') == 'hero')

    def is_alter_ego(self):
        """True if the card is an alter-ego."""
        return (self.value('type_code') == 'alter_ego')

    def front_img_url(self):
        """Returns a URL to the card's front side image (None if not set)."""
        if 'imagesrc' in self._json:
            imagesrc = self.value('imagesrc')
            return f'https://marvelcdb.com{imagesrc}'
        else:
            return None

    def to_octgn_properties(self):
        """Exports card data to an OCTGN properties structure.

        :return: card properties object
        :rtype:  :class:`mcdeck.octgn.OctgnProperties`

        """
        result = OctgnProperties()
        for key, value in self._json.items():
            octgn_key = self._octgn_trans.get(key, None)
            if octgn_key:
                _type, _chk, _params = OctgnProperties.fields[octgn_key]
                if _type is int:
                    value = _type(value)
                if value:  # Only set property if it is not an empty string
                    result.set(octgn_key, value)
            octgn_key = self._octgn_bool.get(key, None)
            if octgn_key:
                _type, _chk, _params = OctgnProperties.fields[octgn_key]
                if value:
                    result.set(octgn_key, 'True')
                elif 'False' in _params:
                    result.set(octgn_key, 'False')

        return result

    def to_octgn_card_data(self):
        """Exports card data as OCTGN card data.

        :return: card data object
        :rtype:  :class:`mcdeck.octgn.OctgnCardData`

        """
        name = self._json.get('name', '')
        image_id = self._json.get('octgn_id', None)
        props = self.to_octgn_properties()
        result = OctgnCardData(name, props, image_id)
        result._source = OctgnCardData._source_marvelcdb
        return result

    def to_mcdeck_card(self, octgn=True, parent=None, copies=1,
                       placeholder=False):
        """

        :param      parent: parent widget of the card (or None)
        :type       parent: :class:`QtWidget.QWidget`
        :param       octgn: if True add OCTGN data to card
        :param      copies: number copies to make
        :type       copies: int
        :param placeholder: if True use img placeholder if img not set in DB
        :return:            MCdeck card object
        :rtype:             :class:`mcdeck.script.Card`

        If *copies* is larger than one, then that many card objects are
        generated, and the are returned as a list. (This can be useful if
        several copies of a card need to be generated, to do so without
        downloading images more than once).

        """
        if Card._Card is None:
            _mod = importlib.import_module('mcdeck.script')
            Card._Card = _mod.Card
            Card._MCDeck = _mod.MCDeck
        MCDeckCard = Card._Card
        MCDeck = Card._MCDeck

        if self.has_player_backside():
            ctype = MCDeckCard.type_player
        elif self.has_encounter_backside():
            ctype = MCDeckCard.type_encounter
        elif self.has_villain_backside():
            ctype = MCDeckCard.type_villain
        else:
            ctype = MCDeckCard.type_unspecified

        # Get alt card (if any)
        if 'linked_card' in self._json:
            # Download card back from linked card
            linked_card = self.linked_card
            linked_code = linked_card['code']
            alt_card = MarvelCDB.card(linked_code)
        else:
            alt_card = None

        # Generate OCTGN card data structure
        octgn_data = self.to_octgn_card_data()
        if alt_card:
            props = alt_card.to_octgn_properties()
            octgn_data.create_alt_card_data(alt_card.name, prop=props)

        # Load front image (and back image if alt card)
        front_img_url = self.front_img_url()
        if front_img_url:
            front_img = download_image(front_img_url)
        else:
            # Try to load from OCTGN, otherwise use placeholder if applicable
            front_img = octgn_data.load_image()
            if front_img is None:
                if placeholder:
                    _name = self.value('name', '')
                    front_img = self._create_placeholder_image(_name)
                else:
                    raise LcgException('Card has no MarvelCDB front image')
        if alt_card:
            back_img_url = alt_card.front_img_url()
            if back_img_url:
                back_img = download_image(back_img_url)
            else:
                # Try to load from OCTGN, otherwise use placeholder
                back_img = octgn_data.alt_data.load_image()
                if back_img is None:
                    if placeholder:
                        _name = self.value('name', '')
                        back_img = self._create_placeholder_image(_name)
                    else:
                        raise LcgException('Card has no MarvelCDB back image')
        else:
            back_img = None

        # Handle aspect transformation
        _images = [front_img, back_img]
        for _i, _img in enumerate(_images):
            if _img:
                _img = LcgImage(_img)
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
                    c_portrait = (_img.heightMm() >= _img.widthMM())
                    if portrait ^ c_portrait:
                        # Wrong aspect, rotate
                        if clockwise:
                            _images[_i] = _img.rotateClockwise()
                        else:
                            _images[_i] = _img.rotateAntiClockwise()
        front_img, back_img = _images

        results = []
        for i in range(copies):
            result = MCDeckCard(front_img, back=back_img, ctype=ctype,
                                parent=parent)
            if octgn:
                result._octgn = octgn_data.copy()
            result._imported = True
            results.append(result)

        if len(results) == 1:
            return results[0]
        else:
            return results

    @classmethod
    def _create_placeholder_image(cls, name):
        pixmap = QtGui.QPixmap(615, 880)
        pixmap.fill(QtGui.QColor('#fb0d03'))
        painter = QtGui.QPainter(pixmap)
        painter.setPen(QtGui.QColor('#d7e702'))
        font = QtGui.QFont('Arial', 36)
        font.setWeight(QtGui.QFont.Bold)
        font.setBold(True)
        font.setUnderline(True)
        painter.setFont(font)
        painter.drawText(QtCore.QPoint(60, 340), 'Image placeholder:')
        font.setBold(False)
        font.setUnderline(False)
        painter.setFont(font)
        if 'name':
            painter.drawText(QtCore.QPoint(60, 420), name)
        del(painter)
        return pixmap.toImage()

    def __getattr__(self, attr):
        if attr in self._json:
            return self._json[attr]
        else:
            raise AttributeError(f'No attribute {attr}')


class Deck(object):
    """A deck of cards downloaded from MarvelCDB.

    Should not be instantiated directly by clients, use
    :meth:`MarvelCDB.load_deck` to generate.

    """

    def __init__(self, deck_json, include_hero=True, _internal=False):
        try:
            self._json = deck_json
            self._name = deck_json['name']
            self._cards = []
            if include_hero:
                hero_card_code = deck_json['investigator_code']
                card = MarvelCDB.card(hero_card_code)
                self._cards.append((card, 1))
            for code, num in deck_json['slots'].items():
                card = MarvelCDB.card(code)
                self._cards.append((card, num))
        except Exception as e:
            raise LcgException(f'Could not parse deck JSON: {e}')

    @property
    def name(self):
        """The name of the deck in MarveCDB."""
        return self._name

    @property
    def cards(self):
        """Tuple of pairs (:class:`Card`, number`)."""
        return tuple(self._cards)
