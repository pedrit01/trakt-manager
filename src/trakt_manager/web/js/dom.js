/**
 * Utilidades para construir la interfaz de forma segura.
 *
 * Todo el contenido que viene de la API (títulos, notas, mensajes de Trakt) se
 * inserta como texto con `textContent`, nunca con `innerHTML`. Así un título con
 * etiquetas HTML no puede ejecutar código en la página (XSS).
 */

/**
 * Crea un elemento HTML.
 *
 * @param {string} tag Etiqueta, por ejemplo "button".
 * @param {object} [attributes] Atributos. Las claves que empiezan por "on" se
 *   registran como eventos (`onClick` → "click"); `className`, `hidden`, `disabled`
 *   y `checked` se asignan como propiedades; el resto con setAttribute.
 * @param {...(Node|string|number|null|undefined|false|Array)} children Hijos; el
 *   texto se inserta como nodo de texto y los valores vacíos se ignoran.
 * @returns {HTMLElement}
 */
export function h(tag, attributes = {}, ...children) {
  const element = document.createElement(tag);
  for (const [name, value] of Object.entries(attributes)) {
    if (value === undefined || value === null || value === false) continue;
    if (name.startsWith("on") && typeof value === "function") {
      element.addEventListener(name.slice(2).toLowerCase(), value);
    } else if (["className", "hidden", "disabled", "checked", "value"].includes(name)) {
      element[name] = value;
    } else {
      element.setAttribute(name, value === true ? "" : String(value));
    }
  }
  append(element, children);
  return element;
}

/**
 * Añade hijos a un elemento, aplanando listas e ignorando valores vacíos.
 *
 * @param {HTMLElement} parent
 * @param {Array} children
 */
function append(parent, children) {
  for (const child of children.flat(Infinity)) {
    if (child === undefined || child === null || child === false) continue;
    parent.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
}

/**
 * Sustituye todo el contenido de un elemento.
 *
 * @param {HTMLElement} element
 * @param {...*} children
 */
export function replaceChildren(element, ...children) {
  element.replaceChildren();
  append(element, children);
}

/**
 * Muestra una notificación breve en la esquina de la pantalla.
 *
 * @param {string} message Texto a mostrar.
 * @param {"info"|"error"} [kind]
 */
export function toast(message, kind = "info") {
  const container = document.getElementById("toasts");
  const item = h("div", { className: `toast ${kind === "error" ? "error" : ""}` }, message);
  container.append(item);
  setTimeout(() => item.remove(), kind === "error" ? 7000 : 4000);
}

/**
 * Pide confirmación al usuario con un diálogo modal.
 *
 * @param {object} options
 * @param {string} options.title Título del diálogo.
 * @param {Array|Node|string} [options.body] Contenido explicativo.
 * @param {string} [options.confirmLabel] Texto del botón de confirmar.
 * @param {boolean} [options.danger] Si la acción es destructiva (botón en rojo).
 * @returns {Promise<boolean>} `true` si el usuario confirma.
 */
export function confirmDialog({ title, body = [], confirmLabel = "Confirmar", danger = false }) {
  return new Promise((resolve) => {
    const dialog = h("dialog", { "aria-labelledby": "dialog-title" });
    const close = (result) => {
      dialog.close();
      dialog.remove();
      resolve(result);
    };
    replaceChildren(
      dialog,
      h("h2", { id: "dialog-title" }, title),
      h("div", { className: "stack" }, body),
      h(
        "div",
        { className: "row" },
        h("button", { type: "button", className: "button", onClick: () => close(false) }, "Cancelar"),
        h(
          "button",
          { type: "button", className: `button ${danger ? "danger" : "primary"}`, onClick: () => close(true) },
          confirmLabel,
        ),
      ),
    );
    // Escape cierra el diálogo: se trata como cancelar.
    dialog.addEventListener("cancel", (event) => {
      event.preventDefault();
      close(false);
    });
    document.body.append(dialog);
    dialog.showModal();
  });
}

/**
 * Copia un texto al portapapeles.
 *
 * La API del portapapeles solo funciona en contextos seguros (HTTPS o localhost);
 * si no está disponible (por ejemplo, entrando por la IP de la red local) se
 * recurre a seleccionar un campo temporal y `execCommand("copy")`.
 *
 * @param {string} text
 * @returns {Promise<boolean>} `true` si se pudo copiar.
 */
export async function copyToClipboard(text) {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // Se intenta el método alternativo.
  }
  const field = h("textarea", { readonly: true, className: "visually-hidden" });
  field.value = text;
  document.body.append(field);
  field.select();
  const copied = document.execCommand("copy");
  field.remove();
  return copied;
}

/**
 * Botón "Copiar" que copia un texto y avisa del resultado.
 *
 * @param {string} text Texto a copiar.
 * @param {string} [label]
 * @returns {HTMLButtonElement}
 */
export function copyButton(text, label = "Copiar") {
  return h(
    "button",
    {
      type: "button",
      className: "button small",
      onClick: async () => {
        const copied = await copyToClipboard(text);
        toast(copied ? "Copiado al portapapeles." : "No se pudo copiar: selecciónalo y cópialo a mano.", copied ? "info" : "error");
      },
    },
    label,
  );
}

/**
 * Bloque de aviso.
 *
 * @param {"info"|"ok"|"warn"|"error"} kind
 * @param {...*} children
 * @returns {HTMLElement}
 */
export function notice(kind, ...children) {
  return h("div", { className: `notice ${kind}`, role: kind === "error" ? "alert" : undefined }, children);
}

/**
 * Lista de errores de validación con su posición y campo.
 *
 * @param {Array<{entry_position: number|null, field: string, message: string}>} errors
 * @returns {HTMLElement}
 */
export function validationErrors(errors) {
  return notice(
    "error",
    h("strong", {}, errors.length === 1 ? "La definición tiene 1 error:" : `La definición tiene ${errors.length} errores:`),
    h(
      "ul",
      {},
      errors.map((issue) =>
        h("li", {}, `${issue.entry_position ? `Entrada ${issue.entry_position}` : "Lista"}, campo «${issue.field}»: ${issue.message}`),
      ),
    ),
  );
}
