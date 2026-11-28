# The simulator: while it runs on a database, every request shares one open
# transaction instead of committing its own. Each click that changes data ends
# with a savepoint, a step one can go back to; keeping the simulation commits
# everything, discarding it (or stopping the server) leaves no trace.
#
# The way Odoo's own browser tests share a transaction across requests: the
# registry hands out cursors wrapping the one real cursor, and their commits
# and rollbacks become savepoint releases and rollbacks. One request at a time
# goes through, which suits one person on a local server (--workers=0).
import logging
import threading
from datetime import datetime, timezone

import psycopg2
from psycopg2 import sql as psql

from odoo import sql_db
from odoo.modules.registry import Registry
from odoo.sql_db import Cursor, Savepoint
from odoo.tools import config

_logger = logging.getLogger(__name__)

# the simulation running on each database
SIMULATIONS = {}
LOCK_TIMEOUT = 300


def current(dbname):
    simulation = SIMULATIONS.get(dbname)
    return simulation if simulation and not simulation.ended else None


class SimulationError(Exception):
    pass


class SimulationEnded(SimulationError):
    pass


class SimConnection:
    """ The connection of a simulated cursor: committing or rolling back only
    ends its savepoint on the simulation's real transaction. """

    def __init__(self, cursor):
        self._cursor = cursor
        self.readonly = False
        self._savepoint = None
        self._obj = None

    def set_session(self, *args, **kwargs):
        pass

    def give_back(self, keep_in_pool=True):
        del self._obj

    def _check_savepoint(self):
        if self._savepoint is None:
            self._savepoint = Savepoint(self._obj)

    def commit(self):
        if self._savepoint is not None:
            self._savepoint.close(rollback=False)
            self._savepoint = None

    def rollback(self):
        if self._savepoint is not None:
            self._savepoint.close(rollback=True)
            self._savepoint = None

    def reset(self):
        self.rollback()

    @property
    def closed(self):
        return self._cursor.closed

    def __getattr__(self, name):
        return getattr(self._cursor._cnx, name)


class SimCursor(Cursor):
    """ A cursor of a request during a simulation. """

    def __init__(self, simulation):
        if not simulation.lock.acquire(timeout=LOCK_TIMEOUT):
            raise SimulationError("The simulation is busy with another request")
        try:
            if simulation.ended:
                raise SimulationEnded()
            super().__init__(SimConnection(simulation.cr), simulation.cr.dbname)
            self._cnx._obj = self._obj
        except Exception:
            simulation.lock.release()
            raise
        self._simulation = simulation
        simulation.stack.append(self)

    def execute(self, *args, **kwargs):
        if self.closed:
            raise psycopg2.InterfaceError("Cursor already closed")
        self._cnx._check_savepoint()
        return super().execute(*args, **kwargs)

    def now(self):
        # one transaction for the whole simulation: its NOW() would never move
        if self._now is None:
            self._now = datetime.now(timezone.utc).replace(tzinfo=None)
        return self._now

    def rollback(self):
        super().rollback()
        # a savepoint made while resetting after the rollback goes too
        if not self.closed:
            self._cnx.rollback()

    def _close(self):
        simulation = self._simulation
        try:
            super()._close()
        finally:
            if simulation.stack and simulation.stack[-1] is self:
                simulation.stack.pop()
            elif self in simulation.stack:
                simulation.stack.remove(self)
            try:
                if not simulation.stack:
                    simulation.run_pending()
            finally:
                simulation.lock.release()


