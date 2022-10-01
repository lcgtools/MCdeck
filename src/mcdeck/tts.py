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

"""Tabletop Simulator export related functionality."""

import os.path

from PySide6 import QtCore, QtWidgets, QtGui

from lcgtools.graphics import LcgImage
from mcdeck.util import ErrorDialog


class TTSExportDialog(QtWidgets.QDialog):
    """Dialog for Tabletop Simulator export.

    :param   parent: parent widget
    :param settings: the application settings object
    :param    cards: list of Card objects to export

    """

    def __init__(self, parent, settings, cards):
        super().__init__(parent)
        self.__settings = settings
        self.__cards = cards

        main_layout = QtWidgets.QVBoxLayout()

        # Path for output images of front and back sides
        output_box = QtWidgets.QGroupBox(self)
        output_box.setTitle('File outputs for Tabletop Simulator deck export')
        output_layout = QtWidgets.QGridLayout()
        lbl = QtWidgets.QLabel
        row = 0
        output_layout.addWidget(lbl('Front side images:'), row, 0)
        self.__front_img_le = QtWidgets.QLineEdit()
        output_layout.addWidget(self.__front_img_le, row, 1, 1, 3)
        front_img_btn = QtWidgets.QPushButton('File...')
        front_img_btn.clicked.connect(self.frontImgBtnClicked)
        output_layout.addWidget(front_img_btn, row, 4, 1, 1)
        row += 1
        output_layout.addWidget(lbl('Back side images:'), row, 0)
        self.__back_img_le = QtWidgets.QLineEdit()
        output_layout.addWidget(self.__back_img_le, row, 1, 1, 3)
        back_img_btn = QtWidgets.QPushButton('File...')
        back_img_btn.clicked.connect(self.backImgBtnClicked)
        output_layout.addWidget(back_img_btn, row, 4, 1, 1)
        output_box.setLayout(output_layout)
        main_layout.addWidget(output_box)

        width_layout = QtWidgets.QHBoxLayout()
        width_layout.addWidget(lbl('Card width (px)'))
        self.__card_width_le = QtWidgets.QLineEdit()
        self.__card_width_le.setText(str(512))
        _val = QtGui.QIntValidator(32, 4096)
        self.__card_width_le.setValidator(_val)
        width_layout.addWidget(self.__card_width_le)
        main_layout.addLayout(width_layout)

        # Pushbuttons
        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok |
                                          QtWidgets.QDialogButtonBox.Cancel)
        btns.rejected.connect(self.reject)
        btns.accepted.connect(self.accept)
        main_layout.addWidget(btns)

        self.setLayout(main_layout)

    def accept(self):
        if not self.__cards:
            ErrorDialog(self, 'No cards to export', 'The deck contains no '
                        'cards to be exported.').exec()
            return
        elif len(self.__cards) > 70:
            ErrorDialog(self, 'Too many cards', 'The maximum number of cards '
                        'that can be exported is 70.').exec()
            return

        # Validate acceptable data
        front_path = self.__front_img_le.text()
        back_path = self.__back_img_le.text()
        if not (front_path and back_path):
            ErrorDialog(self, 'Missing filename', 'Front and/or back image '
                        'path has not been set').exec()
            return
        if front_path == back_path:
            ErrorDialog(self, 'Same filename', 'Front and back images cannot '
                        'have the same path').exec()
            return
        card_width = int(self.__card_width_le.text())
        if not 32 <= card_width <= 4096:
            ErrorDialog(self, 'Card width issue', 'Card width must be '
                        'within 32..4096 pixels').exec()
            return
        if os.path.exists(front_path) or os.path.exists(back_path):
            _q = QtWidgets.QMessageBox.question
            _res = _q(self, 'File(s) already exist', 'Front and/or back '
                      'image already exist. Proceed with overwriting?',
                      QtWidgets.QDialogButtonBox.Ok,
                      QtWidgets.QDialogButtonBox.Cancel)
            if _res == QtWidgets.QDialogButtonBox.Cancel:
                return

        # Calculate relevant dimensions for export
        card_cols = min(4096//card_width, 10)
        card_rows = len(self.__cards)//card_cols
        if len(self.__cards) % card_cols:
            card_rows += 1
        if card_rows == 1:
            card_cols = len(self.__cards)
        _s_c_height = self.__settings.card_height_mm
        _s_c_width = self.__settings.card_width_mm
        card_height = int(card_width*(_s_c_height/_s_c_width))
        card_size = QtCore.QSize(card_width, card_height)
        out_width = card_cols*card_width
        out_height = card_rows*card_height

        # Generate card front image
        pix = QtGui.QPixmap(out_width, out_height)
        p = QtGui.QPainter(pix)
        col, row = 0, 0
        for card in self.__cards:
            xpos, ypos = col*card_width, row*card_height
            c_img = card.front_img
            c_img = c_img.scaled(card_size,
                                 mode=QtCore.Qt.SmoothTransformation)
            p.drawImage(QtCore.QPoint(xpos, ypos), c_img)
            col += 1
            if col >= card_cols:
                row += 1
                col = 0
        del p
        front_img = pix.toImage()

        # Generate card back images
        pix = QtGui.QPixmap(out_width, out_height)
        p = QtGui.QPainter(pix)
        col, row = 0, 0
        for card in self.__cards:
            xpos, ypos = col*card_width, row*card_height
            c_img = card.back_img
            if c_img:
                if card.back_bleed > 0:
                    c_img = LcgImage(c_img).cropBleed(card.back_bleed)
                c_img = c_img.scaled(card_size,
                                     mode=QtCore.Qt.SmoothTransformation)
                p.drawImage(QtCore.QPoint(xpos, ypos), c_img)
            col += 1
            if col >= card_cols:
                row += 1
                col = 0
        del p
        back_img = pix.toImage()

        # Save the images
        try:
            front_img.save(front_path)
        except Exception as e:
            ErrorDialog(self, 'Image save error', 'Could not save file '
                        f'"{front_path}": {e}').exec()
            return
        try:
            back_img.save(back_path)
        except Exception as e:
            ErrorDialog(self, 'Image save error', 'Could not save file '
                        f'"{back_path}": {e}').exec()
            return

        # Display message about success export and how to import in TTS
        title = 'Images successfully exported'
        text = ('<p>The images were successfully exported as the files '
                f'"{front_path}" and "{back_path}".</p>'

                'In order to import these files into a Tabletop Simulator '
                '(TTS) game, perform the following operations in an active '
                'game (instructions confirmed with TTS version 13):</p>'

                '<ul>'
                '  <li>In TTS, choose Objects->Components->Custom->Deck</li>'
                '  <li>Click somewhere on the board, then hit Escape</li>'
                '  <li>In the "Face" field, insert front images file or URL</li>'
                '  <li>Select "Unique Backs"</li>'
                '  <li>In the "Back" field, insert back images file or URL</li>'
                f'  <li>In the "Width" field, enter {card_cols}</li>'
                f'  <li>In the "Height" field, enter {card_rows}</li>'
                f'  <li>In the "Number" field, enter {len(self.__cards)}</li>'
                '</ul>'

                '<p>If the deck is intended to be accessible to other users, '
                'the images must be published to Internet accessible URLs '
                'which can be downloaded by TTS. Make sure to enter those URLs '
                'in the fields "Face" and "Back", rather than selecting '
                'local files.</p>')
        info = QtWidgets.QMessageBox(self, title, '')
        info.setInformativeText(text)
        info.setStandardButtons(QtWidgets.QMessageBox.Ok)
        info.setDefaultButton(QtWidgets.QMessageBox.Ok)
        info.exec()

        super().accept()

    @QtCore.Slot()
    def frontImgBtnClicked(self, checked):
        while True:
            _get = QtWidgets.QFileDialog.getSaveFileName
            title = 'Select output image file for card fronts'
            filter = 'PNG (*.png);;JPEG (*.jpg *.jpeg)'
            _n, _f = _get(self, title, filter=filter)
            if _n:
                other_txt = self.__back_img_le.text()
                if other_txt and _n == other_txt:
                    ErrorDialog(self, 'Invalid file', 'Front and back images '
                                'cannot have the same path').exec()
                else:
                    self.__front_img_le.setText(_n)
                    break
            else:
                break

    @QtCore.Slot()
    def backImgBtnClicked(self, checked):
        while True:
            _get = QtWidgets.QFileDialog.getSaveFileName
            title = 'Select output image file for card backs'
            filter = 'PNG (*.png);;JPEG (*.jpg *.jpeg)'
            _n, _f = _get(self, title, filter=filter)
            if _n:
                other_txt = self.__front_img_le.text()
                if other_txt and _n == other_txt:
                    ErrorDialog(self, 'Invalid file', 'Front and back images '
                                'cannot have the same path').exec()
                else:
                    self.__back_img_le.setText(_n)
                    break
            else:
                break
