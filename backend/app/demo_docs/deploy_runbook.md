# Production Deploy Runbook

Production deploys happen on Tuesday and Thursday after 6 pm IST. No deploys on Friday, weekends, or public holidays.

Before every deploy, run the full smoke test suite on staging. All smoke tests must pass. Post the staging test link in the release channel.

The on-call engineer approves the deploy. If the on-call engineer is unavailable, the engineering manager approves it.

If error rate rises above 2 percent within 30 minutes of a deploy, roll back immediately using the rollback script and open an incident ticket.

Database migrations must be backward compatible, so the previous app version keeps working during a rollback.
