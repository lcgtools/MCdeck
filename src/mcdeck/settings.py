#!/usr/bin/env python3
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

"""Settings object and settings dialog."""

import math

from lcgtools import LcgException
from PySide6 import QtWidgets, QtCore, QtGui

import mcdeck.octgn
import mcdeck.util


class Settings(QtCore.QSettings):
    """Persistent settings."""

    def __init__(self):
        super().__init__('Cloudberries', 'lcgtools')

        # Cache for card back images
        self.__player_back_img = None
        self.__encounter_back_img = None
        self.__villain_back_img = None
        self.__locale = None

        # Check whether country (probably) uses A4 as default
        self.__a4_default = self.uses_a4_as_default()

    def player_back_image(self):
        """Returns player back image if filename is set, otherwise None.

        :return: card back image (or None)
        :rtype:  QtGui.QImage

        Also returns None if image could not be loaded.

        """
        if not self.__player_back_img:
            img = QtGui.QImage()
            fname = self.card_back_file_player
            if fname and img.load(fname):
                self.__player_back_img = img
        return self.__player_back_img

    def encounter_back_image(self):
        """Returns encounter back image if filename is set, otherwise None.

        :return: card back image (or None)
        :rtype:  QtGui.QImage

        Also returns None if image could not be loaded.

        """
        if not self.__encounter_back_img:
            img = QtGui.QImage()
            fname = self.card_back_file_encounter
            if fname and img.load(fname):
                self.__encounter_back_img = img
        return self.__encounter_back_img

    def villain_back_image(self):
        """Returns villain back image if filename is set, otherwise None.

        :return: card back image (or None)
        :rtype:  QtGui.QImage

        Also returns None if image could not be loaded.

        """
        if not self.__villain_back_img:
            img = QtGui.QImage()
            fname = self.card_back_file_villain
            if fname and img.load(fname):
                self.__villain_back_img = img
        return self.__villain_back_img

    def locale(self):
        """The default system locale.

        :return: default system locale
        :rtype:  :class:`QtCore.QLocale`

        """
        if self.__locale is None:
            self.__locale = QtCore.QLocale()
        return self.__locale

    def uses_a4_as_default(self):
        """Return True if locale country (probably) uses A4 page format."""
        country = self.locale().country()
        Country = QtCore.QLocale.Country
        if country in (Country.UnitedStates,
                       Country.UnitedStatesOutlyingIslands,
                       Country.UnitedStatesMinorOutlyingIslands,
                       Country.UnitedStatesVirginIslands,
                       Country.Canada, Country.Chile, Country.Colombia,
                       Country.CostaRica, Country.Mexico, Country.Panama,
                       Country.Guatemala, Country.DominicanRepublic,
                       Country.Philippines):
            # As per https://en.wikipedia.org/wiki/Letter_(paper_size)
            return False
        else:
            return True

    def clear(self):
        super().clear()
        self.__player_back_img = None
        self.__encounter_back_img = None
        self.__villain_back_img = None

    @property
    def pagesize(self):
        """Pagesize (se :attr:`pagesize_list` for allowed values)."""
        size = self.value('pagesize', 'a4' if self.__a4_default else 'letter')
        if size is None:
            size = 'letter' if self.uses_letter_as_default() else 'a4'
        return size

    @pagesize.setter
    def pagesize(self, value):
        value = value.lower()
        if value not in self.pagesize_list:
            raise ValueError('Illegal value')
        self.setValue('pagesize', value)

    @property
    def pagesize_list(self):
        """List of allowed values for :attr:`pagesize`."""
        return ('a4', 'a3', 'letter', 'tabloid')

    @property
    def page_margin_mm(self):
        """Page margin in mm."""
        return float(self.value('page_margin', 5))

    @page_margin_mm.setter
    def page_margin_mm(self, value):
        if value <= 0:
            raise ValueError('Margin must be > 0')
        self.setValue('page_margin', str(value))

    @property
    def feed_dir(self):
        """Paper feed direction (see :attr:`feed_dir_list` for values)"""
        return self.value('feed_dir', 'portrait')

    @feed_dir.setter
    def feed_dir(self, value):
        value = value.lower()
        if value not in self.feed_dir_list:
            raise ValueError('Illegal value')
        self.setValue('feed_dir', value)

    @property
    def feed_dir_list(self):
        """Allowed values for :attr:`feed_dir`"""
        return ('portrait', 'landscape')

    @property
    def page_dpi(self):
        """Resolution in DPI of generated PDF."""
        return float(self.value('page_dpi', 600))

    @page_dpi.setter
    def page_dpi(self, value):
        if value <= 0:
            raise ValueError('Value must be > 0')
        self.setValue('page_dpi', str(value))

    @property
    def card_width_mm(self):
        """Card width in mm on generated PDF (without bleed)."""
        return float(self.value('card_width_mm', 61.5))

    @card_width_mm.setter
    def card_width_mm(self, value):
        if value <= 0:
            raise ValueError('Value must be > 0')
        self.setValue('card_width_mm', str(value))

    @property
    def card_height_mm(self):
        """Card height in mm on generated PDF (without bleed)."""
        return float(self.value('card_height_mm', 88.0))

    @card_height_mm.setter
    def card_height_mm(self, value):
        if value <= 0:
            raise ValueError('Value must be > 0')
        self.setValue('card_height_mm', str(value))

    @property
    def card_bleed_mm(self):
        """Card bleed in mm on generated PDF (all card sides)."""
        return float(self.value('card_bleed_mm', 2))

    @card_bleed_mm.setter
    def card_bleed_mm(self, value):
        if value <= 0:
            raise ValueError('Value must be > 0')
        self.setValue('card_bleed_mm', str(value))

    @property
    def card_min_spacing_mm(self):
        """Minimum spacing (in mm) between cards on generated PDF."""
        return float(self.value('card_min_spacing_mm', 1))

    @card_min_spacing_mm.setter
    def card_min_spacing_mm(self, value):
        if value <= 0:
            raise ValueError('Value must be > 0')
        self.setValue('card_min_spacing_mm', str(value))

    @property
    def card_fold_distance_mm(self):
        """Distance from fold line (in mm) on fold print PDF."""
        return float(self.value('card_fold_distance_mm', 3))

    @card_fold_distance_mm.setter
    def card_fold_distance_mm(self, value):
        if value <= 0:
            raise ValueError('Value must be > 0')
        self.setValue('card_fold_distance_mm', str(value))

    @property
    def twosided(self):
        """If True generate PDF for  2-sided print, otherwise fold-printing."""
        return bool(self.value('twosided', True))

    @twosided.setter
    def twosided(self, value):
        self.setValue('twosided', bool(value))

    @property
    def card_back_file_player(self):
        """File name of card back for player cards (None if not set)."""
        return self.value('card_back_file_player', None)

    @card_back_file_player.setter
    def card_back_file_player(self, name):
        if name and not QtGui.QImage().load(name):
            raise LcgException(f'Not a valid (supported) image: {name}')
        self.setValue('card_back_file_player', name)
        self.__player_back_img = None

    @property
    def card_back_file_encounter(self):
        """File name of card back for encounter cards (None if not set)."""
        return self.value('card_back_file_encounter', None)

    @card_back_file_encounter.setter
    def card_back_file_encounter(self, name):
        if name and not QtGui.QImage().load(name):
            raise LcgException(f'Not a valid (supported) image: {name}')
        self.setValue('card_back_file_encounter', name)
        self.__encounter_back_img = None

    @property
    def card_back_file_villain(self):
        """File name of card back for villain cards (None if not set)."""
        return self.value('card_back_file_villain', None)

    @card_back_file_villain.setter
    def card_back_file_villain(self, name):
        if name and not QtGui.QImage().load(name):
            raise LcgException(f'Not a valid (supported) image: {name}')
        self.setValue('card_back_file_villain', name)
        self.__villain_back_img = None

    @property
    def player_bleed_mm(self):
        """Bleed included in player card back (mm)."""
        return float(self.value('player_bleed_mm', 0))

    @player_bleed_mm.setter
    def player_bleed_mm(self, value):
        if value < 0:
            raise ValueError('Value must be >= 0')
        self.setValue('player_bleed_mm', str(value))

    @property
    def encounter_bleed_mm(self):
        """Bleed included in encounter card back (mm)."""
        return float(self.value('encounter_bleed_mm', 0))

    @encounter_bleed_mm.setter
    def encounter_bleed_mm(self, value):
        if value < 0:
            raise ValueError('Value must be >= 0')
        self.setValue('encounter_bleed_mm', str(value))

    @property
    def villain_bleed_mm(self):
        """Bleed included in villain card back (mm)."""
        return float(self.value('villain_bleed_mm', 0))

    @villain_bleed_mm.setter
    def villain_bleed_mm(self, value):
        if value < 0:
            raise ValueError('Value must be >= 0')
        self.setValue('villain_bleed_mm', str(value))

    @property
    def octgn_path(self):
        """Path to OCTGN Data/ directory."""
        return self.value('octgn_path', None)

    @octgn_path.setter
    def octgn_path(self, value):
        self.setValue('octgn_path', value)

    @property
    def octgn_card_sets_path(self):
        """Default path for OCTGN .zip card sets."""
        return self.value('octgn_card_sets_path', None)

    @octgn_card_sets_path.setter
    def octgn_card_sets_path(self, value):
        self.setValue('octgn_card_sets_path', value)

    @property
    def octgn_allow_fanmade_non_o8d(self):
        """If False card set FanMade folderes may only include .o8d files."""
        return self.value('octgn_allow_fanmade_non_o8d', False)

    @octgn_allow_fanmade_non_o8d.setter
    def octgn_allow_fanmade_non_o8d(self, value):
        self.setValue('octgn_allow_fanmade_non_o8d', bool(value))

    @property
    def card_view_width_px(self):
        """Relative offset between cards (front+back) in view."""
        return int(self.value('card_view_width_px', 200))

    @card_view_width_px.setter
    def card_view_width_px(self, value):
        if value != int(value) or value <= 0:
            raise ValueError('Value must be a positive integer')
        self.setValue('card_view_width_px', str(value))

    @property
    def card_back_rel_offset(self):
        """Relative offset of card back shown under card front in view."""
        return float(self.value('card_back_rel_offset', 0.05))

    @card_back_rel_offset.setter
    def card_back_rel_offset(self, value):
        if not 0 <= value <= 1:
            raise ValueError('Value must be in interval [0, 1]')
        self.setValue('card_back_rel_offset', str(value))

    @property
    def card_back_rel_spacing(self):
        """Relative offset between cards (front+back) in view."""
        return float(self.value('card_back_rel_spacing', 0.05))

    @card_back_rel_spacing.setter
    def card_back_rel_spacing(self, value):
        if not 0 <= value <= 1:
            raise ValueError('Value must be in interval [0, 1]')
        self.setValue('card_back_rel_spacing', str(value))

    @property
    def aspect_rotation(self):
        """Aspect rotation (se :attr:`aspect_rotation_list`)."""
        return self.value('aspect_rotation', 'anticlockwise')

    @aspect_rotation.setter
    def aspect_rotation(self, value):
        value = value.lower()
        if value not in self.aspect_rotation_list:
            raise ValueError('Illegal value')
        self.setValue('aspect_rotation', value)

    @property
    def aspect_rotation_list(self):
        """List of allowed values for :attr:`aspect_rotation`."""
        return ('clockwise', 'anticlockwise', 'none')

    @property
    def corner_rounding_mm(self):
        """Rounding of corners in mm in view (no rounding if zero)."""
        return float(self.value('corner_rounding_mm', 3))

    @corner_rounding_mm.setter
    def corner_rounding_mm(self, value):
        if value < 0:
            raise ValueError('Value must be 0 or higher')
        self.setValue('corner_rounding_mm', str(value))


