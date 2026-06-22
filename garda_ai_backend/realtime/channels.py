# Redis pub/sub channel the pipeline replay worker publishes scored events to and
# the backend WebSocket relay subscribes to. Shared constant — keep both in sync.
LIVE_EVENTS_CHANNEL = "garda:events:live"
