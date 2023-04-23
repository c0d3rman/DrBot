import os
from datetime import datetime
from dateutil.relativedelta import relativedelta

import util


class PointStore:
    """
    Class handling the data structure that stores information about user points.
    Modifications to this data structure are what trigger bans.
    """

    def __init__(self, logger, reddit, point_map):
        self.logger = logger
        self.reddit = reddit
        self.point_map = point_map
        self.megadict = {}
        pass

    def add(self, mod_action):
        """
        Add points for a removal.
        Returns true if it was added and false if it wasn't (e.g. because it costs 0 points).
        Triggers a ban if the addition causes the user goes over the threshold.
        """
        removal_reason_id = mod_action.description
        submission_fullname = mod_action.target_fullname
        username = mod_action.target_author
        removal_time = mod_action.created_utc

        self.logger.debug(f"Processing removal of {submission_fullname} with reason: {removal_reason_id}")

        # Get point cost
        point_cost = self.point_map[removal_reason_id]
        if point_cost == 0:
            self.logger.debug(f"{submission_fullname} ignored because it costs 0 points.")
            return False

        # Check if this submission is already accounted for
        if not username in self.megadict:
            self.megadict[username] = {}
        if submission_fullname in self.megadict[username]:
            self.logger.debug(f"{submission_fullname} already accounted for; skipping")
            return False

        # Check if this submission has already expired
        expiration_duration = self.point_map.get_expiration(removal_reason_id)
        if not expiration_duration is None:
            expiration = datetime.fromtimestamp(removal_time) + relativedelta(months=self.point_map.get_expiration(removal_reason_id))
            if datetime.now() >= expiration:
                self.logger.debug(f"{submission_fullname} already expired before it was added; skipping")
                return False

        # Add the submission to the data
        self.megadict[username][submission_fullname] = {"cost": point_cost}
        if not expiration_duration is None:
            self.megadict[username][submission_fullname]["expires"] = int(datetime.timestamp(expiration))
        new_total = self.get_total(username)
        self.logger.info(f"+{point_cost} to u/{username} from {submission_fullname} (now at {new_total}).")

        # Check for ban
        if new_total >= int(os.getenv("DRBOT_POINT_THRESHOLD")):
            self.ban(username, new_total)

        return True

    def get_total(self, username):
        """
        Get the total current points for a user
        """
        if not username in self.megadict:
            return 0
        return sum(x["cost"] for x in self.megadict[username].values())

    def scan(self, username):
        """
        Scan a user's record for expired or re-approved submissions (and remove them).
        Returns true if anything was removed and false otherwise.
        """
        change = False
        for fullname in list(self.megadict[username].keys()):  # Cloned key list to avoid issues with modifying dict during iteration
            # Check for re-approval
            if not self.reddit.submission(fullname[3:]):
                self.logger.warning(f"Submission {fullname} by user u/{username} has been re-approved; removing")
                del self.megadict[username][fullname]
                change = True
                continue

            # Check for expiration
            if "expires" in self.megadict[username][fullname]:
                expiration = datetime.fromtimestamp(self.megadict[username][fullname]["expires"])
                if datetime.now() >= expiration:
                    self.logger.debug(f"Submission {fullname} by user u/{username} has expired; removing")
                    del self.megadict[username][fullname]
                    change = True
                    continue
        
        # If the user's record is empty now, delete
        if len(self.megadict[username]) == 0:
            self.logger.debug(f"User u/{username} has an empty record now; removing")
            del self.megadict[username]
            change = True

        return change

    def scan_all(self):
        """
        Scan the entire data store for expired or re-approved submissions.
        """
        for username in list(self.megadict.keys()): # Cloned key list to avoid issues with modifying dict during iteration
            self.scan(username)

    def ban(self, username, total):
        """
        Act on a user hitting the threshold.
        Either bans them or just sends modmail.
        Double-checks that all submissions are still removed and not past their expirations.
        Returns true if the ban went through and false if it didn't.
        """

        # Double check
        self.scan(username)
        if self.get_total(username) <= os.getenv("DRBOT_POINT_THRESHOLD"):
            return False

        self.logger.info(f"Banning u/{username} for reaching {total} points.")
