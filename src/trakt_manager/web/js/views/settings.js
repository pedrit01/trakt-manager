/**
 * Vista de ajustes (#/ajustes): origen de cada clave, cambiar las credenciales de
 * Trakt y regenerar la API_KEY.
 *
 * Las claves que vienen de variables de entorno se muestran como no editables:
 * el entorno siempre tiene prioridad sobre lo guardado desde la GUI.
 */

import { api, replaceApiKey } from "../api.js";
import { confirmDialog, copyButton, h, notice, replaceChildren, toast } from "../dom.js";
import { refreshTraktBadge } from "../session.js";

const SOURCE_LABELS = { env: "variable de entorno", stored: "guardada desde la GUI", missing: "sin configurar" };

/**
 * Pinta la vista.
 *
 * @param {HTMLElement} view
 */
export async function renderSettings(view) {
  replaceChildren(view, h("h1", {}, "Ajustes"), h("p", { className: "muted" }, "Cargando…"));
  let settings;
  try {
    settings = await api("GET", "/settings");
  } catch (error) {
    replaceChildren(view, h("h1", {}, "Ajustes"), notice("error", error.message));
    return;
  }
  replaceChildren(view, h("h1", {}, "Ajustes"), credentialsCard(settings, () => renderSettings(view)), apiKeyCard(settings.api_key));
}

/**
 * Tarjeta de las credenciales de la aplicación de Trakt.
 *
 * @param {object} settings Respuesta de GET /settings.
 * @param {Function} reload Vuelve a pintar la vista tras guardar.
 * @returns {HTMLElement}
 */
function credentialsCard(settings, reload) {
  const clientId = settings.trakt_client_id;
  const secret = settings.trakt_client_secret;
  const clientIdInput = h("input", { type: "text", id: "settings-client-id", value: clientId.value || "", disabled: !clientId.editable, autocomplete: "off" });
  const secretInput = h("input", {
    type: "password",
    id: "settings-client-secret",
    placeholder: secret.set ? "•••••••• (déjalo vacío para no cambiarlo)" : "",
    disabled: !secret.editable,
    autocomplete: "off",
  });
  const message = h("div");

  /** Guarda los cambios, avisando antes si el cambio de Client ID cerrará la sesión. */
  async function save(event) {
    event.preventDefault();
    const changes = {};
    if (clientId.editable && clientIdInput.value.trim() !== (clientId.value || "")) changes.trakt_client_id = clientIdInput.value.trim();
    if (secret.editable && secretInput.value.trim()) changes.trakt_client_secret = secretInput.value.trim();
    if (!Object.keys(changes).length) {
      replaceChildren(message, notice("info", "No hay cambios que guardar."));
      return;
    }
    if (changes.trakt_client_id) {
      const confirmed = await confirmDialog({
        title: "¿Cambiar el Client ID?",
        body: "La sesión de Trakt se cerrará, porque pertenece a la aplicación anterior. Tendrás que volver a conectar.",
        confirmLabel: "Cambiar",
      });
      if (!confirmed) return;
    }
    try {
      await api("PUT", "/settings", { body: changes });
      toast("Credenciales guardadas.");
      refreshTraktBadge();
      reload();
    } catch (error) {
      replaceChildren(message, notice("error", error.message));
    }
  }

  const editable = clientId.editable || secret.editable;
  return h(
    "section",
    { className: "card" },
    h("h2", {}, "Aplicación de Trakt"),
    h(
      "form",
      { onSubmit: save },
      h(
        "div",
        { className: "field" },
        h("label", { for: "settings-client-id" }, "Client ID"),
        clientIdInput,
        h("p", { className: "hint" }, `Origen: ${SOURCE_LABELS[clientId.source]}.`),
      ),
      h(
        "div",
        { className: "field" },
        h("label", { for: "settings-client-secret" }, "Client Secret (opcional)"),
        secretInput,
        h(
          "p",
          { className: "hint" },
          `Origen: ${SOURCE_LABELS[secret.source]}. Por seguridad nunca se muestra. `,
          "Las aplicaciones nuevas de Trakt no tienen Client Secret.",
        ),
      ),
      message,
      editable
        ? h("button", { type: "submit", className: "button primary" }, "Guardar")
        : notice("info", "Estas credenciales vienen de variables de entorno: cámbialas en el entorno del contenedor."),
    ),
  );
}

/**
 * Tarjeta de la API_KEY: origen y regeneración.
 *
 * @param {{source: string, editable: boolean}} apiKey Parte de GET /settings.
 * @returns {HTMLElement}
 */
function apiKeyCard(apiKey) {
  const result = h("div");

  /** Regenera la clave, la muestra una vez y la usa a partir de ahora en este navegador. */
  async function regenerate() {
    const confirmed = await confirmDialog({
      title: "¿Regenerar la clave de API?",
      body: "La clave actual dejará de funcionar al momento en todos los navegadores y programas que la usen. Este navegador pasará a usar la nueva.",
      confirmLabel: "Regenerar",
      danger: true,
    });
    if (!confirmed) return;
    try {
      const { api_key: newKey } = await api("POST", "/settings/api-key");
      replaceApiKey(newKey);
      replaceChildren(
        result,
        notice("warn", "Esta es la nueva clave. Guárdala ahora: no se volverá a mostrar."),
        h("div", { className: "secret-box" }, h("code", {}, newKey), copyButton(newKey)),
      );
    } catch (error) {
      replaceChildren(result, notice("error", error.message));
    }
  }

  return h(
    "section",
    { className: "card" },
    h("h2", {}, "Clave de API"),
    h("p", {}, `Origen: ${SOURCE_LABELS[apiKey.source]}.`),
    apiKey.editable
      ? h("button", { type: "button", className: "button danger", onClick: regenerate }, "Regenerar clave")
      : notice("info", "La clave viene de la variable de entorno API_KEY: cámbiala en el entorno del contenedor."),
    result,
  );
}
