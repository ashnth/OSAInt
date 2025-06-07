# OSAINT

Please do not share my API Keys `:)`

## How to start the program

Run `./src/osaint.py` for CLI version or `./web/app.py` for web version (Web url will be displayed in the CLI for web version).

## Error starting?

If you get an error while trying to execute the step above,
- Run `playwright install` for Windows and MacOS.
- Run `playwright install --with-deps` for Debian-based Linux systems.
- For any other systems, please search and install the following system dependancies. `libX11`, `libxcomposite`, `libXcursor`, `libXdamage`, `libXext`, `libXi`, `libXrender`, `libXtst`, `libXScrnSaver`, `gtk3`, `glib2`, `pango`, `cairo`, `at-spi2-core`, `nss`, `alsa-lib`, `cups-libs`, `libdrm`, `libgbm`, `xorg-x11-server-Xvfb`, `libwayland-client`, `libwayland-cursor`, `libwayland-egl`.

## Instructions for execution

- The app takes time, be ready for around a 30 min wait.
- Give the app a first and last name in format `{firstname} {lastname}` e.g. "John Doe", "Jane Doe".
- After the app has finished execution, you can find the graph it used as json file and html visualisation at `./data/{firstname}_{lastname}/{time_at_execution}/`.