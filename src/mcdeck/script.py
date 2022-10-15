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

"""GUI app for building custom card decks for Marvel Champions: TCG."""

from argparse import ArgumentParser
import hashlib
import http.client
import os.path
import pathlib
import posixpath
import sys
import tempfile
import urllib.request
import zipfile

from PySide6 import QtWidgets, QtCore, QtGui

from lcgtools import LcgException
from lcgtools.graphics import LcgCardPdfGenerator, LcgImage
from lcgtools.util import LcgAppResources

import mcdeck
from mcdeck.marvelcdb import MarvelCDB
import mcdeck.octgn as octgn
from mcdeck.settings import Settings, SettingsDialog
from mcdeck.tts import TTSExportDialog
from mcdeck.util import loadImageFromFileDialog, ErrorDialog, download_image
from mcdeck.util import DeckUndoBuffer, to_posix_path, to_local_path
from mcdeck.util import image_mime_type, parse_mcd_file_section_header


class MCDeck(QtWidgets.QMainWindow):
    """Main app window."""

    settingsChanged = QtCore.Signal()  # App settings changed

    settings = Settings()
    conf = None
    root = None
    deck = None
    game = None
    _front_on_top = True
    _clipboard = None
    _export_pdf_action = None

    def __init__(self):
        super().__init__()

        # Set main window title
        self.setWindowTitle('MCdeck - custom card deck builder')

        # Set up main window layout with a Deck as the single contained widget
        deck = Deck()
        if MCDeck.root:
            raise LcgException('Cannot only instantiate one single MCDeck')
        else:
            MCDeck.root = self
        MCDeck.deck = deck
        layout = QtWidgets.QGridLayout()
        layout.addWidget(deck, 0, 0)
        widget = QtWidgets.QWidget()
        widget.setLayout(layout)
        self.setCentralWidget(widget)

        # Define actions
        icon = self.style().standardIcon(QtWidgets.QStyle.SP_FileIcon)
        action = QtGui.QAction(icon, '&New', self)
        action.setShortcut('Ctrl+N')
        action.triggered.connect(deck.newDeck)
        action.setStatusTip('Discard current cards and start new deck')
        new_action = action

        icon = self.style().standardIcon(QtWidgets.QStyle.SP_DialogOpenButton)
        action = QtGui.QAction(icon, '&Open ...', self)
        action.setShortcut('Ctrl+O')
        action.triggered.connect(deck.openDeck)
        action.setStatusTip('Open deck from loadable .zip or .mcd')
        load_action = action

        icon = self.style().standardIcon(QtWidgets.QStyle.SP_DialogSaveButton)
        action = QtGui.QAction(icon, '&Save', self)
        action.setShortcut('Ctrl+S')
        action.triggered.connect(deck.saveDeck)
        action.setStatusTip('Save the deck')
        self.__save_action = action

        action = QtGui.QAction('Save &as ...', self)
        action.setShortcut('Ctrl+Shift+S')
        action.triggered.connect(deck.saveDeckAs)
        action.setStatusTip('Save the deck, selecting a new filename')
        self.__save_as_action = action

        action = QtGui.QAction('&PDF ...', self)
        action.setShortcut('Ctrl+P')
        action.triggered.connect(deck.exportPdf)
        action.setStatusTip('Export deck as a printable PDF document')
        self._export_pdf_action = action

        action = QtGui.QAction('&TTS ...', self)
        action.setShortcut('Ctrl+T')
        action.triggered.connect(deck.exportTts)
        action.setStatusTip('Export Tabletop Simulator deck front/back images')
        export_tts_action = action

        action = QtGui.QAction('&Card set ...', self)
        action.setEnabled(False)
        action.triggered.connect(deck.exportOctgnCardSet)
        action.setStatusTip('Export card set for OCTGN')
        self.__export_octgn_card_set_action = action

        action = QtGui.QAction('&Deck ...', self)
        action.setEnabled(False)
        action.triggered.connect(deck.exportOctgnDeck)
        action.setStatusTip('Export OCTGN .o8d deck')
        self.__export_octgn_deck_action = action

        action = QtGui.QAction('&Exit', self)
        action.setShortcut('Ctrl+Q')
        action.setStatusTip('Exit program')
        action.triggered.connect(self.exitAction)
        exit_action = action

        action = QtGui.QAction('Undo', self)
        action.setShortcut('Ctrl+Z')
        action.setStatusTip('Undo')
        action.triggered.connect(deck.undoAction)
        action.setEnabled(False)
        self.__undo_action = action

        action = QtGui.QAction('Redo', self)
        action.setShortcut('Ctrl+Y')
        action.setStatusTip('Redo')
        action.triggered.connect(deck.redoAction)
        action.setEnabled(False)
        self.__redo_action = action

        action = QtGui.QAction('Cut', self)
        action.setShortcut('Ctrl+X')
        action.setStatusTip('Cut selected cards (only within app)')
        action.triggered.connect(deck.cutCards)
        action.setEnabled(False)
        self.__cut_action = action

        action = QtGui.QAction('Copy', self)
        action.setShortcut('Ctrl+C')
        action.setStatusTip('Copy selected cards (only within app)')
        action.triggered.connect(deck.copyCards)
        action.setEnabled(False)
        self.__copy_action = action

        action = QtGui.QAction('Copy front image', self)
        action.setShortcut('Ctrl+Shift+F')
        action.setStatusTip('Copy front of selected card')
        action.triggered.connect(deck.copyCardFront)
        action.setEnabled(False)
        self.__copy_front = action

        action = QtGui.QAction('Copy back image', self)
        action.setShortcut('Ctrl+Shift+B')
        action.setStatusTip('Copy back of selected card')
        action.triggered.connect(deck.copyCardBack)
        action.setEnabled(False)
        self.__copy_back = action

        action = QtGui.QAction('Paste', self)
        action.setShortcut('Ctrl+V')
        action.setStatusTip('Paste after current (selected) card(s)')
        action.triggered.connect(deck.paste)
        action.setEnabled(False)
        self.__paste_action = action

        action = QtGui.QAction('Paste before', self)
        action.setStatusTip('Paste before current (selected) card(s)')
        action.triggered.connect(deck.pasteBefore)
        action.setEnabled(False)
        self.__paste_before_action = action

        action = QtGui.QAction('Paste as &player', self)
        action.setShortcut('Ctrl+1')
        action.setStatusTip('Paste as player type card')
        action.triggered.connect(deck.pastePlayer)
        action.setEnabled(False)
        self.__paste_player_action = action

        action = QtGui.QAction('Paste as &encounter', self)
        action.setShortcut('Ctrl+2')
        action.setStatusTip('Paste as encounter type card')
        action.triggered.connect(deck.pasteEncounter)
        action.setEnabled(False)
        self.__paste_encounter_action = action

        action = QtGui.QAction('Paste as v&illain', self)
        action.setShortcut('Ctrl+3')
        action.setStatusTip('Paste as villain type card')
        action.triggered.connect(deck.pasteVillain)
        action.setEnabled(False)
        self.__paste_villain_action = action

        action = QtGui.QAction('&Settings', self)
        action.setShortcut('Ctrl+,')
        action.setStatusTip('Edit settings')
        action.triggered.connect(self.menu_sel_settings)
        settings_action = action

        action = QtGui.QAction('&Reset settings', self)
        action.setStatusTip('Reset settings to default values')
        action.triggered.connect(self.menu_res_settings)
        reset_action = action

        action = QtGui.QAction('Show card &back on top', self)
        action.setCheckable(True)
        action.setShortcut('Ctrl+B')
        action.setStatusTip('Show the back image on top')
        action.toggled.connect(deck.back_image_on_top)
        self.__back_on_top = action

        action = QtGui.QAction('&Reset', self)
        action.setShortcut('Ctrl+0')
        action.setStatusTip('Reset zoom to 100% zoom level')
        action.triggered.connect(deck.zoom_reset)
        zoom_reset_action = action

        action = QtGui.QAction('Zoom &In', self)
        key = QtGui.QKeySequence(QtCore.Qt.CTRL | QtCore.Qt.Key_Plus)
        action.setShortcut(key)
        action.setStatusTip('Zoom in one zoom level')
        action.triggered.connect(deck.zoom_in)
        zoom_in_action = action

        action = QtGui.QAction('Zoom &out', self)
        key = QtGui.QKeySequence(QtCore.Qt.CTRL | QtCore.Qt.Key_Minus)
        action.setShortcut(key)
        action.setStatusTip('Zoom out one zoom level')
        action.triggered.connect(deck.zoom_out)
        zoom_out_action = action

        action = QtGui.QAction('Select &all', self)
        action.setShortcut('Ctrl+A')
        action.setStatusTip('Select all cards')
        action.triggered.connect(deck.selectAll)
        select_all_action = action

        action = QtGui.QAction('Select &none', self)
        action.setShortcut('Ctrl+Shift+A')
        action.setStatusTip('Unselect all cards')
        action.triggered.connect(deck.selectNone)
        select_none_action = action

        action = QtGui.QAction('Set &player type', self)
        action.setShortcut('Ctrl+4')
        action.setStatusTip('Set card type to player')
        action.setEnabled(False)
        action.triggered.connect(deck.setPlayerType)
        self.__set_player = action

        action = QtGui.QAction('Set &encounter type', self)
        action.setShortcut('Ctrl+5')
        action.setStatusTip('Set card type to encounter')
        action.setEnabled(False)
        action.triggered.connect(deck.setEncounterType)
        self.__set_encounter = action

        action = QtGui.QAction('Set &villain type', self)
        action.setShortcut('Ctrl+6')
        action.setStatusTip('Set card type to villain')
        action.setEnabled(False)
        action.triggered.connect(deck.setVillainType)
        self.__set_villain = action

        action = QtGui.QAction('Set &unspecified type', self)
        action.setShortcut('Ctrl+7')
        action.setStatusTip('Set card type to unspecified')
        action.setEnabled(False)
        action.triggered.connect(deck.setUnspecifiedType)
        self.__set_unspecified = action

        action = QtGui.QAction('Load &front image ...', self)
        action.setStatusTip('Open image file as new front side')
        action.setEnabled(False)
        action.triggered.connect(deck.setFrontImage)
        self.__set_front_image = action

        action = QtGui.QAction('Load &back image ...', self)
        action.setStatusTip('Open image file as new back side')
        action.setEnabled(False)
        action.triggered.connect(deck.setBackImage)
        self.__set_back_image = action

        action = QtGui.QAction('Use &front as back', self)
        action.setStatusTip('Set back side to be the same as the front image')
        action.setEnabled(False)
        action.triggered.connect(deck.useFrontAsBack)
        self.__use_front_as_back = action

        action = QtGui.QAction('&Remove back', self)
        action.setStatusTip('Remove the back side image (but keep card type)')
        action.setEnabled(False)
        action.triggered.connect(deck.removeBackImage)
        self.__remove_back_image = action

        action = QtGui.QAction('Rota&te 180°', self)
        action.setShortcut('Ctrl+R')
        action.setStatusTip('Rotates the front card(s) 180°')
        action.setEnabled(False)
        action.triggered.connect(deck.rotateHalfCircle)
        self.__rotate_half_circle = action

        action = QtGui.QAction('Rotate 90° (&clockwise)', self)
        action.setStatusTip('Rotates the front card(s) 90° clockwise')
        action.setEnabled(False)
        action.triggered.connect(deck.rotateClockwise)
        self.__rotate_clockwise = action

        action = QtGui.QAction('Rotate 90° (&anticlockwise)', self)
        action.setStatusTip('Rotates the front card(s) 90° anticlockwise')
        action.setEnabled(False)
        action.triggered.connect(deck.rotateAntiClockwise)
        self.__rotate_anti_clockwise = action

        action = QtGui.QAction('Delete', self)
        key = QtGui.QKeySequence(QtCore.Qt.Key_Delete)
        action.setShortcut(key)
        action.setStatusTip('Deletes selected card(s)')
        action.setEnabled(False)
        action.triggered.connect(deck.deleteCards)
        self.__delete_cards = action

        action = QtGui.QAction('&Get back images ...', self)
        action.setStatusTip('Install card back images from Hall of Heroes')
        action.triggered.connect(self.menu_download_card_backs)
        self.__download_card_backs = action

        action = QtGui.QAction('Import card ...', self)
        action.setShortcut('Ctrl+M')
        action.setStatusTip('Import card from marvelcdb.com')
        action.triggered.connect(self.menu_mcdb_import_card)
        mcdb_import_card = action

        action = QtGui.QAction('Import deck ...', self)
        action.setShortcut('Shift+Ctrl+M')
        action.setStatusTip('Import deck from marvelcdb.com')
        action.triggered.connect(self.menu_mcdb_import_deck)
        mcdb_import_deck = action

        action = QtGui.QAction('Enable', self)
        action.setStatusTip('Enable OCTGN metadata for deck')
        action.triggered.connect(self.menu_octgn_enable)
        self._octgn_enable = action

        action = QtGui.QAction('&Edit ...', self)
        action.setShortcut('Ctrl+E')
        action.setStatusTip('Edit OCTGN metadata')
        action.setEnabled(False)
        action.triggered.connect(self.menu_octgn_edit)
        self._octgn_edit = action

        action = QtGui.QAction('&Edit Selected ...', self)
        action.setShortcut('Shift+Ctrl+E')
        action.setStatusTip('Edit OCTGN metadata for selected card(s)')
        action.setEnabled(False)
        action.triggered.connect(self.menu_octgn_edit_selected)
        self._octgn_edit_selected = action

        action = QtGui.QAction('&Delete', self)
        action.setStatusTip('Delete OCTGN metadata')
        action.setEnabled(False)
        action.triggered.connect(self.menu_octgn_delete)
        self._octgn_delete = action

        action = QtGui.QAction('Imp&ort card(s) ...', self)
        action.setShortcut('Shift+Ctrl+O')
        action.setStatusTip('Import card(s) from local OCTGN database')
        action.triggered.connect(self.menu_octgn_import)
        self._octgn_import = action

        action = QtGui.QAction('Import from .o8d ...', self)
        action.setStatusTip('Import card(s) from local OCTGN database')
        action.triggered.connect(self.menu_octgn_import_o8d)
        self._octgn_import_o8d = action

        action = QtGui.QAction('&Install deck as card set', self)
        action.setStatusTip('Install the current deck directly into OCTGN')
        action.setEnabled(False)
        action.triggered.connect(self.menu_octgn_install)
        self._octgn_install = action

        action = QtGui.QAction('&Uninstall deck as card set', self)
        action.setStatusTip('Uninstalls card set with same ID as current deck '
                            ' from OCTGN')
        action.setEnabled(False)
        action.triggered.connect(self.menu_octgn_uninstall)
        self._octgn_uninstall = action

        action = QtGui.QAction('Card set installer', self)
        action.setStatusTip('Install a (set of) .zip format card set(s)')
        action.triggered.connect(self.menu_octgn_card_set_installer)
        self._octgn_card_set_installer = action

        action = QtGui.QAction('Card set uninstaller', self)
        action.setStatusTip('Uninstalls a (set of) .zip format card set(s)')
        action.triggered.connect(self.menu_octgn_card_set_uninstaller)
        self._octgn_card_set_uninstaller = action

        action = QtGui.QAction('&About', self)
        action.setStatusTip('Information about this app')
        action.triggered.connect(self.helpAbout)
        help_about = action

        action = QtGui.QAction('&Resources', self)
        action.setStatusTip('Information about relevant resources')
        action.triggered.connect(self.helpResources)
        help_resources = action

        action = QtGui.QAction('&Usage', self)
        action.setStatusTip('Information about usage')
        action.triggered.connect(self.helpUsage)
        help_usage = action

        # Menu bar
        menu_bar = self.menuBar()
        # Former workaround for non-functional OSX menu integration
        # if platform.system() == 'Darwin':
        #     menu_bar.setNativeMenuBar(False)

        file_menu = menu_bar.addMenu('&File')
        file_menu.addAction(new_action)
        file_menu.addSeparator()
        file_menu.addAction(load_action)
        file_menu.addAction(self.__save_action)
        file_menu.addAction(self.__save_as_action)
        export_menu = file_menu.addMenu('&Export')
        export_menu.addAction(self._export_pdf_action)
        export_menu.addAction(export_tts_action)
        export_octgn_menu = export_menu.addMenu('&Octgn')
        export_octgn_menu.addAction(self.__export_octgn_card_set_action)
        export_octgn_menu.addAction(self.__export_octgn_deck_action)
        file_menu.addSeparator()
        file_menu.addAction(exit_action)

        edit_menu = menu_bar.addMenu('&Edit')
        edit_menu.addAction(self.__undo_action)
        edit_menu.addAction(self.__redo_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self.__cut_action)
        edit_menu.addAction(self.__copy_action)
        edit_menu.addAction(self.__copy_front)
        edit_menu.addAction(self.__copy_back)
        edit_menu.addAction(self.__paste_action)
        paste_menu = edit_menu.addMenu('Paste &special')
        paste_menu.addAction(self.__paste_before_action)
        paste_menu.addAction(self.__paste_player_action)
        paste_menu.addAction(self.__paste_encounter_action)
        paste_menu.addAction(self.__paste_villain_action)
        edit_menu.addSeparator()
        edit_menu.addAction(select_all_action)
        edit_menu.addAction(select_none_action)
        edit_menu.addSeparator()
        edit_menu.addAction(settings_action)
        edit_menu.addAction(reset_action)

        view_menu = menu_bar.addMenu('&View')
        view_menu.addAction(self.__back_on_top)
        zoom_menu = view_menu.addMenu('&Zoom')
        zoom_menu.addAction(zoom_reset_action)
        zoom_menu.addAction(zoom_in_action)
        zoom_menu.addAction(zoom_out_action)

        selection_menu = menu_bar.addMenu('&Selection')
        selection_menu.addAction(self.__set_player)
        selection_menu.addAction(self.__set_encounter)
        selection_menu.addAction(self.__set_villain)
        selection_menu.addAction(self.__set_unspecified)
        selection_menu.addSeparator()
        selection_menu.addAction(self.__set_front_image)
        selection_menu.addAction(self.__set_back_image)
        selection_menu.addAction(self.__use_front_as_back)
        selection_menu.addAction(self.__remove_back_image)
        selection_menu.addSeparator()
        selection_menu.addAction(self.__rotate_half_circle)
        selection_menu.addAction(self.__rotate_clockwise)
        selection_menu.addAction(self.__rotate_anti_clockwise)
        selection_menu.addSeparator()
        selection_menu.addAction(self.__delete_cards)

        tools_menu = menu_bar.addMenu('&Tools')
        tools_menu.addAction(self.__download_card_backs)
        mcdb_menu = tools_menu.addMenu('&MarvelCDB')
        mcdb_menu.addAction(mcdb_import_card)
        mcdb_menu.addAction(mcdb_import_deck)
        octgn_menu = tools_menu.addMenu('&Octgn')
        octgn_menu.addAction(self._octgn_enable)
        octgn_menu.addAction(self._octgn_edit)
        octgn_menu.addAction(self._octgn_edit_selected)
        octgn_menu.addAction(self._octgn_delete)
        octgn_menu.addSeparator()
        octgn_menu.addAction(self._octgn_import)
        octgn_menu.addAction(self._octgn_import_o8d)
        octgn_menu.addSeparator()
        octgn_menu.addAction(self._octgn_install)
        octgn_menu.addAction(self._octgn_uninstall)
        octgn_menu.addSeparator()
        octgn_menu.addAction(self._octgn_card_set_installer)
        octgn_menu.addAction(self._octgn_card_set_uninstaller)
        tools_menu.addSeparator()

        selection_menu = menu_bar.addMenu('&Help')
        selection_menu.addAction(help_about)
        selection_menu.addAction(help_usage)
        selection_menu.addAction(help_resources)

        # Add a toolbar
        toolbar = QtWidgets.QToolBar('Main toolbar')
        toolbar.setIconSize(QtCore.QSize(16,16))
        toolbar.addAction(new_action)
        toolbar.addAction(load_action)
        toolbar.addAction(self.__save_action)
        self.addToolBar(toolbar)

        # Add a status bar
        self.setStatusBar(QtWidgets.QStatusBar(self))

        # Set up some signal/slot connections
        deck.hasSelection.connect(self.deckHasSelection)
        deck.hasClipboard.connect(self.deckHasClipboard)
        self.settingsChanged.connect(deck.settingsChanged)
        deck._undo.haveUndo.connect(self.__undo_action.setEnabled)
        deck._undo.haveRedo.connect(self.__redo_action.setEnabled)
        deck.deckChanged.connect(self.deckChanged)
        deck.filenameChange.connect(self.updateTitleFilename)
        deck.deckHasOctgn.connect(self.enableOctgn)

        # Monitor system clipboard, process once to update menu items
        MCDeck.clipboard().dataChanged.connect(deck.systemClipboardChanged)
        deck.systemClipboardChanged()

        # Enable Drag & Drop onto main window
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        mime = event.mimeData()
        if (mime.hasUrls() or mime.hasImage() or
            'application/x-qt-image' in mime.formats()):
            event.accept()
        else:
            event.ignore()
        event.accept()

    def dropEvent(self, event):
        mime = event.mimeData()

        # If file is a single .zip or .mcd file, process as an "open file"
        # event rather than adding card(s) to the project
        if mime.hasUrls() and len(mime.urls()) == 1:
            url, = mime.urls()
            if url.isLocalFile():
                path = url.toLocalFile()
                _ext = path[-4:].lower()
                if _ext in ('.zip', '.mcd', '.o8d'):
                    if MCDeck.deck.has_cards():
                        _q = QtWidgets.QMessageBox.question
                        _k = QtWidgets.QMessageBox.Open
                        _k = _k | QtWidgets.QMessageBox.Cancel
                        _msg = ('Deck contains cards. Discard current deck to '
                                'load new data?')
                        btn = _q(self, 'Discard current deck?', _msg, _k)
                        if btn == QtWidgets.QMessageBox.Cancel:
                            return
                    if _ext in ('.zip', '.mcd'):
                        MCDeck.deck._open(path)
                        return
                    else:
                        MCDeck.deck.clear(undo=True)
                        try:
                            num = octgn.load_o8d_cards(path, parent=self)
                        except Exception as e:
                            ErrorDialog(self, '.o8d import error', 'Could not '
                                        f'import .o8d file: {e}').exec()
                            MCDeck.deck._undo_action(deselect=False, purge=True)
                        else:
                            MCDeck.deck._deck_changed()
                            MCDeck.deck.reset()
                        return

        # For any other situation, handle through the paste method
        MCDeck.deck.paste(droppedMimeData=mime)

    @classmethod
    def clipboard(cls):
        """Application QClipboard object."""
        if cls._clipboard is None:
            cls._clipboard = QtGui.QGuiApplication.clipboard()
        return cls._clipboard

    @QtCore.Slot()
    def menu_sel_settings(self):
        settings = SettingsDialog(MCDeck.settings)
        if settings.exec():
            self.settingsChanged.emit()

    @QtCore.Slot()
    def menu_res_settings(self):
        _dfun = QtWidgets.QMessageBox.question
        _keys = QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.Cancel
        confirm = _dfun(self, 'Confirm reset', 'Do you really want to reset '
                        'settings to default values?', _keys)
        if confirm == QtWidgets.QMessageBox.Yes:
            MCDeck.settings.clear()
            MCDeck.deck.reset()

    @QtCore.Slot()
    def menu_download_card_backs(self):
        dialog = QtWidgets.QDialog(self)

        main_layout = QtWidgets.QVBoxLayout()
        _hoh_url = 'https://hallofheroeslcg.com/custom-content/'
        _txt = (f'<p>Use card back images from <a href="{_hoh_url}">'
                'Hall of Heroes</a> as the default card backs.</p>'
                '<p>Selecting an image set will (try to) download player, '
                'encounter and villain card back images, and update settings '
                'to use them as the new defaults.</p>'
                '<p>Note: these images may not be the optimal ones for use with'
                ' your printer, and depending on your quality and/or color '
                'correction requirements, you may be better off getting card '
                'back images from other sources.</p>')
        msg = QtWidgets.QLabel(_txt)
        msg.setOpenExternalLinks(True)
        msg.setWordWrap(True)
        main_layout.addWidget(msg)

        card_selector = QtWidgets.QHBoxLayout()
        card_selector.addWidget(QtWidgets.QLabel('Select card set:'))
        cardset_cb = QtWidgets.QComboBox()
        _tip = ('Card set to download and set as default:\n'
                '- Branded, intended for print (source: Hall of Heroes)\n'
                '- Branded, intended for TTS (source: Homebrew)\n'
                '- Promo (source: Hall of Heroes)\n'
                '- Fans (source: Hall of Heroes)')
        cardset_cb.setToolTip(_tip)
        for option in ('Branded, print (HoH)', 'Branded, TTS (Homebrew)',
                       'Promo', 'Fans'):
            cardset_cb.addItem(option)
        card_selector.addWidget(cardset_cb)
        main_layout.addLayout(card_selector)

        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch(1)
        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok |
                                          QtWidgets.QDialogButtonBox.Cancel)
        btns.rejected.connect(dialog.reject)
        btns.accepted.connect(dialog.accept)
        buttons.addWidget(btns)
        main_layout.addLayout(buttons)

        dialog.setLayout(main_layout)
        if dialog.exec():
            cardset = cardset_cb.currentIndex()
            _dict = {0:['marvel-player-back','marvel-encounter-back',
                        'marvel-villain-back'],
                     2:['promo-player-back', 'promo-encounter-back',
                         'promo-villain-back'],
                     3:['fan-back-player', 'fan-back-encounter',
                        'fan-back-villain']}
            if cardset in _dict:
                pre = 'https://hallofheroeshome.files.wordpress.com/2021/02/'
                post = '.png'
                urls = [pre + s + post for s in _dict[cardset]]
            elif cardset == 1:
                urls = [('https://cdn.discordapp.com/attachments/64131799'
                         '9168454685/869297402912321616/trasera_azul.png'),
                        ('https://cdn.discordapp.com/attachments/64131799'
                         '9168454685/869297401549160469/trasera_naranja.png'),
                        ('https://cdn.discordapp.com/attachments/64131799'
                         '9168454685/869297402161537024/trasera_lila.png')]
            else:
                raise RuntimeError('Shold never happen')

            try:
                # Resolve local file names for images
                conf = LcgAppResources(appname='mcdeck', author='Cloudberries')
                conf_dir = conf.user_data_dir()
                back_dir = os.path.join(conf_dir, 'card_back')
                img_paths = []
                for url in urls:
                    _basename = hashlib.sha256(url.encode('utf-8')).hexdigest()
                    _path = os.path.join(back_dir, _basename)
                    img_paths.append(f'{_path}.png')

                # Download images if they do not already exist
                for img_path in img_paths:
                    if not os.path.isfile(img_path):
                        cached = False
                        break
                else:
                    cached = True

                # If not cached, retreive images and store locally
                if not cached:
                    images = []
                    for url in urls:
                        img = download_image(url)
                        img.setWidthMm(63.5)
                        img.setHeightMm(88)
                        images.append(img)

                    # Store downloaded images in standard location
                    pathlib.Path(back_dir).mkdir(parents=True, exist_ok=True)
                    for img, path in zip(images, img_paths):
                        img.save(path)

                # Update settings
                settings = MCDeck.settings
                settings.card_back_file_player = img_paths[0]
                settings.card_back_file_encounter = img_paths[1]
                settings.card_back_file_villain = img_paths[2]
                if cardset == 1:
                    _bleed = 0
                else:
                    _bleed = 2
                settings.player_bleed_mm = _bleed
                settings.encounter_bleed_mm = _bleed
                settings.villain_bleed_mm = _bleed

                _i = QtWidgets.QMessageBox.information
                _msg = ('Settings have been updated to use the images as the '
                        'default card backs for player, encounter and '
                        'villain cards')
                if cached:
                    _msg += ' (using cached images).'
                else:
                    _msg += '.'
                _i(self, 'Settings updated', _msg)
                self.deck.reset()
            except Exception as e:
                err = lambda s1, s2: ErrorDialog(self, s1, s2).exec()
                err('Operation error', f'Could not update images: {e}')

    @QtCore.Slot()
    def menu_mcdb_import_card(self):
        err = lambda s1, s2: ErrorDialog(self, s1, s2).exec()

        # Get card ID(s) or URL(s)
        dialog = MarvelCDBCardImportDialog(self)
        if not dialog.exec():
            return

        # Load cards database (with progress bar) if not already loaded
        try:
            have_db = self._loadMarvelCDB()
        except Exception as e:
            err('MarvelCDB database load error',
                f'Could not load database: {e}')
            return
        else:
            if not have_db:
                return

        # Parse entered values, generating (hopefully valid) IDs.
        s = dialog._le.text().strip()
        if not s:
            err('No input', 'No ID or URL was entered')
            return
        s = s.replace(',', ' ')
        s_l = s.split(' ')
        s_l = [s.strip() for s in s_l if s]
        if not s_l:
            err('Invalid input', 'Invalid format of input')
            return
        id_l = []
        url_prefix = 'https://marvelcdb.com/card/'
        for s in s_l:
            if s.startswith(url_prefix):
                s = s[len(url_prefix):]
            s = s.lower()
            if s.endswith('b'):
                # If alter-ego card, replace with its opposite hero card
                s = s[:-1] + 'a'
            id_l.append(s)

        # Load cards for the provided IDs
        cards = []
        placeholder = dialog._create_placeholders_chk.isChecked()
        self.__operation_cancelled = False
        _qpd = QtWidgets.QProgressDialog
        dlg = _qpd('Importing card(s)', 'Cancel', 0, len(cards))
        dlg.show()

        for code in id_l:
            try:
                _card = MarvelCDB.card(code)
                if _card is None:
                    err('No such card',
                        f'No card with code {code} in local MarvelCDB index')
                    return
                card = _card.to_mcdeck_card(placeholder=placeholder)
                dlg.setValue(dlg.value() + 1)
                QtCore.QCoreApplication.processEvents()  # Force Qt update
                if self.__operation_cancelled:
                    err('Operation cancelled', 'Operation cancelled by user.')
                    return
            except Exception as e:
                dlg.hide()
                err('Card import failed', 'Card import failed for card with '
                    f'id {code}: {e}')
                return
            else:
                cards.append(card)
        dlg.hide()

        # Add card(s) to the deck
        if not MCDeck.deck._octgn:
            self.menu_octgn_enable()
        MCDeck.deck._undo.add_undo_level(hide=False)
        for card in cards:
            self.deck.addCardObject(card)
        self.deck.reset()

    @QtCore.Slot()
    def menu_mcdb_import_deck(self):
        err = lambda s1, s2: ErrorDialog(self, s1, s2).exec()

        # Get deck ID or URL
        dialog = MarvelCDBDeckImportDialog(self)
        if not dialog.exec():
            return

        # Load cards database (with progress bar) if not already loaded
        try:
            have_db = self._loadMarvelCDB()
        except Exception as e:
            err('MarvelCDB database load error',
                f'Could not load database: {e}')
            return
        else:
            if not have_db:
                return

        # Parse entered value as a (hopefully) deck ID
        s = dialog._le.text().strip()
        if not s:
            err('No input', 'No ID or URL was entered')
            return
        url_prefix = 'https://marvelcdb.com/decklist/view/'
        if s.startswith(url_prefix):
            s = s[len(url_prefix):]
            s = s.split('/')[0]

        # Load the deck
        try:
            deck = MarvelCDB.load_deck(s)
        except Exception as e:
            err('Deck import failed', 'Deck import failed for deck ID '
                f'{s}: {e}')
            return

        # Filter cards depending on whether hero and/or non-hero cards
        # should be imported
        import_hero_cards = dialog._include_hero_cards_chk.isChecked()
        import_other_cards = dialog._include_non_hero_cards_chk.isChecked()
        deck_cards = []
        for card, num in deck.cards:
            if card.belongs_to_hero_set():
                if import_hero_cards:
                    deck_cards.append((card, num))
            else:
                if import_other_cards:
                    deck_cards.append((card, num))
        if not deck_cards:
            err('Nothing to import', 'No cards to import (after applying '
                'settings on whether to import hero/non-hero cards)')
            return

        # Load all cards from the deck
        cards = []
        placeholder = dialog._create_placeholders_chk.isChecked()
        num_cards = sum(num for card, num in deck_cards)
        self.__operation_cancelled = False
        _qpd = QtWidgets.QProgressDialog
        dlg = _qpd('Importing card(s)', 'Cancel', 0, num_cards)
        dlg.show()
        for card, num in deck_cards:
            try:
                result = card.to_mcdeck_card(copies=num,
                                             placeholder=placeholder)
                dlg.setValue(dlg.value() + num)
                QtCore.QCoreApplication.processEvents()  # Force Qt update
                if self.__operation_cancelled:
                    err('Operation cancelled', 'Operation cancelled by user.')
                    return
            except Exception as e:
                dlg.hide()
                err('Card import failed', 'Card import failed for card with '
                    f'id {card.code}: {e}')
                return
            else:
                if num == 1:
                    cards.append(result)
                else:
                    for c in result:
                        cards.append(c)
        dlg.hide()

        # Add card(s) to the deck
        if not MCDeck.deck._octgn:
            self.menu_octgn_enable()
        MCDeck.deck._undo.add_undo_level(hide=False)
        for card in cards:
            self.deck.addCardObject(card)
        self.deck.reset()

    @QtCore.Slot()
    def menu_octgn_enable(self):
        if not MCDeck.deck._octgn:
            MCDeck.deck._octgn = octgn.OctgnCardSetData(name='')
            for i, card in enumerate(MCDeck.deck._card_list_copy):
                card._octgn = octgn.OctgnCardData(name='')
            self.enableOctgn(True)

    @QtCore.Slot()
    def menu_octgn_edit(self):
        MCDeck.deck._undo.add_undo_level(hide=False)
        title = 'Edit OCTGN metadata (entire deck)'
        if octgn.OctgnDataDialog(self, MCDeck.deck, title=title).exec():
            MCDeck.deck._deck_changed()
        else:
            MCDeck.deck._undo_action(deselect=False, purge=True)

    @QtCore.Slot()
    def menu_octgn_edit_selected(self):
        cards = MCDeck.deck.selected_cards()
        if cards:
            MCDeck.deck._undo.add_undo_level(hide=False)
            t = f'Edit OCTGN metadata ({len(cards)} selected cards)'
            if octgn.OctgnDataDialog(self, MCDeck.deck, cards, title=t).exec():
                MCDeck.deck._deck_changed()
            else:
                MCDeck.deck._undo_action(deselect=False, purge=True)

    @QtCore.Slot()
    def menu_octgn_delete(self):
        if MCDeck.deck._octgn:
                _dfun = QtWidgets.QMessageBox.question
                _keys = QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel
                _msg = ('This operation removes all current Octgn metadata '
                        'with no undo possible. Proceed with removal?')
                k = _dfun(self, 'Confirm Octgn data removal', _msg, _keys)
                if k == QtWidgets.QMessageBox.Ok:
                    MCDeck.deck._octgn = None
                    MCDeck.deck._undo.clear()
                    self.enableOctgn(False)

    @QtCore.Slot()
    def menu_octgn_import(self):
        MCDeck.deck._undo.add_undo_level(hide=False)
        try:
            dialog = octgn.OctgnCardImportDialog(self)
        except Exception as e:
            err = lambda s1, s2: ErrorDialog(self, s1, s2).exec()
            err('Octgn import error', f'Could not initiate card import: {e}')
        else:
            dialog.addedCards.connect(self._octgn_import_added_cards)
            dialog.exec()
            if dialog._imported_cards:
                MCDeck.deck._deck_changed()
                MCDeck.deck.reset()
            else:
                MCDeck.deck._undo_action(deselect=False, purge=True)

    @QtCore.Slot()
    def menu_octgn_import_o8d(self):
        err = lambda s1, s2: ErrorDialog(self, s1, s2).exec()

        if self.deck._octgn is None:
            _dfun = QtWidgets.QMessageBox.question
            _keys = QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel
            k = _dfun(self, 'Enable OCTGN metadata', 'Successful .o8d import '
                      'requires enabling OCTGN metadata. Proceed?', _keys)
            if k == QtWidgets.QMessageBox.Cancel:
                return

        _dlg = QtWidgets.QFileDialog.getOpenFileName
        _flt = 'OCTGN deck (*.o8d)'
        try:
            data_path = octgn.OctgnCardSetData.get_octgn_data_path(val=True)
        except Exception as e:
            err('Invalid data path', f'No OCTGN data path: {e}')
        _dir = os.path.join(data_path, 'GameDatabase', octgn.mc_game_id,
                            'FanMade')
        if not os.path.isdir(_dir):
            _dir = data_path
        path, cat = _dlg(self, 'Open MCD index or archive containing '
                         'an MCD index', filter=_flt, dir=_dir)
        if not path:
            return

        MCDeck.deck._undo.add_undo_level(hide=False)
        try:
            num = octgn.load_o8d_cards(path, data_path=data_path, parent=self)
        except Exception as e:
            err('.o8d import error', f'Could not import: {e}')
            MCDeck.deck._undo_action(deselect=False, purge=True)
            raise(e)
        else:
            MCDeck.deck._deck_changed()
            MCDeck.deck.reset()

    @QtCore.Slot()
    def _octgn_import_added_cards(self):
        MCDeck.deck.reset()

    @QtCore.Slot()
    def menu_octgn_install(self):
        err = lambda s1, s2: ErrorDialog(self, s1, s2).exec()
        try:
            _f = octgn.OctgnCardSetData.install_octgn_card_set
            success = _f(self, MCDeck.deck, MCDeck.settings)
        except Exception as e:
            err('OCTGN install error', f'Error: {e}')
        else:
            if success:
                _i = QtWidgets.QMessageBox.information
                _name = MCDeck.deck._octgn.name
                _id = MCDeck.deck._octgn.set_id
                _msg = (f'Card set "{_name}" with GUID {_id} was '
                        'successfully installed.')
                _i(self, 'Successful installation', _msg)
            else:
                err('Installation failed', 'Installation did not complete')

    @QtCore.Slot()
    def menu_octgn_uninstall(self):
        err = lambda s1, s2: ErrorDialog(self, s1, s2).exec()
        try:
            _f = octgn.OctgnCardSetData.uninstall_octgn_card_set
            success = _f(self, MCDeck.deck)
        except Exception as e:
            err('OCTGN uninstall error', f'Error: {e}')
        else:
            if success:
                _i = QtWidgets.QMessageBox.information
                _id = MCDeck.deck._octgn.set_id
                _msg = (f'Card set with GUID {_id} was '
                        'successfully uninstalled.')
                _i(self, 'Successful uninstall', _msg)
            else:
                err('Uninstall failed', 'Uninstall did not complete')

    @QtCore.Slot()
    def menu_octgn_card_set_installer(self):
        err = lambda s1, s2: ErrorDialog(self, s1, s2).exec()

        try:
            data_path = octgn.OctgnCardSetData.get_octgn_data_path(val=True)
        except Exception as e:
            err('Invalid OCTGN data path', f'No OCTGN data path: {e}')

        _q = QtWidgets.QMessageBox.question
        _k = QtWidgets.QMessageBox.Ok
        _k = _k | QtWidgets.QMessageBox.Cancel
        _msg = ('The card set installer will install a set of .zip files in '
                'the format generated by '
                'File -> Export -> Octgn -> Card Set.\n\n'
                'This is intended primarily as a way to conveniently '
                'reinstall sets of custom cards after an OCTGN card set '
                'update (which wipes custom card sets); just keep all those '
                '.zip files in some folder, and reinstall them in one single '
                'operation.\n\n'
                'It is also a convenient way to install a new .zip packaged '
                'card set.\n\n'
                'WARNING: installing a card set will wipe any previous card '
                'set installed under the same card set GUID.\n\n'
                'Proceed with card set installation?')
        btn = _q(self, 'Confirm use of card set installer', _msg, _k)
        if btn == QtWidgets.QMessageBox.Cancel:
            return

        _dlg = QtWidgets.QFileDialog.getOpenFileNames
        _flt = 'Card set (*.zip)'
        _dir = self.settings.octgn_card_sets_path
        if not _dir or not os.path.isdir(_dir):
            _dir = None
        paths, cat = _dlg(self, 'Select card set(s) to install',
                          filter=_flt, dir=_dir)
        if not paths:
            return

        installed, skipped = octgn.install_card_sets(data_path, paths)

        if installed:
            # Reload the OCTGN card database
            octgn.OctgnCardSetData.load_all_octgn_sets(data_path=data_path,
                                                       force=True)

        _i = QtWidgets.QMessageBox.information
        _msg = ''
        if installed:
            _msg += 'The following card sets were installed:\n'
            for _f in installed:
                _msg += f'* {_f}\n'
            _msg += '\n'
        if skipped:
            _msg += 'The following card sets could not be installed:\n'
            for _f, _m in skipped:
                _msg += f'* {_f} ({_m})\n'
            _msg += '\n'
        if installed:
            _msg += 'The OCTGN card database has been reloaded.'
        _i(self, 'Card set installation result', _msg)

    @QtCore.Slot()
    def menu_octgn_card_set_uninstaller(self):
        err = lambda s1, s2: ErrorDialog(self, s1, s2).exec()

        try:
            data_path = octgn.OctgnCardSetData.get_octgn_data_path(val=True)
        except Exception as e:
            err('Invalid OCTGN data path', f'No OCTGN data path: {e}')

        _q = QtWidgets.QMessageBox.question
        _k = QtWidgets.QMessageBox.Ok
        _k = _k | QtWidgets.QMessageBox.Cancel
        _msg = ('The card set uninstaller will inspect a set of .zip files in '
                'the format generated by '
                'File -> Export -> Octgn -> Card Set and uninstall the '
                'corresponding files from a local OCTGN database.\n\n'
                'Proceed with selecting card sets for uninstalling?')
        btn = _q(self, 'Confirm use of card set uninstaller', _msg, _k)
        if btn == QtWidgets.QMessageBox.Cancel:
            return

        _dlg = QtWidgets.QFileDialog.getOpenFileNames
        _flt = 'Card set (*.zip)'
        _dir = self.settings.octgn_card_sets_path
        if not _dir or not os.path.isdir(_dir):
            _dir = None
        paths, cat = _dlg(self, 'Select card set(s) to uninstall',
                          filter=_flt, dir=_dir)
        if not paths:
            return

        uninstalled, skipped = octgn.uninstall_card_sets(data_path, paths)

        if uninstalled:
            # Reload the OCTGN card database
            octgn.OctgnCardSetData.load_all_octgn_sets(data_path=data_path,
                                                       force=True)

        _i = QtWidgets.QMessageBox.information
        _msg = ''
        if uninstalled:
            _msg += 'The following card sets were removed:\n'
            for _f in uninstalled:
                _msg += f'* {_f}\n'
            _msg += '\n'
        if skipped:
            _msg += 'The following card sets could not be removed:\n'
            for _f, _m in skipped:
                _msg += f'* {_f} ({_m})\n'
            _msg += '\n'
        if uninstalled:
            _msg += 'The OCTGN card database has been reloaded.'
        _i(self, 'Card set installation result', _msg)

    @QtCore.Slot()
    def deckHasSelection(self, status):
        """Update to whether deck has a current selection of cards."""
        for w in (self.__cut_action, self.__copy_action, self.__set_player,
                  self.__set_encounter, self.__set_villain,
                  self.__set_unspecified, self.__set_front_image,
                  self.__set_back_image, self.__use_front_as_back,
                  self.__remove_back_image, self.__rotate_half_circle,
                  self.__rotate_clockwise, self.__rotate_anti_clockwise,
                  self.__delete_cards):
            w.setEnabled(status)
        _enable_octgn_edit_sel = bool(MCDeck.deck._octgn and status)
        self._octgn_edit_selected.setEnabled(_enable_octgn_edit_sel)

        selected_cards = MCDeck.deck.selected_cards()
        if len(selected_cards) == 1:
            self.__copy_front.setEnabled(True)
            card, = selected_cards
            self.__copy_back.setEnabled(card.back_img is not None)
        else:
            self.__copy_front.setEnabled(False)
            self.__copy_back.setEnabled(False)

    @QtCore.Slot()
    def deckHasClipboard(self, status):
        """Update to whether deck has cards in the clipboard."""
        for w in (self.__paste_action, self.__paste_before_action,
                  self.__paste_player_action, self.__paste_encounter_action,
                  self.__paste_villain_action):
            w.setEnabled(status)

    @QtCore.Slot()
    def exitAction(self):
        if MCDeck.deck._unsaved:
            if self.deck.has_cards() or self.deck._undo.has_undo_information():
                _dfun = QtWidgets.QMessageBox.question
                _keys = QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel
                k = _dfun(self, 'Confirm exit', 'Exit without saving?', _keys)
                if k == QtWidgets.QMessageBox.Cancel:
                    return
        self.close()

    @QtCore.Slot()
    def helpAbout(self):
        """Show a help->about dialog box."""

        about = QtWidgets.QMessageBox(self, 'About MCdeck', '')
        text = '''<p><b>MCdeck - © Cloudberries, 2022</b></p>

        <p><a href="https://pypi.org/project/mcdeck/">MCdeck</a> is a custom
        card deck builder app for
        <a href="https://www.fantasyflightgames.com/en/products/marvel-champions-the-card-game/">
        Marvel Champions: The Card Game</a>. Decks are constructed by adding
        card images, and can then be exported to supported export formats.</p>

        <p>Note that MCdeck is entirely fan made, and is in no way associated
        with or endorsed by owners of Marvel Champions intellectual property. It
        is intended entirely for using with custom user generated content.</p>

        <p>MCdeck is released under the
        <a href="https://www.gnu.org/licenses/gpl-3.0-standalone.html">
        GNU General Public License v3.0</a> or later. License details are
        included with the source code.</p>
        '''
        about.setInformativeText(text)
        about.setStandardButtons(QtWidgets.QMessageBox.Ok)
        about.setDefaultButton(QtWidgets.QMessageBox.Ok)
        about.exec()

    @QtCore.Slot()
    def helpUsage(self):
        """Show a help->usage dialog box."""

        about = QtWidgets.QMessageBox(self, 'Usage', '')
        text = '''<p>Most use of this tool's usage is hopefully more or less
        self explanatory, as most options are explained by tool tips, and the
        app is not really rocket science - you can combine cards into decks, you
        can open and save decks, and you can export to printable PDFs or
        card sets for Tabletop Simulator.</p>

        <p>Many app operations act on a card <em>selection</em>. A single card
        can be selected by left-clicking on it. If the ctrl (or meta) key is
        held while clicking, the card's selection status is toggled. If the
        shift key is held, then the selection is extended as a range to
        include the clicked card.</p>

        <p>Decks can be saved to a *.zip file, which will include a card index
        on the top level (in a file "mcdeck.mcd") as well as card images in
        various sub-directories. Such a card deck .zip file can be opened from
        MCdeck.</p>

        <p>MCdeck can also open a .mcd file directly from the local drive. That
        card index will then be used to reference card images on the local
        drive, rather than inside a .zip file. If you e.g. unzip a .zip file
        generated by MCdeck, you can open the unpacked mcdeck.mcd file and it
        will load the same (unpacked) content.</p>

        <p>The app supports pasting image files and images from the system
        clipboard, as well as dragging image files on the app. If a
        .zip or .mcd file is dragged onto the app, MCdeck will try to
        open that file as a deck.</p>
        '''
        about.setInformativeText(text)
        about.setStandardButtons(QtWidgets.QMessageBox.Ok)
        about.setDefaultButton(QtWidgets.QMessageBox.Ok)
        about.exec()

    @QtCore.Slot()
    def helpResources(self):
        """Show a help->resources dialog box."""

        about = QtWidgets.QMessageBox(self, 'Resources', '')
        text = '''<p>This tool aims to assist with using custom cards together
        with <a href="https://www.fantasyflightgames.com/en/products/marvel-champions-the-card-game/">
        Marvel Champions: The Card Game</a>; printing cards for use with the
        physical game as well as or exporting card sets for use with
        <a href="https://store.steampowered.com/app/286160/Tabletop_Simulator/">
        Tabletop Simulator</a>.</p>

        <p>The tool is intended to be a <em>supplement</em> to the game. You
        will need a physical copy of the game in order to combine with custom
        cards for physical play. Keep in mind, as a user of this product, you
        are responsible for how you use it, including any legal restrictions
        related to e.g. copyrights.</p>

        <p>There is also a <em>moral</em> obligation to ensure that
        fan made custom products act as a <em>supplement</em> to the related
        commercial product, in a way that benefits both the customers and the
        owner of the product. Make sure you use this tool responsibly in a way
        that also supports the business of MC: TGG copyright holders.</p>

        <p>A good starting resources for custom content is
        <a href="https://hallofheroeslcg.com/custom-content/">Hall of Heroes</a>
        . From that page you should be able to find a link to a <em>custom
        content discord</em>, which is a thriving community of all things
        custom MCG.</p>

        <p>Your best bet for getting some level of product support is to
        go to the channel #cloudberries in the previously mentioned discord.
        Please keep expectations regarding support on the low side; this app
        is a marginal side project in the very busy life of its author, and
        I really have very limited time to follow up on questions and issues -
        with small kids it is a miracle I found the time to write the app
        in the first place :-)  Nevertheless, you may try to reach me at
        #cloudberries, and even if I do not have the opportunity to be
        responsive, chances are you may be able to find others who know the
        tool.</p>

        <p>The tool itself is available from the
        <a href="https://pypi.org/project/mcdeck/">Python Package Index</a>,
        including links to source code on GitHub and an issue tracker. Also
        note that MCdeck has <a href="https://pypi.org/project/lcgtools/">
        lcgtools</a> as a dependency, and when that tool is installed, you
        also get access to a set of command line tools for generating card
        PDF documents.</p>

        <p>Best wishes for using this tool!  / Cloudberries</p>
        '''
        about.setInformativeText(text)
        about.setStandardButtons(QtWidgets.QMessageBox.Ok)
        about.setDefaultButton(QtWidgets.QMessageBox.Ok)
        about.exec()

    @QtCore.Slot()
    def deckChanged(self, changed):
        self.__save_action.setEnabled(changed)
        self.__save_as_action.setEnabled(True)

    @QtCore.Slot()
    def updateTitleFilename(self, name):
        """File name changed; update window title."""
        if not name:
            self.setWindowTitle('MCdeck - custom card deck builder')
        else:
            self.setWindowTitle(f'MCdeck: {name}')

    @QtCore.Slot()
    def enableOctgn(self, enable):
        for w in (self._octgn_edit, self._octgn_delete, self._octgn_install,
                  self._octgn_uninstall, self.__export_octgn_card_set_action,
                  self.__export_octgn_deck_action):
            w.setEnabled(enable)
        self._octgn_enable.setEnabled(not enable)
        _enable_octgn_edit_sel = bool(MCDeck.deck._octgn and enable)
        self._octgn_edit_selected.setEnabled(_enable_octgn_edit_sel)

    @QtCore.Slot()
    def cancelOperation(self):
        self.__operation_cancelled = True

    def _loadMarvelCDB(self):
        """Loads MarvelCDB card database if not already loaded."""
        if not MarvelCDB._cards:
            choice_dlg = LoadMarvelCDBDialog(self)
            if not choice_dlg.exec():
                return False

            _qpd = QtWidgets.QProgressDialog
            dlg = _qpd('Loading MarvelCDB cards index ...', 'Cancel', 0, 20)
            dlg.show()
            try:
                MarvelCDB.load_cards(all=choice_dlg._all, progress=dlg)
            finally:
                dlg.hide()
            # Disable PDF generation after downloading cards index
            self._export_pdf_action.setEnabled(False)
            return True
        else:
            return True


