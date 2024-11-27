from supabase import create_client, Client
from typing import Optional, List, Dict, Any
import datetime

class Database:
    def __init__(self, supabase_url: str, supabase_key: str):
        """
        Initialize the Database class with Supabase client.
        """
        self.supabase: Client = create_client(supabase_url, supabase_key)

    def store_vote_data(
        self,
        cnic: str,
        ballot_id: int,
        election_id: int,
        encrypted_vote: str,
        vote_hash: str,
        randomness: str,
        time: datetime.datetime
    ) -> Dict[str, Any]:
        """
        Store vote data in the votes table.
        """
        data = {
            "cnic": cnic,
            "ballot_id": ballot_id,
            "election_id": election_id,
            "encrypted_vote": encrypted_vote,
            "vote_hash": vote_hash,
            "randomness": randomness,
            "time": time,
        }
        response = self.supabase.table("votes").insert(data).execute()
        return response if response else None

    def retrieve_vote_data(self, cnic: str, id: int) -> Optional[Dict[str, Any]]:
        """
        Retrieve vote data from the votes table by CNIC and election ID.
        """
        response = self.supabase.table("votes").select("*").eq("cnic", cnic).eq("election_id", id).execute()
        if response.data:
            return response.data
        return None

    def store_election_data(
        self,
        election_id: int,
        num_candidates: int,
        start_time: datetime.datetime,
        end_time: datetime.datetime,
        status: bool,
        results_visibility: bool,
        encrypted_sum: str,
        encrypted_randomness: str,
        decrypted_tally: str,
        public_key: str,
    ) -> Dict[str, Any]:
        """
        Store election data in the elections table.
        """
        data = {
            "id": election_id,
            "num_candidates": num_candidates,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "ongoing": status,
            "results_visibility": results_visibility,
            "encrypted_sum": encrypted_sum,
            "combined_randomness": encrypted_randomness,
            "decrypted_tally": decrypted_tally,
            "public_key": public_key,
        }
        response = self.supabase.table("elections").insert(data).execute()
        return response

    def store_candidate_data(self, election_id: int, candidates: List[dict]) -> Dict[str, Any]:
        """
        Store candidate data in the candidates table.
        """
        # Add election_id to each candidate's data
        data = [{"election_id": election_id, "name": candidate["name"], "cand_id": candidate["id"], "symbol": candidate["symbol_url"]} for candidate in candidates]
        
        # Insert the data into the 'candidates' table via supabase
        response = self.supabase.table("candidates").insert(data).execute()
        
        # Return the response from the insertion operation
        return response

    def update_result_visibility(self, election_id: int, mode: bool) -> Optional[Dict[str, Any]]:
        """If mode is true, set given election_id to visible. if false, set all elections as insivisble."""
        if mode:
            response = self.supabase.table("elections").update({"results_visibility": True}).eq("id", election_id).execute()
        else:
            response = self.supabase.table("elections").update({"results_visibility": False}).neq("id", -1).execute()
        return response.data
    

    def retrieve_last_election(self):
        response = self.supabase.table('elections').select('*').order('created_at', desc=True).limit(1).execute()

        if not response.data:
            return {"status": "error", "message": "No elections found"}
        return response.data[0]


    def retrieve_candidates(self, election_id: int) -> list:
        """
        Retrieve all candidates for a given election ID from the candidates table.
        """
        try:
            response = self.supabase.table("candidates").select("*", count='exact').eq("election_id", election_id).execute()
            if response.data:
                return response.data  # List of candidates
            else:
                print(f"No candidates found for election ID {election_id}.")
                return []
        except Exception as e:
            print(f"Error retrieving candidates for election ID {election_id}: {e}")
            return []
    
    def set_elections_visibility(self, election_id: str) -> Optional[Dict[str, Any]]:
        """
        Set the visibility of all elections to False, except the one with the given election ID.
        """
        # Update all elections to False except the one with the given election ID
        response = self.supabase.table("elections").update({"results_visibility": False}).neq("id", election_id).execute()
        if response.data:
            return response
        return None

    def end_election(self) -> Optional[Dict[str, Any]]:
        """
        Retrieve most recent election and change status to False
        """
        # Retrieve the last election by ID
        response = self.supabase.table("elections").select("*").order("created_at", desc=True).limit(1).execute()

        if not response.data:
            return {"status": "error", "message": "No elections found"}

        last_election = response.data[0]
        election_id = last_election["id"]

        if last_election["ongoing"]==False:
            return {"status": "skipped", "message": "No ongoing elections found"}

        # Update the status of the last election to False (completed)
        update_response = self.supabase.table("elections").update({"ongoing": False}).eq("id", election_id).execute()
        res = self.update_result_visibility(election_id, True)
        return update_response.data

    def retrieve_election_data(self, election_id: int) -> Optional[Dict[str, Any]]:
        """
        Retrieve election data from the elections table by election ID.
        """
        response = self.supabase.table("elections").select("*").eq("id", election_id).execute()
        return response.data[0] if response.data else None

    def get_votes_by_election(self, election_id: int) -> list:
        """
        Retrieve all votes for a given election ID.
        """
        try:
            response = self.supabase.table("votes").select("*", count="exact").eq("election_id", election_id).execute()
            if response.data:
                return response.data  # List of votes
            else:
                print(f"No votes found for election ID {election_id}.")
                return []
        except Exception as e:
            print(f"Error retrieving votes for election ID {election_id}: {e}")
            return []

    def get_votes_enc_by_election(self, election_id: int) -> list:
        """
        Retrieve all encrypted votes for a given election ID.
        """
        try:
            response = self.supabase.table("votes").select("encrypted_vote", count="exact").eq("election_id", election_id).execute()
            if response.data:
                return response.data  # List of encrypted votes
            else:
                print(f"No encrypted votes found for election ID {election_id}.")
                return []
        except Exception as e:
            print(f"Error retrieving encrypted votes for election ID {election_id}: {e}")
            return []
        
    def get_vote_by_ballot_id(self, ballot_id: str, election_id: str) -> dict:
        """
        Retrieve a vote receipt by ballot ID and election ID.
        """
        try:
            response = self.supabase.table("votes").select("*").eq("ballot_id", ballot_id).eq("election_id", election_id).execute()
            if response.data:
                return response.data[0]  # Return the first matching vote record
            return None
        except Exception as e:
            print(f"Error fetching vote by ballot ID {ballot_id}: {e}")
            return None


    def update_election_results(
        self,
        election_id: int,
        encrypted_sum: str,
        combined_randomness: str,
        decrypted_tally: str,
        results_visibility: bool
    ) -> dict:
        """
        Updates the election row with the given election ID to update
        encrypted_sum, combined_randomness, decrypted_tally, and results_visibility..
        """
        try:
            # Create the update data dictionary
            update_data = {
                "encrypted_sum": encrypted_sum,
                "combined_randomness": combined_randomness,
                "decrypted_tally": decrypted_tally,
                "results_visibility": results_visibility
            }

            # Perform the update operation
            response = self.supabase.table("elections").update(update_data).eq("id", election_id).execute()

            # Check and return the response
            if response.data:
                print(f"Election ID {election_id} updated successfully.")
            else:
                print(f"No rows updated for Election ID {election_id}.")
            return response
        except Exception as e:
            print(f"Error updating election ID {election_id}: {e}")
            return {"error": str(e)}


    def retrieve_public_key(self, election_id: int) -> Optional[str]:
        """
        Retrieve the public key from the elections table by election ID.
        """
        response = self.supabase.table("elections").select("public_key").eq("id", election_id).execute()
        return response.data[0]["public_key"] if response.data else None

    def retrieve_candidates(self, election_id: int) -> List[Dict[str, Any]]:
        """
        Retrieve candidate data from the candidates table by election ID.
        """
        response = self.supabase.table("candidates").select("*").eq("election_id", election_id).execute()
        return response.data if response.data else []
        
    def get_visible_election(self) -> Optional[Dict[str, Any]]:
        """
        Retrieve the first election with visible results (results_visibility=True).
        """
        response = self.supabase.table("elections").select("*").eq("results_visibility", True).limit(1).execute()
        if response.data:
            return response.data[0]  # Return the first visible election
        return None

    def check_admin_username(self, username: str) -> bool:
        """
        Check if an admin username exists in the admins table.
        """
        response = self.supabase.table("admins").select("username").eq("username", username).execute()
        print("Check username response: ", response)
        return bool(response.data)

    def check_admin_password(self, username: str, password: str) -> bool:
        """
        Check if the password matches the admin username in the admins table.
        """
        response = self.supabase.table("admins").select("password").eq("username", username).execute()
        if not response.data:
            return False
        print("Check pw response: ", response)
        return response.data[0]["password"] == password
