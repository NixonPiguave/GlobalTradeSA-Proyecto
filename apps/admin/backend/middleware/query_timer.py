"""
query_timer.py — Middleware X-Query-Time-Ms

Intercepta cada request, reinicia el acumulador de tiempo de consultas SQL
al inicio del ciclo de vida y añade el encabezado ``X-Query-Time-Ms`` con el
tiempo total acumulado (en milisegundos enteros) a toda respuesta.

Requisito cubierto: 7.6
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from backend.database import reset_query_time, get_query_time_ms


class QueryTimerMiddleware(BaseHTTPMiddleware):
    """
    Middleware que mide el tiempo acumulado de todas las consultas SQL
    ejecutadas durante el ciclo de vida de un request y lo expone como
    el encabezado HTTP ``X-Query-Time-Ms``.

    Funcionamiento:
    1. Al inicio de cada request llama a ``reset_query_time()`` para poner
       el acumulador del hilo a cero.
    2. Delega el procesamiento al siguiente middleware/handler mediante
       ``call_next(request)``.
    3. Una vez obtenida la respuesta, lee el acumulador con
       ``get_query_time_ms()`` y añade el encabezado a la respuesta.

    Nota sobre threading:
        FastAPI ejecuta los route handlers síncronos en un thread pool.
        El acumulador usa ``threading.local``, por lo que cada hilo mantiene
        su propio contador. Dado que todos los endpoints de este proyecto
        usan ``get_connection()`` (psycopg2 síncrono), el tiempo se acumula
        correctamente en el hilo del worker. Para rutas 100 % asíncronas sin
        llamadas síncronas a BD, el valor será 0 (comportamiento aceptable).
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # 1. Reiniciar el acumulador al inicio del request
        reset_query_time()

        # 2. Procesar el request (incluye manejo de excepciones internas)
        response: Response = await call_next(request)

        # 3. Leer el tiempo acumulado y añadirlo como encabezado
        query_time_ms: int = get_query_time_ms()
        response.headers["X-Query-Time-Ms"] = str(query_time_ms)

        return response