class SettingsDialog(QtWidgets.QDialog):
    """Settings dialog."""

    def __init__(self, settings):
        super().__init__()
        self.__settings = settings

        # Tabbed widgets
        tab_widget = QtWidgets.QTabWidget()
        self.__tabs = []
        tab = SettingsGeneralTab(settings)
        tab_widget.addTab(tab, 'General')
        self.__tabs.append(tab)
        tab = SettingsCardsTab(settings)
        tab_widget.addTab(tab, 'Card Types')
        self.__tabs.append(tab)
        tab = SettingsPdfTab(settings)
        tab_widget.addTab(tab, 'PDF export')
        self.__tabs.append(tab)
        tab = SettingsOctgnTab(settings)
        tab_widget.addTab(tab, 'OCTGN')
        self.__tabs.append(tab)
        tab = SettingsViewTab(settings)
        tab_widget.addTab(tab, 'View')
        self.__tabs.append(tab)

        # Pushbuttons
        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok |
                                          QtWidgets.QDialogButtonBox.Cancel)
        btns.rejected.connect(self.reject)
        btns.accepted.connect(self.accept)

        # Add widgets to layout
        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(tab_widget)
        layout.addWidget(btns)
        self.setLayout(layout)

        self.setWindowTitle('Settings')
        self.setMinimumWidth(500)

    def accept(self):
        # Validate data on tabs before committing
        try:
            for tab in self.__tabs:
                tab.validate()
        except Exception as e:
            msg_box = QtWidgets.QMessageBox(self)
            msg_box.setWindowTitle('Invalid data')
            msg_box.setText('Settings include invalid data.')
            msg_box.setInformativeText(f'Exception: {e}')
            msg_box.setStandardButtons(QtWidgets.QMessageBox.Cancel)
            msg_box.setDefaultButton(QtWidgets.QMessageBox.Cancel)
            msg_box.exec()
        else:
            # Process data on each tab for acceptance
            for tab in self.__tabs:
                tab.commit()
            self.__settings.sync()
            super().accept()


