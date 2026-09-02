"""T-017 a T-020 · Motor CSP — Backtracking con heurísticas MRV/Degree.

Modela la construcción de un horario como un problema de satisfacción de
restricciones (CSP):

  VARIABLES
    Cada bloque que hay que ubicar: (curso, materia) → necesita `n` celdas.

  DOMINIOS
    Cada celda es un 4-tupla (docente, salón, día, bloque). Se filtran:
      · docente con esa materia designada y asignado a ese curso,
      · disponibilidad del docente que cubra el bloque,
      · salón acorde al tipo requerido por la materia (aula/laboratorio/sala),
      · política "no última hora".
    El dominio se ALEATORIZA (shuffle) al construirse para romper el orden
    secuencial día/bloque y evitar horarios repetitivos y lineales.

  RESTRICCIONES DURAS (Hard) — solo choques por recurso en cada (dia, bloque):
      (1) un profesor NO puede estar en dos cursos al mismo tiempo;
      (2) un salón NO puede ser usado por dos cursos al mismo tiempo;
      (3) un curso NO puede tener dos clases en la misma hora;
      (4) las celdas `bloqueada = true` son fijas: se ocupan de antemano y el
          solver nunca las mueve ni las repite.

  RESTRICCIONES SUAVES (Soft / penalizaciones) — se ordenan pero nunca bloquean:
      · Carga académica del docente (preferible bloques ≤
        floor(carga_horaria*60/bloque); excederla solo penaliza el orden);
      · Reparto de la materia (≤ 2 bloques/día en el curso, §4.3) penalizado;
      · Variabilidad semanal: la misma materia a la MISMA hora (bloque) en
        más de 2 días consecutivos queda penalizada — favorece una
        distribución equilibrada a lo largo de la semana;
      · Reparto uniforme semanal (días con menos bloques de la materia);
      · Anti-contigüidad: bloques del mismo día adyacentes a otra clase de la
        misma materia quedan penalizados (evita clases pegadas).

  ESTOCASTICIDAD (perturbación controlada)
    Para que dos generaciones del mismo problema no produzcan el mismo
    horario, las heurísticas incorporan desempates aleatorios:
      · MRV/Degree/Balance: entre variables empatadas se elige al azar;
      · LCV: el orden de valores termina con un jitter aleatorio (los valores
        con idéntica penalización quedan en orden aleatorio, no por día);
      · Greedy de relleno: mismo jitter en su orden de valores.
    Todo esto NO afecta las restricciones duras: el resultado siempre está
    libre de choques; solo varía cuál de las muchas soluciones válidas se
    entrega. `solve(problem, semilla=...)` permite fijar la semilla para
    reproducibilidad (tests).

  ALGORITMO
    Backtracking con _forward checking_. Heurísticas:
      · MRV   — primero la variable con menos valores aún posibles;
      · Degree — desempate por la que más interacciona con otras variables;
      · LCV   — valor que deja más espacio libre (dia,bloque) menos demandado.

  SALIDA
    Si se asigna todo → estado `completo`. Si no (o límite de nodos), se
    devuelve la mejor asignación parcial + reporte estructurado de conflictos.
"""

from __future__ import annotations

import math
import random
import time
from collections import defaultdict
from typing import Any

from app.scheduler.models import Curso, Jornada, Materia, Problem, ScheduleResult
from app.scheduler.intensity import allocate_intensities

# Límites de seguridad para no colgar el servidor.
MAX_NODES = 200_000
# Tiempo interno máximo de búsqueda (segundos). Superado, se devuelve la mejor
# solución parcial alcanzada (T-027: el endpoint no debe bloquear el hilo).
TIME_LIMIT_SEG = 30
# T-029 · Fallback greedy. Si el backtracking no termina en este tiempo (seg),
# se abandona y se rellenan las celdas restantes con un algoritmo greedy que
# respeta SOLO las restricciones duras (docente, salón y curso a la vez),
# garantizando una grilla sin conflictos duros.
GREEDY_TRIGGER_SEG = 5
# Cada cuántos nodos verificamos el reloj (evita el coste de time() por nodo).
TIME_CHECK_CADA = 256

# T-029 · Reintentos del completado greedy. El llenado es un matching
# perfecto (cada curso necesita exactamente tantos bloques como slots
# libres tiene); con el jitter aleatorio un intento puede acorralar a la
# última variable (~35% de las veces en el peor caso). Reiniciar con otra
# aleatorización es barato (microsegundos) y la tasa de fallo cae
# exponencialmente: 0.35^8 ≈ 0.02%.
GREEDY_REINTENTOS = 8

# Reinicios del backtracking (randomized restarts). La perturbación
# estocástica da alta varianza: algunos órdenes resuelven en <1s y otros se
# pierden en backtracking exponencial. Reiniciar con otra semilla es la
# técnica estándar: cada intento tiene una ventana corta (las semillas
# buenas terminan rápido; las malas nunca convergen) y se prueban varias.
BACKTRACK_REINTENTOS = 6
BACKTRACK_VENTANA_SEG = 3

