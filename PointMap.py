import json
import os

import util


class PointMap:
    """
    Class that handles the mapping between removal reasons and their point costs.
    Also manages info about expiration durations.
    """

    def __init__(self, logger, reddit, path="points.json"):
        self.logger = logger
        self.reddit = reddit

        self.logger.info("Loading removal reasons...")
        with open(path, "r") as f:
            raw = json.load(f)

            # Check for dupes
            if len(raw) != len(set(x["id"] for x in raw)):
                self.logger.error("Duplicate removal reason IDs in points.json:")
                for r in util.get_dupes(x["id"] for x in raw):
                    self.logger.error(f"\t{r}")
                self.logger.error("The last instance of each one will be used.")

            # Build the map
            point_map = {}
            for x in raw:
                point_map[x["id"]] = {"points": int(x["points"])}
                if "expires" in x:
                    point_map["expires"] = int(x["expires"])
            self.logger.debug(f"Point map: {json.dumps(point_map)}")

        # Check for removal reasons on your sub that aren't in the map
        missing_reasons = set(r.title for r in reddit.subreddit(
            os.getenv("DRBOT_SUB")).mod.removal_reasons) - set(point_map.keys())
        if len(missing_reasons) > 0:
            self.logger.warning("Some removal reasons on your sub don't have an entry in points.json:")
            for r in missing_reasons:
                self.logger.warning(f"\t{r}")
            self.logger.warning("These removal reasons will be treated as costing 0 points.")

        self.point_map = point_map

    def __getitem__(self, removal_reason):
        """Get the point value for a removal reason."""
        if not removal_reason in self.point_map:
            self.logger.debug(f"Unknown removal reason '{removal_reason}', defaulting to 0 points.")
            return 0

        return self.point_map[removal_reason]["points"]

    def get_expiration(self, removal_reason):
        """Get the expiration months for a removal reason (or the default if no special duration is specified)."""

        default_expiration = os.getenv("DRBOT_EXPIRATION_MONTHS")
        default_expiration = None if default_expiration == "" or int(default_expiration) == 0 else int(default_expiration)
        
        # Use default if this removal reason is unknown
        if not removal_reason in self.point_map:
            self.logger.debug(f"Unknown removal reason '{removal_reason}', using default expiration ({default_expiration}).")
            return default_expiration
        
        # Otherwise, use the specific duration if available or the default if not
        expiration = self.point_map[removal_reason].get("expires", default_expiration)
        return None if expiration == 0 else expiration
