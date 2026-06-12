# Импортируй сюда все модели, чтобы Alembic autogenerate их видел
# from app.infrastructure.database.models import order, company, user
from app.infrastructure.database.models.ticket import (
    BlockingReasonModel,
    ModerationFieldReportModel,
    ModerationTicketModel,
    ProcessedProductEventModel,
)

__all__ = [
    "BlockingReasonModel",
    "ModerationFieldReportModel",
    "ModerationTicketModel",
    "ProcessedProductEventModel",
]
