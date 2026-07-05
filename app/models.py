from sqlalchemy import Column, Float, Index, Integer, String, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, nullable=False, unique=True, index=True)
    hashed_password = Column(String, nullable=False)
    role = Column(String, nullable=False, default="rep")  # admin / manager / rep
    full_name = Column(String, nullable=False, default="")
    created_at = Column(String, nullable=False)
    is_active = Column(Integer, nullable=False, default=1)  # 1=active, 0=inactive

    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token = Column(String, nullable=False, unique=True, index=True)
    created_at = Column(String, nullable=False)
    revoked_at = Column(String)  # NULL = still valid

    user = relationship("User", back_populates="refresh_tokens")


class Account(Base):
    """A company / organisation that contacts belong to (B2B layer)."""
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    domain = Column(String)
    industry = Column(String)
    website = Column(String)
    phone = Column(String)
    address = Column(String)
    notes = Column(String, nullable=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    created_at = Column(String, nullable=False)
    updated_at = Column(String, nullable=False)

    owner = relationship("User", foreign_keys=[owner_id])
    contacts = relationship("Contact", back_populates="account")


class PipelineStage(Base):
    """Customisable deal pipeline stage."""
    __tablename__ = "pipeline_stages"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)
    position = Column(Integer, nullable=False)  # ordering; lowest first
    probability = Column(Integer, nullable=False, default=0)  # 0–100 whole-number percent
    is_default = Column(Integer, nullable=False, default=0)  # 1 = seeded default
    created_at = Column(String, nullable=False)

    deals = relationship("Deal", back_populates="pipeline_stage")


class Contact(Base):
    __tablename__ = "contacts"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True)
    company = Column(String)
    title = Column(String)
    phone = Column(String)
    source = Column(String)  # referral/inbound/outbound/event/other
    lead_score = Column(Float, nullable=False, default=0.0)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="SET NULL"))
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    created_at = Column(String, nullable=False)
    updated_at = Column(String, nullable=False)

    account = relationship("Account", foreign_keys=[account_id], back_populates="contacts")
    owner = relationship("User", foreign_keys=[owner_id])
    deals = relationship("Deal", back_populates="contact")
    activities = relationship("Activity", back_populates="contact")
    tags = relationship("ContactTag", back_populates="contact", cascade="all, delete-orphan")


class Deal(Base):
    __tablename__ = "deals"

    id = Column(Integer, primary_key=True, index=True)
    contact_id = Column(Integer, ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False)
    title = Column(String, nullable=False)
    amount = Column(Integer, nullable=False, default=0)  # cents (full PRD field, kept for M3+)
    currency = Column(String, nullable=False, default="USD")
    stage = Column(String, nullable=False, default="lead")  # legacy string stage (backward compat)
    stage_id = Column(Integer, ForeignKey("pipeline_stages.id", ondelete="SET NULL"))
    value = Column(Float, nullable=False, default=0.0)
    probability = Column(Float, nullable=False, default=0.0)
    expected_close_date = Column(String)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    created_at = Column(String, nullable=False)
    updated_at = Column(String, nullable=False)
    closed_at = Column(String)

    owner = relationship("User", foreign_keys=[owner_id])
    contact = relationship("Contact", back_populates="deals")
    pipeline_stage = relationship("PipelineStage", back_populates="deals")
    stage_transitions = relationship("StageTransition", back_populates="deal", cascade="all, delete-orphan")
    activities = relationship("Activity", back_populates="deal", cascade="all, delete-orphan")
    tags = relationship("DealTag", back_populates="deal", cascade="all, delete-orphan")


class StageTransition(Base):
    __tablename__ = "stage_transitions"

    id = Column(Integer, primary_key=True, index=True)
    deal_id = Column(Integer, ForeignKey("deals.id", ondelete="CASCADE"), nullable=False)
    from_stage = Column(String)
    to_stage = Column(String, nullable=False)
    occurred_at = Column(String, nullable=False)
    note = Column(Text)

    deal = relationship("Deal", back_populates="stage_transitions")


