/**
 * Vista de acceso (#/acceso): pide la API_KEY antes de mostrar ningún dato.
 */

import { ApiError, api, setApiKey } from "../api.js";
import { h, notice, replaceChildren } from "../dom.js";
import { navigate } from "../router.js";

/**
 * Pinta el formulario de acceso.
 *
 * @param {HTMLElement} view
 */
export function renderLogin(view) {
  const keyInput = h("input", { type: "password", id: "api-key", autocomplete: "current-password", required: true });
  const remember = h("input", { type: "checkbox", id: "remember" });
  const message = h("div");
  const submit = h("button", { type: "submit", className: "button primary" }, "Entrar");

  replaceChildren(
    view,
    h(
      "section",
      { className: "card narrow" },
      h("h1", {}, "Entrar"),
      h("p", { className: "muted" }, "Introduce la clave de API que obtuviste al configurar trakt-manager."),
      h(
        "form",
        { onSubmit: (event) => submitKey(event) },
        h("div", { className: "field" }, h("label", { for: "api-key" }, "Clave de API"), keyInput),
        h(
          "div",
          { className: "field" },
          h("label", { className: "checkbox" }, remember, "Recordarla en este navegador"),
          h("p", { className: "hint" }, "Si no la recuerdas, se olvidará al cerrar la pestaña. No la marques en equipos compartidos."),
        ),
        message,
        submit,
      ),
    ),
  );
  keyInput.focus();

  /** Prueba la clave contra una ruta protegida y, si vale, la guarda. */
  async function submitKey(event) {
    event.preventDefault();
    submit.disabled = true;
    replaceChildren(message);
    const apiKey = keyInput.value.trim();
    try {
      await api("GET", "/settings", { apiKey });
      setApiKey(apiKey, remember.checked);
      navigate("/definiciones");
    } catch (error) {
      const text = error instanceof ApiError && error.status === 401 ? "La clave no es correcta." : error.message;
      replaceChildren(message, notice("error", text));
      submit.disabled = false;
      keyInput.select();
    }
  }
}