class Deck(QtWidgets.QScrollArea):
    """View for a deck of cards."""

    hasSelection = QtCore.Signal(bool)  # Has card(s) selected
    hasClipboard = QtCore.Signal(bool)  # Has cards in clipboard
    deckChanged = QtCore.Signal(bool)   # Deck is changed since initial/save
    filenameChange = QtCore.Signal(str) # Project filename changed
    deckHasOctgn = QtCore.Signal(bool)  # True if deck has octgn metadata

    def __init__(self):
        super().__init__()

        self.__cards = []
        self.__card_width = MCDeck.settings.card_view_width_px
        self.__card_scaled_width = None   # After zoom
        self.__card_scaled_height = None  # After zoom
        self.__zoom_lvl = 0
        self.__zoom_per_lvl = 0.075
        self._update_widget_card_size(reset=False)

        self._undo = DeckUndoBuffer(self)
        self._unsaved = True     # True if current deck state is "unsaved"
        self._save_file = None   # Name of file of current project
        self.filenameChange.emit('')
        self.__clipboard = []    # Cards which have been cut or copied

        self._octgn = None       # OCTGN card set data for the deck (if set)

        self.__view = QtWidgets.QWidget()
        self.setWidget(self.__view)

    def addCard(self, front, back=None, bbleed=0, ctype=0, pos=-1, show=True):
        """Add a card to the card list.

        :param  front: image of front side
        :type   front: :class:`QtGui.QImage`
        :param   back: image of back side (or None if no image)
        :type    back: :class:`QtGui.QImage`
        :param bbleed: amount of bleed on back image
        :param  ctype: card type
        :type   ctype: int
        :param    pos: position to insert (end if -1)
        :param   show: if True call show() on widget before returning
        :return:       generated card object
        :rtype:        :class:`Card`

        """
        card = Card(front, back, bbleed, ctype, self.__view)
        card.setCardWidth(self.__card_scaled_width)
        if pos < 0:
            self.__cards.append(card)
        else:
            self.__cards.insert(pos, card)
        if self._octgn and card._octgn is None:
            card._octgn = octgn.OctgnCardData(name='')
        card.cardSelected.connect(self.cardSingleSelected)
        card.cardCtrlSelected.connect(self.cardCtrlSelected)
        card.cardShiftSelected.connect(self.cardShiftSelected)
        if show:
            card.show()
        self._deck_changed()
        return card

    def addCardObject(self, card, pos=-1, show=True):
        """Add a card object to the card list.

        :param card: card object
        :type  card: :class:`Card`
        :param  pos: position to insert (end if -1)
        :param show: if True call show() on widget before returning

        """
        card.setParent(self.__view)
        card.setCardWidth(self.__card_scaled_width)
        if pos < 0:
            self.__cards.append(card)
        else:
            self.__cards.insert(pos, card)
        card.cardSelected.connect(self.cardSingleSelected)
        card.cardCtrlSelected.connect(self.cardCtrlSelected)
        card.cardShiftSelected.connect(self.cardShiftSelected)
        card.setVisible(show)
        self._deck_changed()

    def reset(self):
        """Resets deck view."""
        self._update_size(self.width(), self.height())
        for card in self.__cards:
            card.reset()
        self.repaint()

    def clear(self, undo=True):
        """Clears the deck.

        :param undo: if True enable undo, otherwise clear undo buffer

        """
        if undo:
            self._undo.add_undo_level()
        else:
            self._undo.clear()
        self.__cards = []
        self._deck_changed()
        self.reset()

    def has_cards(self):
        """True if deck has cards, otherwise False."""
        return bool(self.__cards)

    def has_selected(self):
        """True if deck has one or more selected cards."""
        for card in self.__cards:
            if card.selected:
                return True
        else:
            return False

    def num_selected(self):
        """The number of selected cards."""
        return sum(1 for card in self.__cards if card.selected)

    def selected_cards(self):
        """Returns a list of selected cards."""
        return [card for card in self.__cards if card.selected]

    def show_cards(self):
        """Calls show() on all cards currently in the deck."""
        for card in self.__cards:
            card.show()

    def hide_cards(self):
        """Calls hide() on all cards currently in the deck."""
        for card in self.__cards:
            card.hide()

    def resizeEvent(self, event):
        new_size = event.size()
        self._update_size(new_size.width(), new_size.height())

    def mousePressEvent(self, event):
        if event.buttons() == QtCore.Qt.LeftButton:
            key_mods = QtGui.QGuiApplication.keyboardModifiers()
            shift = key_mods & QtCore.Qt.ShiftModifier
            if not shift:
                # Clicking in deck area outside cards, deselect all cards
                for card in self.__cards:
                    card.select(False)
                self.hasSelection.emit(False)

    def wheelEvent(self, event):
        if event.modifiers() == QtCore.Qt.ControlModifier:
            # Capture Ctrl+Wheel and use for zoom
            y_angle = event.angleDelta().y()
            if y_angle > 0:
                self.zoom_in()
            else:
                self.zoom_out()
        else:
            super().wheelEvent(event)

    @QtCore.Slot()
    def newDeck(self):
        if self._unsaved:
            _dfun = QtWidgets.QMessageBox.question
            _keys = QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.Cancel
            k = _dfun(self, 'Confirm new deck', 'Current deck has unsaved '
                      'changes. Do you really wish to start a new deck?', _keys)
            if k == QtWidgets.QMessageBox.Cancel:
                return

        self.hide_cards()
        self.__cards = []
        self._unsaved = True
        self._save_file = None
        self.filenameChange.emit('')
        self.deckChanged.emit(True)
        self._undo.clear()
        self.reset()

    @QtCore.Slot()
    def openDeck(self):
        err = lambda s1, s2: ErrorDialog(self, s1, s2).exec()
        if self.__cards:
            _q = QtWidgets.QMessageBox.question
            btn = _q(self, 'Discard current deck?', 'Deck contains cards. '
                     'Open file and discard current deck?',
                     QtWidgets.QMessageBox.Open | QtWidgets.QMessageBox.Cancel)
            if btn == QtWidgets.QMessageBox.Cancel:
                return

        _dlg = QtWidgets.QFileDialog.getOpenFileName
        _flt = 'Zip archive (*.zip);;MCD index (*.mcd)'
        path, cat = _dlg(self, 'Open MCD index or archive containing '
                         'an MCD index', filter=_flt)
        if path:
            self._open(path)

    @QtCore.Slot()
    def saveDeck(self):
        err = lambda s1, s2: ErrorDialog(self, s1, s2).exec()
        if self._save_file is None:
            self.saveDeckAs()
        else:
            overwrite = False
            if os.path.exists(self._save_file):
                _dfun = QtWidgets.QMessageBox.question
                keys = QtWidgets.QMessageBox.Save | QtWidgets.QMessageBox.Cancel
                k = _dfun(self, 'Confirm save', f'The file {self._save_file} '
                          'already exists. Do you wish to overwrite?', keys)
                if k == QtWidgets.QMessageBox.Cancel:
                    return
                overwrite = True

            if not overwrite:
                self._save(self._save_file)
            else:
                tfile = tempfile.NamedTemporaryFile(suffix='.zip',
                                                    delete=False)
                tfile.close()
                try:
                    self._save(tfile.name)
                except Exception:
                    os.remove(tfile.name)
                    err('Save error', f'Could not save to {self._save_file}')
                else:
                    os.remove(self._save_file)
                    os.rename(tfile.name, self._save_file)

    @QtCore.Slot()
    def saveDeckAs(self):
        _get = QtWidgets.QFileDialog.getSaveFileName
        _filter='Zip files (*.zip)'
        d = os.path.dirname(self._save_file) if self._save_file else ''
        path, _f = _get(self, 'Select deck filename', dir=d, filter=_filter)
        if not path:
            return

        self._save(path)
        self._save_file = path
        self.filenameChange.emit(path)

    @QtCore.Slot()
    def exportPdf(self):
        if not self.__cards:
            msg_box = QtWidgets.QMessageBox(self)
            msg_box.setWindowTitle('No cards')
            msg_box.setText('There are no cards to export.')
            msg_box.setStandardButtons(QtWidgets.QMessageBox.Cancel)
            msg_box.setDefaultButton(QtWidgets.QMessageBox.Cancel)
            msg_box.exec()
            return

        # Set up a PDF generator
        _get = QtWidgets.QFileDialog.getSaveFileName
        fname, filter = _get(self, 'Select file name for generated PDF file',
                             filter='PDF files (*.pdf);;All files (*.*)')
        if fname:
            if os.path.exists(fname):
                os.remove(fname)
            _s = MCDeck.settings
            Gen = LcgCardPdfGenerator
            gen = Gen(outfile=fname, pagesize=_s.pagesize, dpi=_s.page_dpi,
                      c_width=_s.card_width_mm, c_height=_s.card_height_mm,
                      bleed=_s.card_bleed_mm, margin=_s.page_margin_mm,
                      spacing=_s.card_min_spacing_mm,
                      fold=_s.card_fold_distance_mm, folded=(not _s.twosided))
            gen.setTwosidedSubset(odd=True, even=True)
            gen.setTwosidedEvenPageOffset(0, 0)
            gen.setFeedDir(_s.feed_dir)

            # Draw cards onto generator and render PDF
            for card in self.__cards:
                front = gen.loadCard(card.front_img)
                if card.back_img:
                    back = gen.loadCard(card.back_img, bleed=card.back_bleed)
                else:
                    back = None
                gen.drawCard(front, back)
            gen.finish()

    @QtCore.Slot()
    def exportTts(self):
        """Export as images for importing into Tabletop Simulator."""
        TTSExportDialog(self, MCDeck.settings, self.__cards).exec()

    @QtCore.Slot()
    def exportOctgnCardSet(self):
        """Export deck as Octgn card set"""
        err = lambda s1, s2: ErrorDialog(self, s1, s2).exec()
        if not self._octgn:
            raise RuntimeError('Should never happen')

        if not self.__cards:
            _msg = 'The deck has no cards to export'
            err('Nothing to export', _msg)
            return

        if not octgn.OctgnCardSetData.validate_legal_deck(self):
            _msg = 'The deck does not have a validate set of OCTGN data'
            err('Cannot export Octgn data', _msg)
            return

        # Get a .zip filename for saving
        _get = QtWidgets.QFileDialog.getSaveFileName
        d = MCDeck.settings.octgn_card_sets_path
        if d is None or not os.path.isdir(d):
            d = os.path.dirname(self._save_file) if self._save_file else None
        path, _f = _get(self, 'Select .zip filename for export', dir=d,
                        filter='Zip files (*.zip)')
        if not path:
            return

        try:
            _exp = octgn.OctgnCardSetData.export_octgn_card_set
            with zipfile.ZipFile(path, 'w') as zf:
                _exp(self, zf, MCDeck.settings)
        except Exception as e:
            err('Octgn export error', f'Unable to export: {e}')
        else:
            info = QtWidgets.QMessageBox(self, 'Successful export', '')
            text = f'''<p>An OCTGN card set with GUID
            <tt>{self._octgn.set_id}</tt> and the name "{self._octgn.name}" was
            exported as a .zip file.</p>

            <p>The .zip file can be installed into OCTGN by using the OCTGN
            card set installation option in the Tools OCTGN menu.</p>

            <p>The card set can be installed manually into OCTGN by unpacking
            the .zip file into the OCTGN installation's <tt>Data/</tt>
            directory. This directory normally has the path
            <tt>~/AppData/Local/Programs/OCTGN/Data/</tt>.</p>

            <p>Installed custom cards can be used with
            <a href="https://twistedsistem.wixsite.com/octgnmarvelchampions/">MC: TCG
            in OCTGN</a>. Decks can be made with the OCTGN deck editor. In
            order to be able to use a generated .o8d deck, it needs to
            be copied into the <tt>Data/</tt> subdirectory
            <tt>GameDatabase/055c536f-adba-4bc2-acbf-9aefb9756046/FanMade/</tt>.
            </p>

            <p>Deck(s) created with the deck editor can be added to the .zip
            file by creating the .zip file directory
            <tt>GameDatabase/055c536f-adba-4bc2-acbf-9aefb9756046/FanMade/</tt>
            and adding the .o8d file(s) to that directory.</p>

            <p>To uninstall the card set, use the OCTGN card set uninstall tool
            available from the Tools menu, or remove the following
            <tt>Data/</tt> subdirectories:
            </p>
            <ul><li>
            <tt>GameDatabase/055c536f-adba-4bc2-acbf-9aefb9756046/Sets/{self._octgn.set_id}/</tt>
            </li><li>
            <tt>ImageDatabase/055c536f-adba-4bc2-acbf-9aefb9756046/Sets/{self._octgn.set_id}/</tt>.
            </li><ul>
            '''
            info.setInformativeText(text)
            info.setStandardButtons(QtWidgets.QMessageBox.Ok)
            info.setDefaultButton(QtWidgets.QMessageBox.Ok)
            info.exec()

    @QtCore.Slot()
    def exportOctgnDeck(self):
        """Export deck as an Octgn .o8d deck"""
        octgn.OctgnCardSetData.export_o8d_deck(self, self)

    @QtCore.Slot()
    def cardSingleSelected(self, widget):
        """Handler for card single-selection."""
        for card in self.__cards:
            card.select(card is widget)
        self.hasSelection.emit(True)

    @QtCore.Slot()
    def cardCtrlSelected(self, widget):
        """Handler for card ctrl-selection."""
        for card in self.__cards:
            if card is widget:
                card.select(not card.selected)
                break
        selected = (sum(1 for card in self.__cards if card.selected) > 0)
        self.hasSelection.emit(selected)

    @QtCore.Slot()
    def cardShiftSelected(self, widget):
        """Handler for card shift-selection."""
        w_idx = self.__cards.index(widget)
        sel = [(i, c) for i, c in enumerate(self.__cards) if c.selected]
        if not sel:
            widget.select(True)
        else:
            min_sel = min(i for i, c in sel)
            max_sel = max(i for i, c in sel)
            if min_sel <= w_idx < max_sel:
                max_sel = w_idx
            else:
                min_sel = min(min_sel, w_idx)
                max_sel = max(max_sel, w_idx)
            for i, card in enumerate(self.__cards):
                card.select(min_sel <= i <= max_sel)
        self.hasSelection.emit(True)

    @QtCore.Slot()
    def cutCards(self):
        """Cut selected cards."""
        cut_cards = []
        cards_left = []
        for card in self.__cards:
            if card.selected:
                cut_cards.append(card)
                card.hide()
            else:
                cards_left.append(card)
        if cut_cards:
            MCDeck.clipboard().clear()
            self.__clipboard = cut_cards
            self.hasSelection.emit(False)
            self.hasClipboard.emit(True)
            self._undo.add_undo_level()
            self.__cards = cards_left
            self.show_cards()
            self._deck_changed()
            self.reset()

    @QtCore.Slot()
    def copyCards(self):
        """Copy selected cards."""
        copy_cards = []
        for card in self.__cards:
            if card.selected:
                copy_cards.append(card.copy())
        if copy_cards:
            MCDeck.clipboard().clear()
            self.__clipboard = copy_cards
            self.hasClipboard.emit(True)

    @QtCore.Slot()
    def copyCardFront(self):
        card, = self.selected_cards()
        MCDeck.clipboard().setImage(card.front_img)

    @QtCore.Slot()
    def copyCardBack(self):
        card, = self.selected_cards()
        MCDeck.clipboard().setImage(card.back_img)

    @QtCore.Slot()
    def paste(self, droppedMimeData=None, after=True, ctype=None, back=None):
        """Paste data (also used for drag & drop)."""
        # Resolve start position 'pos' for pasting cards into current deck
        sel_idx = [i for i, c in enumerate(self.__cards) if c.selected]
        if after:
            if sel_idx:
                pos = max(sel_idx) + 1
            else:
                pos = len(self.__cards) + 1
        else:
            if sel_idx:
                pos = min(sel_idx)
            else:
                pos = 0

        if self.__clipboard and not droppedMimeData:
            # Pasting from local application copied/cut card list buffer
            for i, card in enumerate(self.__clipboard):
                self._undo.add_undo_level()
                self.addCardObject(card.copy(), pos=(pos + i))
                self.show_cards()
        else:
            # Pasting from MIME data
            if droppedMimeData:
                mime = droppedMimeData
            else:
                mime = MCDeck.clipboard().mimeData()

            front_images = []
            if mime.hasUrls():
                # Resolve URL(s)
                for url in mime.urls():
                    if url.isLocalFile():
                        # Add image from local file
                        path = url.toLocalFile()
                        if not os.path.exists(path):
                            front_images.append(None)
                        elif os.path.isfile(path):
                            # Try to add single file
                            img = QtGui.QImage()
                            if path and img.load(path):
                                front_images.append(img)
                            else:
                                front_images.append(None)
                        elif os.path.isdir(path):
                            # Add all image files inside directory
                            entries = os.listdir(path)
                            for e in entries:
                                # Ignore hidden files
                                if e.startswith('.'):
                                    continue
                                _p = os.path.join(path, e)
                                if os.path.isfile(_p):
                                    img = QtGui.QImage()
                                    if _p and img.load(_p):
                                        front_images.append(img)
                                    else:
                                        front_images.append(None)
                        else:
                            front_images.append(None)
                    else:
                        # Retreive image from remote URL
                        response = urllib.request.urlopen(url.url())
                        if isinstance(response, http.client.HTTPResponse):
                            ctype = response.getheader('Content-Type', '')
                            mime_types = ctype.split(';')
                            mime_types = [s.strip() for s in mime_types]
                            mime_match = image_mime_type(mime_types)
                            if mime_match:
                                img_data = response.read()
                                img = QtGui.QImage()
                                if img.loadFromData(img_data):
                                    front_images.append(img)
                                    continue
                            front_images.append(None)
                        else:
                            print('Unsupported UTL type:', url.url())
                            front_images.append(None)
            elif mime.hasImage():
                mime_types = set(mime.formats())
                _st = QtGui.QImageReader.supportedMimeTypes()
                supp_types = set([mt.toStdString() for mt in _st])
                overlap = mime_types & supp_types
                if overlap:
                    # Pick a random format
                    mime_type = overlap.pop()
                    img = QtGui.QImage()
                    data = mime.data(mime_type)
                    if img.loadFromData(data, mime_type):
                        front_images.append(img)
                    else:
                        front_images.append(None)
                else:
                    front_images.append(None)
            elif 'application/x-qt-image' in mime.formats():
                mime_types = set(mime.formats())
                img = QtGui.QImage()
                data = mime.data('application/x-qt-image')
                if img.loadFromData(data, 'application/x-qt-image'):
                    front_images.append(img)
                else:
                    front_images.append(None)
            else:
                raise RuntimeError('Should never happen')

            # Handle situation that one or more images did not load
            if sum(1 for img in front_images if img) == 0:
                # No valid images
                msg_box = QtWidgets.QMessageBox(self)
                msg_box.setWindowTitle('No images')
                msg_box.setText('No images could be added (wrong type(s) or '
                                'failed to load).')
                msg_box.setStandardButtons(QtWidgets.QMessageBox.Cancel)
                msg_box.setDefaultButton(QtWidgets.QMessageBox.Cancel)
                msg_box.exec()
                return
            elif sum(1 for img in front_images if img is None) > 0:
                # One or more invalid images
                QMB = QtWidgets.QMessageBox
                _q = QtWidgets.QMessageBox.question
                val = _q(self, 'Invalid image(s)', 'Some images are invalid '
                         '(not images or failed to load). Proceed by '
                         'adding the valid images, ignoring the invalid ones?',
                         buttons=QMB.Ok | QMB.Abort,
                         defaultButton=QMB.Abort)
                if val != QMB.Ok:
                    return
            front_images = [img for img in front_images if img]

            # Handle automatic aspect transformation of cards
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
                for i, img in enumerate(front_images):
                    if not isinstance(img, LcgImage):
                        img = LcgImage(img)
                    c_portrait = (img.heightMm() >= img.widthMM())
                    if portrait ^ c_portrait:
                        # Wrong aspect, rotate
                        if clockwise:
                            front_images[i] = img.rotateClockwise()
                        else:
                            front_images[i] = img.rotateAntiClockwise()

            _added_undo = False
            if ctype is None:
                # Show dialog to ask for what type of card back to use
                dlg = CardTypeDialog(self)
                if dlg.exec():
                    self._undo.add_undo_level()
                    _added_undo = True
                    res_type, res_data = dlg.result
                    if res_type == 3:
                        # Card fronts are the same as card backs
                        ctype = Card.type_unspecified
                        for i, img in enumerate(front_images):
                            self.addCard(img, img, 0, ctype, pos + i)
                    else:
                        if res_type == 1:
                            back = None
                            ctype = res_data
                        elif res_type == 2:
                            back = res_data
                            ctype = Card.type_unspecified
                        elif res_type == 4:
                            back = None
                            ctype = Card.type_unspecified
                        else:
                            raise RuntimeError('Should never happen')
                        for i, img in enumerate(front_images):
                            self.addCard(img, back, 0, ctype, pos + i)
            else:
                # Use card type and card back image from method arguments
                self._undo.add_undo_level()
                _added_undo = True
                for i, img in enumerate(front_images):
                    self.addCard(img, back, 0, ctype, pos + i)
            if _added_undo:
                self.show_cards()

        self.reset()

    @QtCore.Slot()
    def pasteBefore(self):
        """Paste before (currently selected) card(s)."""
        self.paste(after=False)

    @QtCore.Slot()
    def pastePlayer(self):
        """Paste as player type card."""
        self.paste(ctype=Card.type_player)

    @QtCore.Slot()
    def pasteEncounter(self):
        """Paste as encounter type card."""
        self.paste(ctype=Card.type_encounter)

    @QtCore.Slot()
    def pasteVillain(self):
        """Paste as villain type card."""
        self.paste(ctype=Card.type_villain)

    @QtCore.Slot()
    def settingsChanged(self):
        card_width = MCDeck.settings.card_view_width_px
        self._update_widget_card_size(card_width, reset=False)
        self.reset()

    @QtCore.Slot()
    def systemClipboardChanged(self):
        mime = MCDeck.clipboard().mimeData()
        if mime and mime.formats():
            # Clipboard has (changed) data, invalidate any local clipboard
            self.__clipboard = []

            if mime.hasUrls():
                self.hasClipboard.emit(True)
            elif mime.hasImage():
                mime_type = image_mime_type(mime)
                if mime_type:
                    self.hasClipboard.emit(True)
                elif 'application/x-qt-image' in mime.formats():
                    # For now, unable to handle this MIME type, see
                    # https://bugreports.qt.io/browse/QTBUG-93632
                    if not self.__clipboard:
                        self.hasClipboard.emit(False)
                else:
                    # Unsupported image format
                    if not self.__clipboard:
                        self.hasClipboard.emit(False)
            else:
                # Unsupported MIME format
                if not self.__clipboard:
                    self.hasClipboard.emit(False)
        else:
            if not self.__clipboard:
                self.hasClipboard.emit(False)

    @QtCore.Slot()
    def selectAll(self):
        """Select all cards in the deck."""
        for card in self.__cards:
            card.select(True)
        self.hasSelection.emit(True)

    @QtCore.Slot()
    def selectNone(self):
        """Select all cards in the deck."""
        for card in self.__cards:
            card.select(False)
        self.hasSelection.emit(False)

    @QtCore.Slot()
    def setPlayerType(self):
        """Set card type to player for selected cards."""
        if self.has_selected:
            self._undo.add_undo_level()
            for i, card in enumerate(self.__cards):
                if card.selected:
                    card = self._copy_card(card)
                    card.ctype = Card.type_player
                    card.select(True)
                    self.__cards[i] = card
            self._deck_changed()
            self.show_cards()

    @QtCore.Slot()
    def setEncounterType(self):
        """Set card type to encounter for selected cards."""
        if self.has_selected:
            self._undo.add_undo_level()
            for i, card in enumerate(self.__cards):
                if card.selected:
                    card = self._copy_card(card)
                    card.ctype = Card.type_encounter
                    card.select(True)
                    self.__cards[i] = card
            self._deck_changed()
            self.show_cards()

    @QtCore.Slot()
    def setVillainType(self):
        """Set card type to villain for selected cards."""
        if self.has_selected:
            self._undo.add_undo_level()
            for i, card in enumerate(self.__cards):
                if card.selected:
                    card = self._copy_card(card)
                    card.ctype = Card.type_villain
                    card.select(True)
                    self.__cards[i] = card
            self._deck_changed()
            self.show_cards()

    @QtCore.Slot()
    def setUnspecifiedType(self):
        """Set card type to unspecified for selected cards."""
        if self.has_selected:
            self._undo.add_undo_level()
            for i, card in enumerate(self.__cards):
                if card.selected:
                    card = self._copy_card(card)
                    card.ctype = Card.type_unspecified
                    card.select(True)
                    self.__cards[i] = card
            self._deck_changed()
            self.show_cards()

    @QtCore.Slot()
    def useFrontAsBack(self):
        """Use card front image as the back side image also."""
        if self.has_selected:
            self._undo.add_undo_level()
            for i, card in enumerate(self.__cards):
                if card.selected:
                    card = self._copy_card(card)
                    card.set_back_image(card.front_img)
                    card.select(True)
                    self.__cards[i] = card
            self._deck_changed()
            self.show_cards()

    @QtCore.Slot()
    def setFrontImage(self):
        """Open an image file as the card front for the card(s)."""
        if self.has_selected():
            _fun = loadImageFromFileDialog
            img = _fun(self, 'Open card back image file')
            if img:
                # Handle aspect transformation
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

                self._undo.add_undo_level()
                for i, card in enumerate(self.__cards):
                    if card.selected:
                        card = self._copy_card(card)
                        card.set_front_image(img)
                        card.select(True)
                        self.__cards[i] = card
                self._deck_changed()
                self.show_cards()

    @QtCore.Slot()
    def setBackImage(self):
        """Open an image file as the card back for the card(s)."""
        if self.has_selected():
            _fun = loadImageFromFileDialog
            img = _fun(self, 'Open card back image file')
            if img:
                # Handle aspect transformation
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
                self._undo.add_undo_level()
                for i, card in enumerate(self.__cards):
                    if card.selected:
                        card = self._copy_card(card)
                        card.set_back_image(img)
                        card.select(True)
                        self.__cards[i] = card
                self._deck_changed()
                self.show_cards()

    @QtCore.Slot()
    def removeBackImage(self):
        """Remove the back image set on the cards."""
        if self.has_selected:
            # Check if any selected card has alt side OCTGN data
            _has_octgn_alt = False
            for card in self.__cards:
                if card.selected and card._octgn and card._octgn.alt_data:
                    _has_octgn_alt = True
                    break
            if _has_octgn_alt:
                _dfun = QtWidgets.QMessageBox.question
                _msg = ('One or more selected card(s) has OCTGN alt side '
                        'metadata. Removing the back image will also remove '
                        'that metadata. Proceed with removing back image(s)?')
                _k = QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.Cancel
                confirm = _dfun(self, 'Confirm removal', _msg, _k)
                if confirm == QtWidgets.QMessageBox.Cancel:
                    return

            # Remove back images (and any Octgn alt data)
            self._undo.add_undo_level()
            for i, card in enumerate(self.__cards):
                if card.selected:
                    card = self._copy_card(card)
                    card.set_back_image(None)
                    if card._octgn:
                        card._octgn._alt_data = None
                    card.select(True)
                    self.__cards[i] = card
            self._deck_changed()
            self.show_cards()

    @QtCore.Slot()
    def rotateHalfCircle(self):
        """Rotate front card(s) 180 degrees."""
        if self.has_selected:
            self._undo.add_undo_level()
            for i, card in enumerate(self.__cards):
                if card.selected:
                    card = self._copy_card(card)
                    img = LcgImage(card.front_img).rotateHalfCircle()
                    card.set_front_image(img)
                    card.select(True)
                    self.__cards[i] = card
            self._deck_changed()
            self.show_cards()

    @QtCore.Slot()
    def rotateClockwise(self):
        """Rotate front card(s) 90 degrees clockwise."""
        if self.has_selected:
            self._undo.add_undo_level()
            for i, card in enumerate(self.__cards):
                if card.selected:
                    card = self._copy_card(card)
                    img = LcgImage(card.front_img).rotateClockwise()
                    card.set_front_image(img)
                    card.select(True)
                    self.__cards[i] = card
            self._deck_changed()
            self.show_cards()

    @QtCore.Slot()
    def rotateAntiClockwise(self):
        """Rotate front card(s) 90 degrees anticlockwise."""
        if self.has_selected:
            self._undo.add_undo_level()
            for i, card in enumerate(self.__cards):
                if card.selected:
                    card = self._copy_card(card)
                    img = LcgImage(card.front_img).rotateAntiClockwise()
                    card.set_front_image(img)
                    card.select(True)
                    self.__cards[i] = card
            self._deck_changed()
            self.show_cards()

    @QtCore.Slot()
    def deleteCards(self):
        """Delete selected cards."""
        if self.has_selected:
            self._undo.add_undo_level()
            cards_left = []
            for i, card in enumerate(self.__cards):
                if not card.selected:
                    cards_left.append(card)
            self.__cards = cards_left
            self.show_cards()
            self._deck_changed()
            self.reset()

    @QtCore.Slot()
    def back_image_on_top(self, status):
        """Set status whether to show back image on top."""
        reset = ((not MCDeck._front_on_top) ^ status)
        MCDeck._front_on_top = not status
        if reset:
            self.reset()

    @QtCore.Slot()
    def zoom_reset(self):
        """Reset to 100% zoom."""
        self.__zoom_lvl = 0
        self._update_widget_card_size()

    @QtCore.Slot()
    def zoom_in(self):
        """Zoom in one zoom level."""
        self.__zoom_lvl += 1
        self._update_widget_card_size()

    @QtCore.Slot()
    def zoom_out(self):
        """Zoom out one zoom level."""
        self.__zoom_lvl -= 1
        self._update_widget_card_size()

    @QtCore.Slot()
    def cancelOperation(self):
        self.__operation_cancelled = True

    @QtCore.Slot()
    def undoAction(self):
        self._undo_action()

    @QtCore.Slot()
    def redoAction(self):
        self.hide_cards()
        self.__cards = self._undo.redo()
        for card in self.__cards:
            card.select(False)
        self._deck_changed()
        self.reset()

    @property
    def _card_list_copy(self):
        """A copy of the current list of cards."""
        return self.__cards.copy()

    def _undo_action(self, deselect=True, purge=False):
        self.hide_cards()
        self.__cards = self._undo.undo(purge=purge)
        if deselect:
            for card in self.__cards:
                card.select(False)
        self._deck_changed()
        self.reset()

    def _update_widget_card_size(self, width=None, reset=True):
        """Updates card widget size to the specified width (in pixels).

        :param width: new card widget width (in pixels), current if None
        :param reset: if True call :meth:`reset` if width was changed

        Actual width is scaled in accordance with current zoom level.

        """
        if width is None:
            width = self.__card_width
        self.__card_width = width

        if self.__zoom_lvl == 0:
            scaled = width
        elif self.__zoom_lvl > 0:
            scaled = int(width*(1 + self.__zoom_per_lvl)**self.__zoom_lvl)
        elif self.__zoom_lvl < 0:
            scaled = int(width*(1 - self.__zoom_per_lvl)**(-self.__zoom_lvl))
        scaled = max(scaled, 8)  # Ensure we never go below 8 pixels width

        # Update card width and height in deck view
        self.__card_scaled_width = scaled
        _s_c_height = MCDeck.settings.card_height_mm
        _s_c_width = MCDeck.settings.card_width_mm
        self.__card_scaled_height = int(scaled*(_s_c_height/_s_c_width))

        # Update card width (and height) of card widgets
        for card in self.__cards:
            card.setCardWidth(scaled)

        if reset:
            self.reset()

    def _save(self, filename):
        err = lambda s1, s2: ErrorDialog(self, s1, s2).exec()
        self.__operation_cancelled = False
        dlg = QtWidgets.QProgressDialog('Saving card(s)', 'Cancel',
                                        0, len(self.__cards))
        dlg.canceled.connect(self.cancelOperation)
        def dlg_add():
            dlg.setValue(dlg.value() + 1)
            QtCore.QCoreApplication.processEvents()  # Force Qt update
            if self.__operation_cancelled:
                err('Operation cancelled', 'Operation cancelled by user.')
                raise LcgException('Operation was cancelled')

        # Generate OCTGN save data (if any)
        if self._octgn:
            set_info = self._octgn
            card_data_l = []
            for card in self.__cards:
                c_data = card._octgn
                if c_data.alt_data and not card.specified_back_img:
                    _msg = 'Card(s) with no back img have alt card OCTGN data'
                    err('Metadata problem', _msg)
                    return
                card_data_l.append(c_data)
            octgn_file_s = set_info.to_str(card_data_l)
        else:
            octgn_file_s = None

        try:
            with zipfile.ZipFile(filename, 'w') as zf:
                mcd = ('# MCdeck definition of a custom cards MC:TCG deck.\n'
                       '# See https://pypi.org/project/mcdeck/ for info.\n')

                mode = None
                n_p, n_e, n_v, n_s = 0, 0, 0, 0
                for card in self.__cards:
                    _mode = None
                    _next = None
                    if card.ctype == Card.type_player:
                        _mode = 'player'
                        n_p += 1
                        _next = n_p
                    elif card.ctype == Card.type_encounter:
                        _mode = 'encounter'
                        n_e += 1
                        _next = n_e
                    elif card.ctype == Card.type_villain:
                        _mode = 'villain'
                        n_v += 1
                        _next = n_v

                    if _mode:
                        # Store player, encounter or villain card
                        if _mode != mode:
                            mcd += f'\n{_mode}:\n'
                            mode = _mode
                        img = LcgImage(card.front_img)
                        data = img.saveToBytes(format='PNG')
                        path = os.path.join(mode, f'img_{_next:05}.png')
                        zf.writestr(path, data)
                        mcd += f'  {to_posix_path(path)}\n'
                        dlg_add()
                    else:
                        # Single card
                        mode = None
                        n_s += 1
                        if card.back_img and card.back_bleed > 0:
                            mcd += f'\nsingle [back_bleed={card.back_bleed}]:\n'
                        else:
                            mcd += '\nsingle:\n'
                        img = LcgImage(card.front_img)
                        data = img.saveToBytes(format='PNG')
                        if card.back_img:
                            path = os.path.join('single', f'img_{n_s:05}_A.png')
                        else:
                            path = os.path.join('single', f'img_{n_s:05}.png')
                        zf.writestr(path, data)
                        mcd += f'  {to_posix_path(path)}\n'
                        if card.back_img:
                            img = LcgImage(card.back_img)
                            data = img.saveToBytes(format='PNG')
                            path = os.path.join('single', f'img_{n_s:05}_B.png')
                            zf.writestr(path, data)
                            mcd += f'  {to_posix_path(path)}\n'
                        dlg_add()

                # Write the card definition file to the top level of the zipfile
                zf.writestr('mcdeck.mcd', mcd)

                # If the deck has OCTGN metadata, save it
                if octgn_file_s:
                    zf.writestr('octgn.txt', octgn_file_s)

        except Exception as e:
            try:
                os.remove(filename)
            except FileNotFoundError:
                pass
            err('Save error', f'Unable to save file: {e}')
        else:
            self._unsaved = False
            self.deckChanged.emit(False)

    def _open(self, filename):
        """Opens file (must be a .zip or .mcd file).

        Returns True if successful, otherwise False.

        """
        err = lambda s1, s2: ErrorDialog(self, s1, s2).exec()
        if not os.path.exists(filename):
            _msg = f'{filename} does not exist'
            err('No such file', _msg)
            return False
        elif filename.lower().endswith('.zip'):
            zf = zipfile.ZipFile(filename, 'r')
            for s in zf.namelist():
                if s.lower() == 'mcdeck.mcd':
                    mcd = zf.read(s).decode('utf-8')
                    break
            else:
                _msg = ('Zip file does not include required card index file '
                        'mcdeck.mcd in the top dir')
                err('Missing mcdeck.mcd', _msg)
                return False
        elif filename.lower().endswith('.mcd'):
            zf = None
            mcd = open(filename, 'r').read()
            mcd_dir = os.path.dirname(os.path.realpath(filename))
        else:
            _msg = 'File must be .zip or .mcd'
            err('Invalid file', _msg)
            return False

        # If OCTGN metadata file present, decode for later
        octgn_data = None
        try:
            if zf:
                for s in zf.namelist():
                    if s.lower() == 'octgn.txt':
                        _s = zf.read(s).decode('utf-8')
                        octgn_data = octgn.OctgnCardSetData.from_str(_s)
                        break
            else:
                _dir = os.path.dirname(filename)
                octgn_file = os.path.join(_dir, 'octgn.txt')
                if os.path.isfile(octgn_file):
                    with open(octgn_file, 'r') as f:
                        _s = f.read()
                    octgn_data = octgn.OctgnCardSetData.from_str(_s)
        except Exception as e:
            _msg = ('Metadata file "octgn.txt" present but could '
                    f'not parse its contents: {e}')
            err('Metadata error (OCTGN)', _msg)
            return False

        # Clear current deck
        self.clear()
        QtCore.QCoreApplication.processEvents()  # Force Qt display update

        # (Try to) load deck
        _url_download_approved = False
        self.__operation_cancelled = False
        dlg = QtWidgets.QProgressDialog('Parsing mcdeck.mcd', 'Cancel', 0, 100)
        dlg.canceled.connect(self.cancelOperation)
        try:
            mode = None
            mode_sub = None
            mcd_lines = list(enumerate(mcd.splitlines()))
            dlg.setMaximum(len(mcd_lines))
            dlg.show()
            while mcd_lines:
                num, line = mcd_lines.pop(0)
                dlg.setValue(num)
                QtCore.QCoreApplication.processEvents()  # Force Qt update
                if self.__operation_cancelled:
                    err('Operation cancelled', 'Operation cancelled by user.')
                    raise LcgException('Operation was cancelled')
                if line.startswith('#'):
                    continue
                if not line.strip():
                    mode = None
                    continue
                _mode_set_here = False

                if line and line[:1].strip():
                    # First character is not whitespace -> section title line
                    try:
                        l, s, p = parse_mcd_file_section_header(line)
                    except ValueError as e:
                        err('MCD file error',
                            f'Format error line {num + 1}: {e}')
                        raise LcgException('Invalid MCD index file')
                    if l.lower() in ('player', 'encounter', 'villain'):
                        # Player, encounter or villain section
                        if mode:
                            err('MCD file error',
                                f'Missing linespace before line {num + 1}')
                            raise LcgException('Invalid MCD index file')
                        # Re-parse with approved arguments list
                        _p = parse_mcd_file_section_header
                        try:
                            m_str, _s, pairs = _p(line, [], ['source'])
                        except ValueError as e:
                            err('MCD file error',
                                f'Format error line {num + 1}: {e}')
                            raise LcgException('Invalid MCD index file')
                        if 'source' in pairs:
                            _val = pairs['source']
                            if _val in ('url', 'gdrive'):
                                if not _url_download_approved:
                                    _dfun = QtWidgets.QMessageBox.question
                                    _msg = ('Card index contains URL(s). '
                                            'Download the remote image(s)?')
                                    _k = QtWidgets.QMessageBox.Yes
                                    _k = _k | QtWidgets.QMessageBox.Cancel
                                    confirm = _dfun(self, 'Confirm download',
                                                    _msg, _k)
                                    if confirm == QtWidgets.QMessageBox.Cancel:
                                        MCDeck.deck.clear()
                                        return
                                    else:
                                        _url_download_approved = True
                                mode_sub = _val
                            else:
                                err('MCD file error',
                                    f'Invalid source argument line {num + 1}')
                                raise LcgException('Invalid MCD index file')
                        else:
                            mode_sub = None
                        mode = m_str
                        _mode_set_here = True

                if _mode_set_here:
                    continue
                if mode:
                    # Path to card (dir) inside an active mode
                    line = line.strip()
                    if mode_sub is None:
                        if zf:
                            # Read card(s) from zip file
                            path = to_posix_path(line).strip(posixpath.sep)
                            for p in zf.namelist():
                                _path = to_posix_path(p).strip(posixpath.sep)
                                if path == _path:
                                    break
                            else:
                                err('MCD file error',
                                    f'No such path in zip file, line {num + 1}')
                                raise LcgException('Invalid MCD index file')
                            paths = []
                            if zf.getinfo(p).is_dir():
                                for s in zf.namelist():
                                    if s.startswith(p) and not zf.getinfo(s).is_dir():
                                        paths.append(s)
                                if not paths:
                                    err('MCD file error',
                                        f'Directory contains no files, line {num + 1}')
                            else:
                                paths.append(p)
                            for p in paths:
                                img_data = zf.read(p)
                                img = QtGui.QImage()
                                if not img.loadFromData(img_data):
                                    err('Image load error',
                                        f'Could not open image {p} in zip file')
                                    raise LcgException('Image load error')
                                ctype_d = {'player':Card.type_player,
                                           'encounter':Card.type_encounter,
                                           'villain':Card.type_villain}
                                self.addCard(img, ctype=ctype_d[mode])
                        else:
                            # Read card(s) from local file system
                            path = os.path.join(mcd_dir, to_local_path(line))
                            if not os.path.exists(path):
                                err('No such file', f'{path} does not exist')
                            paths = []
                            if os.path.isdir(path):
                                # Traverse subdir, all files
                                for root, dir, files in os.walk(path):
                                    for f in files:
                                        # Add file unless it is hidden
                                        if not f.startswith('.'):
                                            paths.append(os.path.join(root, f))
                                if not paths:
                                    err('MCD file error',
                                        'Directory contains no files, '
                                        f'line {num + 1}')
                            else:
                                paths.append(path)
                            for p in paths:
                                img_data = open(p, 'rb').read()
                                img = QtGui.QImage()
                                if not img.loadFromData(img_data):
                                    err('Image load error',
                                        f'Could not open image {p}')
                                    raise LcgException('Image load error')
                                ctype_d = {'player':Card.type_player,
                                           'encounter':Card.type_encounter,
                                           'villain':Card.type_villain}
                                self.addCard(img, ctype=ctype_d[mode])
                    else:
                        # Load from specified source
                        if mode_sub == 'url':
                            img_url = line
                        elif mode_sub == 'gdrive':
                            img_url = ('https://drive.google.com/uc?'
                                       f'export=download&id={line}')
                        else:
                            raise RuntimeError('Should never happen')
                        try:
                            img = download_image(img_url)
                        except Exception:
                            err('Image load error',
                                f'Could not open image {img_url}')
                            raise LcgException('Image load error')
                        ctype_d = {'player':Card.type_player,
                                   'encounter':Card.type_encounter,
                                   'villain':Card.type_villain}
                        self.addCard(img, ctype=ctype_d[mode])

                elif line and line[:1].strip():
                    # First character is not whitespace -> section
                    try:
                        l, s, p = parse_mcd_file_section_header(line)
                    except ValueError as e:
                        err('MCD file error',
                            f'Format error line {num + 1}: {e}')
                        raise LcgException('Invalid MCD index file')
                    if l != 'single':
                        # player, encounter and villain sections parsed
                        # earlier; if not single here, no possible alternatives
                        err('MCD file error',
                            f'Expected "single" section line {num + 1}')
                        raise LcgException('Invalid MCD index file')
                    _p = parse_mcd_file_section_header
                    try:
                        l, _s, pairs = _p(line, [], ['back_bleed', 'source'])
                    except ValueError as e:
                        err('MCD file error',
                            f'Format error line {num + 1}: {e}')
                        raise LcgException('Invalid MCD index file')
                    if 'back_bleed' in pairs:
                        back_bleed = float(p['back_bleed'])
                        if back_bleed < 0:
                            err('MCD file error',
                                f'Invalid back_bleed arg line {num + 1}')
                            raise LcgException('Invalid MCD index file')
                    else:
                        back_bleed = 0
                    if 'source' in pairs:
                        _val = pairs['source']
                        if _val in ('url', 'gdrive'):
                            mode_sub = _val
                            if not _url_download_approved:
                                _dfun = QtWidgets.QMessageBox.question
                                _msg = ('Card index contains URL(s). '
                                        'Download the remote image(s)?')
                                _k = QtWidgets.QMessageBox.Yes
                                _k = _k | QtWidgets.QMessageBox.Cancel
                                confirm = _dfun(self, 'Confirm download',
                                                _msg, _k)
                                if confirm == QtWidgets.QMessageBox.Cancel:
                                    MCDeck.deck.clear()
                                    return
                                else:
                                    _url_download_approved = True
                        else:
                            err('MCD file error',
                                f'Invalid source argument line {num + 1}')
                            raise LcgException('Invalid MCD index file')
                    else:
                        mode_sub = None

                    # Read single card data
                    single_args = []
                    while mcd_lines:
                        num, line = mcd_lines.pop(0)
                        if not line.strip():
                            break
                        if not line[0].isspace():
                            err('MCD file error',
                                f'Expected indent on line {num + 1}')
                            raise LcgException('Invalid MCD index file')
                        single_args.append(line.strip())
                    if not 1 <= len(single_args) <= 2:
                        err('MCD file error',
                            'Single card should have 1 or 2 args, line '
                            f'{num + 1}')
                        raise LcgException('Invalid MCD index file')
                    single_images = []
                    for arg in single_args:
                        if mode_sub is None:
                            if zf:
                                # Read card(s) from zip file
                                path = to_posix_path(arg).strip(posixpath.sep)
                                for p in zf.namelist():
                                    _path = to_posix_path(p).strip(posixpath.sep)
                                    if path == _path:
                                        break
                                else:
                                    err('MCD file error',
                                        'No such file in zip file, line '
                                        f'{num + 1}')
                                    raise LcgException('Invalid MCD index file')
                                if zf.getinfo(p).is_dir():
                                    err('MCD file error',
                                        f'Entry is a directory, line {num + 1}')
                                img_data = zf.read(p)
                                img = QtGui.QImage()
                                if not img.loadFromData(img_data):
                                    err('Image load error',
                                        f'Could not open image {p} in zip file')
                                    raise LcgException('Image load error')
                                single_images.append(img)
                            else:
                                # Read card(s) from file system
                                path = os.path.join(mcd_dir, to_local_path(arg))
                                if not os.path.exists(path):
                                    err('MCD file error',
                                        f'No such file {path}, line {num + 1}')
                                    raise LcgException('Invalid MCD index file')
                                if os.path.isdir(path):
                                    err('MCD file error',
                                        f'Entry is a directory, line {num + 1}')
                                img_data = open(path, 'rb').read()
                                img = QtGui.QImage()
                                if not img.loadFromData(img_data):
                                    err('Image load error',
                                        f'Could not open image {path}')
                                    raise LcgException('Image load error')
                                single_images.append(img)
                        else:
                            if mode_sub == 'url':
                                img_url = arg
                            elif mode_sub == 'gdrive':
                                img_url = ('https://drive.google.com/uc?'
                                           f'export=download&id={arg}')
                            else:
                                raise RuntimeError('Should never happen')
                            try:
                                img = download_image(img_url)
                            except Exception:
                                err('Image load error',
                                    f'Could not open image from {img_url}')
                                raise LcgException('Image load error')
                            single_images.append(img)

                    # Add single card
                    if len(single_images) == 1:
                        front_img, = single_images
                        back_img = None
                    else:
                        front_img, back_img = single_images
                    self.addCard(front_img, back_img, back_bleed)
                else:
                    err('MCD file error', f'Syntax error line {num}')
                    raise LcgException('Invalid MCD index file')

            # If OCTGN metadata is present, add metadata to cards
            if octgn_data:
                card_set_data, card_data_list = octgn_data
                if len(self.__cards) != len(card_data_list):
                    raise LcgException('Number of cards does not match number '
                                       'of cards with OCTGN metadata')
                self._octgn = card_set_data
                for card, data in zip(self.__cards, card_data_list):
                    if data.alt_data and not card.specified_back_img:
                        _msg = ('There is/are card(s) with alternate card '
                                'OCTGN metadata without a card back side')
                        raise LcgException(_msg)
                    card._octgn = data
                self.deckHasOctgn.emit(True)
            else:
                self.deckHasOctgn.emit(False)

            self.reset()
        except LcgException:
            # Could not load deck, clear the partially loaded deck
            for card in self.__cards:
                card.hide()
            self.__cards = []
            self._octgn = None
            self.reset()
            return False
        else:
            self._unsaved = False
            if filename.lower().endswith('.zip'):
                self._save_file = filename
                self.filenameChange.emit(filename)
            else:
                self._save_file = None
                self.filenameChange.emit('')
            self.deckChanged.emit(False)
            return True

    def _deck_changed(self):
        """Process that a change was made to the deck"""
        self._unsaved = True
        self.deckChanged.emit(True)

    def _update_size(self, width, height):
        # Calculate how many cards fit horizontally in view, and view width
        cols = max(int(width/self.__card_scaled_width), 1)
        x_span = max(self.__card_scaled_width, width)

        # Calculate number of rows and view height
        rows = len(self.__cards) // cols
        if len(self.__cards) % cols > 0:
            rows += 1
        rows = max(rows, 1)
        y_span = max(rows*self.__card_scaled_height, height)

        # Resize internal card view
        self.__view.resize(x_span, y_span)

        # Place cards
        for i, card in enumerate(self.__cards):
            row, col = i // cols, i % cols
            xpos = col*self.__card_scaled_width
            ypos = row*self.__card_scaled_height
            card.move(QtCore.QPoint(xpos, ypos))

    def _copy_card(self, card):
        """Copies a card and connects the result to appropriate deck slots.

        :param card: the card to copy
        :type  card: :class:`Card`
        :return:     copied card
        :rtype:      :class:`Card`

        The card should be a card in the deck.

        """
        if card not in self.__cards:
            raise ValueError('Card not in deck')
        card = card.copy()
        card.cardSelected.connect(self.cardSingleSelected)
        card.cardCtrlSelected.connect(self.cardCtrlSelected)
        card.cardShiftSelected.connect(self.cardShiftSelected)
        return card


