import os

DJANGO_ENV = os.getenv("DJANGO_ENV", "dev")  # default when you just runserver

if DJANGO_ENV == "prod":
    from .prod import *  # noqa
else:
    from .dev import *  # noqa