# Orden institucional §4.3: una materia no ocupa más de 2 bloques por día
# en un mismo curso. Es una RESTRICCIÓN SUAVE: se penaliza en el orden de
# valores, pero no bloquea (T-028: soltar lo soft para llenar la grilla).
MAX_BLOQUES_MATERIA_DIA = 2

# Variabilidad semanal: techo de días CONSECUTIVOS en los que la misma
# materia puede ocupar el mismo bloque horario (soft; p. ej. Matemáticas a
# primera hora Lun-Mar-Mie seguidos queda penalizado a partir del 3er día).
MAX_DIAS_MISMA_HORA = 2


class NodeLimitReached(Exception):
    """Se alcanzó el límite de nodos explorados (búsqueda truncada)."""


class TimeLimitReached(Exception):
    """Se alcanzó el límite de tiempo interno (búsqueda truncada)."""


class _Var:
    """Una celda por colocar: se instancia por cada bloque de (curso, materia)."""

    __slots__ = (
        "vid",
        "curso_id",
        "materia_id",
        "base_domain",
        "docentes",
        "salones",
        "asignado",
    )

    def __init__(
        self,
        vid: int,
        curso_id: int,
        materia_id: int,
        base_domain: list[tuple[int, int, int, int]],
    ) -> None:
        self.vid = vid
        self.curso_id = curso_id
        self.materia_id = materia_id
        self.base_domain = base_domain
        self.docentes = {d for d, _s, _da, _b in base_domain}
        self.salones = {s for _d, s, _da, _b in base_domain}
        self.asignado: tuple[int, int, int, int] | None = None