class Card(QtWidgets.QWidget):

    # Enum values for resolving card types
    type_unspecified = 0
    type_player = 1
    type_encounter = 2
    type_villain = 3

    """View for one single card.

    :param  front: card front side
    :type   front: :class:`PySide6.QtGui.QImage`
    :param   back: card back side (None if no image set)
    :type    back: :class:`PySide6.QtGui.QImage`
    :param  bbleed: amount of bleed on back image
    :param  ctype: card type
    :type   ctype: int
    :param parent: parent widget
    :type  parent: :class:`QtWidgets.QWidget`

    The `ctype` argument must be either `ctype.type_unspecified`,
    `ctype.type_player`, `ctype.type_encounter` or `ctype.type_villain`.

    *args* and *kwargs* are passed to :class:`QtWidgets.QWidget` constructor.

    """

    cardSelected = QtCore.Signal(QtWidgets.QWidget)       # Single card select
    cardCtrlSelected = QtCore.Signal(QtWidgets.QWidget)   # Card ctrl-select
    cardShiftSelected = QtCore.Signal(QtWidgets.QWidget)  # Card shift-select

    def __init__(self, front, back=None, bbleed=0, ctype=0, parent=None):
        super().__init__(parent)

        self.__front = front
        self.__back = back
        self.__back_bleed = bbleed
        if ctype not in (Card.type_unspecified, Card.type_player,
                         Card.type_encounter, Card.type_villain):
            raise ValueError('Illegal card type value')
        self.__type = ctype

        self.__scaled_front_img = None
        self.__scaled_back_img = None
        self.__back_offset = 0
        self.__margin = 0
        self.__cropped_back = None

        self._octgn = None         # OCTGN card data for the card (if set)
        self._octgn_back = None    # OCTGN card data for the card back (if set)
        self._imported = False     # If True the card was originally imported

        self._selected = False

        # Palette for background color when selected
        pal = QtGui.QPalette()
        pal.setColor(QtGui.QPalette.Window, '#cde8ff')
        self.setPalette(pal)

        self.reset()

    def setCardWidth(self, width):
        """Calculates widget height and sets widget size."""
        height = int(self._calcWidgetAspectHeight(width))
        self.setFixedSize(width, height)

    def reset(self):
        """Resets card rendering from card config information."""
        self.__cropped_back = None
        self.__scaled_back_img = None
        self._update_size(self.width(), self.height())
        self.setAutoFillBackground(self._selected)
        self.repaint()

    def paintEvent(self, event):
        # Internal function for drawing front or back image
        def _draw_img(p, img, x, y):
            rounding_mm = MCDeck.settings.corner_rounding_mm
            if rounding_mm == 0:
                p.drawImage(QtCore.QPoint(x, y), img)
            else:
                brush = QtGui.QBrush(img)
                p.setBrush(brush)
                p.setBrushOrigin(x, y)
                w_px, h_px = img.width(), img.height()
                r_x_px = int((rounding_mm/img.widthMm())*w_px)
                r_y_px = int((rounding_mm/img.heightMm())*h_px)
                p.drawRoundedRect(x, y, w_px, h_px, r_x_px, r_y_px)

        painter = QtGui.QPainter(self)
        front_img, back_img = self.__scaled_front_img, self.__scaled_back_img
        if MCDeck._front_on_top:
            if back_img:
                _draw_img(painter, back_img, self.__back_x, self.__back_y)
        if front_img:
            _draw_img(painter, front_img, self.__front_x, self.__front_y)
        if not MCDeck._front_on_top:
            if back_img:
                _draw_img(painter, back_img, self.__back_x, self.__back_y)
        painter.end()

    def resizeEvent(self, event):
        size = event.size()
        self._update_size(size.width(), size.height())

    def mousePressEvent(self, event):
        if event.buttons() == QtCore.Qt.LeftButton:
            key_mods = QtGui.QGuiApplication.keyboardModifiers()
            shift = key_mods & QtCore.Qt.ShiftModifier
            ctrl = key_mods & QtCore.Qt.ControlModifier
            if shift:
                self.cardShiftSelected.emit(self)
            elif ctrl:
                self.cardCtrlSelected.emit(self)
            else:
                self.cardSelected.emit(self)

    def copy(self):
        """Generate a copy of this card."""
        card = Card(self.__front, self.__back, self.__back_bleed, self.__type,
                    self.parentWidget())
        if self._octgn:
            card._octgn = self._octgn.copy()
        card.setCardWidth(self.width())
        card.move(self.pos())
        return card

    def select(self, state):
        """Set new card selection state.

        :param state: new state
        :type  state: bool

        """
        changed = state ^ self._selected
        self._selected = state
        if changed:
            self.reset()

    def set_front_image(self, image):
        """Sets a new front image for the card.

        :param image: image to set as front image (if None, remove it)
        :type  image: :class:`QtGui.QImage`

        """
        if (not isinstance(image, QtGui.QImage) or image.isNull()):
            raise ValueError('Must be a valid image')
        self.__front = image
        self.__scaled_front_img = None
        self.reset()

    def set_back_image(self, image, bleed=0):
        """Sets a back image for the card.

        :param image: image to set as back image (if None, remove it)
        :type  image: :class:`QtGui.QImage`
        :param bleed: bleed included on image, in mm

        """
        if image is None:
            self.__back = None
        else:
            if (not isinstance(image, QtGui.QImage) or image.isNull() or
                bleed < 0):
                raise ValueError('Must be a valid image with bleed >= 0')
            self.__back = image
            self.__back_bleed = bleed
        self.reset()

    @property
    def selected(self):
        """True if card is currently selected."""
        return self._selected

    @property
    def front_img(self):
        """Card front side image."""
        return self.__front

    @property
    def back_img(self):
        """Card back side image (either set on card, or derived from type).

        If no image was set for the back side and the card has a type for which
        a back side has been specified in settings, that image is returned.

        """
        if self.__back:
            return self.__back
        elif self.__type == Card.type_player:
            return MCDeck.settings.player_back_image()
        elif self.__type == Card.type_encounter:
            return MCDeck.settings.encounter_back_image()
        elif self.__type == Card.type_villain:
            return MCDeck.settings.villain_back_image()
        else:
            return None

    @property
    def specified_back_img(self):
        """Back side image set on card (ignoring card backs from card type)."""
        return self.__back

    @property
    def back_bleed(self):
        """Amount of bleed on :attr:`back_img` (mm)."""
        if self.__back:
            return self.__back_bleed
        elif self.__type == Card.type_player:
            return MCDeck.settings.player_bleed_mm
        elif self.__type == Card.type_encounter:
            return MCDeck.settings.encounter_bleed_mm
        elif self.__type == Card.type_villain:
            return MCDeck.settings.villain_bleed_mm
        else:
            return 0

    @property
    def specified_back_bleed(self):
        """Amount of bleed on attr:`specified_back_img` (mm)."""
        return self.__back_bleed

    @property
    def ctype(self):
        """Card type.

        Card type is either `Card.type_unspecified`, `Card.type_player`,
        `Card.type_encounter` or `Card.type_villain`.

        """
        return self.__type

    @ctype.setter
    def ctype(self, value):
        if value not in (Card.type_unspecified, Card.type_player,
                         Card.type_encounter, Card.type_villain):
            raise ValueError('Illegal card type value')
        self.__type = value
        self.__scaled_back_img = None
        self.__cropped_back = None
        self.reset()

    def _update_size(self, width, height):
        _s = MCDeck.settings
        back_rel_offset = _s.card_back_rel_offset
        card_rel_margin = _s.card_back_rel_spacing
        card_width = width/(1 + back_rel_offset)
        card_width /= (1 + 2*card_rel_margin)
        self.__back_offset = card_width * back_rel_offset
        self.__margin = (card_width + self.__back_offset)*card_rel_margin
        _s_c_height = _s.card_height_mm
        _s_c_width = _s.card_width_mm
        card_height = card_width*(_s_c_height/_s_c_width)

        self.__front_x = int(self.__margin)
        self.__front_y = self.__front_x
        self.__back_x = int(self.__margin + self.__back_offset)
        self.__back_y = self.__back_x

        card_width = int(card_width)
        card_height = int(self._calcWidgetAspectHeight(card_width))

        # Card front
        if (self.__scaled_front_img is None or
                self.__scaled_front_img.width() != card_width or
                self.__scaled_front_img.height() != card_height):
            size = QtCore.QSize(card_width, card_height)
            mode = QtCore.Qt.SmoothTransformation
            _img = self.__front.scaled(size, mode=mode)
            self.__scaled_front_img = LcgImage(_img)
            self.__scaled_front_img.setWidthMm(_s.card_width_mm)
            self.__scaled_front_img.setHeightMm(_s.card_height_mm)

        # Card back
        if self.back_img:
            if self.__cropped_back is None:
                if self.back_bleed == 0:
                    self.__cropped_back = self.back_img
                else:
                    img = LcgImage(self.back_img).cropBleed(self.back_bleed)
                    self.__cropped_back = img
            back = self.__cropped_back
            if (self.__scaled_back_img is None or
                    self.__scaled_back_img.width() != card_width or
                    self.__scaled_back_img.height() != card_height):
                size = QtCore.QSize(card_width, card_height)
                mode = QtCore.Qt.SmoothTransformation
                _img = back.scaled(size, mode=mode)
                self.__scaled_back_img = LcgImage(_img)
                self.__scaled_back_img.setWidthMm(_s.card_width_mm)
                self.__scaled_back_img.setHeightMm(_s.card_height_mm)

    def _calcWidgetAspectHeight(self, width):
        """Calculate widget height for correct card aspect for given width.

        :param width: target card width
        :type  width: float or int

        """
        back_rel_offset = MCDeck.settings.card_back_rel_offset
        card_rel_margin = MCDeck.settings.card_back_rel_spacing
        card_width = width/(1 + back_rel_offset)
        card_width /= (1 + 2*card_rel_margin)
        back_offset = card_width * back_rel_offset
        margin = (card_width + back_offset)*card_rel_margin

        card_height = card_width*(MCDeck.settings.card_height_mm /
                                  MCDeck.settings.card_width_mm)
        height = card_height + back_offset
        height += 2*margin
        return height


