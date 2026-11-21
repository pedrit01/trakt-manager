/**
 * Cliente de la API de trakt-manager para la GUI.
 *
 * - Guarda la API_KEY en sessionStorage (se olvida al cerrar la pestaña) o, si el
 *   usuario lo pide, en localStorage (se recuerda en este navegador).
 * - Envía la clave en la cabecera X-API-Key. No se usan cookies, así que no hace
 *   falta protección CSRF.
 * - Traduce los errores HTTP a mensajes en español en un ApiError.
 */

const STORAGE_KEY = "trakt-manager.api-key";

/** Error de una llamada a la API, con un mensaje listo para mostrar al usuario. */
export class ApiError extends Error {
  /**
   * @param {number} status Código HTTP (0 si no se pudo contactar con el servicio).
   * @param {string} message Mensaje en español para el usuario.
   * @param {object|null} body Cuerpo JSON de la respuesta, si lo hay (por ejemplo, los errores de validación).
   */
  constructor(status, message, body = null) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

/** Mensajes por código HTTP cuando la API no envía uno propio. */
const DEFAULT_MESSAGES = {
  401: "La clave de API no es correcta.",
  403: "No autorizado.",
  404: "No encontrado.",
  409: "La operación no se puede hacer ahora.",
  422: "Los datos enviados no son válidos.",
  502: "Trakt no está disponible ahora mismo. Inténtalo de nuevo en unos minutos.",
  503: "El servicio aún no está configurado.",
};

/**
 * Funciones que la aplicación registra para reaccionar a ciertos errores en
 * cualquier vista: una clave incorrecta (401) vuelve al acceso y el modo
 * configuración (503) vuelve al asistente.
 */
const handlers = { unauthorized: () => {}, notConfigured: () => {} };

/**
 * Registra qué hacer ante una clave incorrecta o un servicio sin configurar.
 *
 * @param {{unauthorized?: Function, notConfigured?: Function}} newHandlers
 */
export function onSessionProblem(newHandlers) {
  Object.assign(handlers, newHandlers);
}

/** @returns {string|null} La API_KEY guardada en este navegador, si la hay. */
export function getApiKey() {
  return sessionStorage.getItem(STORAGE_KEY) || localStorage.getItem(STORAGE_KEY);
}

/**
 * Guarda la API_KEY.
 *
 * @param {string} apiKey
 * @param {boolean} remember Si es true se guarda en localStorage (persiste en este navegador).
 */
export function setApiKey(apiKey, remember) {
  forgetApiKey();
  (remember ? localStorage : sessionStorage).setItem(STORAGE_KEY, apiKey);
}

/**
 * Sustituye la clave guardada manteniendo dónde estaba (sesión o recordada).
 * Se usa tras regenerarla, para no echar al usuario.
 *
 * @param {string} apiKey
 */
export function replaceApiKey(apiKey) {
  setApiKey(apiKey, localStorage.getItem(STORAGE_KEY) !== null);
}

/** Olvida la API_KEY en este navegador. */
export function forgetApiKey() {
  sessionStorage.removeItem(STORAGE_KEY);
  localStorage.removeItem(STORAGE_KEY);
}

/**
 * Llama a la API.
 *
 * @param {string} method Método HTTP.
 * @param {string} path Ruta, por ejemplo "/definitions".
 * @param {object} [options]
 * @param {object|string} [options.body] Cuerpo: un objeto se envía como JSON; un texto, tal cual.
 * @param {string} [options.contentType] Content-Type para un cuerpo de texto (por ejemplo "application/yaml").
 * @param {object} [options.query] Parámetros de la query string.
 * @param {string} [options.apiKey] Clave a usar en lugar de la guardada (para probarla en el acceso).
 * @param {boolean} [options.raw] Si es true devuelve el objeto Response en lugar del JSON.
 * @returns {Promise<any>} El JSON de la respuesta.
 * @throws {ApiError}
 */
export async function api(method, path, options = {}) {
  const headers = {};
  const apiKey = options.apiKey ?? getApiKey();
  if (apiKey) headers["X-API-Key"] = apiKey;

  let body;
  if (typeof options.body === "string") {
    body = options.body;
    headers["Content-Type"] = options.contentType || "application/json";
  } else if (options.body !== undefined) {
    body = JSON.stringify(options.body);
    headers["Content-Type"] = "application/json";
  }

  const query = options.query ? `?${new URLSearchParams(options.query)}` : "";
  let response;
  try {
    response = await fetch(`${path}${query}`, { method, headers, body });
  } catch {
    throw new ApiError(0, "No se puede contactar con el servicio. Comprueba que el contenedor está en marcha.");
  }

  if (response.ok) {
    if (options.raw) return response;
    return response.status === 204 ? null : response.json();
  }
  throw await buildError(response, options.apiKey !== undefined);
}

/**
 * Construye el ApiError de una respuesta fallida y avisa a la aplicación si hace falta.
 *
 * @param {Response} response
 * @param {boolean} probingKey Si se estaba probando una clave nueva: entonces un 401
 *   no debe expulsar al usuario, solo informar.
 * @returns {Promise<ApiError>}
 */
async function buildError(response, probingKey) {
  let body = null;
  try {
    body = await response.json();
  } catch {
    // Respuesta sin JSON: se usa el mensaje por defecto.
  }
  const detail = typeof body?.detail === "string" ? body.detail : null;
  const message = response.status === 502 ? DEFAULT_MESSAGES[502] : detail || DEFAULT_MESSAGES[response.status] || `Error inesperado (HTTP ${response.status}).`;

  if (response.status === 401 && !probingKey) handlers.unauthorized();
  if (response.status === 503) handlers.notConfigured();
  return new ApiError(response.status, message, body);
}

/**
 * Descarga una respuesta de la API como fichero.
 *
 * No basta con un enlace normal porque la petición necesita la cabecera X-API-Key.
 *
 * @param {string} path Ruta de la API que devuelve el fichero.
 * @param {string} fileName Nombre con el que guardarlo.
 */
export async function download(path, fileName) {
  const response = await api("GET", path, { raw: true });
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