class _Solver:
    """Estado de la búsqueda: ocupación por recurso + asignaciones parciales."""

    def __init__(
        self,
        problem: Problem,
        plan: dict[int, dict[int, int]],
        cur_nombre: dict[int, str],
        mat_nombre: dict[int, str],
        semilla: int | None = None,
    ) -> None:
        self.problem = problem
        self.mb = problem.minutos_bloque
        self.cur_nombre = cur_nombre
        self.mat_nombre = mat_nombre
        # RNG propio: aleatoriedad de dominios/desempates. Con `semilla`
        # fija la búsqueda es reproducible (tests); sin ella, cada
        # generación produce un horario distinto.
        self.rng = random.Random(semilla)

        # Capacidad en bloques por docente (carga horaria en horas → bloques).
        self.capacidad_bloques: dict[int, int] = {
            d.id: d.carga_horaria * 60 // self.mb for d in problem.docentes
        }

        # Ocupación por recurso en (dia, bloque).
        self.occ_curso: dict[tuple[int, int, int], bool] = {}
        self.occ_docente: dict[tuple[int, int, int], bool] = {}
        self.occ_salon: dict[tuple[int, int, int], bool] = {}
        self.bloques_usados: dict[int, int] = defaultdict(int)
        # Celdas ya asignadas por curso: para repartir el llenado (ver MRV).
        self.asig_curso: dict[int, int] = defaultdict(int)
        # Celdas ya asignadas por (dia, bloque): para llenar primero los slots con
        # salones libres (maximiza el uso de la infraestructura disponible).
        self.occ_slot: dict[tuple[int, int], int] = defaultdict(int)

        # Restricción §4.3: bloques por (curso, materia) en cada día.
        #   self.mat_dia_cuenta[(curso_id, materia_id, dia)] → bloques del día
        self.mat_dia_cuenta: dict[tuple[int, int, int], int] = defaultdict(int)
        # Ocupación puntual por (curso, materia, dia, bloque) para detectar
        # bloques contiguos de la misma asignatura (preferencia anti-pegado).
        self.occ_mismo_materia: dict[tuple[int, int, int, int], bool] = {}
        # Bloques por (docente, dia): balance diario del docente. En los
        # problemas reales cada docente cubre ~28 de sus 30 slots; si todas
        # sus clases se apilan a un mismo día, el matching se acorrala y el
        # backtracking entra en dead-ends exponenciales.
        self.docente_dia: dict[tuple[int, int], int] = defaultdict(int)

        # Celdas fijas: se ocupan de antemano (inmutables para el solver).
        self.fijas: list[dict] = []
        for f in problem.celdas_fijas:
            self.lock_celda(f)

        self.vars: list[_Var] = []
        self._construir_variables(plan)

        # Grado estático por variable (Degree heuristic).
        self.grado = self._calcular_grados()

        # Demanda por (dia, bloque): cuántas variables quieren ese bloque.
        self._demanda = self._calcular_demanda()

        self.nodos = 0
        self.best = {v.vid: v.asignado for v in self.vars if v.asignado}
        self.best_depth = 0
        self.best_soft = self._soft_score() if self.vars else 0
        self._t0 = time.time()
        self._deadline = time.time() + TIME_LIMIT_SEG

    # ------------------------------------------------------------------
    # Construcción
    # ------------------------------------------------------------------

    def lock_celda(self, f: Any) -> None:
        """Registra una celda fija en la ocupación (consume el bloque)."""
        self.occ_curso[(f.curso_id, f.dia, f.bloque)] = True
        self.occ_docente[(f.docente_id, f.dia, f.bloque)] = True
        self.occ_salon[(f.salon_id, f.dia, f.bloque)] = True
        self.bloques_usados[f.docente_id] += 1
        self.mat_dia_cuenta[(f.curso_id, f.materia_id, f.dia)] += 1
        self.docente_dia[(f.docente_id, f.dia)] += 1
        # También ocupa el mapa (curso, materia, dia, bloque): las celdas
        # fijas deben contar para anti-contigüidad y variabilidad semanal.
        self.occ_mismo_materia[(f.curso_id, f.materia_id, f.dia, f.bloque)] = True
        self.fijas.append(
            {
                "curso_id": f.curso_id,
                "materia_id": f.materia_id,
                "docente_id": f.docente_id,
                "salon_id": f.salon_id,
                "dia": f.dia,
                "bloque": f.bloque,
                "hora_inicio": f.hora_inicio,
                "hora_fin": f.hora_fin,
                "bloqueada": True,
            }
        )

    def _constructor_dominio(
        self, curso: Curso, materia_id: int
    ) -> list[tuple[int, int, int, int]]:
        """Dominio inicial de una celda de (curso, materia): (doc, salón, dia, bloq)."""
        materia = self.problem.materias[materia_id]
        dominio: list[tuple[int, int, int, int]] = []

        # Salones compatibles con el tipo que pide la materia.
        if materia.requiere_salon:
            salones = [s for s in self.problem.salones if s.tipo == materia.tipo_salon_requerido]
        else:
            salones = [s for s in self.problem.salones if s.tipo == "aula"]

        # 1) Aleatorizar dominios: barajar la lista de slots (días y bloques)
        # antes de iniciar el bucle de asignación para romper linealidad.
        slots = list(self.problem.jornada.slots)
        self.rng.shuffle(slots)
        for doc in self.problem.docentes:
            # El docente debe dictar esta materia Y estar asignado a este curso.
            if materia_id not in doc.materias or curso.id not in doc.cursos:
                continue
            for sl in slots:
                if materia.no_ultima_hora and sl.ultimo:
                    continue
                if not doc.cubre(sl):
                    continue
                for s in salones:
                    dominio.append((doc.id, s.id, sl.dia, sl.bloque))
        # Aleatorizar el dominio rompe el orden secuencial (dia, bloque) con
        # el que se construyó: sin esto, los empates de las soft tienden a
        # llenar siempre Lunes→Viernes y bloque 1→6, produciendo horarios
        # lineales y repetitivos.
        self.rng.shuffle(dominio)
        return dominio

    def _construir_variables(self, plan: dict[int, dict[int, int]]) -> None:
        """Crea las variables, descontando las celdas fijas ya colocadas."""
        vid = 0
        for curso in self.problem.cursos:
            mats = plan.get(curso.id) or {}
            for materia_id, n_bloques in sorted(mats.items()):
                # Las celdas fijas de esta materia ya satisfacen parte de la carga.
                fijas_por_materia = sum(
                    1 for f in self.fijas if f["curso_id"] == curso.id and f["materia_id"] == materia_id
                )
                restantes = n_bloques - fijas_por_materia
                if restantes <= 0:
                    continue
                dominio = self._constructor_dominio(curso, materia_id)
                for _ in range(restantes):
                    self.vars.append(_Var(vid, curso.id, materia_id, dominio))
                    vid += 1
        # Orden aleatorio de las variables: rompe el patrón curso 1→N,
        # materia 1→M con el que se crearon (complementa el shuffle de
        # dominios para evitar resultados lineales).
        self.rng.shuffle(self.vars)

    def _calcular_grados(self) -> dict[int, int]:
        """Grado: cuántas otras variables comparten curso, docente o salón."""
        grado: dict[int, int] = {}
        for v in self.vars:
            g = 0
            for w in self.vars:
                if v.vid == w.vid:
                    continue
                if (
                    v.curso_id == w.curso_id
                    or (v.docentes & w.docentes)
                    or (v.salones & w.salones)
                ):
                    g += 1
            grado[v.vid] = g
        return grado

    def _calcular_demanda(self) -> dict[tuple[int, int], int]:
        """Cuántas variables quieren cada (dia, bloque). Para LCV."""
        demanda: dict[tuple[int, int], int] = defaultdict(int)
        for v in self.vars:
            for _d, _s, dia, bloque in v.base_domain:
                demanda[(dia, bloque)] += 1
        return demanda

    # ------------------------------------------------------------------
    # Validación / dominio vivo
    # ------------------------------------------------------------------

    def valor_posible(self, v: _Var, valor: tuple[int, int, int, int]) -> bool:
        """¿Puede `v` tomar `valor` dado el estado actual?

        RESTRICCIONES DURAS únicamente (T-028):
            (1) docente no en dos cursos a la vez,
            (2) salón no usado por dos cursos a la vez,
            (3) curso con una sola clase por (dia, bloque).
        La carga horaria del docente y el techo de bloques de la materia por
        día (§4.3) son SUAVES: se penalizan al ordenar valores, no bloquean.
        """
        d, s, dia, bloque = valor
        if self.occ_docente.get((d, dia, bloque)):
            return False
        if self.occ_salon.get((s, dia, bloque)):
            return False
        if self.occ_curso.get((v.curso_id, dia, bloque)):
            return False
        return True

    def _penal_carga(self, d: int) -> int:
        """Soft: cuánto excedería al docente asignarle un bloque más.

        0 si está dentro de su contrato; >0 si ya está sobrecargado. Se suma
        en el orden de valores: no bloquea, solo ordena (T-028).
        """
        return max(0, (self.bloques_usados.get(d, 0) + 1) - self.capacidad_bloques.get(d, 0))

    def _penal_materia_dia(self, v: _Var, dia: int) -> int:
        """Soft: cuánto excedería el techo de 2 bloques/día de la materia (§4.3)."""
        return max(
            0,
            self.mat_dia_cuenta.get((v.curso_id, v.materia_id, dia), 0)
            + 1
            - MAX_BLOQUES_MATERIA_DIA,
        )

    def _penal_slot(self, dia: int, bloque: int) -> int:
        """Cuántas clases ya ocupan este (dia, bloque). Presvenir saturarlo."""
        return self.occ_slot.get((dia, bloque), 0)

    def _penal_dia(self, v: _Var, dia: int) -> int:
        """Preferencia de reparto uniforme: días con menos bloques asignados.

        Devuelve los bloques que la materia `v` ya ocupa en `dia` para este
        curso. Cuanto menor, mejor: empuja la asignación hacia los días menos
        cargados y reparte la materia parejo entre Lunes y Viernes.
        """
        return self.mat_dia_cuenta.get((v.curso_id, v.materia_id, dia), 0)

    def _penal_docente_dia(self, d: int, dia: int) -> int:
        """Bloques que el docente ya tiene ese día.

        En problemas reales cada docente cubre casi todos sus slots; si sus
        clases se apilan a un día, el matching se acorrala (dead-ends). Esta
        soft empuja las clases del docente hacia sus días menos cargados.
        """
        return self.docente_dia.get((d, dia), 0)

    def _penal_contiguos(self, v: _Var, valor: tuple[int, int, int, int]) -> int:
        """Penaliza quedar pegado a otra clase de la MISMA materia, mismo día.

        Suma 1 por cada vecino (bloque-1 / bloque+1 del mismo día) ocupado por
        una celda ya asignada del mismo (curso, materia).
        """
        _d, _s, dia, bloque = valor
        pena = 0
        for b in (bloque - 1, bloque + 1):
            if b < 1:
                continue
            if self.occ_mismo_materia.get((v.curso_id, v.materia_id, dia, b)):
                pena += 1
        return pena

    def _penal_misma_hora_consecutivos(
        self, v: _Var, valor: tuple[int, int, int, int]
    ) -> int:
        """Soft de variabilidad semanal: misma materia a la MISMA hora
        (bloque) en días consecutivos.

        Cuenta la longitud de la racha de días consecutivos (hacia abajo y
        hacia arriba desde `dia`) en los que este (curso, materia) ya ocupa
        este mismo `bloque`. Penaliza solo el exceso sobre
        MAX_DIAS_MISMA_HORA (=2): 0 mientras la racha sea corta, >0 cuando la
        materia amenaza con quedar "clavada" a la misma hora casi toda la
        semana (p. ej. Matemáticas a primera hora Lun-Vie).

        Soft: ordena, nunca bloquea (una racha larga sigue siendo válida si
        es la única forma de llenar la grilla).
        """
        _d, _s, dia, bloque = valor
        k = (v.curso_id, v.materia_id, bloque)
        # La propia celda que se evalúa cuenta como 1 de la racha.
        racha = 1
        # Días anteriores consecutivos con la materia en este mismo bloque.
        d = dia - 1
        while self.occ_mismo_materia.get((v.curso_id, v.materia_id, d, bloque)):
            racha += 1
            d -= 1
        # Días posteriores consecutivos.
        d = dia + 1
        while self.occ_mismo_materia.get((v.curso_id, v.materia_id, d, bloque)):
            racha += 1
            d += 1
        return max(0, racha - MAX_DIAS_MISMA_HORA)

    def valores_vivos(self, v: _Var) -> list[tuple[int, int, int, int]]:
        """Subdominio actual: valores que no chocan con el estado presente."""
        return [val for val in v.base_domain if self.valor_posible(v, val)]

    # ------------------------------------------------------------------
    # Backtracking + heurísticas
    # ------------------------------------------------------------------

    def _siguiente_variable(self) -> _Var | None:
        """MRV (menos valores vivos) con desempate Degree + balance.

        Desempates, en orden:
          1. Degree: la variable que más interacciona con otras;
          2. Balance: la del curso con MENOS celdas asignadas. Evita que un par
             de cursos acaparen las aulas/salones y dejen vacíos al resto
             (T-028: repartir el llenado entre los 6 cursos);
          3. Aleatorio (perturbación estocástica): entre variables empatadas
             en todo lo anterior se elige al azar — evita que el patrón de
             ramificación sea siempre el mismo y diversifica los horarios.
        """
        candidatas: list[_Var] = []
        mejor_clave: tuple | None = None
        for v in self.vars:
            if v.asignado is not None:
                continue
            n = sum(1 for val in v.base_domain if self.valor_posible(v, val))
            if n == 0:
                return v  # sin valores: se detecta como conflicto antes de ramificar
            deg = self.grado[v.vid]
            bal = self.asig_curso.get(v.curso_id, 0)
            clave = (bal, n, -deg)
            if mejor_clave is None or clave < mejor_clave:
                mejor_clave = clave
                candidatas = [v]
            elif clave == mejor_clave:
                candidatas.append(v)
        if not candidatas:
            return None
        return self.rng.choice(candidatas)

    def _valores_ordenados(self, v: _Var) -> list[tuple[int, int, int, int]]:
        """LCV con soft-constraints y preferencias (menor primer).

        Orden de prioridad (T-028, lo suave ordena pero sin bloquear):
          1. exceso de carga horaria del docente (0 = dentro de contrato),
          2. exceso de bloques de la materia en el día (§4.3, techo 2),
          3. racha de días consecutivos con la materia a la MISMA hora
             (variabilidad semanal, techo 2 días),
          4. día menos cargado del DOCENTE (evita apilar sus clases y
              acorralar el matching),
          5. `dia` con menos bloques ya asignados de la materia (reparto Lu→Vi),
          6. menos vecinos contiguos del mismo (curso, materia) en ese día,
          7. (dia, bloque) menos demandado por el resto (criterio LCV clásico),
          8. (dia, bloque) con MENOS clases ya asignadas (llena slots libres),
          9. jitter aleatorio: rompe el orden secuencial entre valores con
              idéntica penalización (perturbación estocástica).
        """
        vivos = self.valores_vivos(v)
        return sorted(
            vivos,
            key=lambda val: (
                self._penal_carga(val[0]),
                self._penal_materia_dia(v, val[2]),
                self._penal_misma_hora_consecutivos(v, val),
                self._penal_docente_dia(val[0], val[2]),
                self._penal_dia(v, val[2]),
                self._penal_contiguos(v, val),
                self._demanda.get((val[2], val[3]), 0),
                self._penal_slot(val[2], val[3]),
                self.rng.uniform(0, 0.01),
            ),
        )

    def _asignar(self, v: _Var, valor: tuple[int, int, int, int]) -> None:
        d, s, dia, bloque = valor
        v.asignado = valor
        self.occ_curso[(v.curso_id, dia, bloque)] = True
        self.occ_docente[(d, dia, bloque)] = True
        self.occ_salon[(s, dia, bloque)] = True
        self.bloques_usados[d] += 1

    def _desasignar(self, v: _Var) -> None:
        if v.asignado is None:
            return
        d, s, dia, bloque = v.asignado
        self.occ_curso.pop((v.curso_id, dia, bloque), None)
        self.occ_docente.pop((d, dia, bloque), None)
        self.occ_salon.pop((s, dia, bloque), None)
        self.bloques_usados[d] -= 1 

    def _soft_score(self) -> int:
        """Suma de excesos suaves del estado actual (carga docente + §4.3).

        Solo se calcula al mejorar el mejor parcial (evento raro), así que su
        coste O(vars) no pesa en el bucle de búsqueda.
        """
        score = 0
        for v in self.vars:
            if v.asignado is None:
                continue
            d, _s, dia, _b = v.asignado
            exceso = self.bloques_usados.get(d, 0) - self.capacidad_bloques.get(d, 0)
            if exceso > 0:
                score += exceso
            mat_dia = self.mat_dia_cuenta.get((v.curso_id, v.materia_id, dia), 0)
            if mat_dia > MAX_BLOQUES_MATERIA_DIA:
                score += mat_dia - MAX_BLOQUES_MATERIA_DIA
        return score

    def _guardar_mejor(self) -> None:
        """Guarda el parcial actual si es el mejor (más profundo; a igualdad,
        con menos violaciones de las restricciones suaves)."""
        profundidad = sum(1 for w in self.vars if w.asignado)
        if profundidad > self.best_depth or (
            profundidad == self.best_depth
            and self.best
            and self._soft_score() < self.best_soft
        ):
            self.best_depth = profundidad
            self.best_soft = self._soft_score()
            self.best = {w.vid: w.asignado for w in self.vars if w.asignado}

    def _backtrack(self) -> bool:
        self.nodos += 1
        if self.nodos > MAX_NODES:
            raise NodeLimitReached()
        # Chequeo periódico del límite de tiempo interno (barato: cada 256 nodos).
        if self.nodos % TIME_CHECK_CADA == 0 and time.time() > self._deadline:
            raise TimeLimitReached()

        v = self._siguiente_variable()
        if v is None:
            return True  # todo asignado

        for valor in self._valores_ordenados(v):
            self._asignar(v, valor)
            self._guardar_mejor()
            try:
                if self._backtrack():
                    return True
            except (NodeLimitReached, TimeLimitReached):
                raise
            self._desasignar(v)
        return False