class CardTypeDialog(QtWidgets.QDialog):
    """Dialog for selecting card type."""

    _back_sources = [(None, 0)]*3
    _back_lazy = [None]*3

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__result = None

        main_layout = QtWidgets.QVBoxLayout()

        btn_width, btn_height = 93, 132
        btns = []
        layout = QtWidgets.QHBoxLayout()
        _s = MCDeck.settings
        d = ((_s.player_back_image(), _s.player_bleed_mm, 'Player',
              'Use default back card for player cards'),
             (_s.encounter_back_image(), _s.encounter_bleed_mm, 'Encounter',
              'Use default back card for encounter cards'),
             (_s.villain_back_image(), _s.villain_bleed_mm, 'Villain',
              'Use default back card for villain cards'))
        for i, entry in enumerate(zip(d, CardTypeDialog._back_sources,
                                      CardTypeDialog._back_lazy)):
            dval, back, lazy = entry
            img, bleed, text, tip = dval
            back_img, back_bleed = back

            btn = QtWidgets.QPushButton()
            if img:
                if back_img is img and back_bleed == bleed:
                    # Lazy-copy icon if possible to avoid expensive rescale
                    icon = lazy
                else:
                    if bleed > 0:
                        img = LcgImage(img).cropBleed(bleed)
                    img = img.scaled(btn_width, btn_height,
                                     mode=QtCore.Qt.SmoothTransformation)
                    pix = QtGui.QPixmap.fromImage(img)
                    icon = QtGui.QIcon(pix)
                    CardTypeDialog._back_sources[i] = (img, bleed)
                    CardTypeDialog._back_lazy[i] = icon
                btn.setIcon(icon)
                btn.setIconSize(pix.rect().size())
                btn.setToolTip(tip)
            else:
                btn.setText(text)
            layout.addWidget(btn)
            btns.append(btn)

        btn = QtWidgets.QPushButton()
        btn.setFixedSize(btn_width, btn_height)
        btn.setText('Select\nfile')
        btn.setToolTip('Select card back image')
        layout.addWidget(btn)
        btns.append(btn)

        btn = QtWidgets.QPushButton()
        btn.setFixedSize(btn_width, btn_height)
        btn.setText('Same\nas\nfront')
        btn.setToolTip('Use card front(s) as the card back(s)')
        layout.addWidget(btn)
        btns.append(btn)

        btn = QtWidgets.QPushButton()
        btn.setFixedSize(btn_width, btn_height)
        btn.setText('No\ncard\nback')
        btn.setToolTip('No back side image')
        layout.addWidget(btn)
        btns.append(btn)

        main_layout.addLayout(layout)
        main_layout.setAlignment(layout, QtCore.Qt.AlignHCenter)

        btns[0].clicked.connect(self.clickedPlayer)
        btns[1].clicked.connect(self.clickedEncounter)
        btns[2].clicked.connect(self.clickedVillain)
        btns[3].clicked.connect(self.clickedSelectBackImage)
        btns[4].clicked.connect(self.clickedSameAsFront)
        btns[5].clicked.connect(self.clickedNoBack)

        # Pushbuttons
        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Cancel)
        btns.rejected.connect(self.reject)
        main_layout.addWidget(btns)
        main_layout.setAlignment(btns, QtCore.Qt.AlignHCenter)

        self.setLayout(main_layout)
        self.setWindowTitle('Select card back')

    @property
    def result(self):
        """Result of accept operation in the form of (res_type, res_data)."""
        return self.__result

    @QtCore.Slot()
    def clickedPlayer(self):
        self.__result = (1, Card.type_player)
        self.accept()

    @QtCore.Slot()
    def clickedEncounter(self):
        self.__result = (1, Card.type_encounter)
        self.accept()

    @QtCore.Slot()
    def clickedVillain(self):
        self.__result = (1, Card.type_villain)
        self.accept()

    @QtCore.Slot()
    def clickedSelectBackImage(self):
        # Open dialog to select back side image
        _fun = loadImageFromFileDialog
        img = _fun(self, 'Open card back image')
        if img:
            self.__result = (2, img)
            self.accept()

    @QtCore.Slot()
    def clickedSameAsFront(self):
        self.__result = (3, None)
        self.accept()

    @QtCore.Slot()
    def clickedNoBack(self):
        self.__result = (4, None)
        self.accept()


