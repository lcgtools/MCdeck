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

"""Utility functionality."""

import http
import ntpath
import platform
import posixpath
import urllib
import urllib.request

from PySide6 import QtWidgets, QtGui, QtCore

from lcgtools import LcgException
from lcgtools.graphics import LcgImage


def loadImageFromFileDialog(parent=None, title='Open image file',
                            ret_name=False):
    """Executes a file open dialog for loading an image.

    :param   parent: parent widget
    :type    parent: :class:`QtWidgets.QtWidget`
    :param    title: title of dialog
    :type     title: str
    :param ret_name: if True, return image filename instead of image
    :return:         loaded image (or None if not loaded)
    :rtype:          :class:`QtGui.QImage`

    """
    _dlg = QtWidgets.QFileDialog.getOpenFileName
    _flt = 'Images ('
    for x in QtGui.QImageReader.supportedImageFormats():
        _flt += f'*.{x.toStdString()} '
    _flt = _flt.strip() + ') ;; All files (*.*)'
    while True:
        path, cat = _dlg(parent, title, filter=_flt)
        if path:
            img = QtGui.QImage()
            if path and img.load(path):
                if ret_name:
                    return path
                else:
                    return img
            else:
                msg_box = QtWidgets.QMessageBox(parent)
                msg_box.setWindowTitle('Image load error')
                msg_box.setText('Image could not be loaded.')
                msg_box.setStandardButtons(QtWidgets.QMessageBox.Cancel)
                msg_box.setDefaultButton(QtWidgets.QMessageBox.Cancel)
                msg_box.exec()
        else:
            return None


def to_posix_path(path):
    """Convert path to posix path format, by replacing \\ separators with /."""
    return path.replace(ntpath.sep, posixpath.sep)


def to_windows_path(path):
    """Convert path to Win path format, by replacing / separators with \\."""
    return path.replace(posixpath.sep, ntpath.sep)


def to_local_path(path):
    """Convert path to local system format."""
    if platform.system() == 'Windows':
        return to_windows_path(path)
    else:
        return to_posix_path(path)


def download_image(url):
    """Tries to download an image from the provided URL.

    :param url: the URL to download from
    :type  url: str
    :returns:   downloaded image
    :rtype:     :class:`lcgtools.graphics.LcgImage`
    :raises:    an exception if URL could not be downloaded as an image

    """
    try:
        response = urllib.request.urlopen(url)
    except urllib.error.HTTPError:
        # If download fails, try again with fake headers
        _ua_val = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWeb'
                   'Kit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari'
                   '/537.36')
        headers = {'User-Agent': _ua_val}
        request = urllib.request.Request(url, headers=headers)
        response = urllib.request.urlopen(request)

    if isinstance(response, http.client.HTTPResponse):
        ctype = response.getheader('Content-Type', '')
        mime_types = ctype.split(';')
        mime_types = [s.strip() for s in mime_types]
        mime_match = image_mime_type(mime_types)
        if mime_match:
            img_data = response.read()
            img = LcgImage()
            d_format = {'image/png':'PNG', 'image/jpeg':'JPG',
                        'image/bmp':'BMP', 'image/gif':'GIF'}
            if mime_match in d_format:
                # No format match to mime type, decode with given format
                success = img.loadFromData(img_data, d_format[mime_match])
                if not success:
                    # Try again without mime-type specified format
                    mime_match = None
            if mime_match not in d_format:
                # No mime type match (or first attempt failed), try w/o format
                success = img.loadFromData(img_data)
            if success:
                return img
    raise LcgException(f'Could not load image.')

def image_mime_type(mime_data):
    """Returns supported image mime type in mime_data.

    :param mime_data: data to validate
    :type  mime_data: QtCore.QMimeData or list of mime-type string values
    :return:          matching mime type as string (or None)
    :rtype:           str

    """
    if isinstance(mime_data, QtCore.QMimeData):
        if not mime_data.hasImage():
            return None
        types = set(mime_data.formats())
    else:
        types = set(mime_data)

    supported = QtGui.QImageReader.supportedMimeTypes()
    supported = set([mt.toStdString() for mt in supported])
    overlap = types & supported
    if overlap:
        return list(overlap)[0]
    else:
        return None


