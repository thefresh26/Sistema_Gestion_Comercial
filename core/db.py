"""
Conexión a la base de datos de Neon (Postgres) y funciones de acceso a los
datos de cada caso, sus documentos (binarios) y las correcciones manuales.

Todo el acceso a datos del sistema pasa por aquí -- las rutas de Flask
(en app.py) nunca escriben SQL directamente.
"""
from __future__ import annotations

import os
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Json

# La cadena de conexión de Neon se lee de una variable de entorno, nunca
# queda escrita en el código -- así el repositorio puede ser público sin
# exponer ninguna credencial.
DATABASE_URL = os.environ.get("DATABASE_URL", "")

# Base de datos de negocio ya existente (Azure Postgres) -- la que usan
# las subastas, Power BI, etc. Se usa SOLO PARA LEER (nunca se escribe
# nada ahí desde este sistema), para tipos de documento como el
# Certificado de Resultado DD que ya viven en esas tablas.
AZURE_DATABASE_URL = os.environ.get("AZURE_DATABASE_URL", "")


@contextmanager
def get_conn():
    if not DATABASE_URL:
        raise RuntimeError(
            "Falta configurar la variable de entorno DATABASE_URL con la "
            "cadena de conexión de Neon."
        )
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        yield conn


@contextmanager
def get_conn_negocio():
    """Conexión de solo lectura a la base de datos de negocio existente
    (subastas, terceros, etc.), separada de Neon."""
    if not AZURE_DATABASE_URL:
        raise RuntimeError(
            "Falta configurar la variable de entorno AZURE_DATABASE_URL con "
            "la cadena de conexión de la base de datos de negocio."
        )
    with psycopg.connect(AZURE_DATABASE_URL, row_factory=dict_row) as conn:
        yield conn


@contextmanager
def get_conn_negocio_tuplas():
    """Igual que `get_conn_negocio()` pero con filas por posición (tuplas),
    no por nombre de columna -- para reutilizar tal cual el código de los
    scripts originales (acta_subasta.py, informe_subasta.py), que fueron
    escritos con psycopg2 y acceso `row[0]`, `row[1]`, etc. Sigue siendo
    SOLO LECTURA como `get_conn_negocio()`."""
    if not AZURE_DATABASE_URL:
        raise RuntimeError(
            "Falta configurar la variable de entorno AZURE_DATABASE_URL con "
            "la cadena de conexión de la base de datos de negocio."
        )
    with psycopg.connect(AZURE_DATABASE_URL) as conn:
        yield conn


def init_schema() -> None:
    """Crea las tablas si no existen (se puede correr las veces que sea,
    no borra nada)."""
    aqui = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ruta_schema = os.path.join(aqui, "schema.sql")
    with open(ruta_schema, encoding="utf-8") as f:
        sql = f.read()
    with get_conn() as conn:
        conn.execute(sql)
        conn.commit()


# ---------------------------------------------------------------------
# Casos
# ---------------------------------------------------------------------

def buscar_casos(termino: str, limite: int = 25, tipo_salida: str | None = None) -> list[dict]:
    """Busca casos por FMI (coincidencia parcial) o por nombre de
    arrendatario (búsqueda de texto). Si se pasa `tipo_salida`, solo
    devuelve casos que ya tengan al menos un documento generado de ese
    tipo (para que el filtro de la interfaz tenga sentido); los casos
    sin ningún documento generado siempre aparecen, para poder crearlos.

    También trae, para cada caso, el id y nombre del documento generado
    MÁS RECIENTE de `tipo_salida` (si existe) -- así la interfaz puede
    ofrecer un botón "Descargar" directo en el resultado de búsqueda, sin
    tener que entrar a la ficha del caso."""
    termino = (termino or "").strip()
    if not termino:
        return []
    with get_conn() as conn:
        filas = conn.execute(
            """
            SELECT c.fmi, c.territorial, c.tipo_bien, c.direccion, c.arrendatario_nombre,
                   c.id_siglas, c.id_numero, c.id_ciudad, c.estado, c.pendientes,
                   c.actualizado_en, d.id AS documento_id, d.nombre_archivo AS documento_nombre
            FROM casos c
            LEFT JOIN LATERAL (
                SELECT doc.id, doc.nombre_archivo
                FROM documentos doc
                WHERE doc.fmi = c.fmi AND doc.tipo = 'documento_generado'
                  AND (%(tipo_salida)s::text IS NULL OR doc.tipo_salida = %(tipo_salida)s::text)
                ORDER BY doc.subido_en DESC
                LIMIT 1
            ) d ON true
            WHERE (c.fmi ILIKE %(patron)s OR c.arrendatario_nombre ILIKE %(patron)s)
            ORDER BY c.actualizado_en DESC
            LIMIT %(limite)s
            """,
            {"patron": f"%{termino}%", "limite": limite, "tipo_salida": tipo_salida},
        ).fetchall()
        return list(filas)


