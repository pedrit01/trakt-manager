/**
 * Vista de definiciones (#/definiciones).
 *
 * - Lista las definiciones disponibles con su origen (incluida o guardada), si son
 *   válidas y su número de entradas, con acciones para previsualizar/sincronizar,
 *   descargar y (solo las guardadas) borrar.
 * - Un editor permite pegar o subir una definición YAML/JSON, validarla sin
 *   contactar con Trakt y guardarla.
 */

import { ApiError, api, download } from "../api.js";
import { confirmDialog, h, notice, replaceChildren, toast, validationErrors } from "../dom.js";
import { navigate } from "../router.js";

const ORIGIN_LABELS = { bundled: "incluida", saved: "guardada" };

const EXAMPLE_DEFINITION = `name: "Mi maratón"
privacy: private
entries:
  - type: movie
    query: "Shang-Chi and the Legend of the Ten Rings"
    year: 2021
  - type: episodes
    query: "Loki"
    season: 2
    episodes: [1, 4, 5, 6]
`;

/**
 * Pinta la vista.
 *
 * @param {HTMLElement} view
 */
export async function renderDefinitions(view) {
  const listContainer = h("div", {}, h("p", { className: "muted" }, "Cargando definiciones…"));
  replaceChildren(
    view,
    h("div", { className: "row spread" }, h("h1", {}, "Definiciones")),
    h("p", { className: "muted" }, "Cada definición describe una lista de Trakt: sus películas, series o episodios en orden."),
    listContainer,
    buildEditor(() => loadList(listContainer)),
  );
  await loadList(listContainer);
}

/**
 * Carga y pinta la tabla de definiciones.
 *
 * @param {HTMLElement} container
 */
async function loadList(container) {
  let definitions;
  try {
    definitions = await api("GET", "/definitions");
  } catch (error) {
    replaceChildren(container, notice("error", error.message));
    return;
  }
  if (!definitions.length) {
    replaceChildren(container, notice("info", "Todavía no hay definiciones. Crea la primera más abajo."));
    return;
  }

  const rows = definitions.map((definition) =>
    h(
      "tr",
      {},
      h("td", { "data-label": "Nombre" }, h("strong", {}, definition.name), h("div", { className: "muted small-text" }, definition.list_name || definition.file)),
      h("td", { "data-label": "Origen" }, h("span", { className: "badge" }, ORIGIN_LABELS[definition.origin] || definition.origin)),
      h(
        "td",
        { "data-label": "Estado" },
        definition.valid
          ? h("span", { className: "badge ok" }, "válida")
          : h("span", { className: "badge error", title: definition.errors.map((issue) => issue.message).join("; ") }, `${definition.errors.length} errores`),
      ),
      h("td", { "data-label": "Entradas", className: "number" }, definition.valid ? `${definition.entries}${definition.extras ? ` (+${definition.extras} extras)` : ""}` : "—"),
      h("td", { className: "actions" }, rowActions(definition, () => loadList(container))),
    ),
  );

  replaceChildren(
    container,
    h(
      "div",
      { className: "card table-wrap" },
      h(
        "table",
        { className: "responsive" },
        h("thead", {}, h("tr", {}, h("th", {}, "Definición"), h("th", {}, "Origen"), h("th", {}, "Estado"), h("th", {}, "Entradas"), h("th", {}))),
        h("tbody", {}, rows),
      ),
    ),
  );
}

/**
 * Botones de acción de una fila de la tabla.
 *
 * @param {object} definition Resumen de la definición devuelto por GET /definitions.
 * @param {Function} reload Recarga la tabla tras borrar.
 * @returns {HTMLElement[]}
 */
function rowActions(definition, reload) {
  const actions = [
    h(
      "button",
      { type: "button", className: "button small primary", disabled: !definition.valid, onClick: () => navigate(`/sincronizar/${encodeURIComponent(definition.name)}`) },
      "Previsualizar / sincronizar",
    ),
    h(
      "button",
      {
        type: "button",
        className: "button small",
        onClick: () => download(`/definitions/${encodeURIComponent(definition.name)}/source`, definition.file).catch((error) => toast(error.message, "error")),
      },
      "Descargar",
    ),
  ];
  if (definition.origin === "saved") {
    actions.push(
      h(
        "button",
        {
          type: "button",
          className: "button small danger",
          onClick: async () => {
            const confirmed = await confirmDialog({
              title: `¿Borrar «${definition.name}»?`,
              body: "Se borra la definición guardada. Las listas que ya creaste en Trakt no se modifican.",
              confirmLabel: "Borrar",
              danger: true,
            });
            if (!confirmed) return;
            try {
              await api("DELETE", `/definitions/${encodeURIComponent(definition.name)}`);
              toast(`Definición «${definition.name}» borrada.`);
              reload();
            } catch (error) {
              toast(error.message, "error");
            }
          },
        },
        "Borrar",
      ),
    );
  }
  return actions;
}