class SettingsGeneralTab(QtWidgets.QDialog):
    """Settings dialog tab for general settings."""

    def __init__(self, settings):
        super().__init__()
        self.__settings = settings

        main_layout = QtWidgets.QVBoxLayout()

        cards_box = QtWidgets.QGroupBox(self)
        cards_box.setTitle('Cards')
        cards_layout = QtWidgets.QGridLayout()
        # Line edits
        def _create_le(val, value):
            w = QtWidgets.QLineEdit()
            w.setValidator(val)
            w.setText(str(value))
            w.setAlignment(QtCore.Qt.AlignRight)
            return w
        _s = self.__settings
        _validator = QtGui.QDoubleValidator(0, math.inf, 2)
        # Card width in millimeters (before applying bleed)
        self.__card_width_le = _create_le(_validator, _s.card_width_mm)
        _tip = 'Physical card width'
        self.__card_width_le.setToolTip(_tip)
        # Card height in millimeters (before applying bleed)
        self.__card_height_le = _create_le(_validator, _s.card_height_mm)
        _tip = 'Physical card height'
        self.__card_height_le.setToolTip(_tip)
        lbl = QtWidgets.QLabel
        row = 0
        cards_layout.addWidget(lbl('Width (mm):'), row, 0)
        cards_layout.addWidget(self.__card_width_le, row, 1, 1, 1)
        row += 1
        cards_layout.addWidget(lbl('Height (mm):'), row, 0)
        cards_layout.addWidget(self.__card_height_le, row, 1, 1, 1)
        cards_box.setLayout(cards_layout)
        main_layout.addWidget(cards_box)

        aspect_layout = QtWidgets.QGridLayout()
        # Combo boxes
        # Rotation to target aspect
        self.__aspect_rotation_cb = QtWidgets.QComboBox()
        _tip = ('If set, cards will automatically rotate to the same aspect '
                'which is implied by specified card dimensions')
        self.__aspect_rotation_cb.setToolTip(_tip)
        for option in self.__settings.aspect_rotation_list:
            self.__aspect_rotation_cb.addItem(option)
        _prop = self.__settings.aspect_rotation
        for i in range(self.__aspect_rotation_cb.count()):
            if self.__aspect_rotation_cb.itemText(i).lower() == _prop:
                self.__aspect_rotation_cb.setCurrentIndex(i)
                break
        else:
            raise RuntimeError('Should never happen')
        lbl = QtWidgets.QLabel
        colspan = 1
        row = 0
        aspect_layout.addWidget(lbl('Rotate to target aspect:'), row, 0)
        aspect_layout.addWidget(self.__aspect_rotation_cb, row, 1, 1, colspan)
        aspect_layout.setRowStretch(aspect_layout.rowCount(), 1)
        main_layout.addLayout(aspect_layout)
        main_layout.addStretch(1)

        self.setMinimumWidth(325)
        self.setLayout(main_layout)

    def validate(self):
        """Checks if data is (probably) valid, raises exception otherwise."""
        # Should be nothing to check here, combo box filters possible values
        _w_fl_val = lambda w: float(w.text())
        _w_fl_val(self.__card_width_le)
        _w_fl_val(self.__card_height_le)

    def commit(self):
        """Commit registered values to config object."""
        _w_fl_val = lambda w: float(w.text())
        self.__settings.card_width_mm = _w_fl_val(self.__card_width_le)
        self.__settings.card_height_mm = _w_fl_val(self.__card_height_le)
        aspect_rotation = self.__aspect_rotation_cb.currentText()
        self.__settings.aspect_rotation = aspect_rotation
        self.accept()


