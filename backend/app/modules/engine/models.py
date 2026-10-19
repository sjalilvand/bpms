# -*- coding: utf-8 -*-
"""مدل‌های فرایند و اجرا: تعریف، نسخه، نمونه اجرایی، وظیفه، رویداد، خطا."""
from datetime import datetime

from sqlalchemy import String, ForeignKey, Text, DateTime, JSON, Integer, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.modules.identity.models import utcnow


class ProcessDefinition(Base):
    __tablename__ = "process_definitions"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, default="")
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    versions: Mapped[list["ProcessVersion"]] = relationship(back_populates="definition", lazy="selectin", order_by="ProcessVersion.version.desc()")

    @property
    def latest_published(self) -> "ProcessVersion | None":
        for v in self.versions:
            if v.status == "published":
                return v
        return None


class ProcessVersion(Base):
    """نسخه ثابت مدل اجرایی — هر نمونه به نسخه مشخص متصل می‌ماند (AC-14)."""
    __tablename__ = "process_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    definition_id: Mapped[int] = mapped_column(ForeignKey("process_definitions.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    bpmn_xml: Mapped[str] = mapped_column(Text)
    main_process_id: Mapped[str] = mapped_column(String(120))
    config_json: Mapped[dict] = mapped_column(JSON, default=dict)
    # config_json: {"bindings": {"Task_x": {"formDefinitionId": n, "results": [...],
    #              "assigneeType": "user|role|field|self", "assigneeValue": ..., "dueHours": n}}}
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)  # draft | published | archived
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    published_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    change_note: Mapped[str | None] = mapped_column(String(300), default="")

    definition: Mapped[ProcessDefinition] = relationship(back_populates="versions")


class ProcessInstance(Base):
    __tablename__ = "process_instances"

    id: Mapped[int] = mapped_column(primary_key=True)
    definition_id: Mapped[int] = mapped_column(ForeignKey("process_definitions.id", ondelete="RESTRICT"), index=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("process_versions.id", ondelete="RESTRICT"), index=True)
    title: Mapped[str] = mapped_column(String(300), default="")
    business_key: Mapped[str | None] = mapped_column(String(120), index=True)
    status: Mapped[str] = mapped_column(String(20), default="running", index=True)  # running|completed|cancelled|error
    started_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    engine_state: Mapped[str | None] = mapped_column(Text)  # وضعیت پایدار موتور (serialized)

    version: Mapped[ProcessVersion] = relationship(lazy="selectin")


class EngineTask(Base):
    """وظایف کاریامان با موتور — صف کارتابل با کنترل رقابت (AC-12)."""
    __tablename__ = "engine_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    instance_id: Mapped[int] = mapped_column(ForeignKey("process_instances.id", ondelete="CASCADE"), index=True)
    task_uuid: Mapped[str] = mapped_column(String(64), index=True)      # شناسه موتور
    spec_id: Mapped[str] = mapped_column(String(160))                    # شناسه فنی پایدار عنصر
    name: Mapped[str] = mapped_column(String(300), default="")
    task_type: Mapped[str] = mapped_column(String(40), default="user")
    status: Mapped[str] = mapped_column(String(20), default="ready", index=True)  # ready|claimed|completed|cancelled|error
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    candidate_role: Mapped[str | None] = mapped_column(String(60), index=True)   # گروه نامزد (کد نقش)
    claimed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # SLA — برای اعلام هشدار/فرازدگی یک‌باره توسط Worker (فاز ۳)
    sla_warned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sla_escalated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    form_version_id: Mapped[int | None] = mapped_column(ForeignKey("form_versions.id", ondelete="SET NULL"))
    data_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result: Mapped[str | None] = mapped_column(String(60))
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    __table_args__ = (Index("ix_engine_tasks_instance_status", "instance_id", "status"),)


class InstanceEvent(Base):
    """تاریخچه اجرا — شروع/پایان، ایجاد/تخصیص/تکمیل وظیفه، تصمیم‌ها، خطاها و مداخله مدیر."""
    __tablename__ = "instance_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    instance_id: Mapped[int] = mapped_column(ForeignKey("process_instances.id", ondelete="CASCADE"), index=True)
    task_id: Mapped[int | None] = mapped_column(Integer, index=True)
    spec_id: Mapped[str | None] = mapped_column(String(160))
    task_name: Mapped[str | None] = mapped_column(String(300))
    event_type: Mapped[str] = mapped_column(String(40), index=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    comment: Mapped[str | None] = mapped_column(Text)
    detail_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class Incident(Base):
    """مورد قابل رسیدگی برای خطای اجرا (سند §۹.۱ و AC-15)."""
    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(primary_key=True)
    instance_id: Mapped[int] = mapped_column(ForeignKey("process_instances.id", ondelete="CASCADE"), index=True)
    task_uuid: Mapped[str | None] = mapped_column(String(64))
    spec_id: Mapped[str | None] = mapped_column(String(160))
    message: Mapped[str] = mapped_column(Text)
    detail_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
