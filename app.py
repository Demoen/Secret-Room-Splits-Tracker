from flask import Flask, request, render_template, redirect, url_for, send_from_directory
import os
import sqlite3
from datetime import datetime

app = Flask(__name__)

DATABASE = 'speedrun.db'
IMAGE_FOLDER = 'images'

def get_db_connection():
    try:
        conn = sqlite3.connect(DATABASE)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        print(f"An error occurred: {e}")
        return None

def create_tables():
    with get_db_connection() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                date TEXT,
                room1 TEXT,
                gullahs TEXT,
                room2 TEXT,
                tengu TEXT,
                room3 TEXT,
                hague TEXT,
                room4 TEXT,
                towers TEXT,
                midboss TEXT,
                finalboss TEXT
            );
        ''')
        conn.commit()

def parse_time(time_str):
    """Converts mm:ss to total seconds."""
    minutes, seconds = map(int, time_str.split(':'))
    return minutes * 60 + seconds

def format_time(seconds):
    """Converts total seconds back to mm:ss format."""
    minutes = seconds // 60
    seconds = seconds % 60
    return f'{minutes:02}:{seconds:02}'

def calculate_cumulative_times(runs):
    start_time_seconds = 60 * 60  # Initial time reference
    cumulative_runs = []

    for run in runs:
        run_dict = dict(run)  # Convert sqlite3.Row to dict
        cumulative_time = start_time_seconds
        cumulative_run = {
            'id': run_dict['id'],
            'name': run_dict['name'],  # Ensure name is included
            'date': run_dict['date']   # Ensure date is included
        }
        previous_end_time = start_time_seconds

        for key, value in run_dict.items():
            if key not in ['id', 'name', 'date']:
                current_remaining_time = parse_time(value)
                segment_duration = previous_end_time - current_remaining_time
                cumulative_time -= segment_duration

                cumulative_run[key] = format_time(segment_duration)
                cumulative_run[f'cumulative_{key}'] = format_time(cumulative_time)
                previous_end_time = current_remaining_time

        cumulative_runs.append(cumulative_run)
    return cumulative_runs

def calculate_individual_best_times(runs):
    if not runs:
        return {}

    segments = [
        'room1', 'gullahs', 'room2', 'tengu', 'room3',
        'hague', 'room4', 'towers', 'midboss', 'finalboss'
    ]

    segment_times = {segment: [] for segment in segments}
    for run in runs:
        previous_time = 60 * 60  # Start from 60 minutes in seconds
        for segment in segments:
            if run[segment]:
                current_time = parse_time(run[segment])
                segment_duration = previous_time - current_time
                segment_times[segment].append(segment_duration)
                previous_time = current_time

    best_times = {segment: min(times) if times else None for segment, times in segment_times.items()}

    ideal_times = {}
    cumulative_time = 60 * 60  # Start from 60 minutes in seconds
    for segment in segments:
        if best_times[segment] is not None:
            cumulative_time -= best_times[segment]
            ideal_times[segment] = {
                'cumulative_time': format_time(cumulative_time),
                'segment_time': format_time(best_times[segment])
            }
        else:
            ideal_times[segment] = {
                'cumulative_time': 'N/A',
                'segment_time': 'N/A'
            }

    return ideal_times

def calculate_total_time(cumulative_finalboss):
    start_time_seconds = 60 * 60  # 60 minutes
    finalboss_time_seconds = parse_time(cumulative_finalboss)
    total_time_seconds = start_time_seconds - finalboss_time_seconds + (16 * 60)
    return format_time(total_time_seconds)

@app.route('/images/<filename>')
def get_image(filename):
    return send_from_directory(IMAGE_FOLDER, filename)

@app.route('/', methods=['GET', 'POST'])
def index():
    conn = get_db_connection()
    query = "SELECT * FROM runs"
    params = []

    if request.method == 'POST':
        filter_name = request.form.get('filter_name', '').strip()
        filter_date = request.form.get('filter_date', '').strip()

        if filter_name and filter_date:
            query += " WHERE name LIKE ? AND date = ?"
            params = [f"%{filter_name}%", filter_date]
        elif filter_name:
            query += " WHERE name LIKE ?"
            params = [f"%{filter_name}%"]
        elif filter_date:
            query += " WHERE date = ?"
            params = [filter_date]

    runs = conn.execute(query, params).fetchall()
    conn.close()
    cumulative_runs = calculate_cumulative_times(runs)
    for run in cumulative_runs:
        run['total_time'] = calculate_total_time(run['cumulative_finalboss'])
        run['date'] = f"{run['date']} ({datetime.strptime(run['date'], '%Y-%m-%d').strftime('%A')})"  # Add weekday

    fastest_run = min(cumulative_runs, key=lambda x: parse_time(x['total_time']), default=None)
    fastest_run_time = fastest_run['total_time'] if fastest_run else 'N/A'

    ideal_times = calculate_individual_best_times(runs)
    ideal_times_total = calculate_total_time(ideal_times['finalboss']['cumulative_time']) if 'finalboss' in ideal_times else 'N/A'

    return render_template('index.html', runs=cumulative_runs, ideal_times=ideal_times, ideal_times_total=ideal_times_total, fastest_run_time=fastest_run_time)


@app.route('/add', methods=['POST'])
def add_run():
    try:
        conn = get_db_connection()
        data = {k: request.form[k] for k in request.form if request.form[k]}
        if not data:
            return "No data received from form", 400
        
        print(f"Received data for addition: {data}")

        columns = ', '.join(data.keys())
        placeholders = ', '.join('?' * len(data))
        values = tuple(data.values())

        sql = f'INSERT INTO runs ({columns}) VALUES ({placeholders})'
        conn.execute(sql, values)
        conn.commit()
    except Exception as e:
        print(f"Error processing add_run: {e}")
        return f"Error adding run: {e}", 500
    finally:
        conn.close()
    return redirect(url_for('index'))

@app.route('/delete/<int:run_id>', methods=['POST'])
def delete_run(run_id):
    try:
        conn = get_db_connection()
        conn.execute('DELETE FROM runs WHERE id = ?', (run_id,))
        conn.commit()
    except Exception as e:
        print(f"Error deleting run: {e}")
        return "Error deleting run", 500
    finally:
        conn.close()
    return redirect(url_for('index'))

@app.route('/edit/<int:run_id>', methods=['POST'])
def edit_run(run_id):
    try:
        conn = get_db_connection()
        segment = request.form['segment']
        time_value = request.form[segment]

        print(f"Updating {segment} of run {run_id} to {time_value}")

        if segment == 'name' or segment == 'date':
            sql = f'UPDATE runs SET {segment} = ? WHERE id = ?'
            conn.execute(sql, (time_value, run_id))
        else:
            sql = f'UPDATE runs SET {segment} = ? WHERE id = ?'
            conn.execute(sql, (time_value, run_id))
        
        conn.commit()
    except Exception as e:
        print(f"Error processing edit_run: {e}")
        return f"Error editing run: {e}", 500
    finally:
        conn.close()
    return redirect(url_for('index'))


if __name__ == '__main__':
    create_tables()
    app.run(debug=True)
