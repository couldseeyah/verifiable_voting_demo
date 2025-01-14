from flask import Flask, render_template, request, redirect, url_for, send_file, jsonify, session
import io
from apscheduler.schedulers.background import BackgroundScheduler
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

# Initialize APScheduler
scheduler = BackgroundScheduler()
scheduler.start()

def get_private_key_path():
    """Returns the appropriate path for storing the private key file"""
    # Check if running on Vercel (VERCEL=1 is automatically set in Vercel environment)
    if os.environ.get('VERCEL') == '1':
        base_dir = '/tmp'
    else:
        # Use current directory for local development
        base_dir = os.path.dirname(os.path.abspath(__file__))
    
    print(f"Using base directory: {base_dir} for private key storage")  # Debug log
    return os.path.join(base_dir, 'private_key.txt')

private_key_file = get_private_key_path()

def update_election_status(election_id):
    """Update the election status to ongoing."""
    try:
        db_handler.update_election_status(election_id, True)
        print(f"Election {election_id} is now ongoing.")
    except Exception as e:
        print(f"Failed to update election status: {str(e)}")

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
    return render_template('admin_login.html')

@app.route('/voter/login', methods=['GET', 'POST'])
def voter_login():
    if request.method == 'POST':
        cnic = request.form['cnic']

        # First, check if the last election is ongoing
        last_election = db_handler.retrieve_last_election()

        if last_election['ongoing'] == True:
            #Check if this cnic has already cast a vote
            voter_data = db_handler.retrieve_voter_data(cnic, last_election['id'])
            # vote_data = db_handler.retrieve_vote_data(cnic, last_election['id'])
            if voter_data:
                return render_template('login.html', message="Vote has already been cast for the current election.")
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
    election_votes = db_handler.get_votes_by_election(election_id) #list of records for each vote

    #Read votes into Ciphertext Objects
    vote_strings = [vote_record['encrypted_vote'] for vote_record in election_votes] #['a,b,c', 'd,e,f']
    encrypted_votes = [] 
    for vote in vote_strings:  
        string_vote_vector = [item.strip() for item in vote.split(',')]  # now vote is a string
        encrypted_vote_vector = [] 
        for i in range(len(string_vote_vector)): 
            encrypted_vote = Ciphertext(int(string_vote_vector[i]))  # C(a), C(b), C(c)
            encrypted_vote_vector.append(encrypted_vote)
        encrypted_votes.append(encrypted_vote_vector)
    
    
    try:
        with open(get_private_key_path(), 'r') as file:
            priv_key = file.read().strip()
    except Exception as e:
        print(f"Error reading private key: {str(e)}")
        return render_template('admin_dashboard.html', message="Error: Could not retrieve election key")
    
    encryption_handler = Encryption(response[0]['public_key'], priv_key)

    #Homomorphic addition
    sum = encrypted_votes[0] #will contain encrypted result
    encrypted_votes = encrypted_votes[1:]
    for vote in encrypted_votes:
        for i in range(len(vote)): 
            sum[i] = encryption_handler.add(sum[i], vote[i])

    #decrypt result and compute negattive for auduting purposes:
    decrypted_result = [] #will contain decrypted result
    negative_result = [] #will contain negative of decrypted result
    for vote in sum: 
        plaintext = encryption_handler.decrypt(vote) #int
        negative = encryption_handler.encrypt(-plaintext, 1) #ciphertext object
        decrypted_result.append(str(plaintext)) #array of strings
        negative_result.append(negative) #array of ciphertext objects
    print("DECRYPTED RESULT: ", decrypted_result)

    #auditing functions for result
    # first add the negative of the decrypted result to the sum
    zero_vector = []
    zero_vector_r = []
    for i in range(len(sum)):
        zero_enc = encryption_handler.add(sum[i], negative_result[i]) #ciphertext object
        r = encryption_handler.extract_randomness_from_zero_vector(zero_enc) #int
        zero_vector.append(zero_enc) #array of ciphertext objects
        zero_vector_r.append(str(r)) #array of strings

    #convert encrypted and decrypted results to string representations
    decrypted_result_string = ','.join(decrypted_result)
    zero_vector_r_string = ','.join(zero_vector_r)
    encrypted_result_string = ','.join(str(vote.ciphertext) for vote in sum)
    negative_result_string = ','.join(str(vote.ciphertext) for vote in negative_result)
    zero_vector_string = ','.join(str(vote.ciphertext) for vote in zero_vector)

    response = db_handler.update_election_results(election_id, encrypted_result_string, decrypted_result_string, True, negative_result_string, zero_vector_string, zero_vector_r_string)
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
        # Format the start_date
        if election["start_date"] is not None:

            # Parse the datetime string into a datetime object
            dt_object = datetime.strptime(election['start_date'], '%Y-%m-%dT%H:%M:%S')
            # Format the datetime object into the desired format
            formatted_datetime = dt_object.strftime('%d %B %Y, %H:%M')

            election['formatted_start_date'] = formatted_datetime

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
    # election_id = request.form['election_id']
    num_candidates = int(request.form['num_candidates'])
    start_immediately = 'start_immediately' in request.form  # Check if checkbox is checked

    if start_immediately:
        # Set start time to now and end time to None (or a default value)
        start_time = datetime.now().strftime('%Y-%m-%dT%H:%M')
        # end_time = None
    else:
        # Retrieve specified start and end times
        start_time = request.form['start_time']
        # end_time = request.form['end_time']

    return render_template('candidate_details.html', 
                           num_candidates=num_candidates, 
                        #    election_id=election_id, 
                           start_time=start_time)