class SettingsCardsTab(QtWidgets.QDialog):
    """Settings dialog tab for card settings."""

    def __init__(self, settings):
        super().__init__()
        self.__settings = settings
        _s = self.__settings

        def _create_le(val, value):
            w = QtWidgets.QLineEdit()
            w.setValidator(val)
            w.setText(str(value))
            w.setAlignment(QtCore.Qt.AlignRight)
            return w
        def _create_le2(value):
            w = QtWidgets.QLineEdit()
            w.setText(str(value))
            return w
        _validator = QtGui.QDoubleValidator(0, math.inf, 2)

        main_layout = QtWidgets.QVBoxLayout()

        files_box = QtWidgets.QGroupBox(self)
        files_box.setTitle('Card back image files by card type')
        files_layout = QtWidgets.QGridLayout(self)
        # Line edits
        lbl = QtWidgets.QLabel
        row = 0
        files_layout.addWidget(lbl('Player:'), row, 0)
        _fname = _s.card_back_file_player
        _fname = '' if not _fname else _fname
        self.__player_back_file = _create_le2(_fname)
        _tip = 'File name of default card back image for player cards'
        self.__player_back_file.setToolTip(_tip)
        files_layout.addWidget(self.__player_back_file, row, 1, 1, 3)
        self.__player_back_btn = QtWidgets.QPushButton('File...')
        self.__player_back_btn.clicked.connect(self.player_file_clicked)
        files_layout.addWidget(self.__player_back_btn, row, 4, 1, 1)
        row += 1
        files_layout.addWidget(lbl('Encounter:'), row, 0)
        _fname = _s.card_back_file_encounter
        _fname = '' if not _fname else _fname
        self.__encounter_back_file = _create_le2(_fname)
        _tip = 'File name of default card back image for encounter cards'
        self.__encounter_back_file.setToolTip(_tip)
        files_layout.addWidget(self.__encounter_back_file, row, 1, 1, 3)
        self.__encounter_back_btn = QtWidgets.QPushButton('File...')
        self.__encounter_back_btn.clicked.connect(self.encounter_file_clicked)
        files_layout.addWidget(self.__encounter_back_btn, row, 4, 1, 1)
        row += 1
        files_layout.addWidget(lbl('Villain:'), row, 0)
        _fname = _s.card_back_file_villain
        _fname = '' if not _fname else _fname
        self.__villain_back_file = _create_le2(_fname)
        _tip = 'File name of default card back image for villain cards'
        self.__villain_back_file.setToolTip(_tip)
        files_layout.addWidget(self.__villain_back_file, row, 1, 1, 3)
        self.__villain_back_btn = QtWidgets.QPushButton('File...')
        self.__villain_back_btn.clicked.connect(self.villain_file_clicked)
        files_layout.addWidget(self.__villain_back_btn, row, 4, 1, 1)
        files_box.setLayout(files_layout)
        main_layout.addWidget(files_box)

        bleed_box = QtWidgets.QGroupBox(self)
        bleed_box.setTitle('Bleed included in image files (mm)')
        bleed_layout = QtWidgets.QGridLayout(self)
        self.__player_bleed = _create_le(_validator, _s.player_bleed_mm)
        _tip = 'Physical bleed included in default player card back image'
        self.__player_bleed.setToolTip(_tip)
        self.__encounter_bleed = _create_le(_validator, _s.encounter_bleed_mm)
        _tip = 'Physical bleed included in default encounter card back image'
        self.__encounter_bleed.setToolTip(_tip)
        self.__villain_bleed = _create_le(_validator, _s.villain_bleed_mm)
        _tip = 'Physical bleed included in default villain card back image'
        self.__villain_bleed.setToolTip(_tip)
        row = 0
        bleed_layout.addWidget(lbl('Player:'), row, 0)
        bleed_layout.addWidget(self.__player_bleed, row, 1, 1, 1)
        row += 1
        bleed_layout.addWidget(lbl('Encounter:'), row, 0)
        bleed_layout.addWidget(self.__encounter_bleed, row, 1, 1, 1)
        row += 1
        bleed_layout.addWidget(lbl('Villain:'), row, 0)
        bleed_layout.addWidget(self.__villain_bleed, row, 1, 1, 1)
        bleed_box.setLayout(bleed_layout)
        main_layout.addWidget(bleed_box)

        main_layout.addStretch(1)

        self.setMinimumWidth(325)
        self.setLayout(main_layout)

    def validate(self):
        """Checks if data is (probably) valid, raises exception otherwise."""
        _w_fl_val = lambda w: float(w.text())
        for w in (self.__player_back_file, self.__encounter_back_file,
                  self.__villain_back_file):
            name = w.text()
            if name and not QtGui.QImage().load(name):
                raise LcgException(f'Could not read card back image: {name}')
        _w_fl_val(self.__player_bleed)
        _w_fl_val(self.__encounter_bleed)
        _w_fl_val(self.__villain_bleed)

    def commit(self):
        """Commit registered values to config object."""
        _w_fl_val = lambda w: float(w.text())
        _name = self.__player_back_file.text()
        if not _name.strip():
            _name = None
        self.__settings.card_back_file_player = _name
        _name = self.__encounter_back_file.text()
        if not _name.strip():
            _name = None
        self.__settings.card_back_file_encounter = _name
        _name = self.__villain_back_file.text()
        if not _name.strip():
            _name = None
        self.__settings.card_back_file_villain = _name

        self.__settings.player_bleed_mm = _w_fl_val(self.__player_bleed)
        self.__settings.encounter_bleed_mm = _w_fl_val(self.__encounter_bleed)
        self.__settings.villain_bleed_mm = _w_fl_val(self.__villain_bleed)

        self.accept()

    @QtCore.Slot()
    def player_file_clicked(self, checked):
        _fun = mcdeck.util.loadImageFromFileDialog
        name = _fun(self, 'Open player card back image', ret_name=True)
        if name:
            self.__player_back_file.setText(name)

    @QtCore.Slot()
    def encounter_file_clicked(self, checked):
        _fun = mcdeck.util.loadImageFromFileDialog
        name = _fun(self, 'Open encounter card back image', ret_name=True)
        if name:
            self.__encounter_back_file.setText(name)

    @QtCore.Slot()
    def villain_file_clicked(self, checked):
        _fun = mcdeck.util.loadImageFromFileDialog
        name = _fun(self, 'Open villain card back image', ret_name=True)
        if name:
            self.__villain_back_file.setText(name)


