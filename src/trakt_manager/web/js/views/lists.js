/**
 * Vista de las listas de Trakt (#/listas y #/listas/<id>).
 */

import { ApiError, api } from "../api.js";
import { h, notice, replaceChildren } from "../dom.js";

const PRIVACY_LABELS = { private: "privada", friends: "amigos", public: "pública" };
const KIND_LABELS = { movie: "película", show: "serie", season: "temporada", episode: "episodio" };

/**
 * Pinta la tabla de listas o, si se indica un id, el detalle de esa lista.
 *
 * @param {HTMLElement} view
 * @param {string|null} listId
 */
export async function renderLists(view, listId) {
  if (listId) {
    await renderListDetail(view, listId);
    return;
  }
  replaceChildren(view, h("h1", {}, "Mis listas"), h("p", { className: "muted" }, "Cargando…"));
  let lists;
  try {
    lists = await api("GET", "/lists");
  } catch (error) {
    replaceChildren(view, h("h1", {}, "Mis listas"), describeError(error));
    return;
  }

  const content = lists.length
    ? h(
        "div",
        { className: "card table-wrap" },
        h(
          "table",
          { className: "responsive" },
          h("thead", {}, h("tr", {}, h("th", {}, "Nombre"), h("th", {}, "Privacidad"), h("th", {}, "Elementos"))),
          h(
            "tbody",
            {},
            lists.map((list) =>
              h(
                "tr",
                {},
                h("td", { "data-label": "Nombre" }, h("a", { href: `#/listas/${list.trakt_id}` }, list.name)),
                h("td", { "data-label": "Privacidad" }, PRIVACY_LABELS[list.privacy] || list.privacy),
                h("td", { "data-label": "Elementos", className: "number" }, String(list.item_count)),
              ),
            ),
          ),
        ),
      )
    : notice("info", "No tienes listas en Trakt todavía. Crea una sincronizando una definición.");
  replaceChildren(view, h("h1", {}, "Mis listas"), content);
}

/**
 * Pinta los elementos de una lista en su orden.
 *
 * @param {HTMLElement} view
 * @param {string} listId Id numérico o slug.
 */
async function renderListDetail(view, listId) {
  const back = h("p", {}, h("a", { href: "#/listas" }, "← Mis listas"));
  replaceChildren(view, back, h("p", { className: "muted" }, "Cargando…"));
  let detail;
  try {
    detail = await api("GET", `/lists/${encodeURIComponent(listId)}`);
  } catch (error) {
    replaceChildren(view, back, describeError(error));
    return;
  }
  const { list, items } = detail;
  replaceChildren(
    view,
    back,
    h("h1", {}, list.name),
    h("p", { className: "muted" }, `${PRIVACY_LABELS[list.privacy] || list.privacy} · ${list.item_count} elementos`),
    h(
      "section",
      { className: "card" },
      items.length
        ? h(
            "ol",
            { className: "items" },
            items.map((item) =>
              h(
                "li",
                {},
                h("span", { className: "badge" }, KIND_LABELS[item.kind] || item.kind),
                " ",
                item.label,
                item.notes ? h("div", { className: "muted small-text" }, item.notes) : null,
              ),
            ),
          )
        : notice("info", "La lista está vacía."),
    ),
  );
}

/**
 * Mensaje de error, con un atajo a conectar si falta la sesión de Trakt.
 *
 * @param {unknown} error
 * @returns {HTMLElement}
 */
function describeError(error) {
  if (error instanceof ApiError && error.status === 409) {
    return notice("warn", "Para ver tus listas primero tienes que conectar con Trakt. ", h("a", { href: "#/trakt" }, "Conectar ahora"));
  }
  return notice("error", error instanceof Error ? error.message : String(error));
}
