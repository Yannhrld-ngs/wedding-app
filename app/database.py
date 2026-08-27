"""
Tools for interacting with SQL database. 
Create table, Insert into table ...
"""

from __future__ import annotations

import datetime
import typing
from typing import Any, Generic, Optional, Type, TypeVar
from dataclasses import asdict
import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, Float, Integer, String 
from sqlalchemy import Column, MetaData, Table, select, text
from sqlalchemy.engine import Engine

import logging
logger = logging.getLogger(__name__)


# # # Map python type hinting with SQL Alchemy type.
_TYPE_MAP: dict[type, Any] = {
    str: String,
    int: Integer,
    float: Float,
    bool: Boolean,
    datetime.datetime: DateTime,
    datetime.date: sa.Date,
}

T = TypeVar("T")

# # # SQL object
class SqlRepository(Generic[T]):

    def __init__(self, engine: Engine, required_tables = ["guests","organizers"]) -> None:
        self.engine = engine
        self.metadata = MetaData(schema="public")
        self.required_tables = required_tables

    def __check__():
        '''
        Useless now but I keep it here, for future work.
        '''
        with self.engine.connect() as conn:
            result = conn.execute(text("SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname = 'public';"))
            all_tables = [row[0] for row in result]
            required_tables = []
            missing_tables = [table for table in required_tables if table not in all_tables]
            if missing_tables:
                raise FileNotFoundError(f"Les tables suivantes sont manquantes dans la base de données {SQL_DATABASE}: {', '.join(missing_tables)}")

    @staticmethod
    def _sa_type_for(py_type: Any) -> Any:
        """
            Map a Python type annotation to a SQLAlchemy column type instance.
        """
        origin = typing.get_origin(py_type)
        if origin is typing.Union:
            args = [a for a in typing.get_args(py_type) if a is not type(None)]
            if len(args) == 1:
                py_type = args[0]
        return _TYPE_MAP.get(py_type, String)()

    def create(self, obj:T, table_name:str, primary_key:str) -> Table:
        """
            Create the table from the dataclass fields (no-op if it already exists).
        """
        # Construct columns, and defining primary key
        attributes_types = typing.get_type_hints(obj)
        cols: list[Column] = []
        for attr in attributes_types.keys():
            py_type = attributes_types[attr]
            cols.append( 
                Column(attr, self._sa_type_for(py_type), primary_key=(attr == primary_key))
                )
        table = Table(table_name, self.metadata, *cols, extend_existing=True)
        self.metadata.create_all(self.engine, tables=[table])
        return table
    
    def insert(self, obj: T, table:Table) -> bool:
        """
            Insert a dataclass instance as a row.
        """
        try:
            with self.engine.begin() as conn:
                conn.execute(table.insert().values(** asdict(obj) ))
            return 
        except Exception as e:
            logger.error(f"Erreur lors de la connexion à la base de données {self.engine.url.database} : {e}")
            return False


    def update(self, obj:T, table:Table, primary_key) -> int:
        """
            Update the row matching primary_key with obj's current values
        """
        values = asdict(obj)
        pk_value = values.pop(primary_key)

        try:
            with self.engine.begin() as conn:
                result = conn.execute(
                    table.update().where(table.c[primary_key] == pk_value).values(**values)
                )
        except Exception as e:
            logger.error(f"Erreur lors de la connexion à la base de données {self.engine.url.database} : {e}")
            return 0
        return result.rowcount

    def delete(self, obj:T, table:Table, primary_key) -> int:
        """
            Delete the row matching primary_key.
        """
        pk_value = getattr(obj, primary_key)

        try:
            with self.engine.begin() as conn:
                result = conn.execute(table.delete().where(table.c[primary_key] == pk_value))
        except Exception as e:
            logger.error(f"Erreur lors de la connexion à la base de données {self.engine.url.database} : {e}")
            return 0
        return result.rowcount

    def load(self, obj:T, table_name:str) -> list[T]:
        """Load all rows as instances of the dataclass."""
        with self.engine.connect() as conn:
            rows = conn.execute( text(f"SELECT * FROM {table_name};") ).mappings()
            field_names = tuple(typing.get_type_hints(obj))
            return [ obj(**{k: v for k, v in row.items() if k in field_names}) for row in rows ]


if __name__ == "__main__":
    from models import Invite, Organisateur
    from config import engine
    db = SqlRepository(engine)
    #inv =  Invite(prenom="x", nom="y", categorie="ax", token="xyz", qr_uuid="tes")
    #org =  Invite(prenom="org", nom="irg", mail="xzz", contact="00", categorie="ax", token="xyz", qr_uuid="tes")
    #data = db.load(Invite, table_name="guests") 

    #table = db.create(Invite, table_name="guests", primary_key="token")
    table = db.create(Organisateur, table_name="organizers", primary_key="mail")
    #check = db.insert(inv, table)
    #db.update(inv, table, primary_key="token") 
