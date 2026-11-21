/**
 * Navegación de la GUI basada en el fragmento de la URL (#/seccion/parametro).
 *
 * Cada ruta es una función que pinta su vista dentro de <main id="view"> y puede
 * devolver una función de limpieza (por ejemplo, para parar un sondeo periódico)
 * que se ejecuta al salir de la vista.
 */

const routes = new Map();
let cleanup = null;
let beforeEach = async () => true;

/**
 * Registra una sección.
 *
 * @param {string} section Primer segmento de la ruta, por ejemplo "listas".
 * @param {(view: HTMLElement, param: string|null) => (Function|void|Promise<Function|void>)} render
 *   Función que pinta la vista; recibe el contenedor y el segundo segmento (si lo hay).
 */
export function route(section, render) {
  routes.set(section, render);
}

/**
 * Registra una comprobación previa a cada navegación (por ejemplo, exigir la clave).
 *
 * @param {(section: string) => Promise<boolean>} guard Devuelve false si ya ha
 *   redirigido a otra ruta y no hay que pintar la pedida.
 */
export function beforeNavigate(guard) {
  beforeEach = guard;
}

/**
 * Navega a una ruta.
 *
 * @param {string} path Por ejemplo "/listas" o "/sincronizar/doomsday".
 */
export function navigate(path) {
  const target = `#${path}`;
  if (window.location.hash === target) {
    render();
  } else {
    window.location.hash = target;
  }
}

/** @returns {{section: string, param: string|null}} La ruta actual. */
export function currentRoute() {
  const [section = "", ...rest] = window.location.hash.replace(/^#\/?/, "").split("/");
  return { section, param: rest.length ? decodeURIComponent(rest.join("/")) : null };
}

/** Pinta la vista de la ruta actual. */
async function render() {
  if (cleanup) {
    cleanup();
    cleanup = null;
  }
  const { section, param } = currentRoute();
  if (!(await beforeEach(section))) return;

  const view = document.getElementById("view");
  const renderSection = routes.get(section) || routes.get("definiciones");
  highlightNavigation(section);
  const result = await renderSection(view, param);
  if (typeof result === "function") cleanup = result;
  view.focus();
}

/**
 * Marca como activo el enlace de navegación de la sección actual.
 *
 * @param {string} section
 */
function highlightNavigation(section) {
  for (const link of document.querySelectorAll("#nav a")) {
    // La vista de sincronización pertenece a la sección de definiciones.
    const active = link.dataset.section === section || (section === "sincronizar" && link.dataset.section === "definiciones");
    link.classList.toggle("active", active);
  }
}

/** Arranca el enrutador: pinta la ruta actual y escucha los cambios. */
export function startRouter() {
  window.addEventListener("hashchange", render);
  render();
}
