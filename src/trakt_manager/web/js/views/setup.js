/**
 * Vista del asistente inicial (#/configurar).
 *
 * Se muestra cuando el servicio arranca sin configurar. Pide el código de
 * configuración (que aparece en los registros del contenedor), el Client ID de la
 * aplicación de Trakt y, opcionalmente, su Client Secret (las aplicaciones nuevas
 * de Trakt no tienen). Al terminar muestra una sola vez la API_KEY generada.
 */

import { ApiError, api, setApiKey } from "../api.js";
import { copyButton, h, notice, replaceChildren } from "../dom.js";
import { navigate } from "../router.js";
import { markConfigured, refreshSetupState } from "../session.js";

const TRAKT_APPLICATIONS_URL = "https://trakt.tv/oauth/applications";
// trakt-manager inicia sesión con un código (device flow) y no usa la Redirect URI,
// pero el formulario de Trakt puede pedirla. Trakt desaconseja "urn:ietf:wg:oauth:2.0:oob".
const SUGGESTED_REDIRECT_URI = "http://localhost:8000/";

/**
 * Pinta el asistente.
 *
 * @param {HTMLElement} view
 */
export async function renderSetup(view) {
  const status = await refreshSetupState();
  if (status.configured) {
    navigate("/acceso");
    return;
  }

  const fromEnv = (key) => status.sources[key] === "env";
  const message = h("div");
  const codeInput = h("input", { type: "text", id: "setup-code", autocomplete: "off", required: true, placeholder: "XXXX-XXXX" });
  const clientIdInput = h("input", { type: "text", id: "client-id", autocomplete: "off", required: true });
  const secretInput = h("input", { type: "password", id: "client-secret", autocomplete: "off" });
  const submit = h("button", { type: "submit", className: "button primary" }, "Guardar configuración");

  const form = h(
    "form",
    { onSubmit: (event) => submitSetup(event) },
    h(
      "div",
      { className: "field" },
      h("label", { for: "setup-code" }, "Código de configuración"),
      codeInput,
      h(
        "p",
        { className: "hint" },
        "Aparece en los registros del contenedor (en Docker Desktop u OrbStack: Containers → trakt-manager → Logs), ",
        "en la línea «usa este código de configuración».",
      ),
    ),
    fromEnv("trakt_client_id")
      ? notice("info", "El Client ID de Trakt viene de una variable de entorno.")
      : h("div", { className: "field" }, h("label", { for: "client-id" }, "Client ID de Trakt"), clientIdInput),
    fromEnv("trakt_client_secret")
      ? notice("info", "El Client Secret de Trakt viene de una variable de entorno.")
      : h(
          "div",
          { className: "field" },
          h("label", { for: "client-secret" }, "Client Secret de Trakt (opcional)"),
          secretInput,
          h("p", { className: "hint" }, "Las aplicaciones nuevas de Trakt no tienen Client Secret: déjalo vacío. Rellénalo solo si tu aplicación lo tiene."),
        ),
    message,
    submit,
  );

  replaceChildren(
    view,
    h(
      "section",
      { className: "card narrow" },
      h("h1", {}, "Configurar trakt-manager"),
      h("p", {}, "Solo hace falta una vez. Necesitas una aplicación de Trakt (es gratis):"),
      h(
        "ol",
        {},
        h("li", {}, "Entra en ", h("a", { href: TRAKT_APPLICATIONS_URL, target: "_blank", rel: "noopener noreferrer" }, "trakt.tv/oauth/applications"), " y pulsa «New Application»."),
        h(
          "li",
          {},
          "Ponle cualquier nombre. Si te pide una «Redirect URI», puedes poner esta (trakt-manager no la usa: el inicio de sesión es con un código):",
          h("div", { className: "secret-box" }, h("code", {}, SUGGESTED_REDIRECT_URI), copyButton(SUGGESTED_REDIRECT_URI)),
        ),
        h("li", {}, "Guarda y copia aquí el Client ID (y el Client Secret solo si tu aplicación lo tiene)."),
      ),
      form,
    ),
  );
  codeInput.focus();

  /** Envía el asistente y, si va bien, muestra la API_KEY generada. */
  async function submitSetup(event) {
    event.preventDefault();
    submit.disabled = true;
    replaceChildren(message);
    try {
      const result = await api("POST", "/setup", {
        body: {
          setup_code: codeInput.value,
          trakt_client_id: clientIdInput.value,
          trakt_client_secret: secretInput.value,
        },
      });
      markConfigured();
      showResult(view, result.api_key);
    } catch (error) {
      replaceChildren(message, notice("error", error instanceof ApiError ? error.message : String(error)));
      submit.disabled = false;
    }
  }
}

/**
 * Muestra el final del asistente: la API_KEY generada, una sola vez.
 *
 * @param {HTMLElement} view
 * @param {string} apiKey Clave generada, o cadena vacía si la API_KEY viene del entorno.
 */
function showResult(view, apiKey) {
  if (!apiKey) {
    replaceChildren(
      view,
      h(
        "section",
        { className: "card narrow" },
        h("h1", {}, "Configuración guardada"),
        h("p", {}, "La API_KEY viene de una variable de entorno: úsala para entrar."),
        h("button", { type: "button", className: "button primary", onClick: () => navigate("/acceso") }, "Entrar"),
      ),
    );
    return;
  }

  const remember = h("input", { type: "checkbox", id: "remember" });
  replaceChildren(
    view,
    h(
      "section",
      { className: "card narrow" },
      h("h1", {}, "¡Listo!"),
      notice("warn", "Esta es tu clave de API. Guárdala ahora (por ejemplo en tu gestor de contraseñas): no se volverá a mostrar."),
      h("div", { className: "secret-box" }, h("code", {}, apiKey), copyButton(apiKey)),
      h("p", { className: "hint" }, "La necesitarás para entrar desde otro navegador o para usar la API."),
      h("label", { className: "checkbox" }, remember, "Recordarla en este navegador"),
      h(
        "div",
        { className: "row" },
        h(
          "button",
          {
            type: "button",
            className: "button primary",
            onClick: () => {
              setApiKey(apiKey, remember.checked);
              navigate("/trakt");
            },
          },
          "He guardado la clave, continuar",
        ),
      ),
    ),
  );
}
