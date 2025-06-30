from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from authlib.integrations.flask_client import OAuth
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_talisman import Talisman
from flask_session import Session

db = SQLAlchemy()
migrate = Migrate()
oauth = OAuth()
limiter = Limiter(key_func=get_remote_address)
talisman = Talisman()
sess = Session()