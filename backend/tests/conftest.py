# -*- coding: utf-8 -*-
"""پیکربندی مشترک آزمون‌ها — ثبت همه مدل‌ها در متادیتا پیش از اجرا."""
from app.core.database import Base, engine  # noqa: F401

# ایمپورت همه ماژول‌های مدل برای کامل‌بودن رجیستری Mapper
from app.modules.identity import models  # noqa
from app.modules.organization import models  # noqa
from app.modules.lookups import router as _lookups  # noqa
from app.modules.forms import models  # noqa
from app.modules.engine import models  # noqa
from app.modules.decisions import models  # noqa
from app.modules.calendars import models  # noqa
from app.modules.audit import service  # noqa
from app.modules.attachments import router as _att  # noqa
from app.modules.notifications import service  # noqa

# ثبت شنونده‌های رویداد زنده (SSE فاز ۳)
from app.modules.events import listeners  # noqa

# فاز ۵: مدل‌های API بیرونی + شنونده Webhook
from app.modules.external import models  # noqa
from app.modules.external import webhooks  # noqa