# ------------------------------------------------------------------
# Fallback greedy (T-029)
# ------------------------------------------------------------------

    def _completo(self) -> bool:
        """True si no queda ninguna celda sin asignar."""
        return all(v.asignado is not None for v in self.vars)

    def _restaurar_mejor(self) -> None:
        """Limpia el estado y reaplica el mejor parcial guardado por el
        backtracking, de modo que el greedy continúe desde ahí."""
        for v in self.vars:
            if v.asignado is not None:
                self._desasignar(v)
        for vid, valor in self.best.items():
            v = next(w for w in self.vars if w.vid == vid)
            self._asignar(v, valor)

    def _valores_greedy(self, v: _Var) -> list[tuple[int, int, int, int]]:
        """Dominio permisivo SOLO para el greedy T-029.

        Se mantiene la exigencia del tipo de salón (aula para materias
        normales, laboratorio/sala cuando la materia lo requiere) para que las
        celdas generadas pasen el trigger `sch_celda_validar` de la BD. Se
        relaja todo lo demás: solo se exige que el docente esté asignado a la
        materia/curso y que cubra el bloque, y que no haya choque duro
        (docente, salón, curso).
        """
        materia = self.problem.materias[v.materia_id]
        if materia.requiere_salon:
            salones = [s for s in self.problem.salones if s.tipo == materia.tipo_salon_requerido]
        else:
            salones = [s for s in self.problem.salones if s.tipo == "aula"]
        valores: list[tuple[int, int, int, int]] = []
        for doc in self.problem.docentes:
            if v.materia_id not in doc.materias or v.curso_id not in doc.cursos:
                continue
            for sl in self.problem.jornada.slots:
                if materia.no_ultima_hora and sl.ultimo:
                    continue
                if not doc.cubre(sl):
                    continue
                for s in salones:
                    valores.append((doc.id, s.id, sl.dia, sl.bloque))
        return valores

    def _rellenar_greedy(self) -> None:
        """T-029 · Completado greedy de las celdas restantes.

        Solo se garantizan las RESTRICCIONES DURAS: docente, salón y curso
        sin choques en cada (dia, bloque). Se ignoran las soft (carga, §4.3,
        anti-contigüidad) y el tipo de salón para maximizar el llenado.

        El llenado usa MRV dinámico (la variable con menos valores vivos en
        cada paso) con jitter aleatorio. Como el problema es un matching
        perfecto, un intento puede acorralar a la última variable; por eso
        se reintenta con nueva aleatorización hasta GREEDY_REINTENTOS,
        conservando el intento que más celdas haya colocado.
        """
        self._restaurar_mejor()
        fijas_previas = [v for v in self.vars if v.asignado is not None]

        mejor_snapshot: dict[int, tuple[int, int, int, int]] = {
            v.vid: v.asignado for v in fijas_previas
        }

        for _intento in range(GREEDY_REINTENTOS):
            if time.time() > self._deadline:
                break
            # Volver al estado base (mejor parcial del backtracking).
            for v in self.vars:
                if v.asignado is not None:
                    self._desasignar(v)
            for vid, valor in mejor_snapshot.items():
                if valor is not None:
                    v = next(w for w in self.vars if w.vid == vid)
                    self._asignar(v, valor)

            self._pasada_greedy()
            colocadas = sum(1 for v in self.vars if v.asignado is not None)
            if colocadas == len(self.vars):
                return  # grilla completa: listo
            # Guardar este intento si mejora; sus asignaciones se conservan
            # como estado para el siguiente ciclo (que las resetea).
            if colocadas > len(mejor_snapshot):
                mejor_snapshot = {
                    v.vid: v.asignado for v in self.vars if v.asignado is not None
                }

        # Asegurar que el estado final refleje el mejor intento alcanzado.
        colocadas = sum(1 for v in self.vars if v.asignado is not None)
        if colocadas < len(mejor_snapshot):
            for v in self.vars:
                if v.asignado is not None:
                    self._desasignar(v)
            for vid, valor in mejor_snapshot.items():
                v = next(w for w in self.vars if w.vid == vid)
                self._asignar(v, valor)

    def _pasada_greedy(self) -> None:
        """Una pasada greedy: MRV dinámico + slot menos saturado + jitter."""
        while True:
            if time.time() > self._deadline:
                return
            # MRV dinámico: la variable SIN asignar con menos valores vivos
            # (ataca primero a las más acorraladas; el tail del matching es
            # lo que rompe al greedy estático).
            candidata: _Var | None = None
            menor = None
            empate: list[_Var] = []
            for v in self.vars:
                if v.asignado is not None:
                    continue
                n = 0
                for val in v.base_domain:
                    if self.valor_posible(v, val):
                        n += 1
                if n == 0:
                    continue  # ya no tiene salida en esta pasada
                if menor is None or n < menor:
                    menor = n
                    empate = [v]
                elif n == menor:
                    empate.append(v)
            if not empate:
                return  # nada más por colocar (o sin opciones)
            v = self.rng.choice(empate) if len(empate) > 1 else empate[0]

            vivos = [
                val
                for val in self._valores_greedy(v)
                if self.valor_posible(v, val)
            ]
            if not vivos:
                continue  # esta pasada no puede ubicarla
            # Slot menos saturado + variabilidad semanal + jitter aleatorio.
            vivos.sort(
                key=lambda val: (
                    self._penal_slot(val[2], val[3]),
                    self._penal_misma_hora_consecutivos(v, val),
                    self.rng.random(),
                )
            )
            self._asignar(v, vivos[0])

    # ------------------------------------------------------------------
    # Cierre / reporte
    # ------------------------------------------------------------------

    def _razon_conflicto(self, v: _Var) -> str:
        """Explica por qué `v` no pudo ubicarse con el estado final."""
        materia = self.problem.materias.get(v.materia_id)
        if not v.docentes:
            return "El docente no está asignado a esta materia/curso (sin candidatos)."
        if not v.salones:
            return (
                f"No hay salones del tipo requerido por la materia "
                f"({materia.tipo_salon_requerido if materia else '?'})."
            )
        motivos = set()
        for d, s, dia, bloque in v.base_domain:
            if self.valor_posible(v, (d, s, dia, bloque)):
                motivos.add("bloques ocupados por otras asignaciones")
                break
            if self.occ_curso.get((v.curso_id, dia, bloque)):
                motivos.add("el curso ya tiene clase en ese (día,bloque)")
            elif self.occ_docente.get((d, dia, bloque)):
                motivos.add("el docente ya dicta en ese (día,bloque)")
            elif self.occ_salon.get((s, dia, bloque)):
                motivos.add("el salón está ocupado en ese (día,bloque)")
            elif self.bloques_usados.get(d, 0) >= self.capacidad_bloques.get(d, 0):
                motivos.add("se agotó la carga horaria del docente")
        if motivos:
            return "Bloqueado porque " + "; ".join(sorted(motivos)[:3]) + "."

    def resultado(self, n_totales: int) -> ScheduleResult:
        """Ensambla el `ScheduleResult` a partir del estado de búsqueda."""
        asignadas = [v for v in self.vars if v.asignado]
        # Completo = se colocaron todas las celdas planificadas (o no había).
        ha_completo = len(asignadas) == n_totales and n_totales > 0
        if n_totales == 0 and not self.fijas:
            tipo_gen = "borrador"  # no hay nada que planificar
        else:
            tipo_gen = "completo" if ha_completo else "parcial"

        # Celdas del solucionador → dicts listos para INSERT.
        celdas_nuevas: list[dict] = []
        for v in asignadas:
            d, s, dia, bloque = v.asignado
            hora_ini, hora_fin = self._horas(dia, bloque)
            celdas_nuevas.append(
            {
                "curso_id": v.curso_id,
                "materia_id": v.materia_id,
                "docente_id": d,
                "salon_id": s,
                "dia": dia,
                "bloque": bloque,
                "hora_inicio": hora_ini,
                "hora_fin": hora_fin,
                "bloqueada": False,
            }
        )

        # Reporte de conflictos: solo si quedó algo sin resolver.
        conflictos: list[dict] = []
        sin_resolver = [v for v in self.vars if v.asignado is None]
        for v in sin_resolver:
            conflictos.append(
                {
                    "tipo": "celda_no_planificada",
                    "curso_id": v.curso_id,
                    "curso": self.cur_nombre.get(v.curso_id, v.curso_id),
                    "materia_id": v.materia_id,
                    "materia": self.mat_nombre.get(v.materia_id, v.materia_id),
                    "motivo": self._razon_conflicto(v),
                }
            )
        conflictos.sort(key=lambda c: c["curso"])

        # Conteo fin de carga por docente para el reporte.
        celdas_completas = self.fijas + celdas_nuevas
        avisos: list[dict] = []
        for doc in self.problem.docentes:
            usados = self.bloques_usados.get(doc.id, 0)
            cap = self.capacidad_bloques.get(doc.id, 0)
            if usados > cap:
                avisos.append(
                    {
                        "tipo": "carga_docente_excedida",
                        "docente_id": doc.id,
                        "docente": f"{doc.nombre} {doc.apellido}",
                        "mensaje": f"Ocupa {usados} bloques; su contrato permite {cap}.",
                    }
                )

        # Soft §4.3: materia con más de 2 bloques en un día (solo aviso, no bloquea).
        mat_dia_viol = defaultdict(int)
        for v in asignadas:
            _d, _s, dia, _b = v.asignado
            k = (v.curso_id, v.materia_id, dia)
            mat_dia_viol[k] += 1
        for (curso_id, materia_id, dia), count in sorted(mat_dia_viol.items()):
            if count > MAX_BLOQUES_MATERIA_DIA:
                avisos.append(
                    {
                        "tipo": "materia_dia_excedida",
                        "curso_id": curso_id,
                        "curso": self.cur_nombre.get(curso_id, curso_id),
                        "materia_id": materia_id,
                        "materia": self.mat_nombre.get(materia_id, materia_id),
                        "dia": dia,
                        "mensaje": (
                            f"{self.mat_nombre.get(materia_id, materia_id)} del curso "
                            f"{self.cur_nombre.get(curso_id, curso_id)} ocupa {count} "
                            f"bloques el día {dia} (techo suave: {MAX_BLOQUES_MATERIA_DIA})."
                        ),
                    }
                )

        stats = {
            "variables": len(self.vars),
            "asignadas": len(asignadas),
            "fijas": len(self.fijas),
            "nodos_explorados": self.nodos,
            "tiempo_seg": round(time.time() - self._t0, 4),
        }
        return ScheduleResult(
            estado=tipo_gen,
            completo=ha_completo,
            celdas=aqui_celdas(celdas_completas),
            conflictos=conflictos,
            avisos=avisos,
            statistics=stats,
        )

    def _horas(self, dia: int, bloque: int) -> tuple[Any, Any]:
        sl = self.problem.jornada.slot(dia, bloque)
        if sl is None:
            return None, None
        return sl.hora_inicio, sl.hora_fin


