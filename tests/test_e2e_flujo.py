"""T-038 — Prueba E2E: login → generar → editar → validar.

Ejecuta el flujo completo de punta a punta contra la app FastAPI real
(in-memory via TestClient) y la base de datos real (Supabase):

    1. LOGIN            → se firma un JWT de Supabase (ES256) y viaja en el
                          header Authorization: Bearer de TODAS las peticiones,
                          exactamente como lo hace el frontend (lib/api.ts).
    2. SEED VIA API     → config de jornada, docente + disponibilidad, materia,
                          salón, curso y asignaciones, TODO por los endpoints
                          REST (nada de SQL directo).
    3. GENERAR          → POST /horarios/generar ejecuta el motor CSP real y
                          persiste horario + celdas.
    4. EDITAR           → POST /horarios/{id}/editar mueve una celda a otro
                          (día, bloque) libre, y una celda nueva que choca se
                          rechaza con 409 sin guardar nada.
    5. VALIDAR          → POST /horarios/validar reporta el estado final; al
                          borrar una celda del curso aparece
                          `carga_curso_incompleta` y el horario deja de ser
                          válido.

Autenticación: el backend verifica el JWT contra las JWKS de Supabase
(app/auth.py). Para que el test sea autocontenido, se generan claves ES256
locales y se reemplaza el cliente JWKS con monkeypatch — el resto del
pipeline de verificación (firma, issuer, audiencia, expiración) corre real.

NOTA sobre la BD compartida: `generar` programa TODOS los cursos activos de
la BD (catálogos compartidos entre usuarios), no solo los del test. Por eso:
  - La config del test replica la jornada estándar (L-V 07:00-13:00, 60 min)
    para que los cursos preexistentes (30 h) completen su carga y el estado
    global del horario sea "completo".
  - Las aserciones de celdas se filtran por el curso propio del test.

Aislamiento y limpieza: cada test usa un `sub` (UUID de usuario) distinto,
insertado en `auth.users` (la FK `horarios.usuario_id` lo exige). Al
finalizar se eliminan en cascada (auth.users → horarios → celdas), junto con
los catálogos creados, y se restaura la configuración activa original.

Ejecución:
    pytest tests/test_e2e_flujo.py -v
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from typing import Any

import jwt
import psycopg
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app as fastapi_app

# ---------------------------------------------------------------------------
# JWT de Supabase firmado localmente (ES256) + JWKS mockeado
# ---------------------------------------------------------------------------

_ISSUER = f"{get_settings().supabase_url_value.rstrip('/')}/auth/v1"


class _JWKSServidorFalso:
    """Simula el cliente JWKS de PyJWT: devuelve la clave pública local."""

    def __init__(self, jwk: dict) -> None:
        self._jwk = jwk

    def get_signing_key_from_jwt(self, token: str) -> Any:
        return self

    @property
    def key(self) -> str:
        from jwt.algorithms import ECAlgorithm

        return ECAlgorithm.from_jwk(self._jwk)


@pytest.fixture(scope="module")
def claves_es256():
    """Par de claves EC P-256 + el JWK público correspondiente."""
    private_key = ec.generate_private_key(ec.SECP256R1())
    from jwt.algorithms import ECAlgorithm

    jwk_public: dict = ECAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    return private_key, jwk_public


@pytest.fixture(scope="module")
def cliente(claves_es256):
    """TestClient con las JWKS interceptadas hacia nuestra clave local."""
    _, jwk_public = claves_es256

    import app.auth as modulo_auth

    original = modulo_auth._get_jwks_client
    modulo_auth._get_jwks_client = lambda: _JWKSServidorFalso(jwk_public)
    try:
        with TestClient(fastapi_app) as client:
            # Petición de calentamiento: levanta el pool de BD y falla
            # ruidosamente si Supabase no está accesible.
            r = client.get("/api/v1/health")
            assert r.status_code == 200, f"Backend sin salud: {r.status_code}"
            yield client
    finally:
        modulo_auth._get_jwks_client = original


def _firmar_token(private_key, sub: str) -> str:
    """Firma un JWT con la forma exacta de los tokens de Supabase Auth."""
    import time as _time

    now = int(_time.time())
    payload = {
        "sub": sub,
        "email": "e2e@test.local",
        "role": "authenticated",
        "aud": "authenticated",
        "iss": _ISSUER,
        "iat": now,
        "exp": now + 3600,
    }
    return jwt.encode(payload, private_key, algorithm="ES256")


@contextmanager
def _conexion_admin():
    """Conexión directa (postgres superuser) para setup/limpieza."""
    conn = psycopg.connect(get_settings().database_url_value)
    try:
        yield conn
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Usuarios de prueba: los `sub` creados se registran aquí para que la
# limpieza (fixture `limpieza`) pueda borrarlos de auth.users (en cascada).
# ---------------------------------------------------------------------------

_SUBS_CREADOS: list[str] = []


@pytest.fixture
def nuevo_usuario(claves_es256):
    """Factory: cada llamada genera un (headers, sub) de usuario nuevo.

    Inserta el usuario en `auth.users` de Supabase porque la FK
    `horarios.usuario_id → auth.users(id)` exige que el `sub` del JWT
    exista como usuario real (el backend nunca crea usuarios).
    """

    def _crear() -> tuple[dict, str]:
        sub = str(uuid.uuid4())
        token = _firmar_token(claves_es256[0], sub=sub)
        try:
            with _conexion_admin() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """INSERT INTO auth.users (id, email, created_at)
                           VALUES (%s, %s, now())
                           ON CONFLICT (id) DO NOTHING""",
                        (sub, f"e2e-{sub[:8]}@test.local"),
                    )
                conn.commit()
        except psycopg.Error as exc:
            pytest.skip(
                f"No se puede crear el usuario de prueba en auth.users: {exc}"
            )
        _SUBS_CREADOS.append(sub)
        return {"Authorization": f"Bearer {token}"}, sub

    return _crear


@pytest.fixture
def auth_header(nuevo_usuario):
    """Header Authorization con un JWT cuyo `sub` es único por test."""
    headers, sub = nuevo_usuario()
    return headers, sub


# ---------------------------------------------------------------------------
# Limpieza: borra todo lo creado por el test
# ---------------------------------------------------------------------------


@pytest.fixture
def limpieza():
    """Registra ids de catálogo creados vía API y borra todo al final.

    Orden del teardown:
      1. `auth.users` de los usuarios de prueba → los horarios y celdas
         caen por ON DELETE CASCADE.
      2. Catálogos registrados (config, docente, materia, salón, curso).
      3. Restaurar la configuración activa que había antes del test.
    """
    creados: dict[str, list[int]] = {
        "configs": [],
        "docentes": [],
        "materias": [],
        "salones": [],
        "cursos": [],
    }

    # La config activa ANTES de que el test cree la suya (setup corre antes
    # del cuerpo del test).
    with _conexion_admin() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM configs WHERE activa = true")
            row = cur.fetchone()
    config_previa = row[0] if row else None

    def registrar(tabla: str, id_: int) -> None:
        creados[tabla].append(id_)

    yield registrar

    with _conexion_admin() as conn:
        with conn.cursor() as cur:
            # 1) Usuarios de prueba (cascada horarios + celdas).
            if _SUBS_CREADOS:
                cur.execute(
                    "DELETE FROM auth.users WHERE id = ANY(%s)",
                    (_SUBS_CREADOS,),
                )
            # 2) Catálogos del test.
            for tabla, ids in creados.items():
                for id_ in ids:
                    cur.execute(f"DELETE FROM {tabla} WHERE id = %s", (id_,))
            # 3) Restaurar la config activa original.
            if config_previa is not None:
                cur.execute(
                    "UPDATE configs SET activa = true WHERE id = %s",
                    (config_previa,),
                )
        conn.commit()
    _SUBS_CREADOS.clear()


# ---------------------------------------------------------------------------
# Seed del flujo vía API REST (como lo haría el usuario en el frontend)
# ---------------------------------------------------------------------------

# Jornada estándar del colegio: L-V 07:00-13:00, bloques de 60 min.
# 6 bloques/día × 5 días = 30 slots — igual que la config activa de la BD,
# para que los cursos preexistentes (30 h) completen su carga.
_DIAS = [1, 2, 3, 4, 5]
_BLOQUES = range(1, 7)  # bloque 1 = 07:00-08:00 … bloque 6 = 12:00-13:00


def _horas_de_bloque(bloque: int) -> tuple[str, str]:
    """(hora_inicio, hora_fin) del bloque n dentro de la jornada 07-13."""
    inicio = 7 + (bloque - 1)
    return (f"{inicio:02d}:00:00", f"{inicio + 1:02d}:00:00")


def _sembrar_datos_minimos(
    client: TestClient, headers: dict, registrar, unico: str
) -> dict[str, int]:
    """Crea config + docente + materia + salón + curso + asignaciones vía API.

    El curso de prueba tiene 2 h semanales y su materia min=max=2, así el
    horario generado debe contener exactamente 2 celdas de ese curso.
    """
    # 1) Config de jornada (misma forma que la estándar del colegio).
    r = client.post(
        "/api/v1/configs",
        json={
            "nombre": f"E2E Cfg {unico}",
            "tipo_jornada": "unica",
            "dias_laborables": _DIAS,
            "hora_inicio": "07:00:00",
            "hora_fin": "13:00:00",
            "minutos_bloque": 60,
            "activa": True,
        },
        headers=headers,
    )
    assert r.status_code == 201, f"config: {r.status_code} {r.text}"
    cfg = r.json()
    registrar("configs", cfg["id"])

    # 2) Docente con carga 2 h.
    r = client.post(
        "/api/v1/docentes",
        json={
            "nombre": "E2E",
            "apellido": f"T038 {unico}",
            "documento": f"T038-{unico}",
            "carga_horaria": 2,
            "activo": True,
        },
        headers=headers,
    )
    assert r.status_code == 201, f"docente: {r.status_code} {r.text}"
    docente = r.json()
    registrar("docentes", docente["id"])

    # 3) Disponibilidad completa L-V 07:00-13:00.
    for dia in _DIAS:
        r = client.post(
            f"/api/v1/docentes/{docente['id']}/disponibilidades",
            json={
                "docente_id": docente["id"],
                "dia": dia,
                "hora_inicio": "07:00:00",
                "hora_fin": "13:00:00",
            },
            headers=headers,
        )
        assert r.status_code == 201, f"disponibilidad {dia}: {r.status_code} {r.text}"

    # 4) Materia de aula con min=max=2 (encuadra con el curso de 2 h).
    r = client.post(
        "/api/v1/materias",
        json={
            "nombre": f"E2E Materia {unico}",
            "categoria": "basica",
            "min_horas": 2,
            "max_horas": 2,
            "requiere_salon": False,
            "tipo_salon_requerido": None,
            "no_ultima_hora": False,
        },
        headers=headers,
    )
    assert r.status_code == 201, f"materia: {r.status_code} {r.text}"
    materia = r.json()
    registrar("materias", materia["id"])

    # 5) Salón tipo aula.
    r = client.post(
        "/api/v1/salones",
        json={
            "nombre": f"E2E Aula {unico}",
            "tipo": "aula",
            "capacidad": 30,
            "activo": True,
        },
        headers=headers,
    )
    assert r.status_code == 201, f"salon: {r.status_code} {r.text}"
    salon = r.json()
    registrar("salones", salon["id"])

    # 6) Curso con 2 horas semanales.
    # NOTA: `nivel` debe ser numérico como string ("6") porque
    # `_load_cursos` ordena con `nivel::int` sobre TODOS los cursos.
    r = client.post(
        "/api/v1/cursos",
        json={
            "nombre": f"E2E Curso {unico}",
            "nivel": "6",
            "horas_semanales": 2,
            "orden": 0,
        },
        headers=headers,
    )
    assert r.status_code == 201, f"curso: {r.status_code} {r.text}"
    curso = r.json()
    registrar("cursos", curso["id"])

    # 7) Asignaciones docente ↔ materia y docente ↔ curso.
    r = client.post(
        "/api/v1/asignaciones/materias",
        json={"docente_id": docente["id"], "materia_id": materia["id"]},
        headers=headers,
    )
    assert r.status_code == 201, f"asig materia: {r.status_code} {r.text}"
    r = client.post(
        "/api/v1/asignaciones/cursos",
        json={"docente_id": docente["id"], "curso_id": curso["id"]},
        headers=headers,
    )
    assert r.status_code == 201, f"asig curso: {r.status_code} {r.text}"

    return {
        "cfg": cfg["id"],
        "docente": docente["id"],
        "materia": materia["id"],
        "salon": salon["id"],
        "curso": curso["id"],
    }


# ---------------------------------------------------------------------------
# TESTS E2E
# ---------------------------------------------------------------------------


class TestE2EFlujoCompleto:
    """Flujo completo: login → seed → generar → editar → validar."""

    def test_login_rechaza_token_invalido(self, cliente):
        """Sin JWT válido no hay acceso: el guardián de la API funciona."""
        r = cliente.get("/api/v1/horarios")
        assert r.status_code == 401

        r = cliente.get(
            "/api/v1/horarios", headers={"Authorization": "Bearer token-falso"}
        )
        assert r.status_code == 401

    def test_login_y_listado_vacio(self, cliente, auth_header, limpieza):
        """Con JWT válido el endpoint responde 200 y el usuario nuevo ve
        cero horarios (aislamiento por usuario)."""
        headers, _sub = auth_header
        r = cliente.get("/api/v1/horarios", headers=headers)
        assert r.status_code == 200
        assert r.json() == []

    def test_flujo_completo_login_generar_editar_validar(
        self, cliente, auth_header, limpieza
    ):
        """E2E completo con el motor CSP real y la BD real."""
        headers, sub = auth_header
        unico = uuid.uuid4().hex[:8]

        # -- 1) SEED vía API ------------------------------------------------
        ids = _sembrar_datos_minimos(cliente, headers, limpieza, unico)
        curso_id = ids["curso"]

        # -- 2) GENERAR horario con el motor CSP ----------------------------
        r = cliente.post(
            "/api/v1/horarios/generar",
            json={"nombre": f"E2E Horario {unico}"},
            headers=headers,
        )
        assert r.status_code == 201, f"generar: {r.status_code} {r.text}"
        generado = r.json()

        horario_id = generado["horario"]["id"]
        todas = generado["celdas"]
        # El solver programa TODOS los cursos activos de la BD; filtramos
        # las celdas del curso propio (2 h + materia min=max=2 → 2 celdas).
        mias = [c for c in todas if c["curso_id"] == curso_id]
        assert len(mias) == 2, f"celdas del curso: {mias}"
        assert generado["estado"] == "completo"
        assert generado["horario"]["usuario_id"] == sub

        # Las celdas propias respetan la jornada L-V 07:00-13:00.
        for c in mias:
            assert c["dia"] in _DIAS
            assert c["hora_inicio"] >= "07:00:00"
            assert c["hora_fin"] <= "13:00:00"

        # -- 3) CONSULTAR el horario guardado --------------------------------
        r = cliente.get(f"/api/v1/horarios/{horario_id}", headers=headers)
        assert r.status_code == 200
        detalle = r.json()
        assert detalle["horario"]["id"] == horario_id
        assert len(detalle["celdas"]) == len(todas)

        # -- 4) EDITAR: mover una celda propia a otro (día, bloque) libre ----
        # NOTA: el solver ubica la celda en CUALQUIER aula válida (no
        # necesariamente el salón creado por el test), así que las
        # exclusiones usan los recursos REALES de la celda movida.
        celda = mias[0]
        ocupados = {
            (c["dia"], c["bloque"])
            for c in todas
            if c["id"] != celda["id"]
            and (
                c["curso_id"] == celda["curso_id"]
                or c["docente_id"] == celda["docente_id"]
                or c["salon_id"] == celda["salon_id"]
            )
        }
        destino = next(
            (d, b) for d in _DIAS for b in _BLOQUES if (d, b) not in ocupados
        )
        dia_destino, bloque_destino = destino
        hora_ini, hora_fin = _horas_de_bloque(bloque_destino)

        r = cliente.post(
            f"/api/v1/horarios/{horario_id}/editar",
            json={
                "celda_id": celda["id"],
                "curso_id": curso_id,
                "dia": dia_destino,
                "bloque": bloque_destino,
                "hora_inicio": hora_ini,
                "hora_fin": hora_fin,
            },
            headers=headers,
        )
        assert r.status_code == 200, f"editar: {r.status_code} {r.text}"
        editada = r.json()
        assert editada["valido"] is True
        assert editada["celda"]["dia"] == dia_destino
        assert editada["celda"]["bloque"] == bloque_destino
        # Mover una celda dentro de un horario completo lo mantiene completo.
        assert editada["estado"] == "completo"

        # -- 5) EDITAR con choque → 409 --------------------------------------
        # Celda nueva con el MISMO salón, docente y (día, bloque) que la
        # celda movida: choque garantizado que debe rechazarse sin guardar.
        r = cliente.post(
            f"/api/v1/horarios/{horario_id}/editar",
            json={
                "curso_id": celda["curso_id"],
                "materia_id": celda["materia_id"],
                "docente_id": celda["docente_id"],
                "salon_id": celda["salon_id"],
                "dia": dia_destino,
                "bloque": bloque_destino,
                "hora_inicio": hora_ini,
                "hora_fin": hora_fin,
            },
            headers=headers,
        )
        assert r.status_code == 409, f"choque esperado: {r.status_code} {r.text}"
        detalle_error = r.json()["detail"]
        assert "violaciones" in detalle_error or "mensaje" in str(detalle_error)

        # El horario sigue intacto tras el rechazo.
        r = cliente.get(f"/api/v1/horarios/{horario_id}", headers=headers)
        assert len(r.json()["celdas"]) == len(todas)

        # -- 6) VALIDAR el horario final --------------------------------------
        r = cliente.post(
            "/api/v1/horarios/validar",
            json={"horario_id": horario_id},
            headers=headers,
        )
        assert r.status_code == 200, f"validar: {r.status_code} {r.text}"
        validacion = r.json()
        assert validacion["valido"] is True
        assert validacion["violaciones"] == []

        # -- 7) BORRAR una celda → el horario deja de ser válido --------------
        celda_borrar = (
            mias[1]["id"] if mias[1]["id"] != celda["id"] else celda["id"]
        )
        r = cliente.delete(
            f"/api/v1/horarios/{horario_id}/celdas/{celda_borrar}",
            headers=headers,
        )
        assert r.status_code == 200, f"borrar: {r.status_code} {r.text}"
        assert r.json()["eliminada"] is True

        # Sin una de sus 2 celdas, la carga del curso queda incompleta.
        r = cliente.post(
            "/api/v1/horarios/validar",
            json={"horario_id": horario_id},
            headers=headers,
        )
        assert r.status_code == 200
        validacion = r.json()
        assert validacion["valido"] is False
        assert any(
            v["tipo"] == "carga_curso_incompleta"
            for v in validacion["violaciones"]
        )


class TestE2EAislamiento:
    """El usuario B no ve ni toca los horarios del usuario A."""

    def test_usuario_b_no_ve_horarios_de_a(
        self, cliente, nuevo_usuario, limpieza
    ):
        headers_a, _sub_a = nuevo_usuario()
        headers_b, _sub_b = nuevo_usuario()
        unico = uuid.uuid4().hex[:8]

        # A prepara sus datos y genera un horario.
        ids = _sembrar_datos_minimos(cliente, headers_a, limpieza, unico)
        r = cliente.post(
            "/api/v1/horarios/generar",
            json={"nombre": f"E2E A {unico}"},
            headers=headers_a,
        )
        assert r.status_code == 201, f"generar A: {r.status_code} {r.text}"
        horario_a = r.json()["horario"]["id"]

        # B lista sus horarios: no ve el de A.
        r = cliente.get("/api/v1/horarios", headers=headers_b)
        assert r.status_code == 200
        assert horario_a not in [h["id"] for h in r.json()]

        # B no puede consultar el horario de A (404 por ownership).
        r = cliente.get(f"/api/v1/horarios/{horario_a}", headers=headers_b)
        assert r.status_code == 404

        # B no puede editar en el horario de A.
        r = cliente.post(
            f"/api/v1/horarios/{horario_a}/editar",
            json={"curso_id": ids["curso"], "dia": 1, "bloque": 1},
            headers=headers_b,
        )
        assert r.status_code == 404

        # B no puede validar el horario de A.
        r = cliente.post(
            "/api/v1/horarios/validar",
            json={"horario_id": horario_a},
            headers=headers_b,
        )
        assert r.status_code == 404
