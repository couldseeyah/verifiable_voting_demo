from flask import Flask, render_template

app = Flask(__name__)

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


# Example database of encrypted votes (for demonstration purposes)
encrypted_votes = {
    "vote1": "ENCRYPTED_DATA_1",
    "vote2": "ENCRYPTED_DATA_2",
    "vote3": "ENCRYPTED_DATA_3"
}

@app.route('/search-vote', methods=['GET'])
def search_vote():
    vote_id = request.args.get('vote_id')
    if vote_id in encrypted_votes:
        return jsonify({"vote_id": vote_id, "encrypted_data": encrypted_votes[vote_id]})
    else:
        return jsonify({"error": "Vote ID not found"}), 404

@app.route('/')
def search_page():
    return render_template('search_votes.html')


if __name__ == '__main__':
    app.run(debug=True)