class MarvelCDBCardImportDialog(QtWidgets.QDialog):
    """Dialog for Tools -> MarvelCDB -> Import Card ..."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._ids = []

        self.setWindowTitle('Import card(s) from MarvelCDB')
        l = QtWidgets.QVBoxLayout()
        _lbl = QtWidgets.QLabel
        _tl = _lbl('Enter <a href="https://marvelcdb.com/">MarvelCDB</a> card '
                   'ID(s) or URL(s) separated by spaces or commas.')
        _tl.setTextFormat(QtCore.Qt.RichText)
        _tl.setOpenExternalLinks(True)
        l.addWidget(_tl)
        box = QtWidgets.QGroupBox()
        box_l = QtWidgets.QHBoxLayout()
        box_l.addWidget(QtWidgets.QLabel('ID(s) or URL(s):'))
        self._le = QtWidgets.QLineEdit()
        box_l.addWidget(self._le)
        box.setLayout(box_l)
        l.addWidget(box)
        _l = QtWidgets.QHBoxLayout()
        self._create_placeholders_chk = QtWidgets.QCheckBox()
        self._create_placeholders_chk.setChecked(True)
        _tip = ('If checked, then a placeholder image is generated if the '
                'card has no image in MarvelCDB.')
        self._create_placeholders_chk.setToolTip(_tip)
        _l.addWidget(self._create_placeholders_chk)
        _l.addWidget(_lbl('Create placeholder if no image in MarvelCDB'))
        _l.addStretch(1)
        l.addLayout(_l)
        if not MCDeck.deck._octgn:
            l.addWidget(_lbl('Note: importing MarvelCDB card(s) '
                             'automatically enables OCTGN metadata'))
        l2 = QtWidgets.QHBoxLayout()
        l2.addStretch(1)
        btn_import = QtWidgets.QPushButton('Import')
        btn_import.clicked.connect(self.accept)
        btn_cancel = QtWidgets.QPushButton('Cancel')
        btn_cancel.clicked.connect(self.reject)
        l2.addWidget(btn_import)
        l2.addWidget(btn_cancel)
        l.addLayout(l2)
        self.setLayout(l)


class MarvelCDBDeckImportDialog(QtWidgets.QDialog):
    """Dialog for Tools -> MarvelCDB -> Import Deck ..."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._ids = []

        self.setWindowTitle('Import deck from MarvelCDB')
        l = QtWidgets.QVBoxLayout()
        _lbl = QtWidgets.QLabel
        _tl = _lbl('Enter <a href="https://marvelcdb.com/">MarvelCDB</a> deck '
                   'ID or URL.')
        _tl.setTextFormat(QtCore.Qt.RichText)
        _tl.setOpenExternalLinks(True)
        l.addWidget(_tl)
        box = QtWidgets.QGroupBox()
        box_l = QtWidgets.QHBoxLayout()
        box_l.addWidget(QtWidgets.QLabel('Deck ID or URL:'))
        self._le = QtWidgets.QLineEdit()
        box_l.addWidget(self._le)
        box.setLayout(box_l)
        l.addWidget(box)
        _l = QtWidgets.QHBoxLayout()
        self._include_hero_cards_chk = QtWidgets.QCheckBox()
        self._include_hero_cards_chk.setChecked(True)
        _tip = ('If unchecked, hero cards are excluded from the import. This '
                'is useful for combining non-hero cards from MarvelCDB with '
                'a custom hero set.')
        self._include_hero_cards_chk.setToolTip(_tip)
        _l.addWidget(self._include_hero_cards_chk)
        _l.addWidget(_lbl('Include hero cards when importing'))
        _l.addStretch(1)
        l.addLayout(_l)
        _l = QtWidgets.QHBoxLayout()
        self._include_non_hero_cards_chk = QtWidgets.QCheckBox()
        self._include_non_hero_cards_chk.setChecked(True)
        _tip = ('If unchecked, non-hero cards are excluded from the import. '
                'This is useful for getting only a set of hero cards to '
                'combine with custom aspect cards.')
        self._include_non_hero_cards_chk.setToolTip(_tip)
        _l.addWidget(self._include_non_hero_cards_chk)
        _l.addWidget(_lbl('Include non-hero cards when importing'))
        _l.addStretch(1)
        l.addLayout(_l)
        _l = QtWidgets.QHBoxLayout()
        self._create_placeholders_chk = QtWidgets.QCheckBox()
        self._create_placeholders_chk.setChecked(True)
        _tip = ('If checked, then a placeholder image is generated if the '
                'card has no image in MarvelCDB.')
        self._create_placeholders_chk.setToolTip(_tip)
        _l.addWidget(self._create_placeholders_chk)
        _l.addWidget(_lbl('Create placeholder if no image in MarvelCDB'))
        _l.addStretch(1)
        l.addLayout(_l)
        if not MCDeck.deck._octgn:
            l.addWidget(_lbl('Note: importing a MarvelCDB deck '
                             'automatically enables OCTGN metadata'))
        l2 = QtWidgets.QHBoxLayout()
        l2.addStretch(1)
        btn_import = QtWidgets.QPushButton('Import')
        btn_import.clicked.connect(self.accept)
        btn_cancel = QtWidgets.QPushButton('Cancel')
        btn_cancel.clicked.connect(self.reject)
        l2.addWidget(btn_import)
        l2.addWidget(btn_cancel)
        l.addLayout(l2)
        self.setLayout(l)