class Activity(Base):
    __tablename__ = "activities"

    id = Column(Integer, primary_key=True, index=True)
    deal_id = Column(Integer, ForeignKey("deals.id", ondelete="CASCADE"))
    contact_id = Column(Integer, ForeignKey("contacts.id", ondelete="SET NULL"))
    type = Column(String, nullable=False)  # call/email/meeting/note
    title = Column(String, nullable=False)
    body = Column(Text)
    due_at = Column(String)
    completed_at = Column(String)
    recurrence_rule = Column(Text)  # JSON RRULE-lite: {"freq": "daily|weekly|monthly", "interval": N}
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    created_at = Column(String, nullable=False)
    updated_at = Column(String, nullable=False)

    owner = relationship("User", foreign_keys=[owner_id])
    deal = relationship("Deal", back_populates="activities")
    contact = relationship("Contact", back_populates="activities")
    reminders = relationship("Reminder", back_populates="activity", cascade="all, delete-orphan")


class Reminder(Base):
    __tablename__ = "reminders"

    id = Column(Integer, primary_key=True, index=True)
    activity_id = Column(Integer, ForeignKey("activities.id", ondelete="CASCADE"), nullable=False)
    remind_at = Column(String, nullable=False)
    dismissed_at = Column(String)
    created_at = Column(String, nullable=False)

    activity = relationship("Activity", back_populates="reminders")


class SavedView(Base):
    __tablename__ = "saved_views"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)
    entity_type = Column(String, nullable=False)  # contacts / deals
    filter_expr = Column(Text, nullable=False)  # JSON-serialised filter AST
    sort_field = Column(String)
    sort_dir = Column(String, nullable=False, default="asc")
    created_at = Column(String, nullable=False)
    updated_at = Column(String, nullable=False)


class Outbox(Base):
    __tablename__ = "outbox"

    id = Column(Integer, primary_key=True, index=True)
    to_address = Column(String, nullable=False)
    subject = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    status = Column(String, nullable=False, default="queued")  # queued/sent/failed
    deal_id = Column(Integer, ForeignKey("deals.id", ondelete="SET NULL"))
    contact_id = Column(Integer, ForeignKey("contacts.id", ondelete="SET NULL"))
    created_at = Column(String, nullable=False)
    sent_at = Column(String)


class EventLog(Base):
    __tablename__ = "event_log"

    id = Column(Integer, primary_key=True, index=True)
    ts = Column(String, nullable=False)
    actor = Column(String, nullable=False)
    verb = Column(String, nullable=False)
    entity = Column(String, nullable=False)
    entity_id = Column(String)
    meta_json = Column(Text)


class Tag(Base):
    __tablename__ = "tags"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)
    created_at = Column(String, nullable=False)

    contacts = relationship("ContactTag", back_populates="tag", cascade="all, delete-orphan")
    deals = relationship("DealTag", back_populates="tag", cascade="all, delete-orphan")


class ContactTag(Base):
    __tablename__ = "contact_tags"

    contact_id = Column(Integer, ForeignKey("contacts.id", ondelete="CASCADE"), primary_key=True)
    tag_id = Column(Integer, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)

    contact = relationship("Contact", back_populates="tags")
    tag = relationship("Tag", back_populates="contacts")


class DealTag(Base):
    __tablename__ = "deal_tags"

    deal_id = Column(Integer, ForeignKey("deals.id", ondelete="CASCADE"), primary_key=True)
    tag_id = Column(Integer, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)

    deal = relationship("Deal", back_populates="tags")
    tag = relationship("Tag", back_populates="deals")