class SettingsPdfTab(QtWidgets.QDialog):
    """Settings dialog tab for settings related to PDF export."""

    def __init__(self, settings):
        super().__init__()
        self.__settings = settings

        # Combo boxes
        _validator = QtGui.QDoubleValidator(0, math.inf, 2)
        # Page size, either A4, A3, Letter or Tabloid
        self.__pagesize_cb = QtWidgets.QComboBox()
        _tip = 'Page format of generated PDF document'
        self.__pagesize_cb.setToolTip(_tip)
        for option in self.__settings.pagesize_list:
            self.__pagesize_cb.addItem(option)
        _prop = self.__settings.pagesize
        for i in range(self.__pagesize_cb.count()):
            if self.__pagesize_cb.itemText(i).lower() == _prop:
                self.__pagesize_cb.setCurrentIndex(i)
                break
        else:
            raise LcgException('Invalid pagesize from settings')
        # Page feed direction; portrait or landscape
        self.__feed_dir_cb = QtWidgets.QComboBox()
        _tip = ('Feed direction when printing the PDF (required for '
                'correct positioning of card backs for 2-sided printing)')
        self.__feed_dir_cb.setToolTip(_tip)
        for option in self.__settings.feed_dir_list:
            self.__feed_dir_cb.addItem(option)
        _prop = self.__settings.feed_dir
        for i in range(self.__feed_dir_cb.count()):
            if self.__feed_dir_cb.itemText(i).lower() == _prop:
                self.__feed_dir_cb.setCurrentIndex(i)
                break
        else:
            raise LcgException('Invalid feed direction from settings')

        # Line edits
        def _create_le(val, value):
            w = QtWidgets.QLineEdit()
            w.setValidator(val)
            w.setText(str(value))
            w.setAlignment(QtCore.Qt.AlignRight)
            return w
        _s = self.__settings
        # PDF output resolution in dots per inch
        self.__dpi_le = _create_le(_validator, _s.page_dpi)
        _tip = 'PDF document graphics resolution in dots per inch'
        self.__dpi_le.setToolTip(_tip)
        # Page margin in millimeters (all sides)
        self.__margin_le = _create_le(_validator, _s.page_margin_mm)
        _tip = 'PDF document\'s page margin (outside printable area for cards)'
        self.__margin_le.setToolTip(_tip)
        # Amount of bleed added in millimeters (all sides)
        self.__card_bleed_le = _create_le(_validator, _s.card_bleed_mm)
        _tip = 'Bleed added for each card in PDF document (all card sides)'
        self.__card_bleed_le.setToolTip(_tip)
        # Minimum horizontal spacing between cards in millimeters
        self.__card_min_spacing_le = _create_le(_validator,
                                                _s.card_min_spacing_mm)
        _tip = 'Minimum space between printed cards (after adding bleed)'
        self.__card_min_spacing_le.setToolTip(_tip)
        # Vertical distance to cards from fold line in millimeters
        self.__card_fold_distance_le = _create_le(_validator,
                                                  _s.card_fold_distance_mm)
        _tip = ('Distance from fold line to cards for folded format '
                'printing')
        self.__card_fold_distance_le.setToolTip(_tip)

        # If True uses twosided printing, if False uses fold printing
        self.__twosided_chk = QtWidgets.QCheckBox('2-sided printing')
        self.__twosided_chk.setChecked(self.__settings.twosided)
        _tip = ('If checked generate PDF for 2-sided printing. If unchecked '
                'generate PDF for "fold&glue" format printing.')
        self.__twosided_chk.setToolTip(_tip)

        main_layout = QtWidgets.QGridLayout(self)
        lbl = QtWidgets.QLabel
        colspan = 1
        row = 0
        main_layout.addWidget(lbl('Page size:'), row, 0)
        main_layout.addWidget(self.__pagesize_cb, row, 1, 1, colspan)
        row += 1
        main_layout.addWidget(lbl('Paper feed direction:'), row, 0)
        main_layout.addWidget(self.__feed_dir_cb, row, 1, 1, colspan)
        row += 1
        main_layout.addWidget(lbl('PDF resolution (DPI):'), row, 0)
        main_layout.addWidget(self.__dpi_le, row, 1, 1, colspan)
        row += 1
        main_layout.addWidget(lbl('Page margin (mm):'), row, 0)
        main_layout.addWidget(self.__margin_le, row, 1, 1, colspan)
        row += 1
        main_layout.addWidget(lbl('Card bleed (mm):'), row, 0)
        main_layout.addWidget(self.__card_bleed_le, row, 1, 1, colspan)
        row += 1
        main_layout.addWidget(lbl('Minimum card spacing (mm):'), row, 0)
        main_layout.addWidget(self.__card_min_spacing_le, row, 1, 1, colspan)
        row += 1
        main_layout.addWidget(lbl('Fold line distance (mm):'), row, 0)
        main_layout.addWidget(self.__card_fold_distance_le, row, 1, 1, colspan)
        row += 1
        main_layout.addWidget(self.__twosided_chk, row, 0)

        main_layout.setRowStretch(main_layout.rowCount(), 1)

        self.setMinimumWidth(325)
        self.setLayout(main_layout)

    def validate(self):
        """Checks if data is (probably) valid, raises exception otherwise."""
        _w_fl_val = lambda w: float(w.text())
        _w_fl_val(self.__margin_le)
        _w_fl_val(self.__dpi_le)
        _w_fl_val(self.__card_bleed_le)
        _w_fl_val(self.__card_min_spacing_le)
        _w_fl_val(self.__card_fold_distance_le)

    def commit(self):
        """Commit registered values to config object."""
        self.__settings.pagesize = self.__pagesize_cb.currentText()
        self.__settings.feed_dir = self.__feed_dir_cb.currentText()
        _w_fl_val = lambda w: float(w.text())
        self.__settings.page_margin_mm = _w_fl_val(self.__margin_le)
        self.__settings.page_dpi = _w_fl_val(self.__dpi_le)
        self.__settings.card_bleed_mm = _w_fl_val(self.__card_bleed_le)
        _val = self.__card_min_spacing_le
        self.__settings.card_min_spacing_mm = _w_fl_val(_val)
        _val = self.__card_fold_distance_le
        self.__settings.card_fold_distance_mm = _w_fl_val(_val)
        self.__settings.twosided = self.__twosided_chk.isChecked()
        self.accept()