@app.route('/admin/start_election', methods=['POST'])
def start_election():
    #retrieve previous election data to get last election ID
    last_election = db_handler.retrieve_last_election()
    if not last_election:
        return "No election data found", 404
    
    last_election_id = last_election['id']
    print("last election ID: ", last_election_id)
    election_id = int(last_election_id)+1

    # Parse form data
    num_candidates = int(request.form['num_candidates'])
    start_time_str = request.form['start_time']
    status = True 
    results_visibility = False  
    encrypted_sum = None
    decrypted_tally = None
    negative_result = None
    zero_vector = None
    zero_vector_r = None

    #for start_date purposes i.e storing in db
    parsed_time = datetime.strptime(start_time_str, "%Y-%m-%dT%H:%M")
    formatted_start_time = parsed_time.strftime("%Y-%m-%d %H:%M:%S.000")

    # for comparing purposes, Remove square brackets and convert string to datetime object
    datetime_obj = datetime.strptime(start_time_str, "%Y-%m-%dT%H:%M")

    right_now = datetime.now()

    # Compare with the current datetime
    if datetime_obj > right_now:  # Use UTC to match Supabase timestamps
        status = False  # Set status to False if 'created_at' is in the future

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
    try:
        with open(get_private_key_path(), 'w') as file:
            file.write(str(encryption.paillier.keys['private_key']['phi']))
    except Exception as e:
        print(f"Error writing private key: {str(e)}")
        return "Failed to store election key", 500

    # Store data in the database
    response1 = db_handler.store_election_data(
        election_id=election_id,
        num_candidates=num_candidates,
        start_time=None,
        # end_time=end_time,
        status=status,
        results_visibility=results_visibility,
        encrypted_sum=encrypted_sum,
        decrypted_tally=decrypted_tally,
        public_key=public_key,
        negative_tally_encryption=negative_result,
        zero_vector=zero_vector,
        zero_randomness=zero_vector_r,
        start_date = formatted_start_time
    )

    response2 = db_handler.store_candidate_data(
        election_id=election_id,
        candidates=candidates
    )

    # Schedule a job to update the election status to True 
    try :
        if datetime_obj > right_now:
            scheduler.add_job(
                func=update_election_status,
                trigger='date',
                run_date=datetime_obj,
                args=[election_id]
            )
    except Exception as e:
        print(f"Error scheduling job: {str(e)}")

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

    for vote in vote_vector:
        ciphertext = enc.encrypt(vote)
        encryption_vector.append(ciphertext.ciphertext)

    # convert vectors to strings seperated by commas
    encryption = ','.join(map(str, encryption_vector))
    hash_value = enc.hash(encryption)

    # Store vote data using Supabase handler
    response = db_handler.store_vote_data(
        ballot_id=ballot_id,
        election_id=election_id,
        encrypted_vote=encryption,
        vote_hash=hash_value,
        time=timestamp
    )

    if response:
        #store CNIC and Election ID in Voter Table
        voter_response = db_handler.store_voter_data(cnic, election_id)
        if voter_response:
            vote_data = db_handler.retrieve_vote_data(ballot_id, election_id)
            return render_template('receipt.html', vote_data=vote_data[0])
        else: 
            return "Failed to store voter data", 500
    else:
        return "Failed to cast vote", 500
    

