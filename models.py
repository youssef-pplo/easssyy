from sqlalchemy import Column, Integer, String
from database import Base

class Student(Base):
    __tablename__ = "students"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    phone = Column(String, unique=True)
    email = Column(String, unique=True)
    parent_phone = Column(String)
    city = Column(String)
    grade = Column(String)
    lang = Column(String)
    password = Column(String)
    student_code = Column(String, unique=True, index=True, nullable=True)
