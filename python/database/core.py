from python.database.base import SessionLocal, engine
from python.database.maintenance import init_db, run_db_maintenance
from python.database.models import (
    AppSetting,
    MasterAuditLog,
    MasterLine,
    MasterLineMonitoringMap,
    MasterMachine,
    MasterMachineId,
    MasterMachineType,
    MasterProblem,
    MasterSupportArea,
    MasterSupportAreaMap,
    ProblemClass,
    ProblemMatch,
    Ticket,
    TicketTakeoverLog,
    User,
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
