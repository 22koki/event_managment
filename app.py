"""Gather: a local, single-organiser event desk."""
import csv
import hmac
import io
import os
import secrets
import sqlite3
from datetime import date, datetime
from pathlib import Path
import click
from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for, Response
from werkzeug.security import check_password_hash, generate_password_hash
from functools import wraps


def create_app(config=None):
    app = Flask(__name__)
    app.config.update(DATABASE=str(Path(app.instance_path) / 'events.sqlite3'), MAX_CONTENT_LENGTH=50_000,
                      SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
                      SESSION_COOKIE_SECURE=os.environ.get('COOKIE_SECURE') == '1')
    if config:
        app.config.update(config)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    if not app.config.get('SECRET_KEY'):
        secret_path = Path(app.instance_path) / 'session.key'
        if not os.environ.get('SECRET_KEY') and not secret_path.exists():
            try:
                with secret_path.open('x') as file:
                    file.write(secrets.token_hex(32))
                secret_path.chmod(0o600)
            except FileExistsError:
                pass
        app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or secret_path.read_text().strip()
    Path(app.config['DATABASE']).parent.mkdir(parents=True, exist_ok=True)

    def db():
        if 'db' not in g:
            g.db = sqlite3.connect(app.config['DATABASE'], timeout=10)
            g.db.row_factory = sqlite3.Row
            g.db.execute('PRAGMA foreign_keys=ON')
        return g.db

    @app.teardown_appcontext
    def close(error):
        connection = g.pop('db', None)
        if connection:
            connection.close()

    with app.app_context():
        db().executescript('''
        CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, name TEXT NOT NULL, date TEXT NOT NULL, time TEXT NOT NULL,
            location TEXT NOT NULL, description TEXT NOT NULL, capacity INTEGER NOT NULL CHECK(capacity>0), status TEXT NOT NULL DEFAULT 'scheduled');
        CREATE TABLE IF NOT EXISTS attendees (id INTEGER PRIMARY KEY, event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
            name TEXT NOT NULL, email TEXT NOT NULL, identity TEXT NOT NULL, checked_in INTEGER NOT NULL DEFAULT 0,
            UNIQUE(event_id, identity));
        ''')
        db().commit()

    def csrf_token():
        if 'csrf' not in session:
            session['csrf'] = secrets.token_hex(32)
        return session['csrf']

    @app.before_request
    def load_user_and_protect_forms():
        g.user = db().execute('SELECT id, username FROM users WHERE id=?', (session.get('user_id'),)).fetchone()
        if request.method == 'POST':
            expected, supplied = session.get('csrf', ''), request.form.get('csrf', '')
            if not expected or not supplied.isascii() or not hmac.compare_digest(expected, supplied):
                abort(400, description='The form expired. Reload the page and try again.')

    @app.context_processor
    def context():
        return {'csrf_token': csrf_token, 'today': date.today().isoformat()}

    def organiser(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            if g.user is None:
                return redirect(url_for('login'))
            return fn(*args, **kwargs)
        return wrapped

    def event_row(event_id):
        row = db().execute('SELECT e.*, COUNT(a.id) AS enrolled, COALESCE(SUM(a.checked_in),0) AS arrived FROM events e LEFT JOIN attendees a ON a.event_id=e.id WHERE e.id=? GROUP BY e.id', (event_id,)).fetchone()
        if row is None:
            abort(404, description='That event could not be found.')
        return row

    def bounded(value, label, limit, required=True):
        value = value.strip()
        if (required and not value) or len(value) > limit:
            raise ValueError(f'{label} must contain {"1–" if required else "at most "}{limit} characters.')
        return value

    def event_values(form):
        name = bounded(form.get('name', ''), 'Event name', 120)
        day, time = form.get('date', ''), form.get('time', '')
        try:
            if date.fromisoformat(day).isoformat() != day or datetime.strptime(time, '%H:%M').strftime('%H:%M') != time:
                raise ValueError()
        except ValueError:
            raise ValueError('Choose a valid date and start time.') from None
        location = bounded(form.get('location', ''), 'Venue', 160)
        description = bounded(form.get('description', ''), 'Description', 3000, False)
        try:
            capacity = int(form.get('capacity', ''))
            if not 1 <= capacity <= 100000:
                raise ValueError()
        except ValueError:
            raise ValueError('Capacity must be a whole number from 1 to 100000.') from None
        return name, day, time, location, description, capacity

    @app.cli.command('init-admin')
    @click.option('--username', prompt=True)
    @click.password_option()
    def init_admin(username, password):
        """Create an organiser account; never installs a default password."""
        username = username.strip()
        if not 1 <= len(username) <= 80 or len(password) < 10:
            raise click.ClickException('Use a username of 1–80 characters and a password of at least 10 characters.')
        try:
            db().execute('INSERT INTO users(username,password_hash) VALUES (?,?)', (username, generate_password_hash(password)))
            db().commit()
        except sqlite3.IntegrityError:
            raise click.ClickException('That organiser already exists.') from None
        click.echo('Organiser created. Start the server and sign in.')

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            user = db().execute('SELECT * FROM users WHERE username=?', (request.form.get('username', '').strip(),)).fetchone()
            if user and check_password_hash(user['password_hash'], request.form.get('password', '')):
                session.clear(); session['user_id'] = user['id']; csrf_token()
                return redirect(url_for('home'))
            flash('The username or password is incorrect.', 'error')
        return render_template('login.html', title='Sign in')

    @app.post('/logout')
    @organiser
    def logout():
        session.clear()
        return redirect(url_for('home'))

    @app.get('/profile')
    @organiser
    def profile():
        return render_template('profile.html', title='Organiser profile')

    @app.get('/')
    def home():
        query = request.args.get('q', '').strip()[:120]
        view = request.args.get('view', 'upcoming')
        if view not in ('upcoming', 'past', 'cancelled', 'all'):
            view = 'upcoming'
        rows = db().execute('SELECT e.*, COUNT(a.id) AS enrolled FROM events e LEFT JOIN attendees a ON a.event_id=e.id GROUP BY e.id ORDER BY e.date,e.time,e.id').fetchall()
        today = date.today().isoformat()
        counts = {'upcoming':sum(e['status']=='scheduled' and e['date']>=today for e in rows), 'attendees':sum(e['enrolled'] for e in rows), 'past':sum(e['status']=='scheduled' and e['date']<today for e in rows)}
        visible = [e for e in rows if (not query or query.casefold() in (e['name']+' '+e['location']).casefold()) and (view=='all' or (view=='cancelled' and e['status']=='cancelled') or (e['status']=='scheduled' and ((view=='upcoming' and e['date']>=today) or (view=='past' and e['date']<today))))]
        return render_template('index.html', title='Your event desk', events=visible, counts=counts, view=view, query=query)

    @app.route('/add_event', methods=['GET', 'POST'])
    @organiser
    def add_event():
        values = {'capacity':100, 'time':'09:00', 'date':date.today().isoformat()}
        if request.method == 'POST':
            values = request.form
            try:
                data = event_values(values)
                cursor = db().execute('INSERT INTO events(name,date,time,location,description,capacity) VALUES (?,?,?,?,?,?)', data)
                db().commit(); flash('Your event is ready.', 'success')
                return redirect(url_for('event_details', event_id=cursor.lastrowid))
            except ValueError as error:
                flash(str(error), 'error')
                return render_template('edit_event.html', title='Create an event', event=values, editing=False), 400
        return render_template('edit_event.html', title='Create an event', event=values, editing=False)

    @app.route('/edit_event/<int:event_id>', methods=['GET', 'POST'])
    @organiser
    def edit_event(event_id):
        event = event_row(event_id)
        if request.method == 'POST':
            try:
                values = event_values(request.form)
                # Lock before checking capacity so registration cannot race an edit.
                db().execute('BEGIN IMMEDIATE')
                if values[-1] < event_row(event_id)['enrolled']:
                    raise ValueError('Capacity cannot be lower than the number of registered attendees.')
                db().execute('UPDATE events SET name=?,date=?,time=?,location=?,description=?,capacity=? WHERE id=?', (*values, event_id))
                db().commit(); flash('Event updated.', 'success')
                return redirect(url_for('event_details', event_id=event_id))
            except ValueError as error:
                db().rollback(); flash(str(error), 'error')
                return render_template('edit_event.html', title='Edit event', event=dict(request.form, id=event_id), editing=True), 400
        return render_template('edit_event.html', title='Edit event', event=event, editing=True)

    @app.get('/event/<int:event_id>')
    def event_details(event_id):
        event = event_row(event_id)
        attendees = db().execute('SELECT * FROM attendees WHERE event_id=? ORDER BY name,id', (event_id,)).fetchall() if g.user else []
        return render_template('event_details.html', title=event['name'], event=event, attendees=attendees)

    @app.post('/event/<int:event_id>/attendees')
    @organiser
    def register(event_id):
        try:
            name = bounded(request.form.get('name',''), 'Attendee name', 120)
            email = bounded(request.form.get('email',''), 'Email', 254, False)
            if email and ('@' not in email or any(c.isspace() for c in email) or '.' not in email.rsplit('@',1)[-1]):
                raise ValueError('Enter a valid email address or leave it blank.')
            db().execute('BEGIN IMMEDIATE'); event = event_row(event_id)
            if event['status'] == 'cancelled' or event['date'] < date.today().isoformat():
                raise ValueError('Registration is closed for this event.')
            if event['enrolled'] >= event['capacity']:
                raise ValueError('This event is full.')
            db().execute('INSERT INTO attendees(event_id,name,email,identity) VALUES (?,?,?,?)', (event_id, name, email, (email or name).casefold()))
            db().commit(); flash('Attendee registered.', 'success')
        except (ValueError, sqlite3.IntegrityError) as error:
            db().rollback(); flash('That attendee is already registered.' if isinstance(error, sqlite3.IntegrityError) else str(error), 'error')
        return redirect(url_for('event_details', event_id=event_id))

    @app.post('/event/<int:event_id>/attendees/<int:attendee_id>/<action>')
    @organiser
    def attendee_action(event_id, attendee_id, action):
        event = event_row(event_id)
        attendee = db().execute('SELECT * FROM attendees WHERE id=? AND event_id=?', (attendee_id,event_id)).fetchone()
        if not attendee or action not in ('checkin','remove'):
            abort(404)
        if action == 'checkin':
            if event['status']=='cancelled':
                flash('Check-in is closed for cancelled events.', 'error')
                return redirect(url_for('event_details', event_id=event_id))
            db().execute('UPDATE attendees SET checked_in=? WHERE id=?', (not attendee['checked_in'],attendee_id))
        else:
            db().execute('DELETE FROM attendees WHERE id=?', (attendee_id,))
        db().commit()
        return redirect(url_for('event_details', event_id=event_id))

    @app.post('/event/<int:event_id>/status')
    @organiser
    def status(event_id):
        event = event_row(event_id)
        db().execute('UPDATE events SET status=? WHERE id=?', ('scheduled' if event['status']=='cancelled' else 'cancelled',event_id)); db().commit()
        flash('Event status updated.', 'success')
        return redirect(url_for('event_details', event_id=event_id))

    @app.route('/delete_event/<int:event_id>', methods=['GET','POST'])
    @organiser
    def delete_event(event_id):
        event = event_row(event_id)
        if request.method == 'POST':
            db().execute('DELETE FROM events WHERE id=?', (event_id,)); db().commit()
            flash('Event and its attendee list deleted.', 'success')
            return redirect(url_for('home'))
        return render_template('delete_event.html', title='Delete event', event=event)

    @app.get('/event/<int:event_id>/export')
    @organiser
    def export(event_id):
        event_row(event_id); output=io.StringIO(); writer=csv.writer(output)
        writer.writerow(['Name','Email','Checked in'])
        for attendee in db().execute('SELECT * FROM attendees WHERE event_id=? ORDER BY name', (event_id,)):
            # Prevent spreadsheet formula evaluation in user-supplied cells.
            safe=lambda value: "'"+value if value.lstrip().startswith(('=','+','-','@')) else value
            writer.writerow([safe(attendee['name']),safe(attendee['email']),'Yes' if attendee['checked_in'] else 'No'])
        return Response(output.getvalue(),mimetype='text/csv',headers={'Content-Disposition':f'attachment; filename=event-{event_id}-attendees.csv'})

    @app.errorhandler(400)
    @app.errorhandler(404)
    @app.errorhandler(413)
    def error_page(error):
        return render_template('error.html', title=f'Error {error.code}', error=error), error.code
    return app


if __name__ == '__main__':
    create_app().run()