class HistoryEntry(Base):
    """Append-only audit history entry for a single entity mutation.

    Created by trigger wiring (create/update/delete/stage-change/assign/complete).
    Retrieved via GET /history?entity_type=deal&entity_id=N.  Never deleted.
    `entity_id` is a plain INTEGER (no FK) so entries survive entity deletion.
    `meta_json` contains a serialised HistoryEvent (see app/core/history.py).

    Trigger mechanism borrowed from Salesforce Field History Tracking: written
    in the same transaction as the mutation, before db.commit().
    """
    __tablename__ = "history_entries"
    # Composite index supports the frequent WHERE entity_type=? AND entity_id=?
    # ORDER BY occurred_at DESC query used by the timeline retrieval endpoint.
    __table_args__ = (
        Index("ix_history_entity", "entity_type", "entity_id", "occurred_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    entity_type = Column(String, nullable=False)    # "deal" / "contact" / "activity"
    entity_id = Column(Integer, nullable=False)     # no FK — survives entity deletes
    actor_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    kind = Column(String, nullable=False)           # discriminator; see app/core/history.py
    meta_json = Column(Text, nullable=False)        # serialised HistoryEvent
    occurred_at = Column(String, nullable=False)    # ISO-8601 UTC (injected clock, ADR-0006)

    actor = relationship("User", foreign_keys=[actor_id])


class AutomationRule(Base):
    """Automation rule: Trigger → (optional) Conditions → Action.

    trigger_type: "after_save" (fires inline at the mutation site, same transaction)
      or "scheduled" (evaluated by the background poller at the configured interval).

    conditions_json: JSON array of condition objects; NULL or "[]" means no
    conditions and the rule fires unconditionally on any matching trigger event.
    A non-empty string that is not valid JSON is treated as corrupted — the rule
    is skipped rather than fired (fail-closed; see app/services/automations.py).

    schedule_config_json: JSON object for scheduled rules; must be present when
    trigger_type == "scheduled".  Supported shapes:
      {"interval_minutes": N}        — recurring, fires every N minutes
      {"run_once_at": "<ISO-8601>"}  — one-shot, fires once at the given UTC time
    Missing or malformed → rule is skipped (fail-closed).

    last_triggered_at: ISO-8601 UTC string; NULL = never fired.  Set by the
    scheduler after each successful fire via a compare-and-swap UPDATE (see
    run_scheduled_automations in app/services/automations.py) to prevent
    double-fire when multiple Gunicorn workers poll concurrently.

    action_config_json: JSON object with action-specific parameters (keys depend
    on action_type; defined per action handler in future slices).
    """
    __tablename__ = "automation_rules"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    trigger_type = Column(String, nullable=False, default="after_save")  # "after_save" | "scheduled"
    trigger_event = Column(String, nullable=False, default="")  # used by after_save rules
    conditions_json = Column(Text)                     # nullable = unconditional
    action_type = Column(String, nullable=False)       # e.g. "notify"
    action_config_json = Column(Text, nullable=False, default="{}")
    schedule_config_json = Column(Text)                # required for scheduled rules; NULL for after_save
    last_triggered_at = Column(String)                 # ISO-8601 UTC; NULL = never fired
    is_active = Column(Integer, nullable=False, default=1)
    created_at = Column(String, nullable=False)


class Notification(Base):
    """In-app notification for a single recipient user.

    Created by trigger wiring (stage changes, deal assignment, @mentions, overdue tasks).
    Retrieved via the pull API; never pushed via WebSocket.
    `read_at` NULL means unread; set to ISO-8601 UTC string when marked read.
    `payload_json` contains a serialised NotificationEvent (see app/core/notifications.py).
    """
    __tablename__ = "notifications"
    # Composite index supports the frequent WHERE recipient_id=? AND read_at IS NULL
    # query used by unread-count and unread_only list filtering (see ADR-0025).
    __table_args__ = (
        Index("ix_notifications_recipient_read", "recipient_id", "read_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    recipient_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    actor_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    kind = Column(String, nullable=False)
    entity_type = Column(String)   # "deal" / "activity" / "contact" / None
    entity_id = Column(Integer)    # PK of the linked entity; None for system events
    payload_json = Column(Text, nullable=False)
    read_at = Column(String)       # NULL = unread
    created_at = Column(String, nullable=False)

    recipient = relationship("User", foreign_keys=[recipient_id])
    actor = relationship("User", foreign_keys=[actor_id])
