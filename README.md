# MCdeck

[MCdeck](https://pypi.org/project/mcdeck/) is a custom card deck builder app for
[Marvel Champions: The Card Game](https://www.fantasyflightgames.com/en/products/marvel-champions-the-card-game/)
(MC). Decks are constructed by adding card images, and possibly card metadata.
Decks can then be exported to the supported export formats.

Cards can currently be exported to PDF documents intended for printing custom
card decks, either for two-sided printing or "fold & glue" printing.

MCdeck uses functionality from [lcgtools](https://pypi.org/project/lcgtools/)
for PDF exports. Lcgtools is an alternative command line based tool for
generating PDFs, made by the same author.

Note that this tool is entirely fan made, and is in no way associated with or
endorsed by owners of MC intellectual property. It is intended entirely for
using with custom user generated content.

We recommended [Hall of Heroes](https://hallofheroeslcg.com/custom-content/) as
a resource for information regarding custom user generated content and related
communities.

# License

MCdeck is released under the [GNU General Public License
v3.0](https://www.gnu.org/licenses/gpl-3.0-standalone.html) or later. License
details are included with the source code.

# Alpha software

The package is an alpha release and is still in development. Though we strive
to make each release functional, some things may not work as expected. As
the tools are in development, tool usage and APIs may undergo changes between
releases.

# Installing

The library with source code can be installed from
[PyPI](https://pypi.org/project/MCdeck/). Dependencies include:

- [lcgtools](https://pypi.org/project/lcgtools/) for PDF generation

- [PySide6](https://pypi.org/project/PySide6/) Qt bindings for python (see the
  [reference](https://doc.qt.io/qtforpython/index.html) for more info)

- [setuptools](https://pypi.org/project/setuptools/) for building from source

The app has been tested to work on OSX, Linux, and Windows (tested with
python from [Microsoft Store](https://tinyurl.com/ekz5558m) and
[Anaconda](https://anaconda.org/)). Unfortunately, it does not (currently) work
with Windows Subsystem for Linux (WSL) due to lack of PySide6 support.

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
