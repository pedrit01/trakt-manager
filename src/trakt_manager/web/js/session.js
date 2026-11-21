/**
 * Estado compartido de la GUI: si el servicio está en modo configuración, si se
 * muestra la navegación y el indicador de la sesión de Trakt en la cabecera.
 */

import { api, forgetApiKey } from "./api.js";

/** `true` en modo configuración, `false` configurado, `null` si aún no se sabe. */
let setupMode = null;

/**
 * Consulta al servicio si está configurado.
 *
 * @returns {Promise<{configured: boolean, missing: string[], sources: object}>}
 */
export async function refreshSetupState() {
  const status = await api("GET", "/setup/status");
  setupMode = !status.configured;
  return status;
}

/** @returns {boolean|null} Si el servicio está en modo configuración. */
export function isSetupMode() {
  return setupMode;
}

/** Anota que el asistente se ha completado (el servicio ya no está en modo configuración). */
export function markConfigured() {
  setupMode = false;
}

/** Anota que el servicio ha vuelto al modo configuración (la API respondió 503). */
export function markNotConfigured() {
  setupMode = true;
}

/**
 * Muestra u oculta la navegación y la zona de sesión de la cabecera.
 *
 * @param {boolean} visible
 */
export function showChrome(visible) {
  document.getElementById("nav").hidden = !visible;
  document.getElementById("session").hidden = !visible;
}

/** Actualiza el indicador "Trakt: ..." de la cabecera con el estado de la sesión. */
export async function refreshTraktBadge() {
  const badge = document.getElementById("trakt-badge");
  try {
    const status = await api("GET", "/auth/status");
    const connected = status.status === "authorized";
    badge.textContent = connected ? `Trakt: ${status.username}` : "Trakt: sin conectar";
    badge.className = `badge ${connected ? "ok" : "warn"}`;
  } catch {
    // Si falla (por ejemplo, Trakt caído) no se cambia el indicador: no es crítico.
  }
}

/** Sale de la GUI: olvida la clave guardada en este navegador. */
export function logout() {
  forgetApiKey();
}
