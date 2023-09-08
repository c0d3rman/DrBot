import json
from drbot import settings, log, reddit
from drbot.util import get_dupes


class PointMap:
    """
    Class that handles the mapping between removal reasons and their point costs.
    Also manages info about expiration durations.
    """

    def __init__(self) -> None:
        log.info("Loading removal reasons.")

        # Check for dupes
        if len(settings.point_config) != len(set(x["id"] for x in settings.point_config)):
            message = "Duplicate removal reason IDs in config/settings.toml (the last instance of each one will be used):"
            for r in get_dupes(x["id"] for x in settings.point_config):
                message += f"\n\t{r}"
            log.error(message)

        # Build the map
        point_map = {}
        for x in settings.point_config:
            point_map[x["id"]] = {"points": int(x["points"])}
            if "expires" in x:
                point_map["expires"] = int(x["expires"])
        log.debug(f"Point map: {json.dumps(point_map)}")

        # Check for removal reasons on your sub that aren't in the map
        missing_reasons = set(r.title for r in reddit().sub.mod.removal_reasons) - set(point_map.keys())
        if len(missing_reasons) > 0:
            message = "Some removal reasons on your sub don't have an entry in config/settings.toml (they will be treated as costing 0 points):"
            for r in missing_reasons:
                message += f"\n\t{r}"
            log.warning(message)

        self.point_map = point_map

    def __getitem__(self, removal_reason) -> int:
        """Get the point value for a removal reason."""
        if not removal_reason in self.point_map:
            log.debug(f"Unknown removal reason '{removal_reason}', defaulting to 0 points.")
            return 0

        return self.point_map[removal_reason]["points"]

    def get_expiration(self, removal_reason) -> int | None:
        """Get the expiration months for a removal reason (or the default if no special duration is specified)."""

        # Use default if this removal reason is unknown
        if not removal_reason in self.point_map:
            expiration = settings.expiration_months if settings.expiration_months > 0 else None
            log.debug(f"Unknown removal reason '{removal_reason}', using default expiration ({expiration}).")
            return expiration

        # Otherwise, use the specific duration if available or the default if not
        expiration = self.point_map[removal_reason].get("expires", settings.expiration_months)
        return expiration if expiration > 0 else None