def parse_mcd_file_section_header(line, labels=None, singles=None, pairs=None):
    """Parses a mcd file section header line.

    :param    line: the line to parse (cannot start with whitespace)
    :param  labels: list of allowed labels (if None no check)
    :param singles: list of allowed arguments without value (if None no check)
    :param   pairs: list of allowed arguments with value (if None no check)
    :returns:       triplet (sec_type, single_key_set, assigned_dict)
    :raises:        :exc:`ValueError` if line has invalid format

    All values are converted to lower case, both labels, keys and values.
    Comparisons against the labels, singles and pairs lists of allowed values,
    are done case insensitive.

    """
    if not line or not (line[:1].strip()):
        raise ValueError('Line cannot be empty or start with whitespace')
    line = line.strip()
    if not line.endswith(':'):
        raise ValueError('Line must end with colon (before final whitespace)')
    line = line[:-1]
    b_i = line.find('[')
    if b_i >= 0:
        label_s, args_s = line[:b_i], line[b_i:]
    else:
        label_s, args_s = line, None
    label_s = label_s.strip().lower()
    s_set, a_dict = {}, dict()
    if args_s is not None:
        args_s = args_s.strip()
        if not args_s.endswith(']'):
            raise ValueError('Illegal use of brackets')
        args_s = args_s[1:-1].strip()
        for sub in args_s.split(','):
            sub = sub.strip()
            pair = sub.split('=')
            if len(pair) == 1:
                single = pair[0].strip().lower()
                if s_set and single in s_set:
                    raise ValueError(f'Argument {single} used more than once')
                s_set.add(single)
            elif len(pair) == 2:
                name, value = pair[0].strip().lower(), pair[1].strip().lower()
                if a_dict and name in a_dict:
                    raise ValueError(f'Argument {name} used more than once')
                a_dict[name] = value
            else:
                raise ValueError('Invalid use of equality signs')
        for s_l in [label_s], s_set, a_dict.keys(), a_dict.values():
            for s in s_l:
                if not s.isalnum():
                    raise ValueError('Args and values must be alphanumeric')

    if labels:
        _compare = {_s.lower() for _s in labels}
        if label_s not in _compare:
            raise ValueError(f'Illegal label {label_s}')
    if singles:
        for s in s_set:
            _compare = {_s.lower() for _s in singles}
            if s.lower() not in _compare:
                raise ValueError(f'Illegal single arg {s}')
    if pairs:
        for s in a_dict.keys():
            _compare = {_s.lower() for _s in pairs.keys()}
            if s not in _compare:
                raise ValueError(f'Illegal pair arg {s}')

    return label_s, s_set, a_dict


class ErrorDialog(QtWidgets.QMessageBox):
    """Convenience class for error messages with only a cancel button.

    :param parent: parent widget
    :param  title: dialog title
    :param   text: dialog text

    """

    def __init__(self, parent, title, text):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setText(text)
        self.setStandardButtons(QtWidgets.QMessageBox.Cancel)
        self.setDefaultButton(QtWidgets.QMessageBox.Cancel)


class DeckUndoBuffer(QtCore.QObject):
    """Undo buffer for the card sets in a deck.

    :param   deck: the deck to apply the buffer to
    :type    deck: :class:`mcdeck.script.Deck`
    :param levels: maximum number of undo levels

    """

    haveUndo = QtCore.Signal(bool)  # Status change on available undo levels
    haveRedo = QtCore.Signal(bool)  # Status change on available redo levels

    def __init__(self, deck, levels=100):
        super().__init__()

        self.__deck = deck
        self.__levels = levels

        self.__buffer = []
        self.__buffer_pos = 0
        self.__pre_undo_cards = None

    def add_undo_level(self, hide=True):
        """Adds the current set of cards in the deck on top of the buffer.

        :param     hide: if True call hide() on all cards placed in buffer
        :param deselect: if True deselect card

        """
        cards = self.__deck._card_list_copy
        if hide:
            for card in cards:
                card.hide()

        if self.__buffer and self.__buffer_pos > 0:
            self.__buffer = self.__buffer[self.__buffer_pos:]
            self.__buffer_pos = 0
        self.__buffer.insert(0, cards)
        if len(self.__buffer) > self.__levels:
            self.__buffer = self.__buffer[:(self.__levels)]
        self.__pre_undo_cards = None

        self.haveUndo.emit(True)
        self.haveRedo.emit(False)

    def undo(self, show=True, purge=False):
        """Return card list for current undo level, and advance undo position.

        :param  show: if True call show() on all returned cards
        :param purge: if True, purge redo buffer above current undo level
        :return:      list of cards, or None if there are no more undo levels

        If this is the first undo operation, then a snapshot of the current
        state is made for later redo() recovery.

        """
        if self.can_undo():
            if self.__pre_undo_cards is None:
                self.__pre_undo_cards = self.__deck._card_list_copy
            cards = self.__buffer[self.__buffer_pos]
            self.__buffer_pos += 1

            if purge:
                self.__buffer = self.__buffer[self.__buffer_pos:]
                self.__buffer_pos = 0
                self.__pre_undo_cards = None

            self.haveUndo.emit(self.can_undo())
            self.haveRedo.emit(self.can_redo())

            if show:
                for card in cards:
                    card.show()
            return cards
        else:
            return None

    def redo(self, show=True):
        """Return card list for previous undo level, and move undo position.

        :param show: if True call show() on all returned cards
        :return:     list of cards, or None if there are no more redo levels

        """
        if self.can_redo():
            if self.__buffer_pos > 1:
                self.__buffer_pos -= 1
                cards = self.__buffer[self.__buffer_pos - 1]
            else:
                cards = self.__pre_undo_cards
                self.__pre_undo_cards = None
                self.__buffer_pos = 0

            self.haveUndo.emit(self.can_undo())
            self.haveRedo.emit(self.can_redo())

            if show:
                for card in cards:
                    card.show()
            return cards
        else:
            return None

    def can_undo(self):
        """True if buffer has more undo levels after current undo position."""
        return self.__buffer and self.__buffer_pos < len(self.__buffer)

    def can_redo(self):
        """True if buffer has available redo level(s)."""
        return self.__buffer_pos > 1 or self.__pre_undo_cards is not None

    def clear(self):
        """Clear the undo buffer."""
        self.__buffer = []
        self.__buffer_pos = 0
        self.haveUndo.emit(False)
        self.haveRedo.emit(False)

    def has_undo_information(self):
        """Returns True if buffer holds undo information."""
        return len(self.__buffer) > 0

    @property
    def undo_position(self):
        """Current position in undo buffer (starts at zero)"""
        return self.__buffer_pos
