from supabase import create_client, Client
from typing import Optional, Dict, Any
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
        encryption: str,
        hash_value: str,
        random_factor: str,
        timestamp: datetime.datetime
    ) -> Dict[str, Any]:
        """
        Store vote data in the votes table.
        """
        if not timestamp.tzinfo:
            raise ValueError("vote_time must include timezone information.")

        data = {
            "cnic": cnic,
            "ballot_id": ballot_id,
            "election_id": election_id,
            "encrypted_vote": encryption,
            "vote_hash": hash_value,
            "randomness": random_factor,
            "time": timestamp.isoformat(),
        }
        response = self.supabase.table("votes").insert(data).execute()
        return response

    def retrieve_vote_data(self, cnic: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve vote data from the votes table by CNIC.
        """
        response = self.supabase.table("votes").select("*").eq("CNIC", cnic).execute()
        return response.data[0] if response.data else None

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
        decrypted_tally: str
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
        }
        response = self.supabase.table("elections").insert(data).execute()
        return response

    def retrieve_election_data(self, election_id: int) -> Optional[Dict[str, Any]]:
        """
        Retrieve election data from the elections table by election ID.
        """
        response = self.supabase.table("elections").select("*").eq("election_id", election_id).execute()
        return response.data[0] if response.data else None

    def check_admin_username(self, username: str) -> bool:
        """
        Check if an admin username exists in the admins table.
        """
        response = self.supabase.table("admins").select("username").eq("username", username).execute()
        return bool(response.data)

    def check_admin_password(self, username: str, password: str) -> bool:
        """
        Check if the password matches the admin username in the admins table.
        """
        response = self.supabase.table("admins").select("password").eq("username", username).execute()
        if not response.data:
            return False
        return response.data[0]["password"] == password
