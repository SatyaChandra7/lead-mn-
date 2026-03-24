"""
Seed script to initialize users and setup the default database structure.
"""
from database import SessionLocal, engine, Base
import models
import crud
from schemas import UserCreate

Base.metadata.create_all(bind=engine)
db = SessionLocal()

admin_user = crud.get_user_by_username(db, "admin")
if not admin_user:
    admin = crud.create_user(
        db, UserCreate(
            username="admin", password="password123", role=models.RoleEnum.ADMIN
        )
    )
    print("Admin user created: admin / password123")
else:
    print("Admin user already exists.")

counsellor_user = crud.get_user_by_username(db, "counsellor1")
if not counsellor_user:
    counsellor = crud.create_user(
        db, UserCreate(
            username="counsellor1", password="password123", role=models.RoleEnum.COUNSELLOR
        )
    )
    print("Counsellor created: counsellor1 / password123")

telecaller_user = crud.get_user_by_username(db, "telecaller1")
if not telecaller_user:
    telecaller = crud.create_user(
        db, UserCreate(
            username="telecaller1", password="password123", role=models.RoleEnum.TELECALLER
        )
    )
    print("Telecaller created: telecaller1 / password123")

db.close()
