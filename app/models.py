from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy import Float

Base = declarative_base()

class Fixture(Base):
    __tablename__ = "fixtures"

    fixture_id = Column(Integer, primary_key=True)
    fixture_date = Column(DateTime)
    venue_id = Column(Integer, ForeignKey("venues.venue_id"))
    venue = relationship("Venue")
    venue_name = Column(String)
    venue_city = Column(String)
    league_id = Column(Integer)
    league_name = Column(String)
    country = Column(String)
    season = Column(Integer)
    round = Column(String)
    status = Column(String)
    home_team_id = Column(Integer)
    home_team = Column(String)
    away_team_id = Column(Integer)
    away_team = Column(String)
    home_goals = Column(Integer)
    away_goals = Column(Integer)

class Venue(Base):
    __tablename__ = "venues"

    venue_id = Column(Integer, primary_key=True)
    name = Column(String)
    address = Column(String)
    city = Column(String)
    country = Column(String)
    capacity = Column(Integer)
    latitude = Column(Float)
    longitude = Column(Float)