def obtener_caso(fmi: str) -> dict | None:
    with get_conn() as conn:
        fila = conn.execute(
            "SELECT * FROM casos WHERE fmi = %(fmi)s", {"fmi": fmi}
        ).fetchone()
        return fila


def upsert_caso(fmi: str, datos: dict) -> None:
    """Crea o actualiza los campos automáticos de un caso (los que saca
    la extracción). No toca las correcciones manuales -- esas viven
    aparte y se aplican por encima al momento de generar el Acta."""
    columnas = [
        "territorial", "tipo_bien", "tipo_contrato", "direccion",
        "arrendatario_nombre", "id_siglas", "id_numero", "id_ciudad",
        "estado", "pendientes",
    ]
    datos = {c: datos.get(c) for c in columnas}
    # `pendientes` es una columna JSONB -- si se manda la lista de Python
    # tal cual, psycopg la serializa como arreglo de Postgres ({"a","b"})
    # en vez de JSON válido (["a","b"]), y Postgres rechaza el INSERT con
    # "invalid input syntax for type json" en cuanto la lista no está vacía.
    # Json(...) fuerza la serialización correcta.
    datos["pendientes"] = Json(datos.get("pendientes") or [])
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO casos (fmi, territorial, tipo_bien, tipo_contrato,
                                direccion, arrendatario_nombre, id_siglas,
                                id_numero, id_ciudad, estado, pendientes)
            VALUES (%(fmi)s, %(territorial)s, %(tipo_bien)s, %(tipo_contrato)s,
                    %(direccion)s, %(arrendatario_nombre)s, %(id_siglas)s,
                    %(id_numero)s, %(id_ciudad)s, %(estado)s, %(pendientes)s)
            ON CONFLICT (fmi) DO UPDATE SET
                territorial = EXCLUDED.territorial,
                tipo_bien = EXCLUDED.tipo_bien,
                tipo_contrato = EXCLUDED.tipo_contrato,
                direccion = EXCLUDED.direccion,
                arrendatario_nombre = EXCLUDED.arrendatario_nombre,
                id_siglas = EXCLUDED.id_siglas,
                id_numero = EXCLUDED.id_numero,
                id_ciudad = EXCLUDED.id_ciudad,
                estado = EXCLUDED.estado,
                pendientes = EXCLUDED.pendientes,
                actualizado_en = now()
            """,
            {"fmi": fmi, **datos},
        )
        conn.commit()


# ---------------------------------------------------------------------
# Correcciones manuales
# ---------------------------------------------------------------------

def obtener_correcciones(fmi: str) -> dict[str, str]:
    with get_conn() as conn:
        filas = conn.execute(
            "SELECT campo, valor FROM correcciones_manuales WHERE fmi = %(fmi)s",
            {"fmi": fmi},
        ).fetchall()
        return {f["campo"]: f["valor"] for f in filas}


def guardar_correccion(fmi: str, campo: str, valor: str, nota: str = "", usuario: str = "") -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO correcciones_manuales (fmi, campo, valor, nota, actualizado_por)
            VALUES (%(fmi)s, %(campo)s, %(valor)s, %(nota)s, %(usuario)s)
            ON CONFLICT (fmi, campo) DO UPDATE SET
                valor = EXCLUDED.valor,
                nota = EXCLUDED.nota,
                actualizado_por = EXCLUDED.actualizado_por,
                actualizado_en = now()
            """,
            {"fmi": fmi, "campo": campo, "valor": valor, "nota": nota, "usuario": usuario},
        )
        conn.commit()


def borrar_correccion(fmi: str, campo: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM correcciones_manuales WHERE fmi = %(fmi)s AND campo = %(campo)s",
            {"fmi": fmi, "campo": campo},
        )
        conn.commit()


