from __future__ import annotations
from datetime import datetime, timezone, timedelta
from pytimeparse import parse
from ..util import validate_duration
from ..log import log
from ..reddit import reddit
from ..Botling import Botling


class QueueSizeWatcher(Botling):
    """Sends a modmail warning when the queue grows beyond a given size limit."""

    default_settings = {
        "threshold": 100,  # The maximum number of items allowed in the queue before a warning is sent
        "period": "10 seconds",  # How frequently to check the modqueue size
        "resend_after": "1 day",  # To avoid spamming you with alerts in case the queue size fluctuates near your threshold size, the bot won't send you more than one alert in this period of time.
        "allow_repeated_alerts": False  # Once the bot has alerted you about the queue size, it won't bug you again until the queue dips below the threshold and goes back up. Set this to True to ignore that behavior - meaning if your sub has an untouched 200 item queue for a month, you'll get a modmail about it every day.z
    }

    def validate_settings(self) -> None:
        assert isinstance(self.DR.settings.threshold, int)
        assert self.DR.settings.threshold > 0, "threshold must be at least 1."
        validate_duration(self.DR.settings.period, key="period", nonzero=True)
        validate_duration(self.DR.settings.resend_after, key="resend_after")
        assert isinstance(self.DR.settings.allow_repeated_alerts, bool)

    def setup(self) -> None:
        # Parse durations
        self.period = parse(self.DR.settings.period)
        self.resend_after = parse(self.DR.settings.resend_after)

        # Initialize storage
        self.DR.storage["last_alerted"] = None  # Time of the last alert
        self.DR.storage["active_alert"] = False  # Whether an alert is currently active (meaning we shouldn't send another until the queue is healthy again, unless allow_repeated_alerts is on)

        # Schedule periodic scan
        self.DR.scheduler.every(self.period).seconds.do(self.scan)

    def scan(self) -> None:
        # If we're in a cooldown period, don't bother pinging reddit
        if self.DR.storage["last_alerted"] and datetime.now(timezone.utc) - self.DR.storage["last_alerted"] < timedelta(seconds=self.resend_after):
            log.debug(f"Skipping sending an alert because {self.DR.settings.resend_after} haven't yet passed since the last one.")
            return

        # Get the queue size
        queue_size = sum(1 for _ in reddit.sub.mod.modqueue(limit=None))
        log.debug(f"Queue size: {queue_size}.")

        # If the queue size is healthy, mark that there's no active alert and quit
        if queue_size <= self.DR.settings.threshold:
            self.DR.storage["active_alert"] = False
            return

        # If there's already an active alert and allow_repeated_alerts is off, quit
        if not self.DR.settings.allow_repeated_alerts and self.DR.storage["active_alert"]:
            log.debug("Skipping sending an alert because there's already an active one.")
            return

        # The queue is unhealthy, so send an alert.
        log.info(f"The queue size is {queue_size}, which is above the threshold ({self.DR.settings.threshold}). Alerting mods.")

        # Send modmail
        reddit.DR.send_modmail(subject=f"The modqueue size has reached {queue_size}",
                               body=f"""The modqueue size has reached {queue_size}, which is more than the threshold of {self.DR.settings.threshold} allowed by your settings. Please tend to the queue.""")

        # Update storage
        self.DR.storage["active_alert"] = True
        self.DR.storage["last_alerted"] = datetime.now(timezone.utc)