/**
 * Construye el editor para crear, validar y guardar una definición.
 *
 * @param {Function} onSaved Se llama tras guardar, para refrescar la tabla.
 * @returns {HTMLElement}
 */
function buildEditor(onSaved) {
  const nameInput = h("input", { type: "text", id: "definition-name", placeholder: "mi-maraton", autocomplete: "off" });
  const formatSelect = h(
    "select",
    { id: "definition-format", className: "button small" },
    h("option", { value: "yaml" }, "YAML"),
    h("option", { value: "json" }, "JSON"),
  );
  const textArea = h("textarea", { id: "definition-text", spellcheck: "false" });
  textArea.value = EXAMPLE_DEFINITION;
  const fileInput = h("input", { type: "file", accept: ".yaml,.yml,.json", id: "definition-file" });
  const result = h("div");

  // Al subir un fichero se carga su texto en el editor y se deducen el formato y el nombre.
  fileInput.addEventListener("change", async () => {
    const file = fileInput.files[0];
    if (!file) return;
    textArea.value = await file.text();
    formatSelect.value = file.name.toLowerCase().endsWith(".json") ? "json" : "yaml";
    if (!nameInput.value) nameInput.value = suggestName(file.name);
    replaceChildren(result);
  });

  const contentType = () => (formatSelect.value === "json" ? "application/json" : "application/yaml");

  /** Valida el texto del editor sin guardar ni contactar con Trakt. */
  async function validate() {
    try {
      const outcome = await api("POST", "/validate", { body: textArea.value, contentType: contentType() });
      replaceChildren(result, notice("ok", `Definición válida: «${outcome.name}» con ${outcome.entries} entradas (${outcome.extras} extras).`));
    } catch (error) {
      replaceChildren(result, describeError(error));
    }
  }

  /** Valida y guarda la definición con el nombre indicado. */
  async function save() {
    const name = nameInput.value.trim();
    if (!name) {
      replaceChildren(result, notice("error", "Indica un nombre para la definición (minúsculas, números y guiones)."));
      nameInput.focus();
      return;
    }
    try {
      await api("PUT", `/definitions/${encodeURIComponent(name)}`, { body: textArea.value, contentType: contentType() });
      replaceChildren(result, notice("ok", `Definición «${name}» guardada.`));
      onSaved();
    } catch (error) {
      replaceChildren(result, describeError(error));
    }
  }

  return h(
    "section",
    { className: "card" },
    h("h2", {}, "Nueva definición"),
    h("p", { className: "muted small-text" }, "Pega el contenido o sube un fichero .yaml/.json. El formato está explicado en el README del proyecto."),
    h(
      "div",
      { className: "field" },
      h("label", { for: "definition-name" }, "Nombre"),
      nameInput,
      h("p", { className: "hint" }, "Solo minúsculas, números y guiones. Si coincide con una incluida, la guardada la sustituye."),
    ),
    h("div", { className: "field" }, h("label", { for: "definition-file" }, "Subir fichero"), fileInput),
    h("div", { className: "field" }, h("div", { className: "row spread" }, h("label", { for: "definition-text" }, "Contenido"), formatSelect), textArea),
    result,
    h(
      "div",
      { className: "row" },
      h("button", { type: "button", className: "button", onClick: validate }, "Validar"),
      h("button", { type: "button", className: "button primary", onClick: save }, "Guardar"),
    ),
  );
}

/**
 * Convierte un error de la API en un bloque para mostrar: los errores de
 * validación se listan con su posición y campo.
 *
 * @param {unknown} error
 * @returns {HTMLElement}
 */
function describeError(error) {
  if (error instanceof ApiError && Array.isArray(error.body?.errors) && error.body.errors.length) {
    return validationErrors(error.body.errors);
  }
  return notice("error", error instanceof Error ? error.message : String(error));
}

/**
 * Propone un nombre de definición a partir del nombre de un fichero.
 *
 * @param {string} fileName Por ejemplo "Mi Maratón.yaml".
 * @returns {string} Por ejemplo "mi-maraton".
 */
function suggestName(fileName) {
  return fileName
    .replace(/\.(ya?ml|json)$/i, "")
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "") // quita las tildes
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 64);
}
