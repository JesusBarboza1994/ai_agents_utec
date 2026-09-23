"""La ficha del cliente: `data` sin tipar y actualizacion parcial, sin Postgres real."""

from contextlib import contextmanager

from app.db.repositories import customers_repository


class _Cursor:
    """Cursor de mentira: recuerda el SQL ejecutado y devuelve la fila preparada."""

    def __init__(self, fila=None, rowcount=1):
        self.fila, self.rowcount, self.ejecutados = fila, rowcount, []

    def __enter__(self):
        return self

    def __exit__(self, *_excepcion):
        return False

    def execute(self, sql, parametros=None):
        """Guarda la consulta y sus parametros en vez de mandarlos a la base."""
        self.ejecutados.append((" ".join(sql.split()), parametros))

    def fetchone(self):
        """Devuelve la fila preparada para esta prueba."""
        return self.fila


@contextmanager
def _conexion_falsa(cursor):
    """Sustituye `connection()` por un doble que siempre presta el mismo cursor."""
    class _Conn:
        def cursor(self):
            """Presta el cursor de la prueba."""
            return cursor
    yield _Conn()


def _instalar(monkeypatch, cursor):
    """Enchufa el cursor de mentira en el repositorio."""
    monkeypatch.setattr(customers_repository, "connection", lambda: _conexion_falsa(cursor))


def test_get_customer_desestructura_el_jsonb_al_mismo_nivel(monkeypatch):
    """Lo guardado en `data` sale al mismo nivel que los campos tipados, sin la clave `data`."""
    cursor = _Cursor(fila=("cust-1", "51999111222", "Ana", None, "51999111222",
                           {"alergias": "mani", "zona_favorita": "terraza"}))
    _instalar(monkeypatch, cursor)

    ficha = customers_repository.get_customer("51999111222")

    assert ficha == {
        "id": "cust-1", "chat_key": "51999111222", "first_name": "Ana",
        "last_name": None, "phone": "51999111222",
        "alergias": "mani", "zona_favorita": "terraza",
    }
    assert "data" not in ficha


def test_get_customer_prefiere_la_columna_tipada_ante_una_clave_repetida(monkeypatch):
    """`phone` es el numero con el que el canal autentico, no el que alguien dijo en el chat."""
    cursor = _Cursor(fila=("cust-1", "51999111222", "Ana", None, "51999111222",
                           {"phone": "900000000"}))
    _instalar(monkeypatch, cursor)

    assert customers_repository.get_customer("51999111222")["phone"] == "51999111222"


def test_get_customer_devuelve_none_cuando_no_existe(monkeypatch):
    """Un cliente que todavia no existe no es un error."""
    _instalar(monkeypatch, _Cursor(fila=None))

    assert customers_repository.get_customer("desconocido") is None


def test_update_customer_solo_toca_lo_que_recibe_y_fusiona_data(monkeypatch):
    """Los campos omitidos se quedan como estan y `data` se fusiona con lo guardado."""
    cursor = _Cursor()
    _instalar(monkeypatch, cursor)

    assert customers_repository.update_customer(
        "51999111222", first_name="Ana", data={"alergias": "mani"}) is True

    sql, parametros = cursor.ejecutados[0]
    assert sql.startswith("UPDATE customers SET first_name = %s, data = data || %s::jsonb")
    assert "last_name" not in sql and "phone" not in sql
    assert parametros[0] == "Ana"
    assert parametros[1].adapted == {"alergias": "mani"}
    assert parametros[-1] == "51999111222"


def test_update_customer_puede_reemplazar_el_jsonb_entero(monkeypatch):
    """Sustituir el objeto es la unica forma de borrar una clave de `data`."""
    cursor = _Cursor()
    _instalar(monkeypatch, cursor)

    customers_repository.update_customer("51999111222", data={}, reemplazar_data=True)

    sql, _parametros = cursor.ejecutados[0]
    assert "data = %s::jsonb" in sql and "data || " not in sql


def test_update_customer_sin_campos_no_toca_la_base(monkeypatch):
    """Una llamada sin datos no gasta una consulta ni miente diciendo que actualizo."""
    cursor = _Cursor()
    _instalar(monkeypatch, cursor)

    assert customers_repository.update_customer("51999111222") is False
    assert cursor.ejecutados == []


def test_update_customer_avisa_cuando_el_cliente_no_existe(monkeypatch):
    """Sin filas afectadas no hay ficha que actualizar."""
    _instalar(monkeypatch, _Cursor(rowcount=0))

    assert customers_repository.update_customer("desconocido", phone="51999111222") is False