@app.route('/perform_audit', methods=['POST'])
def perform_audit():
    last_election = db_handler.retrieve_last_election()
    if not last_election:
        return "No election data found", 404

    candidates = db_handler.retrieve_candidates(last_election['id'])
    decrypted_tally = last_election['decrypted_tally'].split(',') if last_election['decrypted_tally'] else []
    #combining candiate names and votes
    results = [{'name': candidate['name'], 'votes': votes} for candidate, votes in zip(candidates, decrypted_tally)]
    public_key = last_election['public_key'] # Assuming the public key is stored in the election record
    encrypted_tally = last_election['encrypted_sum'].split(',') if last_election['encrypted_sum'] else []
    zero_vector_randomness = last_election['zero_randomness'].split(',') if last_election['zero_randomness'] else []
    encryption_handler = Encryption(public_key=public_key)

    #convert encrypted tally to array of ciphertext objects
    encrypted_tally = [Ciphertext(int(t)) for t in encrypted_tally]
    
    # re-encrypt the negative of the decrypted tally using random factor 1
    negative_tally_enc = [encryption_handler.encrypt(-int(t), 1) for t in decrypted_tally] #ct object

    # subtract to get zero 
    zero_vector = [
        encryption_handler.add(encrypted_tally[i], negative_tally_enc[i])
    for i in range(len(negative_tally_enc))
    ] #an array of ct objects
    #convert this array to string
    zero_vector_string = [str(encrypted.ciphertext) for encrypted in zero_vector] #consists of ciphertext only
    zero_vector_string = ','.join(zero_vector_string)

    for i in range(len(zero_vector_randomness)):
        zero_vector_randomness[i] = int(zero_vector_randomness[i]) #array of ints

    # Re-encrypt the zero vector using the public key
    re_encrypted_tally = []
    zeros = [0] * len(zero_vector_randomness)
    for i in range(len(zeros)):
        re_encrypted_tally.append(encryption_handler.encrypt(zeros[i], zero_vector_randomness[i])) #consists of ciphertext ojects

    re_encrypted_strings = [str(encrypted.ciphertext) for encrypted in re_encrypted_tally] #consists of ciphertext only
    re_encrypted_strings = ','.join(re_encrypted_strings)
    
    # Add data to render in the modal
    modal_data = {
        'zero_vector': zero_vector_string,
        're_encrypted_zero_vector': re_encrypted_strings
    }

    # Render the same template with audit data
    return render_template(
        'results.html',
        last_election=last_election,
        modal_data=modal_data, 
        results = results
    )

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
        decrypted_tally = last_election['decrypted_tally']
        if decrypted_tally:
            decrypted_tally = decrypted_tally.split(',')
            #combining candiate names and votes
            results = [{'name': candidate['name'], 'votes': votes} for candidate, votes in zip(candidates, decrypted_tally)]
            return render_template('results.html', last_election=last_election, results=results)
        return render_template('results.html', last_election=last_election, results=[])
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
    app.run(host='0.0.0.0', port=5001)
else:
    # This is for Vercel
    app = app