class SettingsOctgnTab(QtWidgets.QDialog):
    """Settings dialog tab for OCTGN."""

    def __init__(self, settings):
        super().__init__()
        self.__settings = settings
        _s = self.__settings

        main_layout = QtWidgets.QVBoxLayout()

        _box = QtWidgets.QGroupBox(self)
        _box.setTitle('OCTGN data directory')
        _layout = QtWidgets.QGridLayout(self)
        # Line edits
        lbl = QtWidgets.QLabel
        row = 0
        _layout.addWidget(lbl('Data Path:'), row, 0)
        _fname = _s.octgn_path
        _fname = '' if not _fname else _fname
        self.__octgn_path_le = QtWidgets.QLineEdit()
        self.__octgn_path_le.setText(_fname)
        _tip = ('Path to OCTGN data directory, typically '
                '~\\AppData\\Local\\Programs\\OCTGN\\Data\\')
        self.__octgn_path_le.setToolTip(_tip)
        _layout.addWidget(self.__octgn_path_le, row, 1)
        self.__octgn_path_btn = QtWidgets.QPushButton('Directory...')
        self.__octgn_path_btn.clicked.connect(self.octgn_path_clicked)
        _layout.addWidget(self.__octgn_path_btn, row, 2)
        row += 1
        _layout.addWidget(lbl('Card Set Path:'), row, 0)
        _fname = _s.octgn_card_sets_path
        _fname = '' if not _fname else _fname
        self.__octgn_card_sets_path_le = QtWidgets.QLineEdit()
        self.__octgn_card_sets_path_le.setText(_fname)
        _tip = ('Default path for card sets packaged as .zip files, for '
                'conveniently (un)installing card sets (see the Tools menu).')
        self.__octgn_card_sets_path_le.setToolTip(_tip)
        _layout.addWidget(self.__octgn_card_sets_path_le, row, 1)
        self.__octgn_card_sets_path_btn = QtWidgets.QPushButton('Directory...')
        _w = self.__octgn_card_sets_path_btn
        _w.clicked.connect(self.octgn_card_sets_path_clicked)
        _layout.addWidget(self.__octgn_card_sets_path_btn, row, 2)
        _box.setLayout(_layout)
        main_layout.addWidget(_box)
        _l = QtWidgets.QHBoxLayout()
        self.__octgn_allow_non_o8d_chk = QtWidgets.QCheckBox()
        _checked = _s.octgn_allow_fanmade_non_o8d
        self.__octgn_allow_non_o8d_chk.setChecked(_checked)
        _tip = ('If unchecked, card set install/uninstall fails if the '
                'FanMade folder includes other content than .o8d files')
        self.__octgn_allow_non_o8d_chk.setToolTip(_tip)
        _l.addWidget(self.__octgn_allow_non_o8d_chk)
        _l.addWidget(lbl('Allow FanMade folder content other than .o8d'))
        _l.addStretch(1)
        main_layout.addLayout(_l)
        main_layout.addStretch(1)

        self.setLayout(main_layout)

    def validate(self):
        """Checks if data is (probably) valid, raises exception otherwise."""
        path = self.__octgn_path_le.text()
        if path:
            try:
                mcdeck.octgn.OctgnCardSetData.validate_octgn_data_path(path)
            except Exception as e:
                raise LcgException(f'Path {path} appears not to be a valid '
                                   f'OCTGN Data/ directory: {e}')

    def commit(self):
        """Commit registered values to config object."""
        _name = self.__octgn_path_le.text().strip()
        _name = None if not _name else _name
        self.__settings.octgn_path = _name
        _name = self.__octgn_card_sets_path_le.text().strip()
        _name = None if not _name else _name
        self.__settings.octgn_card_sets_path = _name
        _chk = self.__octgn_allow_non_o8d_chk.isChecked()
        self.__settings.octgn_allow_fanmade_non_o8d = _chk
        self.accept()

    @QtCore.Slot()
    def octgn_path_clicked(self, checked):
        _fun = QtWidgets.QFileDialog.getExistingDirectory
        path = _fun(self, 'Select OCTGN user Data/ directory')
        if path:
            self.__octgn_path_le.setText(path)

    @QtCore.Slot()
    def octgn_card_sets_path_clicked(self, checked):
        _fun = QtWidgets.QFileDialog.getExistingDirectory
        path = _fun(self, 'Select default directory for .zip card sets')
        if path:
            self.__octgn_card_sets_path_le.setText(path)


