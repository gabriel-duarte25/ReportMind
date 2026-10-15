from sqlalchemy.engine import URL

from app.core.config import Settings


def test_mysql_url_preserves_special_password_characters():
    settings = Settings(database_url=None, mysql_password="p@ss:/?#", mysql_database="reportmind")
    url = settings.sqlalchemy_url

    assert isinstance(url, URL)
    assert url.drivername == "mysql+pymysql"
    assert url.password == "p@ss:/?#"
    assert url.database == "reportmind"
