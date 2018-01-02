import os
import sys

from sqlalchemy import Column
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import create_engine

from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship


Base = declarative_base()


class User(Base):
    __tablename__ = 'user'

    id = Column(Integer, primary_key=True)
    name = Column(String(250), nullable=False)
    email = Column(String(250), nullable=False)
    picture = Column(String(250))


class Brewery(Base):
    __tablename__ = 'brewery'

    id = Column(Integer, primary_key=True)
    name = Column(String(250), nullable=False)
    location = Column(String(250), nullable=False)
    user_id = Column(Integer, ForeignKey('user.id'))
    user = relationship(User)

    @property
    def serialize(self):
            return {
                'name': self.name,
                'location': self.location
            }


class Beer(Base):
    __tablename__ = 'beer'

    id = Column(Integer, primary_key=True)
    name = Column(String(80), nullable=False)
    description = Column(String(500))
    style = Column(String(50))
    ibu = Column(String(3))
    abv = Column(String(4))
    brewery_id = Column(Integer, ForeignKey('brewery.id'))
    user_id = Column(Integer, ForeignKey('user.id'))
    brewery = relationship(Brewery)
    user = relationship(User)

    @property
    def serialize(self):
        return {
            'name': self.name,
            'style': self.style,
            'ibu': self.ibu,
            'abv': self.abv
        }


engine = create_engine('sqlite:///beercatalogwithusers.db')
Base.metadata.create_all(engine)
