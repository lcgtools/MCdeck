# MCdeck

[MCdeck](https://pypi.org/project/mcdeck/) is a custom card deck builder app for
[Marvel Champions: The Card Game](https://www.fantasyflightgames.com/en/products/marvel-champions-the-card-game/)
(MC). Decks are constructed by adding card images and metadata. Decks can then
be exported to the supported export formats:

* PDF documents for printing custom card decks (2-sided or folded prints)

* Deck front&back image for importing into
  [Tabletop Simulator](https://store.steampowered.com/app/286160/Tabletop_Simulator/)

* Card sets and .o8d decks for [OCTGN](https://www.octgn.net/) and its
  [Marvel Champions module](https://twistedsistem.wixsite.com/octgnmarvelchampions/)

MCdeck can import cards and decks from [MarvelCDB](https://marvelcdb.com/), and
it can import cards directly from a local OCTGN database as well as loading
OCTGN .o8d deck files when referenced cards are present in the local database. 

The tool is fan made and is in no way associated with or endorsed by owners of
MC intellectual property. It is intended entirely for using with custom user
generated content.

# Alpha software

The package is an alpha release and is still in development. Though we strive
to make each release functional, some things may not work as expected. Tool
usage and APIs may undergo changes between releases.

# Installing

The library with source code can be installed from
[PyPI](https://pypi.org/project/MCdeck/). Dependencies include:

- [lcgtools](https://pypi.org/project/lcgtools/) for PDF generation (created
  by the same author as MCdeck)

- [PySide6](https://pypi.org/project/PySide6/) Qt bindings for python (see the
  [reference](https://doc.qt.io/qtforpython/index.html) for more info)

- [setuptools](https://pypi.org/project/setuptools/) for building from source

The app has been tested to work on OSX, Linux, and Windows (tested with
python from [Microsoft Store](https://tinyurl.com/ekz5558m) and
[Anaconda](https://anaconda.org/)). Unfortunately, it does not work with
Windows Subsystem for Linux (WSL) due to lack of PySide6 support.

MCdeck can be installed from PyPI with the command

```bash
pip install MCdeck  # Alternatively python3 -m pip install MCdeck
````

To install MCdeck from source, run this command from the top directory
(which includes the `pyproject.toml` file),

```bash
pip install .    # alternatively "python -m pip install ."
```

You may wish to install MCdeck with [virtualenv](https://tinyurl.com/2p8hux4r)
in order to separate the install from your general python environment.

# Usage

When properly installed with pip, the software can be launched with the command

```
mcdeck
```

See `mcdeck --help` for command line options (which is currently
limited to specifying a deck .zip or .mcd file to open). If for some reason the
software is installed on a system which does not properly add the program's
executable to its PATH, then it should still be possible to execute the program
with

```
python -m mcdeck.script
```

See Help->Usage in the program's menu for (very) basic information about
program usage.

# Other information

We recommended [Hall of Heroes](https://hallofheroeslcg.com/custom-content/) as
a resource for information regarding custom user generated content and related
communities.


# License

MCdeck is released under the [GNU General Public License
v3.0](https://www.gnu.org/licenses/gpl-3.0-standalone.html) or later. License
details are included with the source code.
