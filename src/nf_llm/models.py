from sqlalchemy import Column, Integer, String, Float, ForeignKey, Date, DateTime, func, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()

class DimPlayer(Base):
    __tablename__ = 'dim_player'
    
    player_id = Column(Integer, primary_key=True)
    player_name = Column(String, nullable=False)
    player_position_id = Column(String, nullable=False)
    player_team_id = Column(String, nullable=False)
    pos_rank = Column(String)
    rank_ecr = Column(Float)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    # Relationships
    projections = relationship("FProjectionRaw", back_populates="player")
    salaries = relationship("FSalaryRaw", back_populates="player")


class DimSlate(Base):
    __tablename__ = 'dim_slate'
    
    slate_id = Column(Integer, primary_key=True)
    slate_date = Column(Date, nullable=False)
    slate_type = Column(String, nullable=False)  # e.g., 'main', 'showdown', etc.
    site = Column(String, nullable=False)        # e.g., 'draftkings', 'fanduel', etc.
    created_at = Column(DateTime, default=func.now())
    
    # Relationships
    projections = relationship("FProjectionRaw", back_populates="slate")
    salaries = relationship("FSalaryRaw", back_populates="slate")


class FProjectionRaw(Base):
    __tablename__ = 'f_projection_raw'
    
    projection_id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey('dim_player.player_id'), nullable=False)
    slate_id = Column(Integer, ForeignKey('dim_slate.slate_id'), nullable=False)
    projected_points = Column(Float, nullable=False)
    source = Column(String, nullable=False)      # source of the projection
    created_at = Column(DateTime, default=func.now())
    
    # Relationships
    player = relationship("DimPlayer", back_populates="projections")
    slate = relationship("DimSlate", back_populates="projections")


class FSalaryRaw(Base):
    __tablename__ = 'f_salary_raw'
    
    salary_id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey('dim_player.player_id'), nullable=False)
    slate_id = Column(Integer, ForeignKey('dim_slate.slate_id'), nullable=False)
    salary = Column(Float, nullable=False)
    created_at = Column(DateTime, default=func.now())
    
    # Relationships
    player = relationship("DimPlayer", back_populates="salaries")
    slate = relationship("DimSlate", back_populates="salaries")


class Lineup(Base):
    __tablename__ = 'lineup'
    
    lineup_id = Column(Integer, primary_key=True)
    slate_id = Column(Integer, ForeignKey('dim_slate.slate_id'), nullable=False)
    user_id = Column(String, nullable=True)  # Optional user identifier
    lineup_data = Column(JSON, nullable=False)  # Store the lineup as JSON
    total_salary = Column(Float, nullable=False)
    projected_points = Column(Float, nullable=False)
    created_at = Column(DateTime, default=func.now())
    
    # Relationship
    slate = relationship("DimSlate", backref="lineups")