class SettingsViewTab(QtWidgets.QDialog):
    """Settings dialog tab for settings related to view."""

    def __init__(self, settings):
        super().__init__()
        self.__settings = settings

        # Line edits
        def _create_le(val, value):
            w = QtWidgets.QLineEdit()
            w.setValidator(val)
            w.setText(str(value))
            w.setAlignment(QtCore.Qt.AlignRight)
            return w
        _s = self.__settings
        _validator = QtGui.QDoubleValidator(0, math.inf, 2)
        # Card width in view (pixels) at 100% zoom
        _value = _s.card_view_width_px
        _int_val = QtGui.QIntValidator(10, 2000)
        self.__card_view_width_px = _create_le(_int_val, _value)
        _tip = 'Card width in deck view at 100% zoom level'
        self.__card_view_width_px.setToolTip(_tip)
        # Card back position offset (percent)
        _offset = 100*_s.card_back_rel_offset
        self.__card_back_rel_offset = _create_le(_validator, _offset)
        _tip = ('Offset between card back and card front in deck view, as '
                'a percentage of card width')
        self.__card_back_rel_offset.setToolTip(_tip)
        # Card spacing (percent)
        _spacing = 100*_s.card_back_rel_spacing
        self.__card_back_rel_spacing = _create_le(_validator, _spacing)
        _tip = ('Space between cards in the deck view, as a percentage of '
                'total width of a displayed card (front+back)')
        self.__card_back_rel_spacing.setToolTip(_tip)
        # Corner rounding (mm)
        _value = _s.corner_rounding_mm
        self.__corner_rounding_mm = _create_le(_validator, _value)
        _tip = 'Corner rounding in view, in mm (set to 0 for no rounding)'
        self.__corner_rounding_mm.setToolTip(_tip)

        main_layout = QtWidgets.QGridLayout(self)
        lbl = QtWidgets.QLabel
        colspan = 1
        row = 0
        main_layout.addWidget(lbl('Card width at 100% zoom (px):'), row, 0)
        main_layout.addWidget(self.__card_view_width_px, row, 1, 1, colspan)
        row += 1
        main_layout.addWidget(lbl('Card back relative spacing (%):'), row, 0)
        main_layout.addWidget(self.__card_back_rel_offset, row, 1, 1, colspan)
        row += 1
        main_layout.addWidget(lbl('Card spacing (%):'), row, 0)
        main_layout.addWidget(self.__card_back_rel_spacing, row, 1, 1, colspan)
        row += 1
        main_layout.addWidget(lbl('Corner rounding (mm):'), row, 0)
        main_layout.addWidget(self.__corner_rounding_mm, row, 1, 1, colspan)

        main_layout.setRowStretch(main_layout.rowCount(), 1)

        self.setMinimumWidth(325)
        self.setLayout(main_layout)

    def validate(self):
        """Checks if data is (probably) valid, raises exception otherwise."""
        _w_int_val = lambda w: int(w.text())
        _w_fl_val = lambda w: float(w.text())
        if _w_int_val(self.__card_view_width_px) <= 0:
            raise LcgException('Card width must be positive')
        if not 0 <= _w_fl_val(self.__card_back_rel_offset) <= 100:
            raise LcgException('Relative offset must be 0-100')
        if not 0 <= _w_fl_val(self.__card_back_rel_spacing) <= 100:
            raise LcgException('Relative spacing must be 0-100')
        if not 0 <= _w_fl_val(self.__corner_rounding_mm):
            raise LcgException('Corner rounding must be >= 0')

    def commit(self):
        """Commit registered values to config object."""
        _w_int_val = lambda w: int(w.text())
        _w_fl_val = lambda w: float(w.text())
        _value = _w_int_val(self.__card_view_width_px)
        self.__settings.card_view_width_px = _value
        _offset = _w_fl_val(self.__card_back_rel_offset)/100
        self.__settings.card_back_rel_offset = _offset
        _spacing = _w_fl_val(self.__card_back_rel_spacing)/100
        self.__settings.card_back_rel_spacing = _spacing
        _rounding = _w_fl_val(self.__corner_rounding_mm)
        self.__settings.corner_rounding_mm = _rounding
        self.accept()
