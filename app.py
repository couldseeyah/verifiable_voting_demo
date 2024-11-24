from flask import Flask, render_template, request, redirect, url_for
from database_handler import Database
from dotenv import load_dotenv
import os
from datetime import datetime, timezone
import random 
from encryption import Encryption, Ciphertext

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

        # First, check if the last election is ongoing
        last_election = db_handler.retrieve_last_election()

        if last_election['ongoing'] == True:
            # Retrieve vote data by cnic
            vote_data = db_handler.retrieve_vote_data(cnic, last_election['id'])
            if vote_data:
                return render_template('receipt.html', vote_data=vote_data[0])
            else:
                # Retrieve candidates and their symbols
                candidates = db_handler.retrieve_candidates(last_election['id'])

                ballot_id = ''.join(random.choices('0123456789', k=6))

                # Pass the candidates to the cast_vote.html page
                return render_template('cast_vote.html', cnic=cnic, candidates=candidates, ballot_id=ballot_id, election_id=last_election['id'])

        # If the last election is not ongoing, check if results visibility is true
        if last_election['results_visibility'] == True:
            return render_template('search_encryptions.html')

        # If none of the conditions are met, show the login invalid message
        message = "No election is ongoing, and results are not visible."
        return render_template('login.html', message=message)

    # If the request method is GET, just render the login page
    return render_template('login.html')


@app.route('/admin/end_election', methods=['POST'])
def end_election():
    # End ongoing election
    response = db_handler.end_election()
    print("End election response: ", response)
    if response.data[0]['id']:
        return render_template('admin_dashboard.html')
    return render_template('admin_dashboard.html', message=response.get("message"))
    

@app.route('/admin/election_setup', methods=['POST'])
def election_setup():
    response = db_handler.supabase.table("elections").select("ongoing").execute()
    for i in response.data:
        if i['ongoing'] == True:
            return "An election is already ongoing!", 403
    return render_template('election_setup.html')

@app.route('/admin/prev_elections', methods=['POST'])
def view_prev_elections():
    response = db_handler.supabase.table('elections').select('*').order('created_at', desc=False).execute()
    elections = response.data

    for election in elections:
        candidates_response = db_handler.supabase.table('candidates').select('name').eq('election_id', election['id']).execute()
        candidates = candidates_response.data  # Access the 'data' attribute
        election['candidates'] = [candidate['name'] for candidate in candidates]

    return render_template('prev_elections.html', elections=elections)

@app.route('/admin/election_setup/set_candidates', methods=['POST'])
def set_candidates():
    # send all data to the set_candidates.html page
    election_id = request.form['election_id']   
    num_candidates = int(request.form['num_candidates'])
    start_time = request.form['start_time']
    end_time = request.form['end_time']
    return render_template('candidate_details.html', num_candidates=num_candidates, election_id=election_id, start_time=start_time, end_time=end_time)

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

    # Initialize a list to store candidate details
    candidates = []

    # Loop through the dynamically generated candidate fields
    for i in range(1, num_candidates + 1):
        candidate_name = request.form.get(f'candidate_name_{i}')
        candidate_id = request.form.get(f'candidate_id_{i}')
        candidate_symbol_file = request.files.get(f'candidate_symbol_{i}')  # Get the uploaded file

        if candidate_name and candidate_symbol_file:
            # Upload the image to Supabase storage
            try:
                file_name = f"election_{election_id}_candidate_{candidate_id}_{candidate_symbol_file.filename}"
                file_path = f"candidate_symbols/{file_name}"

                # Read the file as bytes
                file_content = candidate_symbol_file.read()

                # Supabase storage upload
                response = db_handler.supabase.storage.from_('candidate_symbols').upload(
                    file_path, file_content, {
                        "content-type": candidate_symbol_file.mimetype
                    }
                )

                if response.path:
                    # Generate public URL for the uploaded file
                    symbol_url = db_handler.supabase.storage.from_('candidate_symbols').get_public_url(file_path)

                    if symbol_url:
                        candidates.append({
                            'name': candidate_name,
                            'id': candidate_id,
                            'symbol_url': symbol_url
                        })
                    else:
                        print(f"Failed to generate public URL for {file_name}")
                        return "Error generating public URL for candidate symbol", 500
                else:
                    print(f"Error uploading file to Supabase: {response.status_code}")
                    return "Error uploading candidate symbol to storage", 500

            except Exception as e:
                print(f"Exception during upload: {str(e)}")
                return "Failed to upload candidate symbol", 500

    # Initialize the encryption object
    encryption = Encryption()
    public_key_g = str(encryption.paillier.keys['public_key']['g'])
    public_key_n = str(encryption.paillier.keys['public_key']['n'])
    public_key = public_key_g + ',' + public_key_n

    # Save the private key to a text file
    with open('private_key.txt', 'w') as file:
        file.write(str(encryption.paillier.keys['private_key']['phi']))

    # Store data in the database
    response1 = db_handler.store_election_data(
        election_id=election_id,
        num_candidates=num_candidates,
        start_time=start_time,
        end_time=end_time,
        status=status,
        results_visibility=results_visibility,
        encrypted_sum=encrypted_sum,
        encrypted_randomness=encrypted_randomness,
        decrypted_tally=decrypted_tally,
        public_key=public_key
    )

    response2 = db_handler.store_candidate_data(
        election_id=election_id,
        candidates=candidates
    )

    if response1.data and response2.data:
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
def cast_vote(cnic):
    ballot_id = int(request.form['ballot_id'])
    election_id = int(request.form['election_id'])
    candidate_id = int(request.form['candidate'])
    timestamp = datetime.now(timezone.utc)
    timestamp = timestamp.isoformat()

    candidates = db_handler.retrieve_candidates(election_id)

    # Generate an array of zeros with a 1 in the position of the selected candidate
    vote_vector = [0] * len(candidates)  # Create an array of zeros
    vote_vector[candidate_id - 1] = 1  # Set the position of the selected candidate to 1

    # get the public key
    public_key = db_handler.retrieve_public_key(election_id)

    # Initialize the encryption object with the public key
    enc = Encryption(public_key=public_key)
    encryption_vector = [] 
    random_factor_vector = []

    for vote in vote_vector:
        rand = enc.generate_random_key()
        ciphertext = enc.encrypt(vote, rand)
        encryption_vector.append(ciphertext.ciphertext)
        random_factor_vector.append(ciphertext.randomness)

    # convert vectors to strings seperated by commas
    encryption = ','.join(map(str, encryption_vector))
    random_factor = ','.join(map(str, random_factor_vector))
    hash_value = enc.hash(encryption)

    # Store vote data using Supabase handler
    response = db_handler.store_vote_data(
        cnic=cnic,
        ballot_id=ballot_id,
        election_id=election_id,
        encrypted_vote=encryption,
        vote_hash=hash_value,
        randomness=random_factor,
        time=timestamp
    )

    if response:
        vote_data = db_handler.retrieve_vote_data(cnic, election_id)
        return render_template('receipt.html', vote_data=vote_data[0])
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