# ---------------------------------------------------------------------
# Documentos (binarios)
# ---------------------------------------------------------------------

def guardar_documento(fmi: str, tipo: str, nombre_archivo: str, mime_type: str, contenido: bytes,
                       tipo_salida: str | None = None) -> int:
    with get_conn() as conn:
        fila = conn.execute(
            """
            INSERT INTO documentos (fmi, tipo, tipo_salida, nombre_archivo, mime_type, tamano_bytes, contenido)
            VALUES (%(fmi)s, %(tipo)s, %(tipo_salida)s, %(nombre_archivo)s, %(mime_type)s, %(tamano)s, %(contenido)s)
            RETURNING id
            """,
            {
                "fmi": fmi, "tipo": tipo, "tipo_salida": tipo_salida, "nombre_archivo": nombre_archivo,
                "mime_type": mime_type, "tamano": len(contenido), "contenido": contenido,
            },
        ).fetchone()
        conn.commit()
        return fila["id"]


def listar_documentos(fmi: str, tipo: str | None = None) -> list[dict]:
    """Lista documentos SIN el contenido binario (para mostrar en la UI)."""
    with get_conn() as conn:
        if tipo:
            filas = conn.execute(
                """SELECT id, fmi, tipo, tipo_salida, nombre_archivo, mime_type, tamano_bytes, subido_en
                   FROM documentos WHERE fmi = %(fmi)s AND tipo = %(tipo)s
                   ORDER BY subido_en DESC""",
                {"fmi": fmi, "tipo": tipo},
            ).fetchall()
        else:
            filas = conn.execute(
                """SELECT id, fmi, tipo, tipo_salida, nombre_archivo, mime_type, tamano_bytes, subido_en
                   FROM documentos WHERE fmi = %(fmi)s ORDER BY tipo, subido_en DESC""",
                {"fmi": fmi},
            ).fetchall()
        return list(filas)


def obtener_documento(doc_id: int) -> dict | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM documentos WHERE id = %(id)s", {"id": doc_id}
        ).fetchone()


def obtener_ultimo_documento(fmi: str, tipo: str) -> dict | None:
    with get_conn() as conn:
        return conn.execute(
            """SELECT * FROM documentos WHERE fmi = %(fmi)s AND tipo = %(tipo)s
               ORDER BY subido_en DESC LIMIT 1""",
            {"fmi": fmi, "tipo": tipo},
        ).fetchone()


def obtener_documento_generado(fmi: str, tipo_salida: str) -> dict | None:
    """El documento_generado más reciente de un FMI para un tipo_salida
    puntual (ej. 'certificado_dd') -- a diferencia de obtener_ultimo_documento,
    que solo filtra por la columna `tipo` (documento_generado vs un tipo de
    documento fuente), esta también filtra por tipo_salida, que es lo que
    necesita el flujo de 'generar y descargar de una vez' desde la búsqueda."""
    with get_conn() as conn:
        return conn.execute(
            """SELECT * FROM documentos WHERE fmi = %(fmi)s AND tipo = 'documento_generado'
               AND tipo_salida = %(tipo_salida)s
               ORDER BY subido_en DESC LIMIT 1""",
            {"fmi": fmi, "tipo_salida": tipo_salida},
        ).fetchone()


# ---------------------------------------------------------------------
# Contadores / consecutivos
# ---------------------------------------------------------------------

def siguiente_consecutivo(clave: str, inicial: int = 1) -> int:
    """Devuelve el próximo número de un contador (ej. 'alcance') y lo
    avanza en la misma operación -- reemplaza el archivo de texto local
    que usaban los scripts originales, para que el consecutivo no
    dependa de en qué computador se genera el documento."""
    with get_conn() as conn:
        fila = conn.execute(
            """
            INSERT INTO contadores (clave, valor) VALUES (%(clave)s, %(inicial)s)
            ON CONFLICT (clave) DO UPDATE SET valor = contadores.valor + 1
            RETURNING valor
            """,
            {"clave": clave, "inicial": inicial},
        ).fetchone()
        conn.commit()
        return fila["valor"]


def registrar_generacion(fmi: str, documento_id: int, usuario: str = "") -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO generaciones (fmi, documento_id, generado_por)
               VALUES (%(fmi)s, %(documento_id)s, %(usuario)s)""",
            {"fmi": fmi, "documento_id": documento_id, "usuario": usuario},
        )
        conn.commit()
