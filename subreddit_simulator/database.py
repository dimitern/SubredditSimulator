import json

from sqlalchemy import Text, TypeDecorator, create_engine
from sqlalchemy.orm import sessionmaker
from subreddit_simulator.config import CONFIG


class JSONSerialized(TypeDecorator):
    impl = Text

    def process_bind_param(self, value, dialect):
        return json.dumps(value)

    def process_result_value(self, value, dialect):
        return json.loads(value)


engine = create_engine(CONFIG.database_url)
Session = sessionmaker(bind=engine)
db = Session()
