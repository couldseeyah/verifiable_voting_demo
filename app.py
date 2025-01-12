from flask import Flask, render_template, request, redirect, url_for, send_file, jsonify, session
import io
from database_handler import Database
from dotenv import load_dotenv
import os
import zipfile
from datetime import datetime, timezone
import random 
from encryption import Encryption, Ciphertext
import string
import re

app = Flask(__name__)
load_dotenv()


# use .env file for this??
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'default_secret_key')
db_handler = Database(SUPABASE_URL, SUPABASE_KEY)
# encryption_handler = Encryption()
private_key_file = 'private_key.txt'
print("Supabase URL: ", SUPABASE_URL)

# starting page for the voting app
@app.route('/')
def home():
    return render_template('login.html')

@app.route('/logout', methods=['GET', 'POST'])
def logout():
    # Redirect to login page
    session.pop("results_encryptions", None)
    return redirect(url_for('voter_login'))  # Assuming 'home' renders the login page

@app.route('/admin_dashboard', methods=['GET'])
def admin_dashboard():
    return render_template('admin_dashboard.html')


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
            return redirect(url_for('results'))

        # If none of the conditions are met, show the login invalid message
        message = "No election is ongoing, and results are not visible."
        return render_template('login.html', message=message)

    # If the request method is GET, just render the login page
    return render_template('login.html')


@app.route('/admin/end_election', methods=['POST'])
def end_election():
    response = db_handler.end_election()
    print("End Election Response: ", response)

    if "message" in response:
        return render_template('admin_dashboard.html', message=response.get("message")) #No ongoing election

    election_id = response[0]['id']
    election_votes = db_handler.get_votes_by_election(election_id) #list of records (cnic, vote, randomness, etc for each vote)

    #Read votes into Ciphertext Objects
    vote_strings = [vote_record['encrypted_vote'] for vote_record in election_votes] #['a,b,c', 'd,e,f']
    randomness_strings = [vote_record['randomness'] for vote_record in election_votes] #['ra,rb,rc', 'rd,re,rf']
    encrypted_votes = [] #[[Ara,Brb, Crc], [Drd, Ere, Frf]]
    for vote, randomness in zip(vote_strings, randomness_strings): 
        string_vote_vector = [item.strip() for item in vote.split(',')] #[a, b, c]
        randomness_vector = [item.strip() for item in randomness.split(',')] #[ra, rb, rc]
        encrypted_vote_vector = [] #[Ara, Brb, Crc]
        for i in range(len(string_vote_vector)): 
            encrypted_vote = Ciphertext(int(string_vote_vector[i]), int(randomness_vector[i])) #C(a, ra), C(b, rb), C(c, rc)
            encrypted_vote_vector.append(encrypted_vote)
        encrypted_votes.append(encrypted_vote_vector)
    
    with open(private_key_file, 'r') as file:
        priv_key = file.read().strip()  # Use .strip() to remove leading/trailing whitespace
    
    encryption_handler = Encryption(response[0]['public_key'], priv_key)

    #Homomorphic addition
    sum = encrypted_votes[0] #will contain encrypted result
    encrypted_votes = encrypted_votes[1:]
    for vote in encrypted_votes:
        for i in range(len(vote)): 
            sum[i] = encryption_handler.add(sum[i], vote[i])

    #decrypt result:
    decrypted_result = [] #will contain decrypted result
    for vote in sum: 
        plaintext = encryption_handler.decrypt(vote)
        decrypted_result.append(str(plaintext))
    print("DECRYPTED RESULT: ", decrypted_result)
    #convert encrypted and decrypted results to string representations
    decrypted_result_string = ','.join(decrypted_result)
    encrypted_result = []
    combined_randomness = []
    for vote in sum: 
        encrypted_result.append(str(vote.ciphertext))
        combined_randomness.append(str(vote.randomness))
    
    encrypted_result_string = ','.join(encrypted_result)
    combined_randomness_string = ','.join(combined_randomness)
    response = db_handler.update_election_results(election_id, encrypted_result_string, combined_randomness_string, decrypted_result_string, True)
    if not response.data[0]['ongoing']:
        message = ("Current election ended successfully.")
    else:
        message = ("Error ending current election.")
    return render_template('admin_dashboard.html', message=message)

    

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

    # Prepare data
    for election in elections:
        if election["decrypted_tally"] is not None:
            results = list(map(int, election["decrypted_tally"].split(',')))
            total_votes = sum(results)
            sorted_candidates = sorted(zip(election["candidates"], results), key=lambda x: x[1], reverse=True)
            election["sorted_candidates"] = [
                {
                    "name": candidate,
                    "votes": votes,
                    "percentage": (votes / total_votes * 100) if total_votes > 0 else 0
                }
                for candidate, votes in sorted_candidates
            ]

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
        # fetch latest created election
        response = db_handler.retrieve_last_election()
        res = db_handler.update_result_visibility(election_id, False)
        return render_template('admin_dashboard.html', last_election=response)
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
    print("length of candidates: ", len(candidates))
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
    

