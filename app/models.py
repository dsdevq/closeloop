from sqlalchemy import Column, Float, Integer, String, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


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
    created_at = Column(String, nullable=False)
    updated_at = Column(String, nullable=False)

    deals = relationship("Deal", back_populates="contact")
    activities = relationship("Activity", back_populates="contact")


class Deal(Base):
    __tablename__ = "deals"

    id = Column(Integer, primary_key=True, index=True)
    contact_id = Column(Integer, ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False)
    title = Column(String, nullable=False)
    amount = Column(Integer, nullable=False, default=0)  # cents (full PRD field, kept for M3+)
    currency = Column(String, nullable=False, default="USD")
    stage = Column(String, nullable=False, default="lead")  # lead/qualified/proposal/negotiation/won/lost
    value = Column(Float, nullable=False, default=0.0)
    probability = Column(Float, nullable=False, default=0.0)
    expected_close_date = Column(String)
    created_at = Column(String, nullable=False)
    updated_at = Column(String, nullable=False)
    closed_at = Column(String)

    contact = relationship("Contact", back_populates="deals")
    stage_transitions = relationship("StageTransition", back_populates="deal", cascade="all, delete-orphan")
    activities = relationship("Activity", back_populates="deal", cascade="all, delete-orphan")


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
    created_at = Column(String, nullable=False)
    updated_at = Column(String, nullable=False)

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
