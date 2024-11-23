from flask import Flask, render_template, request, redirect, url_for
from database_handler import Database
from dotenv import load_dotenv
import os
from datetime import datetime, timezone

app = Flask(__name__)
load_dotenv()

# use .env file for this??
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
db_handler = Database(SUPABASE_URL, SUPABASE_KEY)

print("Supabase URL: ", SUPABASE_URL)

# starting page for the voting app
@app.route('/')
def home():
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    user_type = request.form.get('user_type')
    print("USER TYPE: ", user_type)  
    if user_type == 'admin':
        return redirect(url_for('admin_login'))
    elif user_type == 'voter':
        return redirect(url_for('voter_login'))

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        print(f"Retrieved username {username} pw: {password}")
        if db_handler.check_admin_username(username) and db_handler.check_admin_password(username, password):
            print("Login valid.")
            # Fetch all elections using the db_handler class
            response = db_handler.supabase.table("elections").select("*").execute()
            elections = response.data
            last_election = elections[-1] if elections else None
            return render_template('admin_dashboard.html', elections=elections, last_election=last_election)
        else:
            return "Invalid credentials", 401
    return render_template('login.html')

@app.route('/voter/login', methods=['GET', 'POST'])
def voter_login():
    if request.method == 'POST':
        cnic = request.form['cnic']
        
        # Retrieve vote data by CNIC using Supabase handler
        vote_data = db_handler.retrieve_vote_data(cnic)
        if vote_data:
            return render_template('receipt.html', vote_data=vote_data)
        else:
            return "No vote data found for this CNIC", 404
    return render_template('login.html')

@app.route('/admin/end_election', methods=['POST'])
def end_election():
    # End ongoing election
    response = db_handler.end_election()
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/election_setup', methods=['POST'])
def election_setup():
    return render_template('election_setup.html')

@app.route('/admin/start_election', methods=['POST'])
def start_election():
    # Parse form data
    election_id = int(request.form['election_id'])
    num_candidates = int(request.form['num_candidates'])
    start_time_str = request.form['start_time']
    end_time_str = request.form['end_time']
    status = True 
    results_visibility = False  
    encrypted_sum = None
    encrypted_randomness = None
    decrypted_tally = None

    # Convert to datetime objects
    start_time = datetime.strptime(start_time_str, '%Y-%m-%dT%H:%M').time()
    end_time = datetime.strptime(end_time_str, '%Y-%m-%dT%H:%M').time()


    #storing data in DB
    response = db_handler.store_election_data(
        election_id=election_id,
        num_candidates=num_candidates,
        start_time=start_time,
        end_time=end_time,
        status=status,
        results_visibility=results_visibility,
        encrypted_sum=encrypted_sum,
        encrypted_randomness=encrypted_randomness,
        decrypted_tally=decrypted_tally
    )
    if response.data:
        response = db_handler.supabase.table("elections").select("*").execute()
        elections = response.data
        last_election = elections[-1] if elections else None
        return render_template('admin_dashboard.html', elections=elections, last_election=last_election)
    else:
        print(f"Error inserting election: {response}")
        return "Failed to start the election", 500


@app.route('/admin/set_results_visibility', methods=['POST'])
def set_results_visibility():
    election_id = request.form['election_id']
    response = db_handler.update_result_visibility(election_id)
    return redirect(url_for('admin_dashboard'))

@app.route('/vote/cast_vote/<cnic>', methods=['POST'])
def cast_vote():
    cnic = request.form['cnic']
    ballot_id = int(request.form['ballot_id'])
    election_id = int(request.form['election_id'])
    encryption = request.form['encryption']
    hash_value = request.form['hash_value']
    random_factor = request.form['random_factor']
    timestamp = datetime.datetime.now(datetime.timezone.utc)

    # Store vote data using Supabase handler
    response = db_handler.store_vote_data(
        cnic=cnic,
        ballot_id=ballot_id,
        election_id=election_id,
        encryption=encryption,
        hash_value=hash_value,
        random_factor=random_factor,
        timestamp=timestamp
    )
    if response.get("status_code") == 201:
        return "Vote successfully cast!", 200
    else:
        return "Failed to cast vote", 500

@app.route('/search_encryptions', methods=['GET'])
def search_encryptions():
    # Fetch the first election with visible results using the DB handler
    visible_election = db_handler.get_visible_election()
    if visible_election:
        # Fetch votes for the visible election using the DB handler
        votes = db_handler.get_votes_by_election(visible_election['id'])
        return render_template('search_encryptions.html', votes=votes)
    return "No visible results", 403


@app.route('/results', methods=['GET'])
def results():
    last_election = db_handler.retrieve_last_election()
    if last_election:
        results = last_election.decrypted_tally
        return render_template('results.html', results=results)
    return "No results to display", 403

if __name__ == '__main__':
    app.run(debug=True)
