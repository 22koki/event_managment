from flask import Flask, render_template, request, redirect, url_for

app = Flask(__name__)

# Dummy data to simulate a database
events = [
    {"id": 1, "name": "Conference A", "date": "2024-03-15", "participants": ["John", "Jane"]},
    {"id": 2, "name": "Workshop B", "date": "2024-04-20", "participants": ["Bob", "Alice"]},
    {"id": 3, "name": "Seminar X", "date": "2024-05-10", "participants": ["Charlie", "Diana"]},
    {"id": 4, "name": "Hackathon Y", "date": "2024-06-22", "participants": ["Eva", "Frank"]},
    {"id": 5, "name": "Product Launch Z", "date": "2024-08-05", "participants": ["George", "Holly"]},
    {"id": 6, "name": "Networking Event", "date": "2024-09-18", "participants": ["Ivy", "Jack"]},
    {"id": 7, "name": "Tech Conference", "date": "2024-11-02", "participants": ["Kevin", "Lily"]},
    {"id": 8, "name": "Art Exhibition", "date": "2024-12-15", "participants": ["Mike", "Nancy"]},
]

@app.route('/')
def home():
    upcoming_events = [event for event in events if event['date'] >= '2024-02-15']
    past_events = [event for event in events if event['date'] < '2024-02-15']
    return render_template('index.html', upcoming_events=upcoming_events, past_events=past_events)

@app.route('/event/<int:event_id>')
def event_details(event_id):
    event = next((e for e in events if e['id'] == event_id), None)
    return render_template('event_details.html', event=event)

@app.route('/add_event', methods=['POST'])
def add_event():
    if request.method == 'POST':
        new_event = {
            "id": len(events) + 1,
            "name": request.form['name'],
            "date": request.form['date'],
            "participants": []
        }
        events.append(new_event)
        return redirect(url_for('home'))

@app.route('/edit_event/<int:event_id>', methods=['GET', 'POST'])
def edit_event(event_id):
    event = next((e for e in events if e['id'] == event_id), None)
    if request.method == 'POST':
        event['name'] = request.form['name']
        event['date'] = request.form['date']
        return redirect(url_for('home'))
    return render_template('edit_event.html', event=event)

@app.route('/delete_event/<int:event_id>')
def delete_event(event_id):
    global events
    events = [e for e in events if e['id'] != event_id]
    return redirect(url_for('home'))

if __name__ == '__main__':
    app.run(debug=True)
