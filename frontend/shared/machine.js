/**
 * @fileoverview Table-driven state machines.
 *
 * UI state that changes over time lives in a machine whose moves are a plain
 * table of state -> event -> next state. Handlers send events and never
 * assign state, so a move nobody designed is refused instead of silently
 * putting the page into a state it has no way out of.
 */

/**
 * Whether refused moves should be loud. Developers run on localhost or add
 * ?dev=1; everyone else gets a quiet console warning.
 * @return {boolean}
 */
export function isLoudMode() {
  if (typeof location === 'undefined') return true;
  return (
    location.hostname === '127.0.0.1' ||
    location.hostname === 'localhost' ||
    new URLSearchParams(location.search).has('dev')
  );
}

/**
 * @param {string} name Used in refusal reports.
 * @param {!Object<string, !Object<string, string>>} table
 * @param {string} initial
 * @param {{onRefused: (function(string, string, string): void)|undefined,
 *          onChange: (function(string, string, string): void)|undefined}=} hooks
 */
export function createMachine(name, table, initial, hooks = {}) {
  if (!(initial in table)) throw new Error(`${name}: unknown initial state ${initial}`);
  let state = initial;
  const listeners = new Set();
  if (hooks.onChange) listeners.add(hooks.onChange);

  const move = (event, next) => {
    const previous = state;
    state = next;
    for (const listener of listeners) listener(next, previous, event);
    return true;
  };

  return {
    name,
    get state() {
      return state;
    },
    /** True when `event` is a designed move from the current state. */
    can(event) {
      return Boolean(table[state]?.[event]);
    },
    /**
     * Applies a move. Returns false and reports when the table has no such
     * move from the current state.
     */
    send(event) {
      const next = table[state]?.[event];
      if (next === undefined) {
        (hooks.onRefused ?? reportRefused)(name, state, event);
        return false;
      }
      return move(event, next);
    },
    /** Replays a known state (after a reload or a server-side change). */
    sync(target) {
      if (!(target in table)) throw new Error(`${name}: cannot sync to unknown state ${target}`);
      return move('sync', target);
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  };
}

function reportRefused(name, state, event) {
  const message = `${name}: refused "${event}" in state "${state}"`;
  if (!isLoudMode()) {
    console.warn(message);
    return;
  }
  console.error(message);
  if (typeof document === 'undefined') return;
  const toast = document.createElement('div');
  toast.className = 'toast toast-error';
  toast.textContent = message;
  document.body.append(toast);
  setTimeout(() => toast.remove(), 6000);
}