def aqui_celdas(celdas: list[dict]) -> list[dict]:
    """Ordena celdas por (curso, dia, bloque) para facilitar lectura."""
    return sorted(celdas, key=lambda c: (c["curso_id"], c["dia"], c["bloque"]))


def solve(problem: Problem, semilla: int | None = None) -> ScheduleResult:
    """Punto de entrada: asigna intensidades y resuelve el CSP.

    1) `allocate_intensities` → cuántos bloques por materia (T-016).
    2) Backtracking MRV/Degree/LCV con forward checking (T-017…T-020) y
       perturbación estocástica (dominios barajados + desempates aleatorios).
    3) Si no hay solución completa, se entrega el mejor armado parcial
       junto con el reporte estructurado de conflictos y `avisos`.

    `semilla=None` (por defecto) aleatoriza cada generación: dos llamadas
    sobre el mismo problema producen horarios distintos. Con una semilla
    fija la búsqueda es reproducible (útil en tests).
    """
    plan, avisos_intensidad = allocate_intensities(problem)

    cur_nombre = {c.id: c.nombre for c in problem.cursos}
    mat_nombre = {m.id: m.nombre for m in problem.materias.values()}

    solver = _Solver(problem, plan, cur_nombre, mat_nombre, semilla=semilla)
    solver._t0 = time.time()

    n_totales = len(solver.vars)
    # T-029 + estocasticidad: el backtracking se reinicia con otra
    # aleatorización si un intento no converge. La perturbación estocástica
    # da alta varianza (algunos órdenes resuelven en <1s, otros se pierden);
    # cada intento tiene una ventana corta y las semillas buenas terminan
    # muy por debajo de ella. El greedy (con sus propios reintentos) queda
    # como última instancia.
    truncado_por_tiempo = False
    deadline_global = time.time() + TIME_LIMIT_SEG
    for intento in range(BACKTRACK_REINTENTOS):
        if intento > 0:
            # Reinicio estocástico: nueva barajada de dominios/variables y
            # otra secuencia de jitter (el intento anterior ya agotó su orden).
            plan_sig, _av = allocate_intensities(problem)
            solver = _Solver(problem, plan_sig, cur_nombre, mat_nombre)
            n_totales = len(solver.vars)
        solver._deadline = time.time() + BACKTRACK_VENTANA_SEG
        try:
            if solver._backtrack():
                truncado_por_tiempo = False
                break
            truncado_por_tiempo = True  # agotó la búsqueda sin completar
        except (NodeLimitReached, TimeLimitReached):
            truncado_por_tiempo = True
        if time.time() > deadline_global:
            break

    if not solver._completo():
        # Fallback greedy: rellena desde el mejor parcial con 0 conflictos duros.
        # IMPORTANTE: el greedy necesita su PROPIA ventana de tiempo. `_deadline`
        # quedó vencido tras el backtracking (compartía el mismo `_deadline`);
        # si no lo reiniciamos, `_rellenar_greedy` rompe en la primera iteración
        # y entrega el parcial del backtracking sin completar la grilla.
        solver._deadline = min(
            time.time() + GREEDY_TRIGGER_SEG, deadline_global
        )
        solver._rellenar_greedy()

    if truncado_por_tiempo:
        avisos_intensidad.append(
            {
                "tipo": "limite_tiempo",
                "mensaje": (
                    f"El backtracking superó los {GREEDY_TRIGGER_SEG}s y se aplicó "
                    f"el completado greedy (solo evita choques de docente/aula). "
                    f"El horario queda sin conflictos duros."
                ),
            }
        )

    resultado = solver.resultado(n_totales if n_totales else 0)
    resultado.avisos = avisos_intensidad + resultado.avisos
    return resultado