@app.route('/perform_audit', methods=['POST'])
def perform_audit():
    last_election = db_handler.retrieve_last_election()
    if not last_election:
        return "No election data found", 404

    decrypted_tally = last_election['decrypted_tally'].split(',')  # Split tally string into list
    public_key = last_election['public_key'] # Assuming the public key is stored in the election record
    encrypted_tally = last_election['encrypted_sum']
    combined_randomness = last_election['combined_randomness'].split(',')
    encryption_handler = Encryption(public_key=public_key)
    
    # Convert to an integer
    try:
        combined_randomness = [int(random) for random in combined_randomness]
    except ValueError as e:
        print(f"Error converting combined_randomness to int: {e}")
        raise ValueError("Invalid combined_randomness: must be numeric.")

    # Re-encrypt the decrypted tally using the public key
    re_encrypted_tally = []
    for i in range(len(decrypted_tally)):
        re_encrypted_tally.append(encryption_handler.encrypt(int(decrypted_tally[i]), combined_randomness[i])) #consists of ciphertext ojects

    re_encrypted_strings = [str(encrypted.ciphertext) for encrypted in re_encrypted_tally] #consists of ciphertext only
    re_encrypted_strings = ','.join(re_encrypted_strings)
    # Return all data as JSON
    return jsonify({
        'encrypted_tally': encrypted_tally,
        're_encrypted_tally': re_encrypted_strings
    })

@app.route('/search_encryptions', methods=['GET'])
def search_encryptions():
    # Fetch the first election with visible results using the DB handler
    visible_election = db_handler.get_visible_election()
    if visible_election:
        if "results_encryptions" not in session:
            # Fetch votes for the visible election using the DB handler
            votes = db_handler.get_votes_by_election(visible_election['id'])
            session["results_encryptions"] = votes
            return render_template('search_votes.html', votes=votes)
        else:
            return render_template('search_votes.html', votes=session["results_encryptions"])
    return "No visible results", 403

@app.route('/search-vote', methods=['GET'])
def search_vote():
    ballot_id = request.args.get('vote_id')  # Get the ballot_id from the form
    election = db_handler.get_visible_election() # Get the visible election
    vote_result = None

    if ballot_id:
        # Fetch the vote record from the database using the ballot_id
        vote_result = db_handler.get_vote_by_ballot_id(ballot_id, election['id'])

    return render_template(
        'search_votes.html',
        vote_result=vote_result,
        ballot_id=ballot_id,
        ballot_id_provided=True  # Indicates whether a search was performed
    )


@app.route('/results', methods=['GET'])
def results():
    last_election = db_handler.retrieve_last_election()    
    if last_election:
        candidates = db_handler.retrieve_candidates(last_election['id'])
        decrypted_tally = last_election['decrypted_tally'].split(',')
        #combining candiate names and votes
        results = [{'name': candidate['name'], 'votes': votes} for candidate, votes in zip(candidates, decrypted_tally)]
        return render_template('results.html', last_election=last_election, results=results)
    return "No results to display", 403


@app.route('/download_encryptions', methods=['GET'])
def download_encryptions():
    last_election = db_handler.get_visible_election()    
    if last_election:
        encrypted_votes = db_handler.get_votes_enc_by_election(last_election['id'])

        # Create a zip file in memory
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # Add each encrypted vote as a text file to the zip
            for i, vote in enumerate(encrypted_votes):
                file_name = f'vote_{i + 1}.txt'
                zip_file.writestr(file_name, vote['encrypted_vote'])
        
        # Seek to the beginning of the BytesIO buffer
        zip_buffer.seek(0)

        # Send the zip file as a downloadable response
        zip_file_name = "encrypted_votes.zip"
        return send_file(zip_buffer,
                         as_attachment=True,
                         download_name=zip_file_name,
                         mimetype='application/zip')

        return redirect(url_for('results'))

    return "No visible results", 403    

if __name__ == '__main__':
    app.run(debug=True)
