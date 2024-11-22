from flask import Flask, render_template

app = Flask(__name__)

# starting page for the voting app
@app.route('/')
def home():
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    user_type = request.form.get('user_type')  
    if user_type == 'admin':
        return redirect(url_for('admin_login'))
    elif user_type == 'voter':
        return redirect(url_for('voter_login'))

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        admin = Admins.query.filter_by(username=username, password=password).first()
        if admin:
            # Fetch all elections
            elections = Elections.query.all()
            last_election = Elections.query.order_by(Elections.id.desc()).first()
            return render_template('admin_dashboard.html', elections=elections, last_election=last_election)
        else:
            return "Invalid credentials", 401
    return render_template('admin_login.html')

@app.route('/admin/end_election', methods=['POST'])
def end_election():
    # End ongoing election
    last_election = Elections.query.order_by(Elections.id.desc()).first()
    if last_election and last_election.current_status:
        last_election.current_status = False
        last_election.results_visibility = False
        db.session.commit()
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/start_election', methods=['POST'])
def start_election():
    # Start a new election
    num_candidates = request.form['num_candidates']
    start_time = datetime.now()
    new_election = Elections(
        num_candidates=num_candidates,
        starting_time=start_time,
        current_status=True,
        results_visibility=False
    )
    Elections.query.update({Elections.results_visibility: False})  # Turn off previous results
    db.session.add(new_election)
    db.session.commit()
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/set_results_visibility', methods=['POST'])
def set_results_visibility():
    election_id = request.form['election_id']
    Elections.query.update({Elections.results_visibility: False})  # Turn off all results
    election = Elections.query.get(election_id)
    if election and not election.current_status:
        election.results_visibility = True
        db.session.commit()
    return redirect(url_for('admin_dashboard'))

@app.route('/voter/login', methods=['GET', 'POST'])
def voter_login():
    if request.method == 'POST':
        cnic = request.form['cnic']
        last_election = Elections.query.order_by(Elections.id.desc()).first()
        
        if not last_election or not last_election.current_status:
            return "No ongoing election", 403
        
        existing_vote = Encryptions.query.filter_by(election_id=last_election.id, cnic=cnic).first()
        if existing_vote:
            return render_template('vote_receipt.html', vote=existing_vote)
        else:
            return redirect(url_for('cast_vote', cnic=cnic))
    return render_template('voter_login.html')

@app.route('/voter/cast_vote/<cnic>', methods=['GET', 'POST'])
def cast_vote(cnic):
    if request.method == 'POST':
        election_id = request.form['election_id']
        encryption = request.form['encryption']
        hash_value = request.form['hash']
        random_factor = request.form['random_factor']

        new_vote = Encryptions(
            election_id=election_id,
            cnic=cnic,
            encryption=encryption,
            hash=hash_value,
            random_factor=random_factor,
            time_of_vote=datetime.now()
        )
        db.session.add(new_vote)
        db.session.commit()
        return render_template('vote_receipt.html', vote=new_vote)
    return render_template('cast_vote.html', cnic=cnic)

@app.route('/search_encryptions', methods=['GET'])
def search_encryptions():
    visible_election = Elections.query.filter_by(results_visibility=True).first()
    if visible_election:
        votes = Encryptions.query.filter_by(election_id=visible_election.id).all()
        return render_template('search_encryptions.html', votes=votes)
    return "No visible results", 403

@app.route('/results', methods=['GET'])
def results():
    visible_election = Elections.query.filter_by(results_visibility=True).first()
    if visible_election:
        results = visible_election.decrypted_tally
        return render_template('results.html', results=results)
    return "No results to display", 403




# @app.route('/')
# def voting_page():
#     candidates = [
#         ("Socialist", "socialist.png"),
#         ("Libertarian", "libertarian.png"),
#         ("Green", "green.png"),
#         ("Independent", "independent.png"),
#         ("Anarchist", "anarchist.png"),
#         ("Republican", "republican.png"),
#         ("Democrat", "democrat.png")
#     ]
#     return render_template('cast_vote.html', candidates=candidates)


# @app.route('/search-vote', methods=['GET'])
# def search_vote():
#     vote_id = request.args.get('vote_id')
#     if vote_id in encrypted_votes:
#         return jsonify({"vote_id": vote_id, "encrypted_data": encrypted_votes[vote_id]})
#     else:
#         return jsonify({"error": "Vote ID not found"}), 404



if __name__ == '__main__':
    app.run(debug=True)
