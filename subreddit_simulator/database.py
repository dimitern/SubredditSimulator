import json

import attr
from sqlalchemy import Text, TypeDecorator, create_engine
from sqlalchemy.orm import sessionmaker


class JSONSerialized(TypeDecorator):
    impl = Text

    def process_bind_param(self, value, dialect):
        return json.dumps(value)

    def process_result_value(self, value, dialect):
        return json.loads(value)


@attr.s(auto_attribs=True)
class Engine:
    system: str = "sqlite"
    database: str = ""
    host: str = ""
    port: int = 0
    username: str = ""
    password: str = ""

    @property
    def url(self) -> str:
        prefix = f"{self.system}://"
        auth = f"{self.username}:{self.password}@{self.host}:{self.port}"
        suffix = f"/{self.database}"

        if self.system == "sqlite":
            return prefix + suffix

        return prefix + auth + suffix

    @classmethod
    def from_config(cls, config) -> "Engine":
        return cls(  # type: ignore
            system=config.system,
            username=config.username,
            password=config.password,
            host=config.host,
            port=config.port,
            database=config.database,
        )

    def create(self):
        return create_engine(self.url)

    def create_session(self, engine=None):
        engine = engine or self.create()
        Session = sessionmaker(bind=engine)
        return Session()
