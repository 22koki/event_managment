# Gather — an organiser’s event desk

A responsive Flask event desk with SQLite storage, guest registration and check-in. Repairs the duplicate `home` route that prevented startup, completes missing login/profile pages, and replaces disappearing in-memory events.

## Features

- Create/edit events with date, time, venue, description and capacity validation.
- Upcoming/past/cancelled/all collections, current-date filtering, and event/venue search.
- Cancel/reopen events and confirm permanent event deletion.
- Organiser-only guest registrations with duplicate detection and capacity limits.
- Check-in/undo, private guest identities, and downloadable CSV guest lists.
- Password hashing, CSRF protection, POST-only mutations and SQLite persistence.
- Responsive forms and dashboard with no remote assets or React dependency.

## Windows PowerShell setup

Requires Python 3.10+. From the repository directory:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m flask --app app:create_app init-admin --username organiser
```

Enter and confirm a password of at least 10 characters. There are no default accounts or passwords. Then start:

```powershell
.\.venv\Scripts\python.exe -m flask --app app:create_app run --port 5000
```

Open http://127.0.0.1:5000, choose **Organiser sign in**, and create your first event. On macOS/Linux, use `.venv/bin/python` in place of `.\.venv\Scripts\python.exe`. Node is used only for browser testing. `requirements.txt` replaces the old Pipenv manifests.

## Data and behaviour

`instance/events.sqlite3` and a random `instance/session.key` are created automatically. Keep these private and backed up together; pulling code updates does not require deleting them. Set `SECRET_KEY` through the environment when deploying, and `COOKIE_SECURE=1` for HTTPS. The factory accepts a config dictionary containing `DATABASE` and `SECRET_KEY` for isolated tests.

Event descriptions and attendance counts are public. Guest identities, management and exports require organiser login. Past/cancelled events reject registrations; capacity reductions cannot displace existing guests. Email identifies a guest when present, otherwise the normalised name does; namesakes should use distinct emails. CSV exports escape formula-like user input. Times follow the organiser's local convention.

This is a local, single-organiser prototype. Public service operation still needs a production WSGI server, HTTPS, login throttling, account recovery, operational backups and multi-organiser ownership rules. Payments and email invitations are not implemented.

## Tests and contributions

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

CI also runs Chromium against a disposable database: login, CRUD, guests, check-in, CSV downloads, reload persistence and layouts at 320–1440px. `tests/browser_server.py` is QA-only and requires `EVENT_TEST_DATABASE`; use `app:create_app` for normal operation.

Contribute on a feature branch, describe the workflow or bug, and run tests before opening a PR. Include a regression test for substantive changes and keep personal databases, session keys and virtual environments out of Git.