class LoadMarvelCDBDialog(QtWidgets.QDialog):
    """Dialog for first time initialization of MarvelCDB cards index."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setWindowTitle('Download MarvelCDB cards index')
        self.setMaximumWidth(600)
        _l = QtWidgets.QVBoxLayout()
        _txt = '''<p>Accessing <a href="https://marvelcdb.com/">MarvelCDB</a>
        cards requires downloading a card index. Setting up access to all cards
        is slower and more taxing on the MarvelCDB server, so <b>consider
        downloading player cards</b> unless you also need encounters and
        villains.</p>

        <p>After constructing the card index, <b>PDF generation will be
        disabled</b>until the app is closed (a gentle reminder that official
        game cards should not be printed).</p>

        <p>Choose which card set to download:</p>
        '''
        _lbl = QtWidgets.QLabel(_txt)
        _lbl.setTextFormat(QtCore.Qt.RichText)
        _lbl.setOpenExternalLinks(True)
        _lbl.setWordWrap(True)
        _l.addWidget(_lbl)
        _l2 = QtWidgets.QHBoxLayout()
        _l2.addStretch()
        self._fast_btn = QtWidgets.QPushButton('Player cards')
        self._fast_btn.clicked.connect(self.fast_btn)
        _l2.addWidget(self._fast_btn)
        self._slow_btn = QtWidgets.QPushButton('All cards')
        self._slow_btn.clicked.connect(self.slow_btn)
        _l2.addWidget(self._slow_btn)
        self._cancel_btn = QtWidgets.QPushButton('Cancel')
        self._cancel_btn.clicked.connect(self.reject)
        _l2.addWidget(self._cancel_btn)
        self._fast_btn.setDefault(True)
        _l.addLayout(_l2)
        self.setLayout(_l)

    @QtCore.Slot()
    def slow_btn(self):
        self._all = True
        self.accept()

    @QtCore.Slot()
    def fast_btn(self):
        self._all = False
        self.accept()


def main():
    app = QtWidgets.QApplication([sys.argv[0]])
    app.setApplicationName('MCdeck')
    app.setApplicationVersion(mcdeck.__version__)

    # Set up ArgumentParser for parsing command line arguments
    _desc = 'MCdeck - Export custom cards for Marvel Champions: The Card Game'
    parser = ArgumentParser(description=_desc)
    parser.add_argument('deck', metavar='deck_file', nargs='?', type=str,
                        help='source deck to load (.zip or .mcd)')
    parser.add_argument('--version', action='version',
                        version=f'%(prog)s {mcdeck.__version__}')
    args = parser.parse_args(sys.argv[1:])
    deck_path = args.deck

    view = MCDeck()
    view.resize(800, 600)
    view.show()
    if deck_path:
        view.deck._open(deck_path)
        view.deck._undo.clear()

    sys.exit(app.exec())


if __name__ == '__main__':
    main()
