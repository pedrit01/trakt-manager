/**
 * Vista de la sesión de Trakt (#/trakt): estado, conectar con el device flow y desconectar.
 *
 * Mientras la autorización está pendiente se consulta el estado cada 3 segundos;
 * el sondeo se para al salir de la vista (la función de limpieza que devuelve
 * renderTrakt) o cuando el estado deja de ser "pendiente".
 */

import { api } from "../api.js";
import { confirmDialog, copyButton, h, notice, replaceChildren, toast } from "../dom.js";
import { refreshTraktBadge } from "../session.js";

const POLL_INTERVAL_MS = 3000;

/**
 * Pinta la vista y devuelve la función que para el sondeo.
 *
 * @param {HTMLElement} view
 * @returns {Promise<Function>}
 */
export async function renderTrakt(view) {
  let pollTimer = null;
  const stopPolling = () => {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = null;
  };

  const panel = h("section", { className: "card" });
  replaceChildren(view, h("h1", {}, "Sesión de Trakt"), panel);

  /** Pinta el panel según el estado actual de la sesión. */
  async function showStatus() {
    let status;
    try {
      status = await api("GET", "/auth/status");
    } catch (error) {
      replaceChildren(panel, notice("error", error.message));
      return;
    }
    refreshTraktBadge();

    if (status.status === "authorized") {
      stopPolling();
      replaceChildren(
        panel,
        notice("ok", `Conectado como ${status.username}.`),
        h("button", { type: "button", className: "button danger", onClick: disconnect }, "Desconectar"),
      );
      return;
    }
    if (status.status === "pending") return; // Se sigue mostrando el código.

    stopPolling();
    const explanation = {
      none: notice("info", "Sin sesión. Conecta con Trakt para crear y consultar tus listas."),
      expired: notice("warn", "El código ha caducado sin confirmarse. Vuelve a intentarlo."),
      error: notice("error", status.error || "La autorización ha fallado."),
    }[status.status];
    replaceChildren(
      panel,
      explanation,
      h("button", { type: "button", className: "button primary", onClick: connect }, "Conectar con Trakt"),
    );
  }

  /** Inicia el device flow y muestra la URL y el código que hay que confirmar. */
  async function connect() {
    let code;
    try {
      code = await api("POST", "/auth/device");
    } catch (error) {
      toast(error.message, "error");
      return;
    }
    replaceChildren(
      panel,
      h("p", {}, "1. Abre esta página (en este o en cualquier otro dispositivo):"),
      h("p", {}, h("a", { href: code.verification_url, target: "_blank", rel: "noopener noreferrer" }, code.verification_url)),
      h("p", {}, "2. Introduce este código:"),
      h("div", { className: "row" }, h("span", { className: "big-code" }, code.user_code), copyButton(code.user_code)),
      h("p", { className: "muted" }, "Esperando confirmación… Esta página se actualizará sola."),
    );
    stopPolling();
    pollTimer = setInterval(showStatus, POLL_INTERVAL_MS);
  }

  /** Cierra la sesión de Trakt tras pedir confirmación. */
  async function disconnect() {
    const confirmed = await confirmDialog({
      title: "¿Desconectar de Trakt?",
      body: "Tendrás que volver a conectar para sincronizar listas. Tus listas en Trakt no se modifican.",
      confirmLabel: "Desconectar",
      danger: true,
    });
    if (!confirmed) return;
    try {
      await api("DELETE", "/auth");
      toast("Sesión de Trakt cerrada.");
    } catch (error) {
      toast(error.message, "error");
    }
    showStatus();
  }

  await showStatus();
  return stopPolling;
}