class Simulation:

    def __init__(self, dbname, uid):
        self.dbname = dbname
        self.uid = uid
        self.started = datetime.now(timezone.utc).replace(tzinfo=None)
        self.lock = threading.RLock()
        self.stack = []
        self.pending = []
        self.steps = []
        self.counter = 0
        self.ended = False
        self.outcome = None
        # a connection of its own, out of the pool's reach until the end
        self.cr = sql_db.db_connect(dbname).cursor()
        self.start_point = self._savepoint()

    #
    # the savepoints, on the real transaction
    #

    def _execute(self, query):
        self.cr._obj.execute(query)

    def _savepoint(self):
        self.counter += 1
        name = f'flow_sim_{self.counter}'
        self._execute(psql.SQL('SAVEPOINT {}').format(psql.Identifier(name)))
        return name

    def _rollback_to(self, name):
        self._execute(psql.SQL('ROLLBACK TO SAVEPOINT {}').format(psql.Identifier(name)))
        self._clear_caches()

    def _clear_caches(self):
        registry = Registry(self.dbname)
        for _sequence, cache in getattr(registry, 'registry_caches__', {}).values():
            cache.clear()

    #
    # what the requests ask: done once their cursors are closed
    #

    def ask(self, operation, **values):
        with self.lock:
            self.pending.append((operation, values))
            if not self.stack:
                self.run_pending()

    def run_pending(self):
        while self.pending and not self.ended:
            operation, values = self.pending.pop(0)
            try:
                getattr(self, f'_do_{operation}')(**values)
            except Exception:
                _logger.exception("Simulation on %s: %s failed", self.dbname, operation)
                if operation in ('keep', 'discard'):
                    self._end('failed')

    def _do_step(self, trace_id, name, model, res_id, action='', target='', target_model='', target_id=False):
        self.steps.append({
            'id': len(self.steps) + 1, 'trace_id': trace_id, 'name': name,
            'model': model, 'res_id': res_id, 'savepoint': self._savepoint(), 'abandoned': False,
            'action': action, 'target': target, 'target_model': target_model, 'target_id': target_id,
            'date': datetime.now(timezone.utc).replace(tzinfo=None).isoformat(sep=' ', timespec='seconds'),
        })

    def _do_rewind(self, step_id):
        if step_id:
            step = next(step for step in self.steps if step['id'] == step_id and not step['abandoned'])
            name = step['savepoint']
        else:
            step, name = None, self.start_point
        self._rollback_to(name)
        position = self.steps.index(step) + 1 if step else 0
        for later in self.steps[position:]:
            later['abandoned'] = True

    def _do_keep(self):
        self.cr.commit()
        self._end('kept')

    def _do_discard(self):
        self.cr.rollback()
        self._end('discarded')

    def _end(self, outcome):
        self.ended = True
        self.outcome = outcome
        registry = Registry(self.dbname)
        # only its own cursor factory: never one put there by someone else
        if registry.__dict__.get('cursor') == self.cursor:
            del registry.cursor
        _unpatch_bus(self.dbname)
        try:
            self.cr.close()
        except Exception:  # noqa: BLE001 - the connection may be gone already
            _logger.warning("Simulation on %s: could not close its connection", self.dbname, exc_info=True)
        self._clear_caches()
        if SIMULATIONS.get(self.dbname) is self:
            del SIMULATIONS[self.dbname]
        _logger.info("Simulation on %s %s after %s steps", self.dbname, outcome, len(self.steps))

    #
    # for the web client
    #

    def cursor(self, readonly=False):
        try:
            return SimCursor(self)
        except SimulationEnded:
            # it ended while this request waited: back to the database as it is
            return sql_db.db_connect(self.dbname).cursor()

    def state(self):
        return {
            'active': not self.ended,
            'started': self.started.isoformat(sep=' ', timespec='seconds'),
            'steps': [{key: value for key, value in step.items() if key != 'savepoint'} for step in self.steps],
        }


def start(dbname, uid):
    if config['workers']:
        raise SimulationError("The simulator needs Odoo to run in one process (workers = 0).")
    if current(dbname):
        raise SimulationError("A simulation already runs on this database.")
    simulation = Simulation(dbname, uid)
    SIMULATIONS[dbname] = simulation
    # every cursor of the database is now one of the simulation
    Registry(dbname).cursor = simulation.cursor
    _patch_bus(dbname, simulation)
    _logger.info("Simulation on %s started", dbname)
    return simulation


#
# the live notifications open their cursors themselves: they join the simulation
#

_bus_patched = {}


def _patch_bus(dbname, simulation):
    try:
        from odoo.addons.bus.tools import misc as bus_misc  # noqa: PLC0415
    except ImportError:
        return
    original = _bus_patched.setdefault('db_connect', bus_misc.db_connect)

    def db_connect(to, allow_uri=False, readonly=False):
        running = current(to) if isinstance(to, str) else None
        if running:
            class _Connection:
                def cursor(self):
                    return running.cursor()
            return _Connection()
        return original(to, allow_uri=allow_uri, readonly=readonly)

    bus_misc.db_connect = db_connect


def _unpatch_bus(dbname):
    if any(current(name) for name in SIMULATIONS if name != dbname):
        return
    try:
        from odoo.addons.bus.tools import misc as bus_misc  # noqa: PLC0415
    except ImportError:
        return
    if 'db_connect' in _bus_patched:
        bus_misc.db_connect = _bus_patched.pop('db_connect')


def real_cursor(dbname):
    """ A cursor out of the simulation: what is written on it stays, whatever the simulation becomes. """
    return sql_db.db_connect(dbname).cursor()
