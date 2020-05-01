# Malo

Malo (or мало, which means "a little", "a few", "a bit", "some" in a number of slavic languages) allows searching through an e-mail archive indexed with [`notmuch`](https://notmuchmail.org/) from a browser.

Malo started as a fork of [net viel](https://github.com/DavidMStraub/netviel).

Malo is a work in progress.

## Installation

Malo is not currently present in PyPI, so you'll need to clone this repository first.

```
make # this will fetch js dependencies; no npm required!
python3 -m pip install . --user
```

## Requirements

You need to have `notmuch` installed with its Python bindings. On Debian-based systems, this is achieved with

```
sudo apt install notmuch python3-notmuch
```

Python 3.6 or above is required.

## Usage

The web interface accessing your local `notmuch` database is opened simply with
```
python3 -m malo
```
The Flask default port 5000 can be changed with the `--ports` option.

**:warning: malo is meant for *local* use only. Do *not* expose this to the Internet as-is. Bad things will happen! :warning:**


